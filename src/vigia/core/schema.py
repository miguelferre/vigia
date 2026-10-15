"""Modelos de datos del motor (pydantic v2) y constantes de columnas
canónicas. El motor solo trabaja con estas columnas; los loaders traducen
desde los formatos de origen (harness, CSV, Parquet).
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from enum import Enum
from itertools import pairwise
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

# --------------------------------------------------------------------------
# Columnas canónicas
# --------------------------------------------------------------------------

COL_SEQ = "seq"
COL_BATCH = "batch_seq"
COL_VERSION = "model_version"
COL_ID = "external_id"
COL_TS = "timestamp"
COL_PREDICTION = "prediction"
COL_PROB = "prob_favorable"
COL_LABEL = "label"
COL_PROTECTED = "protected_value"
COL_GROUP = "group_code"
COL_CLINICIAN = "clinician_pseudonym"
COL_SUBGROUP = "subgroup"

# En multiclase `prediction`, `label` y `prob_favorable` siguen
# siendo el 0/1 de pertenencia al conjunto favorable y la suma de sus
# probabilidades. La clase predicha, la clase real (texto normalizado) y las `k`
# probabilidades, en el orden de `TaskSpec.classes`, van en estas columnas.
COL_PREDICTION_CLASS = "prediction_class"
COL_LABEL_CLASS = "label_class"
PREFIJO_PROB = "prob__"

# En regresión el valor continuo va en estas columnas (`float`).
# `prediction` y `label` guardan el 0/1 de pertenencia al rango favorable; sin
# rango, `prediction` es 0 y `label` es 0 con etiqueta y nulo sin ella.
COL_PREDICTION_VALUE = "prediction_value"
COL_LABEL_VALUE = "label_value"


def col_prob(indice: int) -> str:
    """Nombre canónico de la probabilidad de la clase `indice` (`prob__0`...)."""
    return f"{PREFIJO_PROB}{indice}"


def es_col_prob(nombre: str) -> bool:
    return nombre.startswith(PREFIJO_PROB) and nombre[len(PREFIJO_PROB):].isdigit()


# Columnas canónicas que nunca son variables del modelo (por nombre); las
# `prob__<i>` lo son por prefijo: `es_columna_canonica` cubre las dos.
COLUMNAS_CANONICAS = frozenset(
    {
        COL_SEQ,
        COL_BATCH,
        COL_VERSION,
        COL_ID,
        COL_TS,
        COL_PREDICTION,
        COL_PROB,
        COL_LABEL,
        COL_PROTECTED,
        COL_GROUP,
        COL_CLINICIAN,
        COL_SUBGROUP,
        COL_PREDICTION_CLASS,
        COL_LABEL_CLASS,
        COL_PREDICTION_VALUE,
        COL_LABEL_VALUE,
    }
)


def es_columna_canonica(nombre: str) -> bool:
    return nombre in COLUMNAS_CANONICAS or es_col_prob(nombre)


# Las métricas por clase se guardan como `Measurement` con el mismo
# `metric_key` y `group_code = "clase:<valor>"`, sin umbral.
PREFIJO_GRUPO_CLASE = "clase:"


def grupo_clase(clase: int | str) -> str:
    return f"{PREFIJO_GRUPO_CLASE}{clave_clase(clase)}"


def es_grupo_clase(group_code: str | None) -> bool:
    return bool(group_code) and str(group_code).startswith(PREFIJO_GRUPO_CLASE)


def clave_clase(valor: Any) -> str:
    """Forma de texto de una clase para comparar e indexar:
    espacios recortados; un decimal entero (1.0, como lo lee pandas) vale lo
    mismo que el entero (1). No cambia mayúsculas: eso lo decide la ingesta."""
    if isinstance(valor, bool):
        return str(int(valor))
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


# Tipo de tarea del proyecto.: `regression` entra en el
# motor y en el alta.
TaskType = Literal["binary", "multiclass", "regression"]
MIN_CLASES_MULTICLASE = 3
MAX_CLASES = 20
# Largo máximo del nombre de una clase; el mismo que `MAX_NOMBRE_CLASE` de la API.
MAX_LARGO_CLASE = 100

# Rango favorable de 1 a 3 intervalos cerrados `[min, max]` en
# la unidad de la salida; un extremo nulo es abierto.
RangoFavorable = tuple[float | None, float | None]
MAX_RANGOS_FAVORABLES = 3
MAX_UNIDAD = 30

# Motivos compartidos. B copia los literales en la guardia;
# la interfaz los enseña tal cual.
MOTIVO_SIN_RANGO = "sin rango favorable: solo el error por grupo"
MOTIVO_CAPA_HUMANA_SIN_RANGO = "la capa humana de regresión necesita un rango favorable"
MOTIVO_SIN_PROBABILIDAD = "regresión: sin probabilidad"
MENSAJE_SIM_SOLO_BINARIO = "El modelo simulado solo existe para clasificación binaria"

# Claves de regresión. Van aparte de las de
# clasificación (`CLAVES_MOTOR == 43` no cambia).
CLAVES_CALIDAD_REGRESION = (
    "mean_absolute_error",
    "root_mean_squared_error",
    "r2",
    "mean_error",
)
CLAVES_CALIDAD_REGRESION_DETALLE = ("mean_squared_error", "median_absolute_error")
# Por grupo, como `Measurement` con `group_code` del grupo y sin umbral.
CLAVES_ERROR_POR_GRUPO = ("mean_absolute_error", "mean_error")
CLAVES_EQUIDAD_ERROR = (
    "mean_absolute_error_difference",
    "mean_absolute_error_ratio",
    "mean_error_difference",
)
CLAVES_REGRESION = (
    *CLAVES_CALIDAD_REGRESION,
    *CLAVES_CALIDAD_REGRESION_DETALLE,
    *CLAVES_EQUIDAD_ERROR,
)
# Claves de clasificación que una evaluación de regresión no publica.
CLAVES_SOLO_CLASIFICACION = (
    "accuracy",
    "area_under_roc",
    "area_under_pr",
    "log_loss",
    "confidence_drift_score",
    "model_quality_score",
)


class DatosNoValidos(ValueError):
    """Los datos no sirven para calcular.

    El mensaje va en español, dice qué pasó y qué hacer, y nunca lleva una
    traza ni un texto de una librería: la ingesta lo guarda tal cual en
    `evaluate_motivo` y la evaluación suelta en el `error` del trabajo. Hereda
    de `ValueError` para que los `except ValueError` de hoy lo sigan cogiendo.
    """


class ProtectedKind(str, Enum):
    numeric_ranges = "numeric_ranges"
    categorical = "categorical"


# Valor de la clase favorable: número, texto o,
# una lista (el conjunto de clases favorables). En binario, un valor.
FavorableLabel = int | str | list[int | str]
Clase = int | str


def _normalizar_clases(clases: list[Clase]) -> list[Clase]:
    """Recorta espacios de las clases de texto y exige que sean
    distintas y como mucho `MAX_CLASES`. Común a mapeo y plantilla."""
    limpias: list[Clase] = [c.strip() if isinstance(c, str) else c for c in clases]
    claves = [clave_clase(c) for c in limpias]
    if any(k == "" for k in claves):
        raise ValueError("classes: hay una clase vacía; quítala de la lista")
    if any(k.casefold() == "nan" for k in claves):
        # «nan» se lee como celda vacía en los ficheros.
        raise ValueError(
            "classes: «nan» no sirve como nombre de clase, porque los ficheros lo leen como "
            "una celda vacía; dale otro nombre"
        )
    if any("," in k for k in claves):
        # Una clase con coma no se puede pedir por `group_code` ni en listas separadas por comas.
        con_coma = [k for k in claves if "," in k]
        raise ValueError(
            f"classes: la clase «{con_coma[0]}» lleva una coma, que Vigía usa para separar "
            "listas de clases; quita la coma del nombre"
        )
    if any(len(k) > MAX_LARGO_CLASE for k in claves):
        # El nombre de clase se repite en cada fila por clase de cada evaluación.
        raise ValueError(
            f"classes: un nombre de clase admite como mucho {MAX_LARGO_CLASE} caracteres; "
            "acórtalo"
        )
    if len(set(claves)) != len(claves):
        repetidas = sorted({k for k in claves if claves.count(k) > 1})
        raise ValueError(
            f"classes: las clases deben ser distintas y se repiten {', '.join(repetidas)}"
        )
    if len(limpias) > MAX_CLASES:
        raise ValueError(
            f"classes: Vigía admite como mucho {MAX_CLASES} clases y hay {len(limpias)}"
        )
    return limpias


def _lista_favorable(valor: FavorableLabel | None) -> list[Clase]:
    if valor is None:
        return []
    if isinstance(valor, list):
        return list(valor)
    return [valor]


def _comprobar_coherencia_clases(
    classes: list[Clase],
    favorable: FavorableLabel | None,
    probability_cols: list[str],
    probability_col: str | None,
) -> None:
    """Reglas que no dependen del tipo de tarea."""
    if classes:
        validas = {clave_clase(c) for c in classes}
        fuera = [f for f in _lista_favorable(favorable) if clave_clase(f) not in validas]
        if fuera:
            raise ValueError(
                "favorable_label: "
                + ", ".join(str(f) for f in fuera)
                + " no está entre las clases declaradas ("
                + ", ".join(str(c) for c in classes)
                + ")"
            )
    if probability_cols:
        if probability_col is not None:
            raise ValueError(
                "probability_cols y probability_col no van juntas: usa una columna "
                "por clase o una sola columna con la lista de probabilidades"
            )
        if len(set(probability_cols)) != len(probability_cols):
            raise ValueError("probability_cols: hay columnas repetidas")
        if classes and len(probability_cols) != len(classes):
            raise ValueError(
                f"Hay {len(classes)} clases y {len(probability_cols)} columnas de "
                "probabilidad: pon una columna por clase, en el orden de las clases"
            )


def _extremo(valor: Any) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise DatosNoValidos("favorable_ranges: un extremo del rango es un número, no verdadero o falso")
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise DatosNoValidos(
            f"favorable_ranges: el extremo {valor!r} no es un número; escribe el valor sin unidad "
            "(40, no «40 h») o déjalo vacío para un extremo abierto"
        ) from None
    if not math.isfinite(numero):
        raise DatosNoValidos(
            "favorable_ranges: un extremo no puede ser NaN ni infinito; déjalo vacío para un extremo abierto"
        )
    return numero


def validar_rangos(rangos: Iterable[Any]) -> tuple[RangoFavorable, ...]:
    """De 1 a 3 intervalos `[min, max]`, cada uno con `min <= max`, sin
    solaparse y con al menos un extremo no nulo. Una lista vacía es «sin rango».
    Devuelve los intervalos ordenados por su extremo inferior. Lanza
    `DatosNoValidos` en español."""
    lista = list(rangos or [])
    if not lista:
        return ()
    if len(lista) > MAX_RANGOS_FAVORABLES:
        raise DatosNoValidos(
            f"favorable_ranges: admite de 1 a {MAX_RANGOS_FAVORABLES} intervalos y hay {len(lista)}"
        )
    salida: list[RangoFavorable] = []
    for i, intervalo in enumerate(lista, start=1):
        if isinstance(intervalo, (str, bytes)) or not hasattr(intervalo, "__len__") or len(intervalo) != 2:
            raise DatosNoValidos(
                f"favorable_ranges: el intervalo {i} debe ser una pareja [mínimo, máximo]"
            )
        bajo, alto = _extremo(intervalo[0]), _extremo(intervalo[1])
        if bajo is None and alto is None:
            raise DatosNoValidos(
                f"favorable_ranges: el intervalo {i} no tiene extremos; pon al menos el mínimo o el máximo"
            )
        if bajo is not None and alto is not None and bajo > alto:
            raise DatosNoValidos(
                f"favorable_ranges: en el intervalo {i} el mínimo ({bajo:g}) es mayor que el máximo ({alto:g})"
            )
        salida.append((bajo, alto))
    salida.sort(key=lambda r: float("-inf") if r[0] is None else r[0])
    for (_b1, a1), (b2, _a2) in pairwise(salida):
        if a1 is None or b2 is None or b2 <= a1:
            raise DatosNoValidos(
                "favorable_ranges: los intervalos no pueden solaparse ni tocarse; "
                "únelos en uno o sepáralos"
            )
    return tuple(salida)


def validar_unidad(unidad: str | None) -> str | None:
    """La unidad de la salida es texto de 1 a 30 caracteres, opcional."""
    if unidad is None:
        return None
    limpia = str(unidad).strip()
    if not limpia or len(limpia) > MAX_UNIDAD:
        raise DatosNoValidos(
            f"target_unit: la unidad tiene de 1 a {MAX_UNIDAD} caracteres (por ejemplo «días», "
            "«horas por semana» o «€»)"
        )
    return limpia


def en_rango(valor: Any, rangos: Iterable[RangoFavorable]) -> bool | None:
    """Única función que decide si un valor cae en el rango favorable.

    Extremos incluidos; un extremo nulo es abierto. Un valor nulo, NaN o no
    numérico da `None` (sin pertenencia). Sin rango (lista vacía) la pertenencia
    no se calcula: `ValueError`, porque quien llama debe despachar antes con
    `TaskSpec.sin_rango_favorable`."""
    lista = tuple(rangos)
    if not lista:
        raise ValueError(MOTIVO_SIN_RANGO)
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if math.isnan(numero):
        return None
    for bajo, alto in lista:
        if (bajo is None or numero >= bajo) and (alto is None or numero <= alto):
            return True
    return False


def pertenencia(valores: Iterable[Any], rangos: Iterable[RangoFavorable]) -> list[float | None]:
    """`en_rango` aplicado a cada valor: 1.0, 0.0 o `None`. Es la forma de las
    columnas `prediction` y `label` en regresión."""
    lista = tuple(rangos)
    salida: list[float | None] = []
    for v in valores:
        r = en_rango(v, lista)
        salida.append(None if r is None else float(r))
    return salida


def texto_rangos(rangos: Iterable[RangoFavorable], unidad: str | None = None) -> str:
    """Texto de los títulos y la interfaz: «de 40 a 81 horas por semana»."""
    sufijo = f" {unidad}" if unidad else ""
    partes = []
    for bajo, alto in rangos:
        if bajo is None:
            partes.append(f"hasta {alto:g}{sufijo}")
        elif alto is None:
            partes.append(f"desde {bajo:g}{sufijo}")
        else:
            partes.append(f"de {bajo:g} a {alto:g}{sufijo}")
    return ", ".join(partes[:-1]) + (" y " if len(partes) > 1 else "") + partes[-1] if partes else ""


def validar_grupos_protegidos(
    tipo: ProtectedKind, unpriv: list[Any], priv: list[Any]
) -> None:
    """Forma, valores finitos y disjunción de los grupos protegidos.

    `numeric_ranges`: cada grupo es una lista de intervalos `[mínimo, máximo]`,
    con extremos finitos y mínimo no mayor que el máximo (un intervalo de un solo
    valor, `[0, 0]`, vale: así se declara un atributo codificado 0/1). `categorical`:
    cada grupo es una lista de textos. Los dos grupos no comparten valores.
    Lanza `ValueError` con el nombre del campo, que la API traduce a un 422.
    """
    for nombre, grupos in (("unpriv_groups", unpriv), ("priv_groups", priv)):
        if tipo == ProtectedKind.categorical:
            if any(not isinstance(g, str) for g in grupos):
                raise ValueError(f"{nombre}: en un atributo categórico cada grupo es una lista de textos")
            continue
        for i, g in enumerate(grupos, start=1):
            if isinstance(g, str) or not isinstance(g, (list, tuple)) or len(g) != 2:
                raise ValueError(
                    f"{nombre}: el intervalo {i} necesita dos números [mínimo, máximo]"
                )
            if not all(math.isfinite(x) for x in g):
                raise ValueError(f"{nombre}: el intervalo {i} tiene un extremo que no es un número finito")
            if g[0] > g[1]:
                raise ValueError(f"{nombre}: el intervalo {i} tiene el mínimo mayor que el máximo")
    if tipo == ProtectedKind.categorical:
        comunes = sorted(set(unpriv) & set(priv))
        if comunes:
            raise ValueError(
                f"priv_groups: se solapa con unpriv_groups en {', '.join(map(str, comunes))}; "
                "un valor no puede estar en los dos grupos"
            )
        return
    for a, b in unpriv:
        for c, d in priv:
            if max(a, c) <= min(b, d):
                raise ValueError(
                    f"priv_groups: el intervalo [{c:g}, {d:g}] se solapa con el de unpriv_groups "
                    f"[{a:g}, {b:g}]; un valor no puede estar en los dos grupos"
                )


class ColumnMapping(BaseModel):
    """Mapeo de columnas del fichero al esquema canónico.

    - `prediction_col` es opcional: un dataset `feedback` solo necesita `id_col`
      y `label_col`. Que sea obligatorio en `combined` y `payload` lo
      comprueba la ingesta, que conoce el `kind` del dataset.
    - `favorable_label` omitido (`None`) se hereda de la plantilla del proyecto
      o del mapeo de la línea base; lo resuelve la ingesta antes de
      llamar al motor. El motor, si le llega `None`, usa 1, la convención de
      siempre (`favorable_resuelto`), para no mover los números.
    - `id_col` obligatorio en `combined` y `payload` salvo `acepta_feedback=false`
      en el proyecto: también lo comprueba la ingesta.
    """

    model_config = ConfigDict(extra="forbid")

    prediction_col: str | None = None
    probability_col: str | None = None
    probability_format: Literal["scalar", "list"] = "scalar"
    probability_index: int = 1
    label_col: str | None = None
    id_col: str | None = None
    timestamp_col: str | None = None
    protected_attr_col: str | None = None
    protected_kind: ProtectedKind = ProtectedKind.numeric_ranges
    unpriv_groups: list[list[float]] | list[str] = Field(default_factory=list)
    priv_groups: list[list[float]] | list[str] = Field(default_factory=list)
    feature_cols: list[str] = Field(default_factory=list)
    clinician_col: str | None = None
    subgroup_col: str | None = None
    favorable_label: FavorableLabel | None = None
    # Clases declaradas, en el orden de las probabilidades, y una
    # columna de probabilidad por clase. Vacías por defecto: un mapeo binario
    # guardado se relee igual. Las reglas por tipo están en `validar_mapeo_por_tipo`.
    classes: list[Clase] = Field(default_factory=list)
    probability_cols: list[str] = Field(default_factory=list)
    # Unidad de la salida y rango favorable de una regresión.
    # Vacíos por defecto; las reglas están en `validar_mapeo_por_tipo`, no en un
    # validador del modelo, para que un mapeo guardado se relea igual.
    target_unit: str | None = None
    favorable_ranges: list[tuple[float | None, float | None]] = Field(default_factory=list)

    @property
    def favorable_resuelto(self) -> int | str:
        """Clase favorable efectiva del motor binario: 1 si no se ha resuelto,
        el único elemento si es una lista de uno. Un conjunto de varias clases
        es multiclase y se lee con `favorables` o `TaskSpec`."""
        valor = self.favorable_label
        if valor is None:
            return 1
        if isinstance(valor, list):
            if len(valor) != 1:
                raise ValueError(
                    "favorable_label: un conjunto de varias clases favorables es de "
                    "un proyecto multiclase; léelo con TaskSpec"
                )
            return valor[0]
        return valor

    @property
    def favorables(self) -> list[Clase]:
        """Conjunto favorable como lista (vacía si no se ha fijado)."""
        return _lista_favorable(self.favorable_label)

    @model_validator(mode="after")
    def _clases_coherentes(self) -> ColumnMapping:
        if self.classes:
            self.classes = _normalizar_clases(self.classes)
        _comprobar_coherencia_clases(
            self.classes, self.favorable_label, self.probability_cols, self.probability_col
        )
        return self

    @model_validator(mode="after")
    def _grupos_no_vacios(self) -> ColumnMapping:
        if self.protected_attr_col is not None and (
            not self.unpriv_groups or not self.priv_groups
        ):
            raise ValueError(
                "protected_attr_col fijado: unpriv_groups y priv_groups no pueden estar vacíos"
            )
        validar_grupos_protegidos(self.protected_kind, self.unpriv_groups, self.priv_groups)
        return self

    @model_validator(mode="after")
    def _indice_de_probabilidad(self) -> ColumnMapping:
        """El índice de la probabilidad en lista cae entre 0 y k-1 (k son las
        clases declaradas, las columnas de probabilidad o, en binario, 2)."""
        if self.probability_index < 0:
            raise ValueError("probability_index: no puede ser negativo")
        if self.probability_format == "list":
            k = len(self.classes) or len(self.probability_cols) or 2
            if self.probability_index >= k:
                raise ValueError(
                    f"probability_index: con la probabilidad en lista va de 0 a {k - 1}, "
                    f"y se ha indicado {self.probability_index}"
                )
        return self

    @model_validator(mode="after")
    def _fecha_no_es_variable(self) -> ColumnMapping:
        """La columna de fecha no es una variable del modelo.
        Con un solo valor por fichero es una categórica de categorías
        disjuntas y manda `feature_drift_score` a ~1. Se saca de
        `feature_cols` en vez de rechazar el mapeo: los mapeos ya guardados
        (que sí la traen en las dos listas) se releen con este modelo."""
        fecha = self.timestamp_col
        if fecha is not None and fecha in self.feature_cols:
            self.feature_cols = [c for c in self.feature_cols if c != fecha]
        return self


class MappingTemplate(BaseModel):
    """Plantilla de mapeo del proyecto: lo estable entre
    datasets y versiones. Se guarda en `Project.mapping_template_json`; cada
    dataset la hereda al sugerir su mapeo (lo que falte, desde las columnas del
    fichero) y puede apartarse de ella con evento en el diario.

    `positive_label` sale del esquema; el conjunto favorable
    cubre su uso. Una plantilla guardada que aún lo trae se relee sin error:
    `_sin_positive_label` lo quita antes de validar, y la ingesta deja el aviso
    en el diario si traía valor (`positive_label_ignorado`).
    """

    model_config = ConfigDict(extra="forbid")

    favorable_label: FavorableLabel | None = None
    # Clases declaradas y columnas de probabilidad por clase.
    classes: list[Clase] = Field(default_factory=list)
    probability_cols: list[str] = Field(default_factory=list)
    # Unidad de la salida y rango favorable de una regresión.
    target_unit: str | None = None
    favorable_ranges: list[tuple[float | None, float | None]] = Field(default_factory=list)
    # Las tres columnas del modelo también son estables entre lotes;
    # sin ellas el segundo lote de un proyecto volvía a pedirlas.
    prediction_col: str | None = None
    probability_col: str | None = None
    label_col: str | None = None
    id_col: str | None = None
    # Columna de fecha del fichero, estable entre lotes y fuera
    # de `feature_cols` (no es una variable del modelo).
    timestamp_col: str | None = None
    feature_cols: list[str] = Field(default_factory=list)
    protected_attr_col: str | None = None
    protected_kind: ProtectedKind = ProtectedKind.numeric_ranges
    unpriv_groups: list[list[float]] | list[str] = Field(default_factory=list)
    priv_groups: list[list[float]] | list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _sin_positive_label(cls, datos: Any) -> Any:
        if isinstance(datos, dict) and "positive_label" in datos:
            datos = {k: v for k, v in datos.items() if k != "positive_label"}
        return datos

    @property
    def favorables(self) -> list[Clase]:
        return _lista_favorable(self.favorable_label)

    @model_validator(mode="after")
    def _coherente(self) -> MappingTemplate:
        if self.timestamp_col is not None and self.timestamp_col in self.feature_cols:
            raise ValueError(
                f"timestamp_col: la columna de fecha {self.timestamp_col!r} no puede ser "
                "también una variable del modelo; quítala de feature_cols"
            )
        if self.classes:
            self.classes = _normalizar_clases(self.classes)
        _comprobar_coherencia_clases(
            self.classes, self.favorable_label, self.probability_cols, self.probability_col
        )
        if self.protected_attr_col is not None and (
            not self.unpriv_groups or not self.priv_groups
        ):
            raise ValueError(
                "protected_attr_col fijado: unpriv_groups y priv_groups no pueden estar vacíos"
            )
        validar_grupos_protegidos(self.protected_kind, self.unpriv_groups, self.priv_groups)
        return self


# --------------------------------------------------------------------------
# Tipo de tarea
# --------------------------------------------------------------------------


class TaskSpec(BaseModel):
    """Lo que el motor sabe del tipo de tarea: inmutable, lo construyen la
    ingesta y la evaluación desde el proyecto y el mapeo, y lo pasan a `core/`.

    - `classes` va en el orden de las `k` probabilidades (`prob__0`...) y de la
      matriz de confusión. Vacío en binario: el motor se comporta como
      antes (los 31 números).
    - `favorables` es el conjunto de clases favorables. En multiclase puede ir
      vacío: sin conjunto favorable, solo calidad por grupo.
    - En `regression`, `classes` y `favorables` van vacíos, `k`
      lanza `ValueError`, `unidad` es la unidad de la salida y
      `rangos_favorables` los intervalos (vacío: sin rango).

    Fuera de este módulo y de `app/services/tarea.py`, el tipo se decide con
    `match task.task_type` y `case _: raise`, nunca con
    `es_multiclase`: un tipo nuevo no debe caer en la rama binaria.
    """

    model_config = ConfigDict(frozen=True)

    task_type: TaskType = "binary"
    classes: tuple[Clase, ...] = ()
    favorables: tuple[Clase, ...] = ()
    unidad: str | None = None
    rangos_favorables: tuple[RangoFavorable, ...] = ()

    @model_validator(mode="after")
    def _coherente_por_tipo(self) -> TaskSpec:
        match self.task_type:
            case "regression":
                if self.classes or self.favorables:
                    raise ValueError("una regresión no tiene clases ni conjunto favorable")
            case "binary" | "multiclass":
                if self.rangos_favorables or self.unidad is not None:
                    raise ValueError("la unidad y el rango favorable son solo de regresión")
            case _:
                raise ValueError(f"tipo de tarea no reconocido: {self.task_type!r}")
        return self

    @property
    def es_multiclase(self) -> bool:
        return self.task_type == "multiclass"

    @property
    def es_regresion(self) -> bool:
        return self.task_type == "regression"

    @property
    def k(self) -> int:
        if self.task_type == "regression":
            raise ValueError("una regresión no tiene clases: k no está definido")
        return len(self.classes) if self.classes else 2

    @property
    def sin_conjunto_favorable(self) -> bool:
        """Solo multiclase. En regresión es `False`: su análogo es
        `sin_rango_favorable`, y mezclarlos llevaría una regresión por el
        camino multiclase sin conjunto."""
        return self.es_multiclase and not self.favorables

    @property
    def sin_rango_favorable(self) -> bool:
        return self.es_regresion and not self.rangos_favorables

    def en_rango(self, valor: Any) -> bool | None:
        """`en_rango` del módulo con los rangos de esta tarea."""
        return en_rango(valor, self.rangos_favorables)

    @property
    def claves(self) -> tuple[str, ...]:
        return tuple(clave_clase(c) for c in self.classes)

    def indice(self, clase: Any) -> int:
        """Posición de `clase` en `classes`; `ValueError` si no está."""
        return self.claves.index(clave_clase(clase))

    def es_favorable(self, clase: Any) -> bool:
        return clave_clase(clase) in {clave_clase(f) for f in self.favorables}

    @classmethod
    def binario(cls) -> TaskSpec:
        return cls()

    @classmethod
    def desde_mapeo(
        cls,
        task_type: TaskType,
        mapping: ColumnMapping | MappingTemplate,
        classes: list[Clase] | None = None,
        *,
        unidad: str | None = None,
        rangos: Iterable[Any] | None = None,
    ) -> TaskSpec:
        """`classes`, `unidad` y `rangos` explícitos (p. ej. `project.classes_json`,
        `project.target_unit` y `project.favorable_ranges_json`) mandan sobre los
        del mapeo. Valida con `validar_mapeo_por_tipo` antes de construir."""
        clases = list(classes) if classes is not None else list(mapping.classes)
        validar_mapeo_por_tipo(mapping, task_type, clases)
        match task_type:
            case "regression":
                return cls(
                    task_type="regression",
                    unidad=validar_unidad(unidad if unidad is not None else mapping.target_unit),
                    rangos_favorables=validar_rangos(
                        rangos if rangos is not None else mapping.favorable_ranges
                    ),
                )
            case "binary" | "multiclass":
                return cls(
                    task_type=task_type,
                    classes=tuple(clases),
                    favorables=tuple(mapping.favorables),
                )
            case _:
                raise DatosNoValidos(f"tipo de tarea no reconocido: {task_type!r}")


def validar_mapeo_por_tipo(
    mapping: ColumnMapping | MappingTemplate,
    task_type: TaskType,
    classes: list[Clase] | None = None,
) -> None:
    """Reglas que dependen del tipo de tarea. `classes` explícito es la
    lista resuelta (la del proyecto si el mapeo del lote no la trae). Lanza
    `DatosNoValidos` con el mensaje en español."""
    match task_type:
        case "regression":
            _validar_mapeo_regresion(mapping, classes)
            return
        case "binary" | "multiclass":
            if mapping.favorable_ranges:
                raise DatosNoValidos(
                    "favorable_ranges es solo de regresión: en clasificación lo favorable "
                    "es una clase (favorable_label)"
                )
            if mapping.target_unit is not None:
                raise DatosNoValidos(
                    "target_unit es solo de regresión: un modelo de clasificación predice "
                    "clases, sin unidad"
                )
        case _:
            raise DatosNoValidos(f"tipo de tarea no reconocido: {task_type!r}")
    clases = list(classes) if classes is not None else list(mapping.classes)
    favorables = mapping.favorables
    if task_type == "binary":
        if clases and len(clases) != 2:
            raise DatosNoValidos(
                f"Un proyecto binario tiene 2 clases y se declaran {len(clases)}. "
                "Si el modelo predice más de dos, crea un proyecto multiclase."
            )
        if len(favorables) > 1:
            raise DatosNoValidos(
                "En un proyecto binario la clase favorable es un solo valor. "
                "Si hay varias clases favorables, crea un proyecto multiclase."
            )
        return
    if not MIN_CLASES_MULTICLASE <= len(clases) <= MAX_CLASES:
        raise DatosNoValidos(
            f"Un proyecto multiclase declara de {MIN_CLASES_MULTICLASE} a {MAX_CLASES} "
            f"clases y hay {len(clases)}. Con dos clases, crea un proyecto binario."
        )
    if favorables and len(favorables) > len(clases) - 1:
        raise DatosNoValidos(
            "El conjunto favorable no puede tener todas las clases: deja al menos una "
            "fuera, o déjalo vacío para vigilar solo la calidad por grupo."
        )
    # Una plantilla no lleva `probability_format`: el formato lo fija el mapeo
    # de cada fichero, así que la regla solo se aplica a un `ColumnMapping`.
    formato = getattr(mapping, "probability_format", None)
    if mapping.probability_col is not None and formato == "scalar":
        raise DatosNoValidos(
            "En multiclase la probabilidad va en una columna por clase "
            "(probability_cols) o en una sola columna con la lista de las "
            f"{len(clases)} probabilidades (probability_format='list')."
        )
    if mapping.probability_cols and len(mapping.probability_cols) != len(clases):
        raise DatosNoValidos(
            f"Hacen falta {len(clases)} columnas de probabilidad, una por clase y en el "
            f"orden de las clases, y hay {len(mapping.probability_cols)}."
        )


def _validar_mapeo_regresion(
    mapping: ColumnMapping | MappingTemplate, classes: list[Clase] | None
) -> None:
    """ en regresión. `prediction_col` obligatoria la exige la ingesta por el
    `kind` del dataset, como en binario (un `feedback` solo trae `id_col` y
    `label_col`); aquí van las reglas que no dependen del `kind`."""
    rechazados: list[str] = []
    if classes or mapping.classes:
        rechazados.append("classes")
    if mapping.favorable_label is not None:
        rechazados.append("favorable_label")
    if mapping.probability_col is not None:
        rechazados.append("probability_col")
    if mapping.probability_cols:
        rechazados.append("probability_cols")
    # `probability_format` tiene valor por defecto («scalar»): solo se rechaza el
    # que no es el de fábrica. Una plantilla no lo lleva.
    if getattr(mapping, "probability_format", "scalar") != "scalar":
        rechazados.append("probability_format")
    if rechazados:
        raise DatosNoValidos(
            "Un modelo de regresión predice un número, sin clases ni probabilidades: quita "
            + ", ".join(rechazados)
            + " del mapeo. Lo favorable, si lo hay, va en favorable_ranges."
        )
    validar_unidad(mapping.target_unit)
    validar_rangos(mapping.favorable_ranges)


# --------------------------------------------------------------------------
# Mapeos del harness (escenarios/shared, solo lectura)
# --------------------------------------------------------------------------

HARNESS_DIAG_COLS: list[str] = [
    "Neck_signs_symptoms",
    "Dorsal_signs_symptoms",
    "Lumbar_signs_symptoms",
    "Thoracic_signs_symptoms",
    "Flanks_armpits_signs_symptoms",
    "Jaw_signs_symptoms",
    "Shoulder_signs_symptoms",
    "Arm_signs_symptoms",
    "Elbow_signs_symptoms",
    "Wrist_signs_symptoms",
    "Hand_fingers_signs_symptoms",
    "Hip_signs_symptoms",
    "Thigh_leg_signs_symptoms",
    "Knee_signs_symptoms",
    "Ankle_signs_symptoms",
    "Foot_toes_signs_symptoms",
    "Muscle_pain",
    "Fibromyalgia",
    "Other_unspecified_muscular_signs_symptoms",
    "Unspecified_joint_signs_symptoms",
    "Locomotor_system_disability",
    "Other_locomotor_system_signs_symptoms",
    "Neck_syndromes",
    "Lumbar_thoracic_syndromes_without_irradiation",
    "Acquired_spinal_deformities",
    "Lumbar_thoracic_syndromes_with_irradiation",
    "Bursitis_tendinitis_synovitis_unspecified",
    "Rheumatoid_arthritis",
    "Ankylosing_spondylitis",
    "Hip_osteoarthritis",
    "Knee_arthrosis",
    "Other_arthrosis",
    "Shoulder_syndromes",
    "Tennis_elbow",
    "Osteochondrosis",
    "Osteoporosis",
    "Acquired_limb_deformities",
    "Other_locomotor_diseases",
    "Gout",
]

HARNESS_FEEDBACK_MAPPING = ColumnMapping(
    prediction_col="_original_prediction",
    probability_col="_original_probability",
    probability_format="list",
    probability_index=1,
    label_col="Has_Referral_in_Window",
    id_col="Episode_Id",
    timestamp_col="Episode_Start_Date",
    protected_attr_col="Age",
    unpriv_groups=[[18, 35]],
    priv_groups=[[36, 75]],
    feature_cols=["Age", "Previous_PC_episodes"] + HARNESS_DIAG_COLS,
    favorable_label=1,
)

HARNESS_PAYLOAD_MAPPING = ColumnMapping(
    prediction_col="PREDICTION",
    probability_col="PROBABILITIES",
    probability_format="list",
    probability_index=1,
    label_col=None,
    protected_attr_col="Age",
    unpriv_groups=[[18, 35]],
    priv_groups=[[36, 75]],
    feature_cols=["Age", "Previous_PC_episodes"] + HARNESS_DIAG_COLS,
    favorable_label=1,
)


# --------------------------------------------------------------------------
# Umbrales
# --------------------------------------------------------------------------


class ThresholdKind(str, Enum):
    lower_limit = "lower_limit"
    upper_limit = "upper_limit"


# Origen de un umbral: propuesto desde la línea
# base del modelo, dado por el fabricante, fijado por criterio clínico, impuesto
# por una política de la organización o el valor de fábrica de
# `core/thresholds.py` sin calibrar.
ThresholdOrigen = Literal[
    "linea_base", "fabricante", "criterio_clinico", "politica_organizacion", "fabrica"
]


class Threshold(BaseModel):
    metric_key: str
    kind: ThresholdKind
    value: float
    # Opcionales y sin migración: un umbral sin origen es uno de antes.
    origen: ThresholdOrigen | None = None
    nota: str | None = None
    # Umbral de fábrica relativo a la prevalencia de la línea
    # base: `prevalencia + value x (métrica de la línea base - prevalencia)`.
    # `value` es entonces la fracción (0,8). Sin migración: nulo es absoluto.
    relativo_a: Literal["prevalencia"] | None = None

    @model_serializer(mode="wrap")
    def _sin_origen_vacio(self, handler: Any) -> dict[str, Any]:
        # Un umbral sin origen se guarda y se sirve igual que antes.
        datos = handler(self)
        for campo in ("origen", "nota", "relativo_a"):
            if datos.get(campo) is None:
                datos.pop(campo, None)
        return datos


class MonitorThresholds(BaseModel):
    thresholds: list[Threshold] = Field(default_factory=list)

    def limits(self, metric_key: str) -> tuple[float | None, float | None]:
        """Límites absolutos de `metric_key`. Un umbral relativo no
        cuenta: su `value` es una fracción y lo resuelve el motor."""
        low: float | None = None
        high: float | None = None
        for thr in self.thresholds:
            if thr.metric_key != metric_key or thr.relativo_a is not None:
                continue
            if thr.kind == ThresholdKind.lower_limit:
                low = thr.value
            else:
                high = thr.value
        return low, high


class FairnessConfig(BaseModel):
    min_records: int = 200
    min_group: int = 20
    min_positives: int = 5
    window_step: int = 10
    interval_windows_max: int = 200
    label_min_records: int = 100


class QualityConfig(BaseModel):
    min_feedback: int = Field(default=100, ge=1)


class DriftConfig(BaseModel):
    psi_bins: int = 10
    confidence_bins: int = 20
    baseline_mode: Literal["frozen", "previous_batch"] = "frozen"


# --------------------------------------------------------------------------
# Estados
# --------------------------------------------------------------------------


class State(str, Enum):
    ok = "ok"
    aviso = "aviso"
    alerta = "alerta"
    inestable = "inestable"
    sin_datos = "sin_datos"


_ORDEN_ESTADO = {
    State.alerta: 4,
    State.inestable: 3,
    State.aviso: 2,
    State.sin_datos: 1,
    State.ok: 0,
}


def worst(states: Iterable[State]) -> State:
    peor = State.ok
    visto = False
    for s in states:
        visto = True
        if _ORDEN_ESTADO[s] > _ORDEN_ESTADO[peor]:
            peor = s
    if not visto:
        return State.sin_datos
    return peor


def estado_monitor(measurements: Iterable[Measurement]) -> State:
    """Estado agregado de un monitor.

    `sin_datos` solo si todas las métricas con umbral están en `sin_datos`; si
    alguna se evaluó, manda la peor de las evaluadas y las que faltan se
    enumeran aparte (`EvaluationResult.metricas_sin_datos`). Cuentan como
    métricas del estado las que llevan umbral o ya están en un estado de
    vigilancia (`aviso`, `inestable`, `alerta`); las auxiliares sin umbral
    (`n`, `tp`, `label_rate`...) no deciden. Sin ninguna métrica con umbral se
    aplica `worst()` a todas, como siempre. `worst()` no cambia.
    """
    medidas = list(measurements)
    relevantes = [
        m
        for m in medidas
        if m.threshold_low is not None
        or m.threshold_high is not None
        or m.state in (State.aviso, State.inestable, State.alerta)
    ]
    if not relevantes:
        return worst(m.state for m in medidas)
    evaluadas = [m.state for m in relevantes if m.state != State.sin_datos]
    if not evaluadas:
        return State.sin_datos
    return worst(evaluadas)


# --------------------------------------------------------------------------
# Medidas y ventanas
# --------------------------------------------------------------------------


class Measurement(BaseModel):
    metric_key: str
    value: float | None
    interval_low: float | None = None
    interval_high: float | None = None
    threshold_low: float | None = None
    threshold_high: float | None = None
    state: State
    group_code: str | None = None
    motivo: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class WindowInfo(BaseModel):
    kind: Literal["ultimos_n", "batch", "acumulado", "baseline_vs_batch"]
    n: int
    requested_n: int | None = None
    start_seq: int | None = None
    end_seq: int | None = None
    batches: list[int] = Field(default_factory=list)
    model_version: str | None = None
    complete: bool = True
    motivo: str | None = None
    interval_windows: int | None = None


class MonitorType(str, Enum):
    fairness = "fairness"
    quality = "quality"
    drift = "drift"
    explain = "explain"
    cross = "cross"


class EvaluationResult(BaseModel):
    monitor: MonitorType
    window: WindowInfo
    measurements: list[Measurement]
    config_snapshot: dict[str, Any]
    core_version: str
    details: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        datos = self.model_dump(mode="json")
        # `details.metricas_sin_datos` solo aparece si hay alguna.
        faltan = self.metricas_sin_datos()
        if faltan:
            datos["details"] = {**datos["details"], "metricas_sin_datos": faltan}
        return datos

    def states(self) -> dict[str, State]:
        return {m.metric_key: m.state for m in self.measurements}

    @property
    def worst_state(self) -> State:
        """Estado del monitor: ver `estado_monitor`."""
        return estado_monitor(self.measurements)

    def metricas_sin_datos(self) -> list[dict[str, Any]]:
        """Métricas con umbral en `sin_datos`, con su motivo.

        Solo las que importan al estado (con umbral) y las medidas por clase de
        multiclase; las auxiliares sin umbral no se enumeran. El motivo sale de la propia medida, y si no lo trae, de
        `details["motivo"]` o de `window.motivo`.
        """
        salida: list[dict[str, Any]] = []
        for m in self.measurements:
            if m.state != State.sin_datos:
                continue
            # Un umbral pendiente de la línea base también importa.
            pendiente = bool(m.extra.get("umbral_pendiente"))
            # Una medida de una clase rara sin datos no tiene umbral,
            # pero se enumera con su motivo para que la interfaz la diga por clase.
            por_clase = es_grupo_clase(m.group_code)
            if m.threshold_low is None and m.threshold_high is None and not pendiente and not por_clase:
                continue
            motivo = m.motivo or self.details.get("motivo") or self.window.motivo
            salida.append(
                {
                    "metric_key": m.metric_key,
                    "group_code": m.group_code,
                    "motivo": motivo or "sin valor calculable en esta ventana",
                }
            )
        return salida


# --------------------------------------------------------------------------
# Explicabilidad
# --------------------------------------------------------------------------


class FeatureImportance(BaseModel):
    feature: str
    importance: float
    rule: str | None = None


class ExplanationResult(BaseModel):
    kind: Literal["global_permutation", "global_shap", "local_lime"]
    available: bool
    motivo: str | None = None
    features: list[FeatureImportance] = Field(default_factory=list)
    row_seq: int | None = None
    prob_favorable: float | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    # Las `k` probabilidades de la fila, en el orden de
    # `TaskSpec.classes`, y la clase que explica (texto `clave_clase`).
    probabilities: list[float] | None = None
    clase_explicada: str | None = None
    # Valor predicho de la fila en una regresión, en la unidad.
    prediction_value: float | None = None

    @model_serializer(mode="wrap")
    def _sin_campos_r4_vacios(self, handler: Any) -> dict[str, Any]:
        # Una explicación binaria se guarda y se sirve igual que antes.
        datos = handler(self)
        for campo in ("probabilities", "clase_explicada", "prediction_value"):
            if datos.get(campo) is None:
                datos.pop(campo, None)
        return datos

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# --------------------------------------------------------------------------
# Diario de uso y alertas cruzadas
# --------------------------------------------------------------------------

USAGE_LOG_COLUMNS = (
    "date",
    "clinician_pseudonym",
    "subgroup",
    "human_decision",
    "model_output",
    "ground_truth",
    "record_seq",
    "model_version",
)


class CrossAlert(BaseModel):
    rule: str
    group: str | None
    value: float | None
    reference: float | None
    z: float | None
    n: int
    state: State
    motivo: str


class CrossAlertResult(BaseModel):
    mode: Literal["calibracion", "vigilancia"]
    alerts: list[CrossAlert]
    measurements: list[Measurement]
    reference: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
