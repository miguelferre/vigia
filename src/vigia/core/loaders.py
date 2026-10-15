"""Carga de datos externos (JSON del harness, CSV, Parquet) y traducción al
frame canónico. Misma semántica que `research/proto_oss.py`
(`load_feedback`, `load_payload`).
"""
from __future__ import annotations

import codecs
import csv
import io
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.io.parsers.readers import STR_NA_VALUES as _NA_PANDAS_DEFECTO

from vigia.core.fairness import assign_groups
from vigia.core.schema import (
    COL_BATCH,
    COL_CLINICIAN,
    COL_GROUP,
    COL_ID,
    COL_LABEL,
    COL_LABEL_CLASS,
    COL_LABEL_VALUE,
    COL_PREDICTION,
    COL_PREDICTION_CLASS,
    COL_PREDICTION_VALUE,
    COL_PROB,
    COL_PROTECTED,
    COL_SEQ,
    COL_SUBGROUP,
    COL_TS,
    COL_VERSION,
    HARNESS_FEEDBACK_MAPPING,
    ColumnMapping,
    DatosNoValidos,
    TaskSpec,
    clave_clase,
    col_prob,
    es_columna_canonica,
    pertenencia,
)

# ---------------------------------------------------------------------------
# Dialecto de CSV y límite de filas
# ---------------------------------------------------------------------------

MSG_FORMATO_NO_RECONOCIDO = (
    "no se reconoce el formato del fichero: se esperaba CSV (coma, punto y "
    "coma o tabulador) o JSON; si lo tienes en Excel, guárdalo como CSV"
)
MSG_FICHERO_VACIO = "el fichero está vacío: súbelo otra vez con la cabecera y al menos una fila"
MSG_CODIFICACION = (
    "no se reconoce el formato del fichero: el texto no se lee como UTF-8 "
    "(con o sin BOM) ni como Windows-1252, que son las codificaciones que "
    "prueba Vigía; guárdalo como CSV UTF-8 y súbelo otra vez"
)
MSG_FILAS_IRREGULARES = (
    "el CSV tiene una fila con un número de columnas distinto al de la "
    "cabecera: revisa el fichero"
)


def mensaje_filas_irregulares(error: Exception | None = None, linea: int | None = None) -> str:
    """`MSG_FILAS_IRREGULARES` con el número de línea, si se conoce: el que da
    pandas («line 7») o el que pasa quien llama."""
    if linea is None and error is not None:
        hallazgo = re.search(r"line (\d+)", str(error))
        linea = int(hallazgo.group(1)) if hallazgo else None
    if linea is None:
        return MSG_FILAS_IRREGULARES
    return (
        "el CSV tiene una fila con un número de columnas distinto al de la cabecera "
        f"(línea {linea} del fichero): revisa esa línea"
    )


def _primera_fila_irregular(raw: bytes, dialecto: dict[str, str]) -> int | None:
    """Línea de la primera fila con menos o más campos que la cabecera.

    Pandas rellena con vacío las filas cortas y no avisa; los lectores de texto
    (registro de uso y outcomes) no pueden aceptarlas sin más. Ignora
    las líneas en blanco. `None` si todas casan."""
    texto = raw.decode(dialecto["encoding"])
    lector = csv.reader(io.StringIO(texto, newline=""), delimiter=dialecto["separator"])
    esperado: int | None = None
    for fila in lector:
        if not fila:
            continue
        if esperado is None:
            esperado = len(fila)
            continue
        if len(fila) != esperado:
            return lector.line_num
    return None


_SEPARADORES_CSV = (",", ";", "\t")
_MUESTRA_SNIFF = 65536  # 64 KB
_TROZO_CONTEO = 1 << 20  # 1 MiB
LIMITE_FILAS_LOTE = 1_000_000

_NUM_CON_COMA = re.compile(r"^-?\d+,\d+$")
_NUM_CON_PUNTO = re.compile(r"^-?\d+\.\d+$")


def _decodificar_prefijo(prefijo: bytes) -> tuple[str, str]:
    """Decodifica un prefijo de fichero (hasta 64 KB) sin partir un carácter
    multibyte a mitad: `utf-8-sig` primero (quita el BOM si lo hay), cae a
    `cp1252` si el prefijo no es utf-8 válido. 422 (`DatosNoValidos`) si
    ninguna de las dos codifica."""
    try:
        decodificador = codecs.getincrementaldecoder("utf-8-sig")()
        return decodificador.decode(prefijo, False), "utf-8-sig"
    except UnicodeDecodeError:
        pass
    try:
        return prefijo.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        raise DatosNoValidos(MSG_CODIFICACION) from None


def _detectar_separador(muestra: str) -> str:
    """Coma, punto y coma o tabulador con `csv.Sniffer`; si ninguno aparece
    en la cabecera (una sola columna, CSV válido) cae a coma, el separador
    por defecto de pandas."""
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters="".join(_SEPARADORES_CSV))
        if dialecto.delimiter in _SEPARADORES_CSV:
            return dialecto.delimiter
    except csv.Error:
        pass
    primera_linea = muestra.splitlines()[0] if muestra else ""
    conteos = {sep: primera_linea.count(sep) for sep in _SEPARADORES_CSV}
    separador = max(conteos, key=conteos.get)
    return separador if conteos[separador] > 0 else ","


def _detectar_decimal(muestra: str, separador: str) -> str:
    """Coma decimal solo si el separador de columnas no es la coma y las
    celdas numéricas de las primeras filas la usan."""
    if separador == ",":
        return "."
    lineas = muestra.splitlines()[1:6]
    celdas = [c.strip() for linea in lineas for c in linea.split(separador)]
    n_coma = sum(1 for c in celdas if _NUM_CON_COMA.match(c))
    n_punto = sum(1 for c in celdas if _NUM_CON_PUNTO.match(c))
    return "," if n_coma > n_punto else "."


def sniff_csv_dialect(raw: bytes) -> dict[str, str]:
    """Detecta codificación, separador y decimal de un CSV a partir de sus
    primeros 64 KB. 422 (`DatosNoValidos`) si nada encaja."""
    prefijo = raw[:_MUESTRA_SNIFF]
    if not prefijo.strip():
        raise DatosNoValidos(MSG_FICHERO_VACIO)
    if b"\x00" in prefijo:
        raise DatosNoValidos(MSG_FORMATO_NO_RECONOCIDO)
    texto, codificacion = _decodificar_prefijo(prefijo)
    separador = _detectar_separador(texto)
    decimal = _detectar_decimal(texto, separador)
    return {"encoding": codificacion, "separator": separador, "decimal": decimal}


def read_csv_smart(
    raw: bytes, *, na_pandas_cols: set[str] | None = None, como_texto: bool = False
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Lee un CSV detectando su dialecto. `keep_default_na=False` con
    `na_values=[""]` en todas las columnas salvo `na_pandas_cols` (
    predicción, probabilidad y etiqueta), que conservan los nulos por
    defecto de pandas. Devuelve el dataframe y el dialecto detectado.
    `como_texto=True` (registro de uso y outcomes) lee todo como texto,
    sin nulos: la normalización de cada columna es de quien llama."""
    dialecto = sniff_csv_dialect(raw)
    prefijo, _ = _decodificar_prefijo(raw[:_MUESTRA_SNIFF])
    primera_linea = prefijo.splitlines()[0] if prefijo else ""
    try:
        columnas = next(csv.reader([primera_linea], delimiter=dialecto["separator"]))
    except StopIteration:
        columnas = []
    exentas = na_pandas_cols or set()
    na_values = {col: list(_NA_PANDAS_DEFECTO) if col in exentas else [""] for col in columnas}
    opciones: dict[str, Any] = {"na_values": na_values}
    if como_texto:
        opciones = {"dtype": str}
    try:
        df = pd.read_csv(
            io.BytesIO(raw),
            sep=dialecto["separator"],
            decimal=dialecto["decimal"],
            encoding=dialecto["encoding"],
            keep_default_na=False,
            **opciones,
        )
    except pd.errors.ParserError as exc:
        raise DatosNoValidos(mensaje_filas_irregulares(exc)) from None
    except UnicodeDecodeError:
        raise DatosNoValidos(MSG_CODIFICACION) from None
    except pd.errors.EmptyDataError:
        raise DatosNoValidos(MSG_FICHERO_VACIO) from None
    if como_texto:
        irregular = _primera_fila_irregular(raw, dialecto)
        if irregular is not None:
            raise DatosNoValidos(mensaje_filas_irregulares(linea=irregular))
    return df, dialecto


def contar_filas_csv(raw: bytes) -> int:
    """Cuenta las filas de datos (sin la cabecera) de un CSV por trozos de
    1 MiB, sin construir un DataFrame."""
    total = len(raw)
    n_saltos = 0
    for inicio in range(0, total, _TROZO_CONTEO):
        n_saltos += raw.count(b"\n", inicio, min(inicio + _TROZO_CONTEO, total))
    if raw and not raw.endswith(b"\n"):
        n_saltos += 1
    return max(n_saltos - 1, 0)


def mensaje_limite_filas(n: int) -> str:
    def _miles(x: int) -> str:
        return f"{x:,}".replace(",", " ")

    return (
        f"el fichero tiene {_miles(n)} filas; el máximo por lote es "
        f"{_miles(LIMITE_FILAS_LOTE)}: pártelo en varios lotes"
    )


# ---------------------------------------------------------------------------
# Comparación normalizada contra la clase favorable
# ---------------------------------------------------------------------------

# Dos clases fijas de alias de texto: sí/verdadero valen como una, no/falso
# como la otra. `str(valor).strip().casefold()` antes de mirar aquí.
_ALIAS_CLASE_SI = frozenset({"sí", "si", "true", "verdadero", "1"})
_ALIAS_CLASE_NO = frozenset({"no", "false", "falso", "0"})


def es_valor_nulo(valor: Any) -> bool:
    """`True` si `valor` es `None` o un nulo de pandas/numpy (incluida NaN)."""
    if valor is None:
        return True
    try:
        return bool(pd.isna(valor))
    except (TypeError, ValueError):
        return False


def _clase_alias(texto: str) -> str | None:
    if texto in _ALIAS_CLASE_SI:
        return "si"
    if texto in _ALIAS_CLASE_NO:
        return "no"
    return None


def resolver_favorable(valor_crudo: Any, favorable: int | str) -> bool | None:
    """Compara un valor crudo (predicción, etiqueta o feedback) contra la
    clase favorable ya resuelta del mapeo: número contra número si los
    dos lo son; si no, texto normalizado (`strip().casefold()`) con los alias
    fijos de sí/no y verdadero/falso como una sola clase cada uno. `None` si
    `valor_crudo` es nulo o si no hay alias que lo reconozca ni coincide con
    el texto de `favorable`: nunca cae en silencio a la clase no favorable."""
    if es_valor_nulo(valor_crudo):
        return None

    crudo_es_num = isinstance(valor_crudo, (int, float)) and not isinstance(valor_crudo, bool)
    favorable_es_num = isinstance(favorable, (int, float)) and not isinstance(favorable, bool)
    if crudo_es_num and favorable_es_num:
        return float(valor_crudo) == float(favorable)

    texto_crudo = str(valor_crudo).strip().casefold()
    texto_favorable = str(favorable).strip().casefold()
    if texto_crudo == texto_favorable:
        return True

    clase_crudo = _clase_alias(texto_crudo)
    clase_favorable = _clase_alias(texto_favorable)
    if clase_crudo is not None and clase_favorable is not None:
        return clase_crudo == clase_favorable
    return None


def contar_sin_alias_reconocido(serie: pd.Series, favorable: int | str) -> int:
    """Cuenta las filas no nulas de `serie` que `resolver_favorable` no puede
    clasificar (ni favorable ni la clase contraria): el recuento que exige
 para no perder de vista un valor sin alias."""
    return sum(
        1
        for valor in serie
        if not es_valor_nulo(valor) and resolver_favorable(valor, favorable) is None
    )


def detectar_cardinalidad_binaria(
    df: pd.DataFrame, mapping: ColumnMapping, task: TaskSpec | None = None
) -> list[str]:
    """Aviso si la predicción o la etiqueta tienen más de dos
    valores distintos en el fichero (sin contar nulos). No cambia lo que se
    guarda. Con un proyecto multiclase no hay nada que avisar (`[]`); en
    binario el texto remite al tipo multiclase.: en regresión la
    cardinalidad no es un aviso (un valor continuo tiene muchos valores)."""
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "multiclass" | "regression":
            return []
        case "binary":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    avisos = []
    for columna in (mapping.prediction_col, mapping.label_col):
        if not columna or columna not in df.columns:
            continue
        n_valores = df[columna].dropna().nunique()
        if n_valores > 2:
            avisos.append(
                "Vigía vigila hoy modelos binarios: la columna "
                f"{columna} tiene {n_valores} valores. Si el modelo predice más de dos "
                "clases, crea un proyecto multiclase; si no, elige la columna correcta "
                "en el mapeo o deja solo dos valores"
            )
    return avisos


def contar_ids_duplicados_en_lote(df: pd.DataFrame, id_col: str | None) -> int:
    """Filas del propio lote cuyo id ya apareció antes en el mismo
    fichero (recuento de las repeticiones, no de los ids distintos)."""
    if not id_col or id_col not in df.columns:
        return 0
    ids = df[id_col].dropna().astype(str)
    return int(ids.duplicated().sum())


def _columnas_requeridas_por_mapeo(mapping: ColumnMapping) -> list[str]:
    directas = [
        c
        for c in (
            mapping.prediction_col,
            mapping.probability_col,
            mapping.label_col,
            mapping.id_col,
            mapping.timestamp_col,
            mapping.protected_attr_col,
            mapping.clinician_col,
            mapping.subgroup_col,
        )
        if c is not None
    ]
    return directas + list(mapping.probability_cols) + list(mapping.feature_cols)


def comprobar_columnas_mapeo(df: pd.DataFrame, mapping: ColumnMapping) -> None:
    """Comprueba que las columnas que el mapeo necesita (las 8 directas más
    `feature_cols`) siguen en `df`: la reutilizan `load_tabular` y
    `to_canonical` para no duplicar la validación (arregla que
    reventaba con un `KeyError` crudo en `feature_cols`)."""
    faltan = [c for c in _columnas_requeridas_por_mapeo(mapping) if c not in df.columns]
    if not faltan:
        return
    raise DatosNoValidos(
        f"el fichero ya no tiene la columna '{faltan[0]}' que el mapeo necesita: "
        "revisa el mapeo o vuelve a subir el fichero"
    )


def load_payload(path: str | Path) -> pd.DataFrame:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if "input_data" not in d or "output_data" not in d:
        raise ValueError(
            f"{path}: se esperaba un payload con 'input_data' y 'output_data'"
        )
    inp = d["input_data"][0]
    df = pd.DataFrame(inp["values"], columns=inp["fields"])
    out = d["output_data"][0]
    df["PREDICTION"] = [v[0] for v in out["values"]]
    df["PROBABILITIES"] = [v[1] for v in out["values"]]
    return df


def load_feedback(path: str | Path) -> pd.DataFrame:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if "fields" not in d or "values" not in d:
        raise ValueError(f"{path}: se esperaba un feedback con 'fields' y 'values'")
    return pd.DataFrame(d["values"], columns=d["fields"])


def _cargar_json_tabular(path: Path) -> pd.DataFrame:
    d = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(d, list):
        return pd.DataFrame(d)
    if isinstance(d, dict) and "fields" in d and "values" in d:
        return pd.DataFrame(d["values"], columns=d["fields"])
    if isinstance(d, dict) and "input_data" in d and "output_data" in d:
        return load_payload(path)
    raise ValueError(
        f"{path}: JSON no reconocido (se esperaba lista de objetos, "
        "{'fields','values'} o formato payload)"
    )


def load_tabular(path: str | Path, mapping: ColumnMapping | None = None) -> pd.DataFrame:
    ruta = Path(path)
    sufijo = ruta.suffix.lower()
    if sufijo == ".csv":
        cols_na_pandas: set[str] = set()
        if mapping is not None:
            cols_na_pandas = {
                c for c in (mapping.prediction_col, mapping.probability_col, mapping.label_col) if c
            }
        df, _dialecto = read_csv_smart(ruta.read_bytes(), na_pandas_cols=cols_na_pandas)
    elif sufijo == ".parquet":
        try:
            df = pd.read_parquet(ruta)
        except ImportError as exc:
            raise ValueError(
                "Parquet no disponible en este equipo (pyarrow bloqueado o ausente): "
                f"{exc}"
            ) from None
    elif sufijo == ".json":
        df = _cargar_json_tabular(ruta)
    else:
        raise ValueError(f"{path}: extensión no soportada ({sufijo!r})")

    if mapping is not None:
        comprobar_columnas_mapeo(df, mapping)

    return df


def _lista_probabilidades(valor: Any) -> list[float] | None:
    """Lista de probabilidades de una celda (lista, array o texto JSON)."""
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            return None
    if isinstance(valor, (list, tuple, np.ndarray)):
        try:
            return [float(x) for x in valor]
        except (TypeError, ValueError):
            return None
    return None


def _matriz_probabilidades(
    df: pd.DataFrame, mapping: ColumnMapping, task: TaskSpec
) -> np.ndarray | None:
    """La matriz `(n, k)` de probabilidades en el orden de
    `task.classes`, desde `probability_cols` (una columna por clase) o desde
    una sola columna con la lista de `k` valores. `None` si el mapeo no trae
    probabilidad. Longitud distinta de `k` o `NaN`: `DatosNoValidos`."""
    k = task.k
    if mapping.probability_cols:
        columnas = mapping.probability_cols
        if len(columnas) != k:
            raise DatosNoValidos(
                f"Hacen falta {k} columnas de probabilidad, una por clase y en el orden "
                f"de las clases, y el mapeo tiene {len(columnas)}: revisa las columnas de "
                "probabilidad del mapeo."
            )
        try:
            matriz = df[columnas].apply(pd.to_numeric, errors="raise").to_numpy(dtype=float)
        except (TypeError, ValueError):
            raise DatosNoValidos(
                "las columnas de probabilidad deben contener números: revisa "
                f"{', '.join(columnas)} en el mapeo o en el fichero"
            ) from None
        nombre = "las columnas de probabilidad"
    elif mapping.probability_col:
        if mapping.probability_format != "list":
            raise DatosNoValidos(
                "En multiclase la probabilidad va en una columna por clase "
                "(probability_cols) o en una sola columna con la lista de las "
                f"{k} probabilidades (probability_format='list')."
            )
        filas: list[list[float]] = []
        for valor in df[mapping.probability_col]:
            lista = _lista_probabilidades(valor)
            if lista is None or len(lista) != k:
                tiene = "ningún valor" if lista is None else f"{len(lista)} valores"
                raise DatosNoValidos(
                    f"la columna de probabilidad '{mapping.probability_col}' debe traer "
                    f"{k} probabilidades por fila, una por clase y en el orden de las "
                    f"clases, y hay una fila con {tiene}: revisa el mapeo o el fichero"
                )
            filas.append(lista)
        matriz = np.array(filas, dtype=float).reshape(len(filas), k)
        nombre = f"la columna de probabilidad '{mapping.probability_col}'"
    else:
        return None
    n_nulas = int(np.isnan(matriz).any(axis=1).sum())
    if n_nulas:
        raise DatosNoValidos(
            f"Hay {n_nulas} de {len(matriz)} filas con alguna probabilidad vacía en "
            f"{nombre}. En multiclase hacen falta las {k} probabilidades de cada fila: "
            "rellena los huecos o quita esas filas del fichero y vuelve a subirlo."
        )
    return matriz


def _clase_de_etiqueta(
    valor: Any, claves: frozenset[str], por_minuscula: dict[str, list[str]]
) -> tuple[str | None, str | None, bool]:
    """`(clase, texto, por_mayusculas)` de una etiqueta. Recorta
    espacios; coincide exacta, o sin distinguir mayúsculas con una sola clase
    declarada (`por_mayusculas`); si no, `clase` es `None` y `texto` guarda lo
    recortado (clase desconocida). Un valor vacío es `(None, None, False)`."""
    if es_valor_nulo(valor):
        return None, None, False
    texto = clave_clase(valor)
    if texto == "":
        return None, None, False
    if texto in claves:
        return texto, texto, False
    candidatas = por_minuscula.get(texto.casefold(), [])
    if len(candidatas) == 1:
        return candidatas[0], texto, True
    return None, texto, False


def _indices_minuscula(task: TaskSpec) -> dict[str, list[str]]:
    por_minuscula: dict[str, list[str]] = {}
    for clave in task.claves:
        por_minuscula.setdefault(clave.casefold(), []).append(clave)
    return por_minuscula


def _columnas_multiclase(
    canon: pd.DataFrame, df: pd.DataFrame, mapping: ColumnMapping, task: TaskSpec
) -> None:
    """Rellena `prediction`, `prob_favorable`, `label`
    (0/1 de pertenencia al conjunto favorable y suma de sus probabilidades,
    y las columnas nuevas `prediction_class`, `label_class` y `prob__i`."""
    n = len(df)
    claves = frozenset(task.claves)
    favorables = {clave_clase(f) for f in task.favorables}
    columna = mapping.prediction_col

    predichas: list[str] = []
    n_vacias = 0
    for valor in df[columna]:
        if es_valor_nulo(valor) or clave_clase(valor) == "":
            n_vacias += 1
            predichas.append("")
            continue
        clase = clave_clase(valor)
        if clase not in claves:
            raise DatosNoValidos(
                f"El modelo predice la clase {clase}, que no está entre las clases del "
                f"proyecto ({', '.join(task.claves)}). Si es una versión nueva del "
                "modelo, créala."
            )
        predichas.append(clase)
    if n_vacias:
        raise DatosNoValidos(
            f"la columna de predicción '{columna}' tiene {n_vacias} de {n} valores "
            "vacíos: revisa el mapeo o el fichero"
        )
    canon[COL_PREDICTION] = [1 if c in favorables else 0 for c in predichas]

    matriz = _matriz_probabilidades(df, mapping, task)
    indices_fav = [task.indice(f) for f in task.favorables]
    if matriz is not None and indices_fav:
        canon[COL_PROB] = matriz[:, indices_fav].sum(axis=1)
    else:
        canon[COL_PROB] = float("nan")

    if mapping.label_col:
        por_minuscula = _indices_minuscula(task)
        etiquetas = [
            _clase_de_etiqueta(v, claves, por_minuscula) for v in df[mapping.label_col]
        ]
        canon[COL_LABEL] = [
            (float(clase in favorables) if clase is not None else float("nan"))
            for clase, _texto, _mayus in etiquetas
        ]
        label_class = [clase if clase is not None else texto for clase, texto, _m in etiquetas]
    else:
        canon[COL_LABEL] = float("nan")
        label_class = [None] * n
    canon[COL_PREDICTION_CLASS] = predichas
    canon[COL_LABEL_CLASS] = pd.Series(label_class, index=canon.index, dtype=object)
    for i in range(task.k):
        canon[col_prob(i)] = matriz[:, i] if matriz is not None else float("nan")


def _numeros_de_columna(serie: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Lee una columna como números sin `resolver_favorable`. Devuelve
    `(valores, vacias, texto, infinitas)`: `valores` en `float` (NaN donde la celda
    no es un número finito) y tres máscaras que dicen por qué no lo es: celda
    vacía, texto que no es un número e infinito."""
    vacias = np.array([es_valor_nulo(v) for v in serie], dtype=bool)
    numeros = pd.to_numeric(serie, errors="coerce").to_numpy(dtype=float)
    # Un booleano no es un valor medido: `to_numeric` lo dejaría pasar como 1 o 0.
    es_booleano = np.array([isinstance(v, (bool, np.bool_)) for v in serie], dtype=bool)
    numeros = np.where(es_booleano, np.nan, numeros)
    texto = ~vacias & np.isnan(numeros)
    infinitas = np.isinf(numeros)
    valores = np.where(np.isfinite(numeros), numeros, np.nan)
    return valores, vacias, texto, infinitas


_RE_COMA_DECIMAL = re.compile(r"^\s*[-+]?\d+,\d+\s*$")
_RE_UNIDAD_PEGADA = re.compile(r"^\s*[-+]?\d+(?:[.,]\d+)?\s*[^\d\s.,].*$")
_MAX_CLASES_DE_TEXTO = 20


def _causa_del_texto(celdas: list[Any], n_total: int) -> str:
    """Por qué una columna de regresión trae texto. `coma` (decimal con
    coma), `unidad` (unidad pegada al valor), `clases` (pocos textos distintos que
    son la mayoría de la columna: parece un modelo de clasificación) u `otro`."""
    textos = [str(c).strip() for c in celdas]
    n_coma = sum(bool(_RE_COMA_DECIMAL.match(t)) for t in textos)
    n_unidad = sum(bool(_RE_UNIDAD_PEGADA.match(t)) for t in textos)
    if n_coma and n_coma >= n_unidad:
        return "coma"
    if n_unidad:
        return "unidad"
    distintos = sorted(set(textos))
    if 2 <= len(distintos) <= _MAX_CLASES_DE_TEXTO and len(textos) * 2 >= n_total:
        return "clases"
    return "otro"


def _consejo_del_texto(celdas: list[Any], n_total: int) -> str:
    causa = _causa_del_texto(celdas, n_total)
    if causa == "coma":
        return "usa el punto como separador decimal («44,3» pasa a 44.3)"
    if causa == "unidad":
        return "quita la unidad pegada al valor («12 h» pasa a 12)"
    if causa == "clases":
        ejemplos = ", ".join(f"«{t}»" for t in sorted({str(c).strip() for c in celdas})[:3])
        return (
            f"los valores parecen clases ({ejemplos}): si el modelo es de clasificación, "
            "crea un proyecto de clasificación"
        )
    return "quita el texto de esas celdas"


def _detalle_celdas_no_validas(vacias: np.ndarray, texto: np.ndarray, infinitas: np.ndarray) -> str:
    partes = []
    if vacias.any():
        partes.append(f"{int(vacias.sum())} vacías")
    if texto.any():
        partes.append(f"{int(texto.sum())} de texto")
    if infinitas.any():
        partes.append(f"{int(infinitas.sum())} infinitas")
    return ", ".join(partes)


def _columnas_regresion(
    canon: pd.DataFrame, df: pd.DataFrame, mapping: ColumnMapping, task: TaskSpec
) -> None:
    """Rellena `prediction_value` y `label_value` (el valor
    continuo, en `float`) y `prediction` y `label` (el 0/1 de pertenencia al
    rango favorable con `pertenencia`, que es la única que lo decide).
    Sin rango, `prediction` es 0 y `label` es 0 con etiqueta y nulo sin ella. No
    pasa por `resolver_favorable` (aplanaría 37,2 a 0) y no crea `prob_favorable`
    ni `prob__<i>`: una regresión no tiene probabilidad.

    Una predicción vacía, de texto o infinita detiene la ingesta
    (`DatosNoValidos` con el recuento y la primera fila); una etiqueta vacía es
    «sin etiqueta» y una de texto o infinita queda sin etiqueta (el aviso lo da
    `avisos_regresion`)."""
    n = len(df)
    columna = mapping.prediction_col
    valores, vacias, texto, infinitas = _numeros_de_columna(df[columna])
    malas = vacias | texto | infinitas
    if malas.any():
        primera = int(np.argmax(malas))
        celda = df[columna].iloc[primera]
        cual = "vacía" if es_valor_nulo(celda) else f"«{celda}»"
        consejos = []
        if texto.any():
            consejos.append(_consejo_del_texto(list(df[columna][texto]), n))
        if infinitas.any():
            consejos.append("corrige los valores infinitos")
        if vacias.any():
            consejos.append("rellena los huecos o quita esas filas")
        raise DatosNoValidos(
            f"la columna de predicción '{columna}' tiene {int(malas.sum())} de {n} valores que "
            f"no son un número ({_detalle_celdas_no_validas(vacias, texto, infinitas)}); la "
            f"primera está en la fila {primera + 1} de los datos ({cual}). Un modelo de "
            f"regresión predice un número: {'; '.join(consejos)} y vuelve a subir el fichero"
        )
    canon[COL_PREDICTION_VALUE] = valores.astype(float)

    if mapping.label_col:
        etiquetas, _v, _t, _i = _numeros_de_columna(df[mapping.label_col])
    else:
        etiquetas = np.full(n, np.nan)
    canon[COL_LABEL_VALUE] = etiquetas

    if task.rangos_favorables:
        pred_pert = pertenencia(valores, task.rangos_favorables)
        canon[COL_PREDICTION] = np.array([int(p) for p in pred_pert], dtype=int)  # type: ignore[arg-type]
        canon[COL_LABEL] = np.array(
            [np.nan if p is None else p for p in pertenencia(etiquetas, task.rangos_favorables)],
            dtype=float,
        )
    else:
        canon[COL_PREDICTION] = np.zeros(n, dtype=int)
        canon[COL_LABEL] = np.where(np.isnan(etiquetas), np.nan, 0.0)


def avisos_regresion(
    df: pd.DataFrame, mapping: ColumnMapping, task: TaskSpec | None
) -> list[str]:
    """Avisos de la ingesta de regresión, en español y
    con qué hacer. No detienen nada: etiquetas de texto o infinitas que quedan sin
    etiqueta, predicción constante y una predicción con menos de 3 valores
    distintos (¿es un modelo de clasificación?). Vacío fuera de regresión."""
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "binary" | "multiclass":
            return []
        case "regression":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    avisos: list[str] = []
    columna = mapping.label_col
    if columna and columna in df.columns:
        _val, _vac, texto, infinitas = _numeros_de_columna(df[columna])
        n_malas = int(texto.sum() + infinitas.sum())
        if n_malas:
            consejos = []
            if texto.any():
                consejos.append(_consejo_del_texto(list(df[columna][texto]), len(df)))
            if infinitas.any():
                consejos.append("corrige los valores infinitos")
            todas = " Ninguna fila conserva etiqueta." if n_malas == int((~_vac).sum()) else ""
            avisos.append(
                f"{n_malas} filas de la columna {columna} no traen un número (texto o infinito) y "
                f"quedan sin etiqueta, fuera de la calidad.{todas} Para recuperarlas: "
                f"{'; '.join(consejos)}, y vuelve a subir el fichero"
            )
    columna = mapping.prediction_col
    if columna and columna in df.columns:
        valores, vacias, texto, infinitas = _numeros_de_columna(df[columna])
        buenas = valores[~(vacias | texto | infinitas)]
        distintos = len(np.unique(buenas)) if len(buenas) else 0
        if distintos == 1 and len(buenas) > 1:
            avisos.append(
                f"La columna {columna} tiene el mismo valor en todas las filas: ¿es la columna "
                "de predicción? Con una predicción constante la deriva y el R² no dicen nada. "
                "Revisa en el paso Mapeo qué columna es la predicción y vuelve a subir el fichero"
            )
        elif 1 < distintos < 3:
            avisos.append(
                f"La columna {columna} tiene solo {distintos} valores distintos: ¿es un modelo de "
                "clasificación? Si lo es, crea un proyecto de clasificación"
            )
    return avisos


def avisos_clases(
    df: pd.DataFrame, mapping: ColumnMapping, task: TaskSpec, *, es_linea_base: bool
) -> list[str]:
    """Avisos de la ingesta multiclase, en español: etiquetas
    asignadas a su clase sin distinguir mayúsculas, etiquetas de una clase
    desconocida (con su recuento) y, en la línea base, clases declaradas sin
    filas. Vacío en binario."""
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "binary" | "regression":
            return []  # los avisos de regresión: `avisos_regresion`
        case "multiclass":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    avisos: list[str] = []
    claves = frozenset(task.claves)
    por_minuscula = _indices_minuscula(task)
    presentes: set[str] = set()

    columna_prediccion = mapping.prediction_col
    if columna_prediccion and columna_prediccion in df.columns:
        presentes.update(clave_clase(v) for v in df[columna_prediccion].dropna())

    columna = mapping.label_col
    if columna and columna in df.columns:
        asignadas: dict[tuple[str, str], int] = {}
        desconocidas: dict[str, int] = {}
        for valor in df[columna]:
            clase, texto, por_mayusculas = _clase_de_etiqueta(valor, claves, por_minuscula)
            if clase is not None:
                presentes.add(clase)
                if por_mayusculas and texto is not None:
                    asignadas[(texto, clase)] = asignadas.get((texto, clase), 0) + 1
            elif texto is not None:
                desconocidas[texto] = desconocidas.get(texto, 0) + 1
        if asignadas:
            ejemplos = ", ".join(f"«{o}» a {c}" for (o, c) in list(asignadas)[:3])
            avisos.append(
                f"{sum(asignadas.values())} etiquetas de la columna {columna} se han "
                f"asignado a su clase sin distinguir mayúsculas ({ejemplos})."
            )
        if desconocidas:
            nombres = ", ".join(sorted(desconocidas)[:5])
            avisos.append(
                f"{sum(desconocidas.values())} filas de la columna {columna} traen una "
                f"clase que no está entre las clases del proyecto ({', '.join(task.claves)}): "
                f"{nombres}. Se ingieren, pero esas filas quedan fuera de la calidad. "
                "Si es un error de la etiqueta, corrígela en el fichero y vuelve a subirlo; "
                "si la clase es nueva de verdad, crea un modelo o una versión con esa clase."
            )
    if es_linea_base:
        for clase in task.claves:
            if clase not in presentes:
                avisos.append(
                    f"La clase {clase} no tiene filas en la línea base (soporte 0): se "
                    "conserva porque Vigía necesita una columna de probabilidad por cada "
                    "clase declarada. Las clases de un modelo no cambian después de subir la "
                    "línea base: si la clase no existe en tus datos, crea el modelo de nuevo "
                    "sin ella; si existe, crea el modelo de nuevo con una línea base que "
                    "tenga casos de esa clase."
                )
    return avisos


def to_canonical(
    df: pd.DataFrame,
    mapping: ColumnMapping,
    *,
    batch_seq: int = 0,
    model_version: str = "v1",
    seq_start: int = 0,
    task: TaskSpec | None = None,
) -> pd.DataFrame:
    """Traduce `df` al frame canónico. Con `task` multiclase añade
    `prediction_class`, `label_class` y `prob__0..k-1`; `prediction`, `label` y
    `prob_favorable` siguen siendo el 0/1 de pertenencia al conjunto favorable
    y la suma de sus probabilidades. Con `task=None` o binario, todo
    queda como antes."""
    tipo = task.task_type if task is not None else "binary"
    comprobar_columnas_mapeo(df, mapping)  # Mismo mensaje en español que load_tabular
    n = len(df)
    canon = pd.DataFrame(index=range(n))
    canon[COL_SEQ] = range(seq_start, seq_start + n)
    canon[COL_BATCH] = batch_seq
    canon[COL_VERSION] = model_version
    canon[COL_ID] = df[mapping.id_col].to_numpy() if mapping.id_col else None
    canon[COL_TS] = df[mapping.timestamp_col].to_numpy() if mapping.timestamp_col else None

    if mapping.prediction_col is None:
        raise DatosNoValidos(
            "el mapeo no tiene columna de predicción: los lotes y la línea base la necesitan"
        )
    match tipo:
        case "multiclass":
            _columnas_multiclase(canon, df, mapping, task)  # type: ignore[arg-type]
            _columnas_comunes(canon, df, mapping)
            return canon
        case "regression":
            _columnas_regresion(canon, df, mapping, task)  # type: ignore[arg-type]
            _columnas_comunes(canon, df, mapping)
            return canon
        case "binary":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    favorable = mapping.favorable_resuelto
    # Comparación normalizada (número contra número, o texto con alias
    # fijos de sí/no y verdadero/falso). La predicción es de guardado
    # obligatorio (no admite nulo): un valor vacío o sin alias reconocido
    # para el mismo, aquí, detiene la ingesta con un mensaje claro en vez de
    # aplanarlo en silencio a la clase no favorable.
    pred_resueltos = [resolver_favorable(v, favorable) for v in df[mapping.prediction_col]]
    n_pred_sin_clase = sum(1 for r in pred_resueltos if r is None)
    if n_pred_sin_clase:
        raise DatosNoValidos(
            f"la columna de predicción '{mapping.prediction_col}' tiene {n_pred_sin_clase} de {n} "
            "valores vacíos o que no coinciden con la clase favorable ni sus alias "
            "(sí/si/true/verdadero/1, no/false/falso/0): revisa el mapeo o el fichero"
        )
    canon[COL_PREDICTION] = [int(r) for r in pred_resueltos]

    if mapping.probability_col:
        prob_raw = df[mapping.probability_col]
        if mapping.probability_format == "list":
            canon[COL_PROB] = [float(v[mapping.probability_index]) for v in prob_raw]
        else:
            canon[COL_PROB] = prob_raw.astype(float).to_numpy()
    else:
        canon[COL_PROB] = float("nan")

    if mapping.label_col:
        label_resueltos = [resolver_favorable(v, favorable) for v in df[mapping.label_col]]
        # Un valor sin alias reconocido pasa a nulo, igual que uno
        # que ya venía vacío: la etiqueta, a diferencia de la predicción, sí
        # admite nulo (fila sin supervisar).
        canon[COL_LABEL] = [float(r) if r is not None else float("nan") for r in label_resueltos]
    else:
        canon[COL_LABEL] = float("nan")

    _columnas_comunes(canon, df, mapping)
    return canon


def _columnas_comunes(canon: pd.DataFrame, df: pd.DataFrame, mapping: ColumnMapping) -> None:
    """Grupo protegido, profesional, subgrupo y variables: igual en binario y en
    multiclase (las columnas de probabilidad por clase no son variables)."""
    if mapping.protected_attr_col:
        canon[COL_PROTECTED] = df[mapping.protected_attr_col].to_numpy()
        canon[COL_GROUP] = assign_groups(df, mapping).to_numpy()
    else:
        canon[COL_PROTECTED] = None
        canon[COL_GROUP] = -1

    canon[COL_CLINICIAN] = df[mapping.clinician_col].to_numpy() if mapping.clinician_col else None
    canon[COL_SUBGROUP] = df[mapping.subgroup_col].to_numpy() if mapping.subgroup_col else None

    # Una variable con nombre canónico sustituiría en silencio la columna
    # canónica ya calculada (`seq`, `label`, `group_code`...). Declarada a mano, se
    # rechaza; sin declarar, se deja fuera de las variables.
    if mapping.feature_cols:
        cols_features = mapping.feature_cols
        canonicas = [c for c in cols_features if es_columna_canonica(c)]
        if canonicas:
            listado = ", ".join(f"«{c}»" for c in canonicas)
            raise DatosNoValidos(
                f"las variables del mapeo incluyen columnas con nombre reservado: {listado}; "
                "renómbralas en el fichero o quítalas de las variables"
            )
    else:
        mapeadas = {
            c
            for c in (
                mapping.prediction_col,
                mapping.probability_col,
                mapping.label_col,
                mapping.id_col,
                mapping.timestamp_col,
                mapping.protected_attr_col,
                mapping.clinician_col,
                mapping.subgroup_col,
                *mapping.probability_cols,
            )
            if c is not None
        }
        cols_features = [c for c in df.columns if c not in mapeadas and not es_columna_canonica(c)]
    for col in cols_features:
        canon[col] = df[col].to_numpy()


def load_harness_pair(
    payload_path: str | Path, feedback_path: str | Path, **kw
) -> pd.DataFrame:
    payload = load_payload(payload_path)
    feedback = load_feedback(feedback_path)
    pred_feedback = feedback["_original_prediction"].astype(int).to_numpy()
    pred_payload = payload["PREDICTION"].to_numpy()
    if len(pred_feedback) != len(pred_payload) or not (pred_feedback == pred_payload).all():
        raise ValueError("orden distinto")
    return to_canonical(feedback, HARNESS_FEEDBACK_MAPPING, **kw)


def concat_history(frames: list[pd.DataFrame]) -> pd.DataFrame:
    partes = []
    seq = 0
    for frame in frames:
        f = frame.copy()
        n = len(f)
        f[COL_SEQ] = range(seq, seq + n)
        seq += n
        partes.append(f)
    return pd.concat(partes, ignore_index=True)
