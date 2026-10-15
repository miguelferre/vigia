"""Registro de subidas, mapeo e ingesta a lotes y registros.

`register_upload` detecta el formato y sugiere un mapeo; sin pseudonimización,
el informe de privacidad es la constante de `privacy.empty_report` y
nada se enmascara. `set_mapping` fija el mapeo definitivo (`privacy_decisions`
se acepta y se ignora). `ingest_dataset` traduce al frame canónico con
`vigia.core.loaders.to_canonical` e inserta `batch`/`record` en bloques de 1000,
cancelable entre bloques sin dejar un lote a medias. `delete_batch` y
`delete_dataset` completan el ciclo de vida.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import func
from sqlalchemy import update as sa_update
from sqlmodel import Session, select

from vigia.app.bus import EventBus
from vigia.app.errores import no_encontrado, texto_error_trabajo
from vigia.app.events import ACTOR_MODELO, ACTOR_SISTEMA, Actor, record_event
from vigia.app.jobs import JobCancelled, JobContext
from vigia.app.models import (
    Batch,
    Dataset,
    Evaluation,
    Explanation,
    ModelVersion,
    Project,
    Record,
    UsageLog,
)
from vigia.app.services import alerting, privacy
from vigia.app.services import projects as projects_service
from vigia.app.services import tarea as tarea_service
from vigia.app.services.composition import (
    batch_composition,
    group_labeller,
)
from vigia.app.services.fechas import aviso_fechas_ilegibles
from vigia.core import loaders as _loaders_core
from vigia.core.loaders import (
    _ALIAS_CLASE_NO,
    _ALIAS_CLASE_SI,
    LIMITE_FILAS_LOTE,
    contar_filas_csv,
    contar_ids_duplicados_en_lote,
    contar_sin_alias_reconocido,
    detectar_cardinalidad_binaria,
    es_valor_nulo,
    load_feedback,
    load_payload,
    mensaje_limite_filas,
    read_csv_smart,
    resolver_favorable,
    to_canonical,
)
from vigia.core.schema import (
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
    HARNESS_FEEDBACK_MAPPING,
    HARNESS_PAYLOAD_MAPPING,
    ColumnMapping,
    DatosNoValidos,
    MappingTemplate,
    ProtectedKind,
    TaskSpec,
    clave_clase,
    col_prob,
    en_rango,
    es_columna_canonica,
    validar_rangos,
    validar_unidad,
)

__all__ = [
    "MOTIVO_REINGESTA_BLOQUEADA",
    "IngestResult",
    "batch_composition",
    "delete_batch",
    "delete_dataset",
    "ensure_ingestible",
    "group_labeller",
    "ingest_dataset",
    "record_to_dict",
    "register_upload",
    "set_mapping",
]

_BLOQUE = 1000
# más de 20 valores numéricos distintos en una columna que se lee como clase son
# los de un modelo de regresión.
MIN_VALORES_CONTINUOS = 20

_KINDS_VALIDOS = ("combined", "payload", "feedback", "usage_log", "outcome")
_ROLES_VALIDOS = ("baseline", "production")

# Estados de `dataset.status`: subido, mapeado, ingerido y `error` (la ingesta
# falló y su fichero en bruto se borró, `_fallo_de_ingesta`).
MOTIVO_REINGESTA_BLOQUEADA = (
    "la ingesta de este dataset falló y su fichero en bruto se borró: vuelve a subir el fichero"
)
# un dataset ya ingerido no se remapea ni se reingiere.
MOTIVO_YA_INGERIDO = (
    "este fichero de datos ya está ingerido: no se puede volver a mapear ni a ingerir; "
    "sube el fichero otra vez si necesitas otro mapeo"
)


@dataclass
class IngestResult:
    """Resultado de una ingesta: lo que devuelve el job al terminar.

    `avisos` son textos que no bloquean nada, solo
    informan. `n_ambiguos` son emparejamientos de feedback con más de
    un registro candidato (gana el del lote más reciente, pero queda
    contado). `n_id_duplicados` son filas de un lote nuevo cuyo id ya
    existía, dentro del propio lote o ya ingerido antes en la misma versión.
    """

    batch_id: int | None
    n_rows: int
    n_labeled: int
    n_matched: int
    n_unmatched: int
    privacy_applied: dict[str, str]
    avisos: list[str] = field(default_factory=list)
    n_ambiguos: int = 0
    n_id_duplicados: int = 0
    # la ingesta congeló la línea base de la versión al ingerir un
    # dataset con rol `baseline`.
    linea_base_congelada: bool = False
    # lotes que recibieron al menos una etiqueta (solo en un fichero de etiquetas).
    lotes_con_verdad: list[int] = field(default_factory=list)
    # etiquetas de un fichero de etiquetas que no se aplicaron (línea base
    # congelada o etiqueta ya registrada).
    etiquetas_omitidas: int = 0


# ---------------------------------------------------------------------------
# Utilidades de fichero y formato
# ---------------------------------------------------------------------------


def _safe_filename(filename: str) -> str:
    nombre = Path(filename).name or "dataset"
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in nombre)


def _es_feedback_harness(d: dict[str, Any]) -> bool:
    return "fields" in d and "values" in d and "_original_prediction" in d.get("fields", [])


def _clasificar_json(d: Any) -> str:
    if isinstance(d, dict) and "input_data" in d and "output_data" in d:
        return "harness_payload"
    if isinstance(d, dict) and _es_feedback_harness(d):
        return "harness_feedback"
    if isinstance(d, dict) and "fields" in d and "values" in d:
        return "json"
    if isinstance(d, list):
        return "json"
    raise HTTPException(
        422,
        "el JSON no tiene el formato de Vigía: sube un CSV o un JSON con una lista de objetos, uno por fila",
    )


# Firmas binarias de Excel: ZIP (.xlsx) y OLE (.xls), aunque el
# fichero venga renombrado con otra extensión.
_FIRMA_ZIP = b"PK\x03\x04"
_FIRMA_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
MSG_XLSX_NO_SOPORTADO = (
    "Vigía lee CSV y JSON: abre el fichero en Excel y guárdalo como CSV "
    "(delimitado por comas o por punto y coma)"
)


def detect_format(filename: str, raw: bytes) -> str:
    """Detecta el formato del fichero subido (§3.3): harness_payload, harness_feedback, json o csv.

    XLSX/XLS se reconoce por sufijo o por firma binaria y da 422 sin
    leerlo, tanto si viene bien nombrado como si viene renombrado.
    """
    sufijo = Path(filename or "").suffix.lower()
    if sufijo in (".xlsx", ".xls") or raw.startswith((_FIRMA_ZIP, _FIRMA_OLE)):
        raise HTTPException(422, MSG_XLSX_NO_SOPORTADO)
    if sufijo == ".parquet":
        raise HTTPException(
            422,
            "Parquet no disponible en este equipo (pyarrow bloqueado o ausente): usa CSV o JSON",
        )
    if sufijo == ".csv":
        return "csv"
    try:
        d = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        if sufijo == ".json":
            raise HTTPException(
                422,
                "el fichero JSON no es válido: revisa las comas y las comillas, o súbelo como CSV",
            ) from None
        return "csv"
    except (RecursionError, ValueError):
        # demasiado anidado, o un entero con miles de cifras. El
        # `ValueError` va después de `UnicodeDecodeError` y `JSONDecodeError`, que lo heredan.
        raise HTTPException(
            422,
            "el fichero JSON no se puede leer: está demasiado anidado o tiene un número "
            "con demasiadas cifras; súbelo como CSV o simplifícalo",
        ) from None
    return _clasificar_json(d)


def _contar_filas_subida(fmt: str, raw: bytes) -> int | None:
    """Estima el número de filas de la subida antes de construir el
    DataFrame completo. `None` si no se puede estimar sin parsear
    del todo (el fichero se rechaza más tarde por otro motivo si procede)."""
    if fmt == "csv":
        return contar_filas_csv(raw)
    if fmt in ("json", "harness_feedback"):
        try:
            d = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if isinstance(d, list):
            return len(d)
        if isinstance(d, dict) and "values" in d:
            return len(d["values"])
        return None
    if fmt == "harness_payload":
        try:
            d = json.loads(raw.decode("utf-8-sig"))
            return len(d["input_data"][0]["values"])
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
            return None
    return None


def _tabular_desde_json(d: Any) -> pd.DataFrame:
    if isinstance(d, list):
        return pd.DataFrame(d)
    if isinstance(d, dict) and "fields" in d and "values" in d:
        return pd.DataFrame(d["values"], columns=d["fields"])
    raise HTTPException(422, "JSON no reconocido como tabla")


def load_dataframe(
    path: Path, fmt: str, mapping: ColumnMapping | None = None
) -> tuple[pd.DataFrame, dict[str, str] | None]:
    """Carga el fichero según el formato detectado, sin depender de su extensión.

    Para CSV detecta el dialecto (codificación, separador y decimal) y
    lee con `keep_default_na=False` salvo en las columnas mapeadas como
    predicción, probabilidad y etiqueta, que conservan los nulos
    por defecto de pandas. Devuelve el dataframe y el dialecto detectado
    (`None` para el resto de formatos). 422 si el CSV no se puede reconocer
    de ninguna forma (`DatosNoValidos` de `core.loaders`, traducida aquí).
    """
    if fmt == "harness_payload":
        return load_payload(path), None
    if fmt == "harness_feedback":
        return load_feedback(path), None
    if fmt == "csv":
        cols_na_pandas: set[str] = set()
        if mapping is not None:
            cols_na_pandas = {
                c
                for c in (
                    mapping.prediction_col,
                    mapping.probability_col,
                    mapping.label_col,
                    *mapping.probability_cols,
                )
                if c
            }
        try:
            df, dialecto = read_csv_smart(Path(path).read_bytes(), na_pandas_cols=cols_na_pandas)
        except DatosNoValidos as exc:
            raise HTTPException(422, str(exc)) from exc
        return df, dialecto
    if fmt == "json":
        d = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return _tabular_desde_json(d), None
    raise HTTPException(422, f"formato de dataset no soportado: {fmt!r}")


def _columns_info(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Info de columnas del dataframe crudo. Sin enmascarado: Vigía no
    pseudonimiza, la muestra es el valor real tal como llega."""
    columnas = []
    for col in df.columns:
        serie = df[col]
        no_nulos = serie.dropna()
        muestra = privacy.to_jsonable(no_nulos.iloc[0]) if len(no_nulos) else None
        columnas.append(
            {
                "name": str(col),
                "dtype": str(serie.dtype),
                "n_null": int(serie.isna().sum()),
                "sample": muestra,
            }
        )
    return columnas


_PREFIJOS_PROB_CLASE = ("probability_", "proba_", "prob_")


def _columnas_prob_por_clase(df: pd.DataFrame) -> list[tuple[str, str]]:
    """columnas `prob_<clase>` (o `probability_<clase>`, `proba_<clase>`) en
    el orden del fichero, como `(columna, sufijo)`. Una columna `prob` a secas
    no cuenta: es la probabilidad escalar de siempre."""
    encontradas: list[tuple[str, str]] = []
    for col in df.columns:
        nombre = str(col).strip()
        bajo = nombre.casefold()
        for prefijo in _PREFIJOS_PROB_CLASE:
            if bajo.startswith(prefijo) and len(nombre) > len(prefijo):
                encontradas.append((str(col), nombre[len(prefijo):].strip("_ ")))
                break
    return [(c, suf) for c, suf in encontradas if suf]


def _clase_como_valor(valor: Any) -> int | str:
    """Una clase leída de un fichero a `int` si es un entero, si no a texto."""
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, (int,)):
        return int(valor)
    texto = str(valor).strip()
    if texto.lstrip("-").isdigit():
        return int(texto)
    return texto


def _sugerir_clases(
    df: pd.DataFrame,
    prediccion: str | None,
    sufijos: list[str],
    etiqueta: str | None = None,
) -> list[int | str]:
    """las clases desde la columna de predicción de la línea base.

    Con columnas `prob_<clase>`, en su orden (la de las probabilidades manda);
    si cada sufijo coincide con una clase de la predicción, se usa el
    valor de la predicción (`1`, no `"1"`). Sin ellas, los valores distintos de
    la predicción en orden natural (el que escribe `skl2onnx`)."""
    valores: dict[str, int | str] = {}
    for columna in (prediccion, etiqueta):
        if columna and columna in df.columns:
            for v in df[columna].dropna().unique():
                if es_valor_nulo(v):
                    continue
                c = _clase_como_valor(v)
                valores.setdefault(clave_clase(c), c)
    if sufijos:
        por_minuscula = {k.casefold(): v for k, v in valores.items()}
        return [por_minuscula.get(suf.casefold(), _clase_como_valor(suf)) for suf in sufijos]
    claves = list(valores.values())
    try:
        return sorted(claves, key=lambda c: (isinstance(c, str), c))  # type: ignore[arg-type,return-value]
    except TypeError:
        return sorted(claves, key=str)


def _suggest_mapping(
    df: pd.DataFrame, fmt: str, *, task_type: str = "binary", role: str = "baseline"
) -> dict[str, Any]:
    if fmt == "harness_feedback":
        return HARNESS_FEEDBACK_MAPPING.model_dump(mode="json")
    if fmt == "harness_payload":
        mapping = HARNESS_PAYLOAD_MAPPING.model_dump(mode="json")
        # HARNESS_PAYLOAD_MAPPING no lleva id_col (el motor no lo necesita para
        # reproducir el escenario); aquí sí, para poder emparejar feedback
        # ingerido después por (project_id, external_id).
        if "Episode_Id" in df.columns:
            mapping["id_col"] = "Episode_Id"
        return mapping

    normalizados = {privacy.normalize_name(c): c for c in df.columns}

    def buscar(*candidatos: str) -> str | None:
        for candidato in candidatos:
            if candidato in normalizados:
                return normalizados[candidato]
        return None

    prob_por_clase = _columnas_prob_por_clase(df)
    prediction_col = buscar("prediction", "pred") or ""
    probability_cols: list[str] = []
    clases: list[int | str] = []
    # Multiclase: el conjunto favorable lo marca la persona; un `1` suelto no es
    # una clase de texto. Regresión: ni favorable ni probabilidad, solo la
    # predicción y la etiqueta (números).
    favorable: int | None
    match task_type:
        case "binary":
            favorable = 1
            probability_col = buscar("probability", "prob", "proba")
        case "multiclass":
            # una columna de probabilidad por clase y las clases desde la
            # predicción de la línea base.
            favorable = None
            if len(prob_por_clase) >= 2:
                probability_cols = [c for c, _s in prob_por_clase]
            if role == "baseline":
                clases = _sugerir_clases(
                    df,
                    prediction_col or None,
                    [suf for _c, suf in prob_por_clase] if probability_cols else [],
                    buscar("label", "target", "y"),
                )
            probability_col = None if probability_cols else buscar("probability", "prob", "proba")
        case "regression":
            favorable = None
            probability_col = None
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task_type!r}")
    return {
        "prediction_col": prediction_col,
        "probability_col": probability_col,
        "probability_cols": probability_cols,
        "classes": clases,
        "probability_format": "scalar",
        "probability_index": 1,
        "label_col": buscar("label", "target", "y"),
        "id_col": buscar("id"),
        "timestamp_col": buscar("timestamp", "date", "fecha"),
        "protected_attr_col": buscar("age", "edad") or buscar("sex", "sexo"),
        "protected_kind": "numeric_ranges",
        "unpriv_groups": [],
        "priv_groups": [],
        # la sugerencia no propone variables, así que la columna de fecha
        # nunca entra en ellas; el cruce con la plantilla lo cuida
        # `_mapeo_sugerido_con_plantilla`.
        "feature_cols": [],
        "clinician_col": buscar("clinician", "clinico", "clinician_pseudonym"),
        "subgroup_col": buscar("subgroup", "subgrupo"),
        "favorable_label": favorable,
    }


# Campos de `MappingTemplate` (migración 10): lo estable entre
# datasets de un mismo proyecto.
_CAMPOS_PLANTILLA = (
    "favorable_label",
    "classes",
    "probability_cols",
    "prediction_col",
    "probability_col",
    "label_col",
    "id_col",
    "timestamp_col",
    "feature_cols",
    "protected_attr_col",
    "protected_kind",
    "unpriv_groups",
    "priv_groups",
    # unidad de la salida y rango favorable de una regresión.
    "target_unit",
    "favorable_ranges",
)


# columnas del modelo que la plantilla fija; solo se sugieren si el
# fichero las trae (un lote con otros nombres no recibe una columna que no existe).
# la columna de fecha se trata igual.
_COLUMNAS_DEL_MODELO = ("prediction_col", "probability_col", "label_col", "timestamp_col")
# campos de la plantilla que solo existen en regresión.
_CAMPOS_SOLO_REGRESION = ("target_unit", "favorable_ranges")


def _mapeo_sugerido_con_plantilla(
    suggested_mapping: dict[str, Any] | None,
    plantilla: dict[str, Any] | None,
    columnas: set[str] | None = None,
) -> dict[str, Any] | None:
    """la sugerencia de mapeo de `GET /datasets/{id}` se rellena desde
    `project.mapping_template_json` (lo que la plantilla ya trae); lo que la
    plantilla no fija se queda con la propuesta de `_suggest_mapping`.
    `columnas` (nombres del fichero) filtra las tres columnas del modelo."""
    if not plantilla:
        return suggested_mapping
    combinado = dict(suggested_mapping or {})
    for campo in _CAMPOS_PLANTILLA:
        valor = plantilla.get(campo)
        if valor in (None, [], ""):
            continue
        if campo in _COLUMNAS_DEL_MODELO and columnas is not None and valor not in columnas:
            continue
        combinado[campo] = valor
    # la plantilla de antes de este arreglo puede traer la
    # columna de fecha entre las variables; nunca se sugiere como variable.
    fecha = combinado.get("timestamp_col")
    if fecha and fecha in (combinado.get("feature_cols") or []):
        combinado["feature_cols"] = [c for c in combinado["feature_cols"] if c != fecha]
    return combinado


def _valor_plano(valor: Any) -> Any:
    """El valor sin `Enum` y con las tuplas como listas: el mapeo da tuplas
    (`favorable_ranges`) y el JSON de la plantilla listas, y no son un apartamiento."""
    valor = valor.value if hasattr(valor, "value") else valor
    if isinstance(valor, (list, tuple)):
        return [_valor_plano(v) for v in valor]
    return valor


def mapeo_se_aparta_de_plantilla(mapping: ColumnMapping, plantilla: dict[str, Any] | None) -> bool:
    """si el mapeo que se guarda difiere de un campo que la plantilla
    del proyecto sí fija, es un apartamiento (evento `dataset.mapeo_distinto_plantilla`,
    no bloquea nada)."""
    if not plantilla:
        return False
    for campo in _CAMPOS_PLANTILLA:
        valor_plantilla = plantilla.get(campo)
        if valor_plantilla in (None, [], ""):
            continue
        valor = _valor_plano(getattr(mapping, campo, None))
        if campo in _COLUMNAS_DEL_MODELO and valor is None:
            # Un fichero que no usa la columna (feedback sin predicción) no se aparta.
            continue
        if campo in _CAMPOS_SOLO_REGRESION and valor in (None, []):
            # Un mapeo que no dice unidad ni rango rige con los del proyecto: no se aparta.
            continue
        if valor != _valor_plano(valor_plantilla):
            return True
    return False


# ---------------------------------------------------------------------------
# Serialización de lectura
# ---------------------------------------------------------------------------


def dataset_to_dict(
    d: Dataset,
    *,
    con_privacidad: bool = True,
    project: Project | None = None,
    n_batches: int = 0,
) -> dict[str, Any]:
    """Dataset sin `file_path` real de disco expuesto más allá de su nombre.

    Con `project`, `suggested_mapping` se rellena desde
    `project.mapping_template_json`: lo que la plantilla ya fija manda, lo
    que le falta lo sigue proponiendo `_suggest_mapping` tal como se guardó
    al subir.
    """
    suggested = d.suggested_mapping_json
    if project is not None:
        nombres = {c["name"] if isinstance(c, dict) else str(c) for c in (d.columns_json or [])}
        suggested = _mapeo_sugerido_con_plantilla(
            suggested, project.mapping_template_json, nombres or None
        )
    # el registro de uso guarda en `mapping_json` solo la
    # declaración `{"valor_favorable": ...}`, que no es un mapeo de columnas.
    mapping = d.mapping_json
    valor_favorable = None
    if isinstance(mapping, dict) and "valor_favorable" in mapping:
        valor_favorable = mapping["valor_favorable"]
        mapping = {k: v for k, v in mapping.items() if k != "valor_favorable"} or None
    data = {
        "id": d.id,
        "project_id": d.project_id,
        "name": d.name,
        "source": d.source,
        "kind": d.kind,
        "role": d.role,
        "format": d.format,
        "sha256": d.sha256,
        "sha256_privado": d.sha256_privado,
        "raw_purged": d.raw_purged,
        "n_rows": d.n_rows,
        "columns": d.columns_json,
        "mapping": mapping,
        "suggested_mapping": suggested,
        "valor_favorable": valor_favorable,
        "dialect": d.dialect_json,
        "status": d.status,
        "created_at": d.created_at,
        "n_batches": n_batches,
    }
    if con_privacidad:
        data["privacy_report"] = d.privacy_report_json
        data["privacy_decisions"] = d.privacy_decisions_json
    return data


def batch_to_dict(b: Batch, *, dataset_name: str | None = None) -> dict[str, Any]:
    return {
        "id": b.id,
        "project_id": b.project_id,
        "dataset_id": b.dataset_id,
        "model_version_id": b.model_version_id,
        "seq": b.seq,
        "phase_label": b.phase_label,
        "n_rows": b.n_rows,
        "n_labeled": b.n_labeled,
        "orden_manipulado": b.orden_manipulado,
        "motivo_manipulacion": b.motivo_manipulacion,
        "demo_run_id": b.demo_run_id,
        "created_at": b.created_at,
        "dataset_name": dataset_name,
    }


def record_to_dict(
    r: Record, *, with_features: bool, group_label: str | None = None
) -> dict[str, Any]:
    data = {
        "id": r.id,
        "batch_id": r.batch_id,
        "seq": r.seq,
        "external_id": r.external_id,
        "timestamp": r.timestamp,
        "prediction": r.prediction,
        "prob_favorable": r.prob_favorable,
        "label": r.label,
        "prediction_class": r.prediction_class,
        "label_class": r.label_class,
        "probabilities": r.probabilities_json,
        "prediction_value": r.prediction_value,
        "label_value": r.label_value,
        "protected_value": r.protected_value,
        "group_code": r.group_code,
        "group_label": group_label,
        "clinician_pseudonym": r.clinician_pseudonym,
        "subgroup": r.subgroup,
    }
    if with_features:
        data["features"] = r.features_json
    return data


# ---------------------------------------------------------------------------
# Subida y mapeo
# ---------------------------------------------------------------------------


def register_upload(
    session: Session,
    project: Project,
    *,
    file_bytes: bytes,
    filename: str,
    kind: str,
    role: str,
    name: str | None = None,
    source: str = "upload",
    data_dir: Path,
    actor: Actor,
    correlation_id: str | None = None,
    job_id: int | None = None,
    bus: EventBus | None = None,
) -> tuple[Dataset, list[dict[str, Any]]]:
    """Guarda la subida, detecta el formato y calcula privacidad y mapeo sugerido.

    Devuelve el `Dataset` y la previsualización enmascarada (no se guarda en la
    base de datos: la calcula el router para la respuesta de la subida). El
    dialecto de CSV detectado se guarda en `dataset.dialect_json`.
    """
    if kind not in _KINDS_VALIDOS:
        raise HTTPException(
            422, f"el tipo de datos {kind!r} no es válido: elige uno de {', '.join(_KINDS_VALIDOS)}"
        )
    if role not in _ROLES_VALIDOS:
        raise HTTPException(
            422, f"el papel {role!r} no es válido: elige uno de {', '.join(_ROLES_VALIDOS)}"
        )

    nombre_seguro = _safe_filename(filename)
    fmt = detect_format(filename, file_bytes)

    # se cuentan las filas antes de crear el dataset o escribir nada en
    # disco, para no dejar un registro a medias cuando el fichero es
    # demasiado grande.
    n_estimado = _contar_filas_subida(fmt, file_bytes)
    if n_estimado is not None and n_estimado > LIMITE_FILAS_LOTE:
        raise HTTPException(422, mensaje_limite_filas(n_estimado))

    dataset = Dataset(
        project_id=project.id,
        name=name or nombre_seguro,
        source=source,
        kind=kind,
        role=role,
        format=fmt,
        status="subido",
    )
    session.add(dataset)
    session.flush()

    carpeta = Path(data_dir) / "uploads" / str(project.id)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{dataset.id}_{nombre_seguro}"
    try:
        ruta.write_bytes(file_bytes)

        dataset.file_path = str(ruta)
        dataset.sha256 = hashlib.sha256(file_bytes).hexdigest()

        df, dialecto = load_dataframe(ruta, fmt)
        dataset.n_rows = len(df)
        # Vigía no pseudonimiza. Sin detección de columnas identificadoras
        # ni decisiones de privacidad; el informe es la constante de
        # `privacy.empty_report` y `columns_json` lleva la muestra tal cual llega.
        dataset.privacy_report_json = privacy.empty_report()
        suggested = _suggest_mapping(df, fmt, task_type=project.task_type, role=role)
        dataset.suggested_mapping_json = suggested
        dataset.columns_json = _columns_info(df)
        session.add(dataset)
        session.flush()

        # el dialecto detectado (solo CSV) se guarda en el dataset y viaja
        # también en el evento de subida.
        after_evento: dict[str, Any] = {"format": fmt, "n_rows": dataset.n_rows}
        if dialecto is not None:
            after_evento["dialect"] = dialecto
        dataset.dialect_json = dialecto
        record_event(
            session,
            actor_kind=actor.kind,
            actor_id=actor.id,
            role=actor.role,
            action="dataset.subido",
            object_type="dataset",
            object_id=dataset.id,
            project_id=project.id,
            after=after_evento,
            correlation_id=correlation_id,
            job_id=job_id,
            bus=bus,
        )
        session.commit()
    except BaseException:
        # Una subida rechazada no deja el fichero en uploads/.
        ruta.unlink(missing_ok=True)
        raise
    session.refresh(dataset)

    # sin enmascarado. `to_jsonable` normaliza los tipos de pandas a JSON.
    preview = [
        {col: privacy.to_jsonable(valor) for col, valor in fila.items()}
        for _, fila in df.head(20).iterrows()
    ]
    return dataset, preview


def _plantilla_del_proyecto(project: Project) -> MappingTemplate | None:
    if not project.mapping_template_json:
        return None
    try:
        return MappingTemplate(**project.mapping_template_json)
    except (TypeError, ValueError):
        return None


def _mapeo_baseline_mas_reciente(session: Session, project: Project) -> dict[str, Any] | None:
    """Mapeo del dataset de la línea base congelada del proyecto: la
    de la versión activa si la tiene, si no la de la versión congelada más
    reciente."""
    ids_candidatos: list[int] = []
    if project.active_version_id is not None:
        ids_candidatos.append(project.active_version_id)
    otras = session.exec(
        select(ModelVersion.id)
        .where(ModelVersion.project_id == project.id, ModelVersion.baseline_batch_id.is_not(None))
        .order_by(ModelVersion.id.desc())  # type: ignore[union-attr]
    ).all()
    for version_id in otras:
        if version_id not in ids_candidatos:
            ids_candidatos.append(version_id)

    for version_id in ids_candidatos:
        version = session.get(ModelVersion, version_id)
        if version is None or version.baseline_batch_id is None:
            continue
        batch = session.get(Batch, version.baseline_batch_id)
        if batch is None or batch.dataset_id is None:
            continue
        baseline_dataset = session.get(Dataset, batch.dataset_id)
        if baseline_dataset is not None and baseline_dataset.mapping_json:
            return baseline_dataset.mapping_json
    return None


def _resolver_favorable_heredado(session: Session, project: Project) -> Any:
    """`favorable_label` omitido se hereda de la plantilla del proyecto
    y, si no hay, del mapeo de la línea base congelada; `None` si ninguna de
    las dos lo tiene (el llamador da 422)."""
    plantilla = _plantilla_del_proyecto(project)
    if plantilla is not None and plantilla.favorable_label is not None:
        return plantilla.favorable_label
    mapeo_base = _mapeo_baseline_mas_reciente(session, project)
    if mapeo_base is not None:
        valor = mapeo_base.get("favorable_label")
        if valor is not None:
            return valor
    return None


def _validar_favorable_en_etiqueta(dataset: Dataset, mapping: ColumnMapping) -> None:
    """422 si la columna de etiquetas trae valores no nulos y ni
    la clase favorable ni sus alias están entre ellos (un `-1` que no existe en
    una columna 0/1 dejaba pasar el lote con alertas espurias). Enumera hasta 10
    valores encontrados. Se salta si el fichero en bruto ya no se puede leer.
    Una etiqueta de un solo valor binario (lote sin favorables, con favorable
    también binario) es legítima y pasa."""
    if not mapping.label_col or dataset.raw_purged or not dataset.file_path:
        return
    ruta = Path(dataset.file_path)
    if not ruta.is_file():
        return
    try:
        df, _dialecto = load_dataframe(ruta, dataset.format, mapping)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001  # un fichero ilegible ya fallará al ingerir
        return
    if mapping.label_col not in df.columns:
        return
    favorable = mapping.favorable_resuelto
    valores = [v for v in df[mapping.label_col].dropna().unique() if not es_valor_nulo(v)]
    if not valores:
        return
    if any(resolver_favorable(v, favorable) is True for v in valores):
        return

    def _binario(x: Any) -> bool:
        if isinstance(x, (int, float)) and not isinstance(x, bool) and float(x).is_integer():
            x = int(x)
        return str(x).strip().casefold() in (_ALIAS_CLASE_SI | _ALIAS_CLASE_NO)

    if _binario(favorable) and all(_binario(v) for v in valores):
        return
    vistos = [str(v) for v in valores[:10]]
    resto = len(valores) - len(vistos)
    listado = ", ".join(vistos) + (f" (y {resto} más)" if resto > 0 else "")
    # una etiqueta numérica con muchos valores distintos es la de una regresión.
    numeros = pd.to_numeric(pd.Series(valores, dtype=object), errors="coerce")
    continuos = (
        len(valores) > MIN_VALORES_CONTINUOS and bool(numeros.notna().all())
    )
    pista = (
        ". Esos valores parecen los de un modelo de regresión: si lo es, crea un proyecto de regresión"
        if continuos
        else ""
    )
    raise HTTPException(
        422,
        f"la clase favorable {favorable!r} no aparece en la columna de etiquetas "
        f"{mapping.label_col!r} ni tiene alias reconocido entre sus valores; "
        f"valores encontrados: {listado}; revisa la clase favorable en el paso Mapeo{pista}",
    )


def _completar_clases(project: Project, mapping: ColumnMapping) -> ColumnMapping:
    """Un mapeo sin `classes` hereda las del proyecto (`classes_json`) para que
    `mapping_json` sea autosuficiente."""
    if mapping.classes:
        return mapping
    del_proyecto = tarea_service.clases_del_proyecto(project)
    if del_proyecto:
        return mapping.model_copy(update={"classes": del_proyecto})
    return mapping


def _mensaje_clase_desconocida(clase: Any, task: TaskSpec) -> str:
    """Texto del aviso (el mismo que lanza `to_canonical`)."""
    return (
        f"El modelo predice la clase {clase}, que no está entre las clases del proyecto "
        f"({', '.join(str(c) for c in task.classes)}). "
        "Si es una versión nueva del modelo, créala."
    )


def _validar_prediccion_en_clases(dataset: Dataset, mapping: ColumnMapping, task: TaskSpec) -> None:
    """422 al guardar el mapeo si la columna de predicción trae una
    clase fuera de las del proyecto, antes de que la ingesta consuma el fichero
    en bruto. `to_canonical` repite la comprobación como red de seguridad. Se
    salta si el fichero ya no se puede leer. Una etiqueta con clase nueva no
    bloquea (se ingiere y se avisa)."""
    if not mapping.prediction_col or dataset.raw_purged or not dataset.file_path:
        return
    ruta = Path(dataset.file_path)
    if not ruta.is_file():
        return
    try:
        df, _dialecto = load_dataframe(ruta, dataset.format, mapping)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001  # un fichero ilegible ya fallará al ingerir
        return
    if mapping.prediction_col not in df.columns:
        return
    conocidas = set(task.claves)
    for v in df[mapping.prediction_col].dropna().unique():
        if es_valor_nulo(v):
            continue
        if clave_clase(v) not in conocidas:
            raise HTTPException(422, _mensaje_clase_desconocida(clave_clase(v), task))


FILAS_COMPROBACION_NUMERICA = 200


def _comprobar_unidad_y_rango_fijados(
    session: Session, project: Project, mapping: ColumnMapping
) -> None:
    """con la línea base congelada, el mapeo no puede traer otra unidad ni otro rango
    favorable que los del proyecto (la pertenencia al rango ya está guardada en los lotes).
    Un mapeo que no los dice rige con los del proyecto. 409 con la pauta de crear un
    proyecto nuevo."""
    if not projects_service.linea_base_congelada(session, project):
        return
    try:
        unidad = validar_unidad(mapping.target_unit)
        rangos = validar_rangos(mapping.favorable_ranges)
    except DatosNoValidos as exc:
        raise HTTPException(422, str(exc)) from exc
    fijados = tarea_service.rangos_del_proyecto(project) or ()
    if (unidad is not None and unidad != project.target_unit) or (rangos and rangos != fijados):
        raise HTTPException(409, tarea_service.MENSAJE_CAMBIO_UNIDAD_O_RANGO)


def _mensaje_prediccion_no_numerica(columna: str, malos: list[Any], fila: int | None = None) -> str:
    """el 422 de una predicción que no es un número dice qué hacer
    según lo que haya en las celdas malas: infinitos, clases de texto (un clasificador) o un
    número con la unidad pegada."""
    ejemplo = str(malos[0])
    donde = f"La primera está en la fila {fila} de los datos. " if fila is not None else ""
    base = (
        f"la columna de predicción «{columna}» tiene valores que no son un número "
        f"(por ejemplo {ejemplo!r}). {donde}"
    )
    textos = [str(v).strip().lower().lstrip("+-") for v in malos]
    if any(t in ("inf", "infinity", "∞") for t in textos):
        return (
            base + "Un modelo de regresión predice un número finito: quita o sustituye los "
            "infinitos (inf) de esa columna, o elige la columna correcta en el paso Mapeo"
        )
    sin_cifras = all(not any(c.isdigit() for c in str(v)) for v in malos)
    distintos = {str(v).strip() for v in malos}
    if sin_cifras and 2 <= len(distintos) <= 20:
        return (
            base + "Parece un modelo de clasificación: crea un proyecto binario o multiclase, "
            "o elige la columna correcta en el paso Mapeo"
        )
    return (
        base + "Un modelo de regresión predice un número: quita la unidad pegada al valor "
        "(«12 h» pasa a 12) o elige la columna correcta en el paso Mapeo"
    )


def _validar_numerico_regresion(dataset: Dataset, mapping: ColumnMapping) -> None:
    """en las primeras 200 filas, la predicción es un número en todas
    las celdas con valor y la etiqueta trae al menos un número. Una etiqueta con algunas
    celdas de texto pasa (la ingesta avisa y las deja sin etiqueta); una columna sin
    ningún número no es la etiqueta de una regresión. Se salta si el fichero ya no se
    puede leer."""
    if dataset.raw_purged or not dataset.file_path:
        return
    ruta = Path(dataset.file_path)
    if not ruta.is_file():
        return
    try:
        df, _dialecto = load_dataframe(ruta, dataset.format, mapping)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001  # un fichero ilegible ya fallará al ingerir
        return
    for rol, columna in (("predicción", mapping.prediction_col), ("etiqueta", mapping.label_col)):
        if not columna or columna not in df.columns:
            continue
        # La fila es la posición en los datos más uno, como en la ingesta («fila 41»).
        posiciones = [
            i
            for i, v in enumerate(df[columna].iloc[:FILAS_COMPROBACION_NUMERICA].tolist())
            if not es_valor_nulo(v)
        ]
        muestra = [df[columna].iloc[i] for i in posiciones]
        if not muestra:
            continue
        numeros = pd.to_numeric(pd.Series(muestra, dtype=object), errors="coerce").to_numpy(dtype=float)
        malas = ~np.isfinite(numeros)
        if not malas.any():
            continue
        primera_mala = int(np.argmax(malas))
        ejemplo = str(muestra[primera_mala])
        fila_mala = posiciones[primera_mala] + 1
        if rol == "predicción":
            raise HTTPException(
                422,
                _mensaje_prediccion_no_numerica(
                    columna, [v for v, mala in zip(muestra, malas, strict=True) if mala], fila_mala
                ),
            )
        if malas.all():
            raise HTTPException(
                422,
                f"la columna de etiquetas «{columna}» no tiene ningún número en las primeras "
                f"{len(muestra)} filas (por ejemplo {ejemplo!r}, en la fila {fila_mala} de los datos). En una regresión la etiqueta es "
                "el valor real, un número. Si el modelo clasifica en clases, crea un proyecto de "
                "clasificación; si no, elige la columna correcta en el paso Mapeo",
            )


def _rechazar_columnas_con_nombre_reservado(
    dataset: Dataset,
    mapping: ColumnMapping,
    columnas_reales: set[str],
    referenciadas: list[str],
) -> None:
    """422 si una variable del mapeo, o una columna que queda sin mapear y
    pasaría a ser variable, se llama como una columna canónica (`seq`, `label`,
    `group_code`...): sustituiría en silencio el valor del lote. Un fichero de etiquetas
    (`feedback`) no construye el lote, así que sus columnas sobrantes no cuentan."""
    if mapping.feature_cols:
        candidatas = {c for c in mapping.feature_cols}
    elif dataset.kind != "feedback":
        candidatas = columnas_reales - set(referenciadas)
    else:
        return
    reservadas = sorted(c for c in candidatas if es_columna_canonica(c))
    if reservadas:
        listado = ", ".join(f"«{c}»" for c in reservadas)
        pista = ""
        if {"human_decision", "model_output"} <= {str(c).strip().casefold() for c in columnas_reales}:
            pista = " Si es un registro de uso, súbelo en Capa humana > Registro de uso."
        raise HTTPException(
            422,
            f"el fichero tiene columnas con un nombre que Vigía reserva para sus propios datos: "
            f"{listado}. Renómbralas en el fichero, o elige para qué sirven en el paso Mapeo.{pista}",
        )


def set_mapping(
    session: Session,
    dataset: Dataset,
    mapping: ColumnMapping,
    privacy_decisions: dict[str, str] | None = None,
    *,
    actor: Actor,
    correlation_id: str | None = None,
    job_id: int | None = None,
    bus: EventBus | None = None,
) -> Dataset:
    """Fija el mapeo de columnas del dataset.

    `privacy_decisions` se acepta y se ignora (`MappingBody`
    lo sigue enviando por compatibilidad): Vigía no exige ni aplica
    decisiones de privacidad.
    """
    del privacy_decisions
    # tras la ingesta el fichero en bruto está purgado y los validadores
    # que lo leen no corren; un remapeo sin ellos dejaría un mapeo sin comprobar.
    if dataset.status == "ingerido":
        raise HTTPException(409, MOTIVO_YA_INGERIDO)
    columnas_reales = {c["name"] for c in (dataset.columns_json or [])}
    referenciadas = [
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
            *mapping.feature_cols,
        )
        if c
    ]
    faltan = sorted({c for c in referenciadas if c not in columnas_reales})
    if faltan:
        listado = ", ".join(f"«{c}»" for c in faltan)
        raise HTTPException(
            422,
            f"el mapeo usa columnas que no están en el fichero: {listado}; "
            "elige columnas del fichero en el paso Mapeo",
        )
    _rechazar_columnas_con_nombre_reservado(dataset, mapping, columnas_reales, referenciadas)

    if dataset.kind == "feedback" and not mapping.label_col:
        raise HTTPException(
            422,
            "falta la columna de etiquetas en el mapeo: elígela en el paso Mapeo, este tipo de datos la necesita",
        )
    # solo la línea base exige la etiqueta. Un lote de producción sin ella se
    # ingiere con la plantilla, porque la etiqueta puede llegar después (etiquetas tardías).
    if dataset.kind == "combined" and dataset.role == "baseline" and not mapping.label_col:
        raise HTTPException(
            422,
            "falta la columna de etiquetas en el mapeo: la línea base la necesita para medir; "
            "elígela en el paso Mapeo (un lote de producción puede subirse sin ella)",
        )
    if dataset.kind == "feedback" and not mapping.id_col:
        raise HTTPException(
            422,
            "falta la columna de identificador en el mapeo: elígela en el paso Mapeo para poder emparejar el feedback",
        )
    # prediction_col solo hace falta en combined y payload (un feedback
    # de solo id_col y label_col no lo necesita para emparejar).
    if dataset.kind in ("combined", "payload") and not mapping.prediction_col:
        raise HTTPException(
            422,
            "falta la columna de predicción en el mapeo: elígela en el paso Mapeo, este tipo de datos la necesita",
        )

    project = session.get(Project, dataset.project_id)
    if project is None:
        raise no_encontrado("modelo", dataset.project_id, "modelos")
    # una plantilla guardada con `positive_label` deja un aviso y lo pierde.
    tarea_service.limpiar_positive_label(session, project, bus=bus)

    # id_col obligatorio en combined y payload para poder
    # emparejar feedback más tarde, salvo que el proyecto declare que nunca
    # lo recibirá (`Project.acepta_feedback=False`).
    if dataset.kind in ("combined", "payload") and not mapping.id_col and project.acepta_feedback:
        raise HTTPException(
            422,
            "falta la columna de identificador en el mapeo: elígela en el paso Mapeo para poder "
            "emparejar el feedback más tarde, o indica en los ajustes del modelo que no recibirá feedback",
        )

    # favorable_label omitido se hereda de la plantilla del proyecto y,
    # si no hay, del mapeo de la línea base; sin ninguno, 422. Solo hace
    # falta cuando el mapeo compara algo contra la clase favorable. En
    # multiclase "sin conjunto favorable" es legítimo: se hereda si hay
    # y, si no, queda vacío; para vaciarlo contra una plantilla que lo fija se
    # manda `[]`.
    if mapping.favorable_label is None and (mapping.prediction_col or mapping.label_col):
        match project.task_type:
            case "regression":
                # una regresión no tiene clase favorable; su rango va en
                # `favorable_ranges` y no se hereda ni se exige aquí.
                pass
            case "multiclass":
                heredado = _resolver_favorable_heredado(session, project)
                if heredado is not None:
                    mapping = mapping.model_copy(update={"favorable_label": heredado})
            case "binary":
                heredado = _resolver_favorable_heredado(session, project)
                if heredado is None:
                    raise HTTPException(
                        422,
                        "no hay una clase favorable que heredar: indícala en el paso Mapeo o en la "
                        "plantilla del modelo, o mapea antes la línea base",
                    )
                mapping = mapping.model_copy(update={"favorable_label": heredado})
            case _:
                raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")

    # reglas del mapeo por tipo de tarea; las clases
    # del mapeo se completan con las del proyecto y no pueden contradecirlas.
    mapping = _completar_clases(project, mapping)
    try:
        task = tarea_service.tarea_del_proyecto(project, mapping)
    except DatosNoValidos as exc:
        raise HTTPException(422, str(exc)) from exc
    match task.task_type:
        case "multiclass":
            _validar_prediccion_en_clases(dataset, mapping, task)
        case "binary":
            _validar_favorable_en_etiqueta(dataset, mapping)
        case "regression":
            _comprobar_unidad_y_rango_fijados(session, project, mapping)
            _validar_numerico_regresion(dataset, mapping)
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task.task_type!r}")

    # sin decisiones de privacidad que exigir; `privacy_decisions` se
    # ignora si llega (compatibilidad del cuerpo, `MappingBody`).
    dataset.mapping_json = mapping.model_dump(mode="json")
    dataset.privacy_decisions_json = None
    dataset.status = "mapeado"
    session.add(dataset)
    session.flush()

    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="dataset.mapeado",
        object_type="dataset",
        object_id=dataset.id,
        project_id=dataset.project_id,
        after={"mapping": dataset.mapping_json},
        correlation_id=correlation_id,
        job_id=job_id,
        bus=bus,
    )

    # un mapeo que se aparta de la plantilla del proyecto deja aviso
    # en el diario; no bloquea la subida.
    if mapeo_se_aparta_de_plantilla(mapping, project.mapping_template_json):
        record_event(
            session,
            actor_kind=actor.kind,
            actor_id=actor.id,
            role=actor.role,
            action="dataset.mapeo_distinto_plantilla",
            object_type="dataset",
            object_id=dataset.id,
            project_id=dataset.project_id,
            after={"mapping": dataset.mapping_json},
            correlation_id=correlation_id,
            job_id=job_id,
            bus=bus,
        )

    session.commit()
    session.refresh(dataset)
    return dataset


# ---------------------------------------------------------------------------
# Ingesta
# ---------------------------------------------------------------------------


def _next_batch_seq(session: Session, project_id: int) -> int:
    maximo = session.exec(select(func.max(Batch.seq)).where(Batch.project_id == project_id)).one()
    return 0 if maximo is None else int(maximo) + 1


def _next_record_seq(session: Session, project_id: int) -> int:
    maximo = session.exec(select(func.max(Record.seq)).where(Record.project_id == project_id)).one()
    return 0 if maximo is None else int(maximo) + 1


def _valor_o_none(fila: pd.Series, columna: str) -> Any:
    valor = fila[columna]
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    return valor


def _valor_columna(fila: pd.Series, columna: str) -> Any:
    """Como `_valor_o_none`, pero `None` también si el frame no trae la columna
    (binario: no hay `prediction_class` ni `label_class`)."""
    if columna not in fila.index:
        return None
    return _valor_o_none(fila, columna)


def _probabilidades(fila: pd.Series, task: TaskSpec | None) -> list[float] | None:
    """Las `k` probabilidades del registro, en el orden de `task.classes`."""
    if task is None:
        return None
    nombres = [col_prob(i) for i in range(task.k)]
    if any(n not in fila.index for n in nombres):
        return None
    return [float(fila[n]) for n in nombres]


def _str_o_none(valor: Any) -> str | None:
    return None if valor is None else str(valor)


def _flotante_o_none(valor: Any) -> float | None:
    """`valor` como `float` finito, o `None` (columnas continuas del registro)."""
    if valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if np.isfinite(numero) else None


def _a_numero(valor: Any) -> float | None:
    """Número de una celda (`12`, `"12.5"`); `None` si es texto, como «12 h»."""
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _etiqueta_de_valor(valor: float, task: TaskSpec) -> float:
    """el 0/1 de `label` de una regresión: la pertenencia al rango favorable y, sin
    rango, 0 (hay etiqueta). `en_rango` es la única función que decide."""
    if not task.rangos_favorables:
        return 0.0
    return float(bool(en_rango(valor, task.rangos_favorables)))


def _columnas_mapeadas(df: pd.DataFrame, mapping: ColumnMapping) -> list[str]:
    """Columnas de `df` que el mapeo usa fuera de las variables de entrada (sin `feature_cols`)."""
    usadas = {
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
        if c
    }
    return [c for c in df.columns if c in usadas]


def retirar_variables_guardadas(session: Session, project: Project) -> int:
    """Quita las variables de entrada ya guardadas (`store_features=false`).

    Pone `features_json` a nulo en los registros del proyecto y deja en cada
    `.privado.csv` solo las columnas mapeadas. Devuelve los registros afectados.
    No hace commit: lo hace quien llama.
    """
    resultado = session.exec(
        sa_update(Record)  # type: ignore[arg-type]
        .where(Record.project_id == project.id, Record.features_json.is_not(None))  # type: ignore[union-attr]
        .values(features_json=None)
    )
    for dataset in session.exec(select(Dataset).where(Dataset.project_id == project.id)).all():
        if not (dataset.raw_purged and dataset.file_path and dataset.mapping_json):
            continue
        ruta = Path(dataset.file_path)
        if not (ruta.name.endswith(".privado.csv") and ruta.is_file()):
            continue
        df = pd.read_csv(ruta, dtype=str, keep_default_na=False, encoding="utf-8")
        conservar = _columnas_mapeadas(df, ColumnMapping(**dataset.mapping_json))
        if len(conservar) == len(df.columns):
            continue
        df[conservar].to_csv(ruta, index=False, encoding="utf-8")
        dataset.sha256_privado = hashlib.sha256(ruta.read_bytes()).hexdigest()
        session.add(dataset)
    session.flush()
    return int(resultado.rowcount or 0)


def _purgar_fichero_en_bruto(
    dataset: Dataset, df: pd.DataFrame, *, project: Project, mapping: ColumnMapping
) -> None:
    """Sustituye el fichero subido en bruto por una versión privada tras ingerir con éxito.

    Con `project.store_features=false` la versión privada solo lleva las
    columnas mapeadas: ni las variables de entrada ni las no mapeadas.

    `df` es el frame tal como se ingirió, sin transformar (sin
    pseudonimizar, cualquier identificador que trajera el fichero original
    sigue en claro aquí): se vuelca como CSV UTF-8 junto al original en
    `<dataset_id>_<nombre_sin_extension>.privado.csv`, y el original se
    borra. Solo se llama tras `_ingest_crear`/`_ingest_emparejar` ya
    completados sin excepción: si la ingesta se cancela o falla antes, el
    fichero en bruto se conserva (hallazgo de privacidad).
    """
    if dataset.raw_purged or not dataset.file_path:
        return
    ruta_original = Path(dataset.file_path)
    if not ruta_original.is_file():
        return
    ruta_privada = ruta_original.parent / f"{ruta_original.stem}.privado.csv"
    volcado = df if project.store_features else df[_columnas_mapeadas(df, mapping)]
    volcado.to_csv(ruta_privada, index=False, encoding="utf-8")
    dataset.sha256_privado = hashlib.sha256(ruta_privada.read_bytes()).hexdigest()
    ruta_original.unlink()
    dataset.file_path = str(ruta_privada)
    dataset.raw_purged = True


def ensure_ingestible(dataset: Dataset) -> None:
    """409 si el dataset quedó en `error` (su fichero en bruto ya no existe) o si
    ya está `ingerido`: reingerirlo duplicaría el lote o repetiría las
    etiquetas del primer fichero sobre las que llegaron después."""
    if dataset.status == "error":
        raise HTTPException(409, MOTIVO_REINGESTA_BLOQUEADA)
    if dataset.status == "ingerido":
        raise HTTPException(409, MOTIVO_YA_INGERIDO)


def _fallo_de_ingesta(
    session: Session,
    dataset: Dataset,
    exc: BaseException,
    *,
    correlation_id: str | None,
    job: JobContext | None,
    bus: EventBus | None,
) -> None:
    """Cierra una ingesta fallida sin dejar el fichero en bruto en disco.

    Hace rollback de lo escrito a medias, borra el fichero original, deja el
    dataset en `status="error"` con `raw_purged=True` y `file_path` vacío,
    registra `dataset.ingesta_fallida` y hace commit de ese estado; quien llama
    relanza la excepción para que el job quede en error. Un dataset así no se
    puede volver a ingerir (`ensure_ingestible`): hay que subir el fichero otra
    vez. La cancelación (`JobCancelled`) no pasa por aquí: conserva el fichero.
    """
    session.rollback()
    _unlink_dataset_file(dataset)
    dataset.file_path = ""
    dataset.raw_purged = True
    dataset.status = "error"
    session.add(dataset)
    session.flush()
    record_event(
        session,
        actor_kind=ACTOR_MODELO[0],
        actor_id=ACTOR_MODELO[1],
        action="dataset.ingesta_fallida",
        object_type="dataset",
        object_id=dataset.id,
        project_id=dataset.project_id,
        after={"error": texto_error_trabajo(exc, "ingesta"), "raw_purged": True},
        correlation_id=correlation_id,
        job_id=job.job_id if job is not None else None,
        bus=bus,
    )
    session.commit()


FILAS_COMPROBACION_ORDEN = 200
FRACCION_MINIMA_ORDEN = 0.99
TOLERANCIA_SUMA_PROBABILIDADES = 0.02
FRACCION_MAXIMA_SUMA_FUERA = 0.05


def _aviso_orden_de_probabilidades(
    canon: pd.DataFrame, mapping: ColumnMapping, task: TaskSpec
) -> str | None:
    """aviso si la clase de mayor probabilidad no coincide con la
    predicción del fichero en al menos el 99 % de las primeras 200 filas. Es la
    señal de que las columnas de probabilidad van en otro orden que `classes`
    (el fallo silencioso más caro). Es un aviso y no un 422 porque la predicción de
    un fichero puede no ser el argmax (una regla de decisión propia)."""
    nombres = [col_prob(i) for i in range(task.k)]
    if COL_PREDICTION_CLASS not in canon.columns or any(n not in canon.columns for n in nombres):
        return None
    muestra = canon.head(FILAS_COMPROBACION_ORDEN)
    predichas = muestra[COL_PREDICTION_CLASS].astype(str).to_numpy()
    matriz = muestra[nombres].to_numpy(dtype=float)
    if len(muestra) == 0 or not np.isfinite(matriz).all():
        return None
    # las probabilidades de una fila suman 1. Si no, el orden no es lo
    # primero que revisar (una columna de más, probabilidades sin normalizar).
    sumas = matriz.sum(axis=1)
    fuera = float((np.abs(sumas - 1.0) > TOLERANCIA_SUMA_PROBABILIDADES).mean())
    if fuera > FRACCION_MAXIMA_SUMA_FUERA:
        return (
            "Las probabilidades no suman 1: no suman 1 en el "
            f"{fuera:.0%} de las {len(muestra)} primeras filas (suma media "
            f"{float(sumas.mean()):.2f}). Revisa que el mapeo tenga todas las columnas de "
            "probabilidad de las clases y solo esas, y que el modelo las normaliza."
        )
    mayores = np.array(task.claves, dtype=object)[matriz.argmax(axis=1)]
    tasa = float((mayores == predichas).mean())
    if tasa >= FRACCION_MINIMA_ORDEN:
        return None
    columnas = (
        ", ".join(mapping.probability_cols)
        if mapping.probability_cols
        else "la lista de probabilidades"
    )
    return (
        "Las probabilidades no cuadran con la predicción: la clase de mayor probabilidad "
        f"coincide con la predicción en el {tasa:.0%} de las {len(muestra)} primeras filas "
        f"y debería ser casi todas. Si las columnas de probabilidad no van en el orden de "
        f"las clases ({', '.join(task.claves)}), corrige el orden en el mapeo. Orden que "
        f"usa Vigía: {columnas}."
    )


def _ingest_crear(
    session: Session,
    dataset: Dataset,
    df: pd.DataFrame,
    mapping: ColumnMapping,
    *,
    project: Project,
    model_version: ModelVersion,
    phase_label: str | None,
    orden_manipulado: bool,
    motivo_manipulacion: str | None,
    demo_run_id: int | None,
    job: JobContext | None,
    task: TaskSpec | None = None,
) -> tuple[Batch, int, int, str | None]:
    seq_start = _next_record_seq(session, project.id)
    batch_seq = _next_batch_seq(session, project.id)
    tipo = task.task_type if task is not None else "binary"
    # `task=` solo fuera del binario; en binario `to_canonical` se llama
    # como siempre (la regresión también lleva `task=`.
    match tipo:
        case "binary":
            extra_canonico: dict[str, Any] = {}
        case "multiclass" | "regression":
            extra_canonico = {"task": task}
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    canon = to_canonical(
        df,
        mapping,
        batch_seq=batch_seq,
        model_version=model_version.label,
        seq_start=seq_start,
        **extra_canonico,
    )
    aviso_orden: str | None = None
    match tipo:
        case "multiclass":
            aviso_orden = _aviso_orden_de_probabilidades(canon, mapping, task)  # type: ignore[arg-type]
            con_probabilidades = True
        case "binary" | "regression":
            con_probabilidades = False
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")

    # ids que se repiten dentro del propio lote, más los que ya
    # existían en la versión antes de esta ingesta. Aviso, no bloquea.
    n_id_duplicados = contar_ids_duplicados_en_lote(df, mapping.id_col)
    if mapping.id_col:
        ids_lote = [str(v) for v in df[mapping.id_col].dropna().unique()]
        # SQLite limita las variables por consulta (32 766 en este equipo):
        # con lotes grandes un único IN(...) con todo `ids_lote` dispara
        # "too many SQL variables". Se trocea en el mismo `_BLOQUE` que ya
        # usa `_ingest_emparejar` y se suman los `count()` parciales.
        for inicio in range(0, len(ids_lote), _BLOQUE):
            trozo = ids_lote[inicio : inicio + _BLOQUE]
            n_dup_version = session.exec(
                select(func.count())
                .select_from(Record)
                .join(Batch, Batch.id == Record.batch_id)  # type: ignore[arg-type]
                .where(
                    Batch.model_version_id == model_version.id,
                    Record.external_id.in_(trozo),  # type: ignore[attr-defined]
                )
            ).one()
            n_id_duplicados += int(n_dup_version)

    batch = Batch(
        project_id=project.id,
        dataset_id=dataset.id,
        model_version_id=model_version.id,
        seq=batch_seq,
        phase_label=phase_label,
        n_rows=len(canon),
        orden_manipulado=orden_manipulado,
        motivo_manipulacion=motivo_manipulacion,
        demo_run_id=demo_run_id,
        sha256=dataset.sha256,
    )
    session.add(batch)
    session.flush()

    columnas_features = [c for c in canon.columns if not es_columna_canonica(c)]
    n_labeled = 0
    n_total = len(canon)
    try:
        for inicio in range(0, n_total, _BLOQUE):
            if job is not None:
                job.raise_if_cancelled()
            bloque = canon.iloc[inicio : inicio + _BLOQUE]
            for _, fila in bloque.iterrows():
                etiqueta_raw = _valor_o_none(fila, COL_LABEL)
                etiqueta = None if etiqueta_raw is None else float(etiqueta_raw)
                if etiqueta is not None:
                    n_labeled += 1
                features = None
                if project.store_features:
                    features = {c: privacy.to_jsonable(fila[c]) for c in columnas_features}
                session.add(
                    Record(
                        batch_id=batch.id,
                        project_id=project.id,
                        seq=int(fila[COL_SEQ]),
                        external_id=_str_o_none(_valor_o_none(fila, COL_ID)),
                        timestamp=_str_o_none(_valor_o_none(fila, COL_TS)),
                        prediction=int(fila[COL_PREDICTION]),
                        # una regresión no tiene probabilidad; el frame no trae la columna.
                        prob_favorable=_valor_columna(fila, COL_PROB),
                        label=etiqueta,
                        prediction_class=_str_o_none(_valor_columna(fila, COL_PREDICTION_CLASS)),
                        label_class=_str_o_none(_valor_columna(fila, COL_LABEL_CLASS)),
                        probabilities_json=_probabilidades(fila, task) if con_probabilidades else None,
                        prediction_value=_flotante_o_none(_valor_columna(fila, COL_PREDICTION_VALUE)),
                        label_value=_flotante_o_none(_valor_columna(fila, COL_LABEL_VALUE)),
                        protected_value=_str_o_none(_valor_o_none(fila, COL_PROTECTED)),
                        group_code=int(fila[COL_GROUP]),
                        clinician_pseudonym=_str_o_none(_valor_o_none(fila, COL_CLINICIAN)),
                        subgroup=_str_o_none(_valor_o_none(fila, COL_SUBGROUP)),
                        features_json=features,
                    )
                )
            batch.n_labeled = n_labeled
            session.add(batch)
            # Commit intermedio: no mantener el lock de escritor de SQLite abierto
            # durante toda la ingesta, para que `JobManager.cancel()` (que escribe
            # `cancel_requested` con su propia sesión) no choque con él en lotes
            # grandes.
            session.commit()
            if job is not None:
                job.progress(
                    min(1.0, (inicio + len(bloque)) / max(n_total, 1)), "ingiriendo registros"
                )
    except JobCancelled:
        # Compensar el lote parcial ya committeado: no debe quedar un batch a
        # medias visible tras cancelar.
        session.rollback()
        session.exec(sa_delete(Record).where(Record.batch_id == batch.id))  # type: ignore[arg-type]
        session.exec(sa_delete(Batch).where(Batch.id == batch.id))  # type: ignore[arg-type]
        session.commit()
        raise

    return batch, n_labeled, n_id_duplicados, aviso_orden


@dataclass
class _ResultadoEmparejar:
    """Resultado interno de `_ingest_emparejar`: más detallado
    que la tupla `(n_matched, n_unmatched)` de antes."""

    n_matched: int
    n_unmatched: int
    n_ambiguos: int
    n_etiqueta_sin_alias: int
    motivo_sin_id: str | None = None
    clases_desconocidas: list[str] = field(default_factory=list)
    # etiquetas que solo coincidieron con una clase sin distinguir mayúsculas.
    asignadas_sin_mayusculas: list[str] = field(default_factory=list)
    # lotes que recibieron al menos una etiqueta, en orden ascendente.
    lotes_con_verdad: list[int] = field(default_factory=list)
    # etiquetas que no se aplicaron porque la fila es de la línea base
    # congelada o ya tenía etiqueta.
    omitidas_linea_base: int = 0
    omitidas_registradas: int = 0

    @property
    def etiquetas_omitidas(self) -> int:
        return self.omitidas_linea_base + self.omitidas_registradas


MOTIVO_VERSION_SIN_ID = (
    "los lotes de esta versión se subieron sin columna de identificador: "
    "el feedback no se puede emparejar"
)


def _clase_de_etiqueta(valor: Any, task: TaskSpec) -> str | None:
    """Clase de `task.classes` a la que corresponde una etiqueta: igualdad exacta
    por `clave_clase` o, si no, sin mayúsculas y solo si es una única clase.
    `None` si no encaja con ninguna."""
    clave = clave_clase(valor)
    claves = task.claves
    if clave in claves:
        return clave
    coincidencias = [c for c in claves if c.casefold() == clave.casefold()]
    return coincidencias[0] if len(coincidencias) == 1 else None


def _avisos_de_cardinalidad(df: pd.DataFrame, mapping: ColumnMapping, task: TaskSpec) -> list[str]:
    """avisos de cardinalidad por tipo. En binario, el del motor (más de dos
    valores) y, si una columna es numérica con más de 20 valores distintos, en su lugar el
    que remite al tipo regresión. En multiclase y regresión no sale ninguno (el motor
    decide por tipo)."""
    avisos = list(detectar_cardinalidad_binaria(df, mapping, task))
    match task.task_type:
        case "binary":
            pass
        case "multiclass" | "regression":
            return avisos
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task.task_type!r}")
    for columna in (mapping.prediction_col, mapping.label_col):
        if not columna or columna not in df.columns:
            continue
        valores = [v for v in df[columna] if not es_valor_nulo(v)]
        if len(valores) < 2:
            continue
        numeros = pd.to_numeric(pd.Series(valores, dtype=object), errors="coerce")
        if numeros.notna().mean() < 0.9 or numeros.nunique() <= MIN_VALORES_CONTINUOS:
            continue
        avisos = [a for a in avisos if f"la columna {columna} tiene" not in a]
        avisos.append(
            f"La columna {columna} tiene {numeros.nunique()} valores numéricos distintos: parece "
            "la salida de un modelo de regresión, no de una clasificación binaria. Si lo es, "
            "crea un proyecto de regresión; si no, elige la columna correcta en el mapeo"
        )
    return avisos


def _avisos_de_clases(
    df: pd.DataFrame, mapping: ColumnMapping, task: TaskSpec, dataset: Dataset
) -> list[str]:
    """avisos de la ingesta multiclase (etiquetas asignadas sin
    mayúsculas, clases desconocidas en la etiqueta, clase declarada sin filas
    en la línea base). Los redacta el motor (`core.loaders.avisos_clases`)."""
    return list(
        _loaders_core.avisos_clases(df, mapping, task, es_linea_base=dataset.role == "baseline")
    )


def _ingest_emparejar(
    session: Session,
    df: pd.DataFrame,
    mapping: ColumnMapping,
    *,
    project: Project,
    model_version: ModelVersion,
    job: JobContext | None,
    task: TaskSpec | None = None,
) -> _ResultadoEmparejar:
    if not mapping.id_col:
        raise HTTPException(
            422,
            "falta la columna de identificador en el mapeo: elígela en el paso Mapeo para emparejar el feedback",
        )

    # si ningún registro de la versión de destino tiene id (los lotes
    # se ingirieron sin `id_col` en su mapeo), decirlo en vez de devolver un
    # `n_unmatched` igual al total, indistinguible de "no había coincidencias".
    tiene_ids = session.exec(
        select(func.count())
        .select_from(Record)
        .join(Batch, Batch.id == Record.batch_id)  # type: ignore[arg-type]
        .where(Batch.model_version_id == model_version.id, Record.external_id.is_not(None))
    ).one()
    if not tiene_ids:
        return _ResultadoEmparejar(0, len(df), 0, 0, motivo_sin_id=MOTIVO_VERSION_SIN_ID)

    n_matched = 0
    n_unmatched = 0
    n_ambiguos = 0
    n_etiqueta_sin_alias = 0
    clases_desconocidas: list[str] = []
    asignadas_sin_mayusculas: list[str] = []
    lotes_afectados: set[int] = set()
    lotes_con_etiqueta: set[int] = set()
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "binary":
            favorable: int | str | None = mapping.favorable_resuelto
        case "multiclass" | "regression":
            favorable = None
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    # la línea base congelada y las etiquetas ya registradas no se
    # sobrescriben; esas filas se omiten y se cuentan.
    lotes_linea_base = {
        b
        for b in session.exec(
            select(ModelVersion.baseline_batch_id).where(
                ModelVersion.project_id == project.id,
                ModelVersion.baseline_batch_id.is_not(None),  # type: ignore[union-attr]
            )
        ).all()
        if b is not None
    }
    omitidas_linea_base = 0
    omitidas_registradas = 0
    n_total = len(df)
    for inicio in range(0, n_total, _BLOQUE):
        if job is not None:
            job.raise_if_cancelled()
        bloque = df.iloc[inicio : inicio + _BLOQUE]
        # El id sale de su columna, no de la fila: `iterrows` pasa la fila a `float`
        # si las demás columnas son numéricas (una etiqueta continua de regresión) y
        # el id 7151 llegaría como «7151.0», que no empareja.
        ids_bloque = bloque[mapping.id_col].tolist()
        for (_, fila), id_valor in zip(bloque.iterrows(), ids_bloque, strict=True):
            if es_valor_nulo(id_valor):
                n_unmatched += 1
                continue
            # por lote descendente, gana el más reciente; más de un
            # candidato cuenta como ambiguo (se aplica igual al más reciente).
            consulta = (
                select(Record)
                .join(Batch, Batch.id == Record.batch_id)  # type: ignore[arg-type]
                .where(Record.project_id == project.id, Record.external_id == str(id_valor))
            )
            if model_version is not None:
                consulta = consulta.where(Batch.model_version_id == model_version.id)
            consulta = consulta.order_by(Batch.seq.desc())  # type: ignore[union-attr]
            candidatos = session.exec(consulta).all()
            if not candidatos:
                n_unmatched += 1
                continue
            if len(candidatos) > 1:
                n_ambiguos += 1
            registro = candidatos[0]
            if mapping.label_col:
                etiqueta_raw = fila.get(mapping.label_col)
                if not es_valor_nulo(etiqueta_raw):
                    if (
                        registro.label is not None
                        or registro.label_class is not None
                        or registro.label_value is not None
                    ):
                        # La línea base sin etiquetas sí las recibe (payload y feedback
                        # del harness); una etiqueta ya puesta no se pisa nunca. En
                        # regresión sin rango la verdad vive en `label_value` y en
                        # multiclase una clase desconocida deja `label` vacío.
                        if registro.batch_id in lotes_linea_base:
                            omitidas_linea_base += 1
                        else:
                            omitidas_registradas += 1
                        continue
                    match tipo:
                        case "multiclass":
                            # la etiqueta se recorta y se asigna sin mayúsculas a
                            # una sola clase; si no encaja con ninguna, queda el texto
                            # recortado, la etiqueta 0/1 vacía y se cuenta.
                            clase = _clase_de_etiqueta(etiqueta_raw, task)  # type: ignore[arg-type]
                            if clase is None:
                                registro.label_class = clave_clase(etiqueta_raw)
                                registro.label = None
                                n_etiqueta_sin_alias += 1
                                if registro.label_class not in clases_desconocidas:
                                    clases_desconocidas.append(registro.label_class)
                            else:
                                if clave_clase(etiqueta_raw) != clase:
                                    par = f"«{str(etiqueta_raw).strip()}» a {clase}"
                                    if par not in asignadas_sin_mayusculas:
                                        asignadas_sin_mayusculas.append(par)
                                registro.label_class = clase
                                registro.label = 1.0 if task.es_favorable(clase) else 0.0  # type: ignore[union-attr]
                                lotes_con_etiqueta.add(registro.batch_id)
                        case "binary":
                            # también en el emparejamiento de feedback, la
                            # comparación normalizada; sin alias reconocido, la
                            # etiqueta se cuenta y se deja sin tocar (nunca a la
                            # clase no favorable en silencio).
                            resuelto = resolver_favorable(etiqueta_raw, favorable)
                            if resuelto is None:
                                n_etiqueta_sin_alias += 1
                            else:
                                registro.label = 1.0 if resuelto else 0.0
                                lotes_con_etiqueta.add(registro.batch_id)
                        case "regression":
                            # el valor real va a `label_value` y `label` es el
                            # 0/1 de pertenencia al rango del proyecto. Un valor que
                            # no es un número finito se cuenta y no se aplica.
                            valor = _flotante_o_none(_a_numero(etiqueta_raw))
                            if valor is None:
                                n_etiqueta_sin_alias += 1
                            else:
                                registro.label_value = valor
                                registro.label = _etiqueta_de_valor(valor, task)  # type: ignore[arg-type]
                                lotes_con_etiqueta.add(registro.batch_id)
                        case _:
                            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
            session.add(registro)
            n_matched += 1
            lotes_afectados.add(registro.batch_id)
        # Commit intermedio, igual que en `_ingest_crear`: no mantener el lock de
        # escritor de SQLite abierto durante todo el emparejamiento. Aquí el
        # trabajo son actualizaciones sobre `Record` ya existentes (no un lote
        # nuevo), así que cancelar a mitad no se compensa por borrado: las
        # etiquetas ya emparejadas en bloques anteriores quedan aplicadas y el
        # trabajo termina `cancelado` sin reprocesar el resto.
        session.commit()
        if job is not None:
            job.progress(
                min(1.0, (inicio + len(bloque)) / max(n_total, 1)), "emparejando etiquetas"
            )

    for batch_id in lotes_afectados:
        batch = session.get(Batch, batch_id)
        if batch is None:
            continue
        n_etiquetadas = session.exec(
            select(func.count())
            .select_from(Record)
            .where(  # type: ignore[arg-type]
                Record.batch_id == batch_id, Record.label.is_not(None)
            )
        ).one()
        batch.n_labeled = int(n_etiquetadas)
        session.add(batch)

    return _ResultadoEmparejar(
        n_matched,
        n_unmatched,
        n_ambiguos,
        n_etiqueta_sin_alias,
        clases_desconocidas=clases_desconocidas,
        asignadas_sin_mayusculas=asignadas_sin_mayusculas,
        lotes_con_verdad=sorted(lotes_con_etiqueta),
        omitidas_linea_base=omitidas_linea_base,
        omitidas_registradas=omitidas_registradas,
    )


_MAX_AVISOS_NULOS = 5


def _aviso_registro_de_uso(df: pd.DataFrame) -> list[str]:
    """aviso si el fichero tiene las columnas del registro de uso
    (`human_decision` y `model_output`, `docs/api/formatos.md`) y se sube como
    datos del modelo. No bloquea nada."""
    columnas = {str(c).strip().casefold() for c in df.columns}
    if {"human_decision", "model_output"} <= columnas:
        return [
            (
                "este fichero parece un registro de uso (tiene las columnas human_decision y "
                "model_output): súbelo en Capa humana > Registro de uso"
            )
        ]
    return []


def _avisos_nulos_por_variable(df: pd.DataFrame, mapping: ColumnMapping) -> list[str]:
    """un aviso por columna con valores vacíos (cuántos y en cuál). Mira
    predicción, probabilidad, atributo protegido y variables; no la etiqueta,
    donde un lote sin etiquetar es normal. No cambia lo que se guarda."""
    columnas = [
        c
        for c in (mapping.prediction_col, mapping.probability_col, mapping.protected_attr_col)
        if c
    ] + list(mapping.feature_cols)
    vistas: set[str] = set()
    avisos: list[str] = []
    n_filas = len(df)
    sin_avisar = 0
    for columna in columnas:
        if columna in vistas or columna not in df.columns:
            continue
        vistas.add(columna)
        n_nulos = int(df[columna].isna().sum())
        if not n_nulos:
            continue
        if len(avisos) >= _MAX_AVISOS_NULOS:
            sin_avisar += 1
            continue
        pct = f"{100 * n_nulos / max(n_filas, 1):.1f}".replace(".", ",")
        avisos.append(
            f"la columna {columna} tiene {n_nulos} valores vacíos de {n_filas} filas ({pct} %): "
            "revisa el fichero de origen y corrige los errores; Vigía calcula con las filas "
            "que tienen valor"
        )
    if sin_avisar:
        avisos.append(f"otras {sin_avisar} columnas más también tienen valores vacíos")
    return avisos


def _avisos_grupos_ausentes(df: pd.DataFrame, mapping: ColumnMapping) -> list[str]:
    """T2.9 (fila 16): aviso por cada grupo del atributo protegido del mapeo que
    no aparece en el lote (un grupo sin filas deja la equidad sin datos). No
    cambia lo que se guarda ni el cálculo."""
    columna = mapping.protected_attr_col
    if not columna or columna not in df.columns:
        return []
    serie = df[columna].dropna()
    avisos: list[str] = []
    categorico = mapping.protected_kind == ProtectedKind.categorical
    valores = set(serie.astype(str)) if categorico else None
    numeros = None if categorico else pd.to_numeric(serie, errors="coerce").dropna()
    for nombre, grupos in (
        ("no privilegiado", mapping.unpriv_groups),
        ("privilegiado", mapping.priv_groups),
    ):
        for grupo in grupos:
            if categorico:
                presente = str(grupo) in (valores or set())
                etiqueta = str(grupo)
            else:
                try:
                    lo, hi = float(grupo[0]), float(grupo[1])
                except (TypeError, ValueError, IndexError):
                    continue
                presente = bool(((numeros >= lo) & (numeros <= hi)).any())
                etiqueta = alerting._formato_rango(lo, hi)
            if not presente:
                avisos.append(
                    f"el grupo «{etiqueta}» del atributo protegido ({nombre}) no aparece en este "
                    f"lote: revisa los valores del grupo en el mapeo y la columna {columna}"
                )
    return avisos


def ingest_dataset(
    session: Session,
    dataset: Dataset,
    *,
    model_version: ModelVersion,
    phase_label: str | None = None,
    orden_manipulado: bool = False,
    motivo_manipulacion: str | None = None,
    mode: str | None = None,
    demo_run_id: int | None = None,
    congelar_automatico: bool = True,
    job: JobContext | None = None,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
    actor: Actor | None = None,
) -> IngestResult:
    """Aplica el mapeo del dataset e inserta lote y registros (o empareja feedback).

    Sin pseudonimización: `df` se usa tal como llega, `external_id`
    guarda el id de mapeo sin hashear.

    Cancelable entre bloques de 1000 filas: si `job.cancelled`, hace rollback
    del lote entero (no queda un batch a medias) y conserva el fichero subido.
    Cualquier otro fallo sí borra el fichero en bruto y deja el dataset en
    `error` (`_fallo_de_ingesta`): no hay reintento sin volver a subirlo.
    """
    if dataset.mapping_json is None:
        raise HTTPException(
            422, "los datos no tienen mapeo: guarda el mapeo en el paso Mapeo antes de ingerir"
        )
    ensure_ingestible(dataset)

    project = session.get(Project, dataset.project_id)
    if project is None:
        raise no_encontrado("modelo", dataset.project_id, "modelos")

    # Quien pidió la ingesta; sin él (demo, laboratorio) consta el motor como antes.
    quien = actor or Actor(kind=ACTOR_MODELO[0], id=ACTOR_MODELO[1])

    try:
        mapping = _completar_clases(project, ColumnMapping(**dataset.mapping_json))
        df, _dialecto = load_dataframe(Path(dataset.file_path), dataset.format, mapping)
        aplicado: dict[str, str] = {}
        # El mapeo resuelto se valida por tipo y da el
        # `TaskSpec` que va al motor. Un fallo sale como error del trabajo.
        task = tarea_service.tarea_del_proyecto(project, mapping)

        # aviso de cardinalidad (predicción y/o etiqueta con más de dos
        # valores distintos); no cambia nada de lo que se guarda. En multiclase
        # no sale.
        avisos: list[str] = _avisos_de_cardinalidad(df, mapping, task)
        # un registro de uso subido como datos del modelo.
        avisos.extend(_aviso_registro_de_uso(df))

        modo = mode or ("emparejar" if dataset.kind == "feedback" else "crear")

        if modo == "crear":
            avisos.extend(_avisos_nulos_por_variable(df, mapping))
            avisos.extend(_avisos_grupos_ausentes(df, mapping))
            if mapping.timestamp_col and mapping.timestamp_col in df.columns:
                avisos.extend(
                    aviso_fechas_ilegibles(df[mapping.timestamp_col], mapping.timestamp_col)
                )
            match task.task_type:
                case "multiclass":
                    avisos.extend(_avisos_de_clases(df, mapping, task, dataset))
                case "regression":
                    # el aviso de alias y el de cardinalidad binaria no
                    # salen en regresión; sí los suyos (etiquetas de texto, constante).
                    avisos.extend(_loaders_core.avisos_regresion(df, mapping, task))
                case "binary":
                    if mapping.label_col:
                        n_etiqueta_sin_alias = contar_sin_alias_reconocido(
                            df[mapping.label_col], mapping.favorable_resuelto
                        )
                        if n_etiqueta_sin_alias:
                            avisos.append(
                                f"{n_etiqueta_sin_alias} filas tienen una etiqueta que no coincide con "
                                "la clase favorable ni sus alias: se guardan sin etiqueta"
                            )
                case _:
                    raise ValueError(f"tipo de tarea no reconocido: {task.task_type!r}")
            batch, n_labeled, n_id_duplicados, aviso_orden = _ingest_crear(
                session,
                dataset,
                df,
                mapping,
                project=project,
                model_version=model_version,
                phase_label=phase_label,
                orden_manipulado=orden_manipulado,
                motivo_manipulacion=motivo_manipulacion,
                demo_run_id=demo_run_id,
                job=job,
                task=task,
            )
            if aviso_orden:
                avisos.append(aviso_orden)
            if n_id_duplicados:
                avisos.append(
                    f"{n_id_duplicados} filas de este lote tienen un identificador que ya "
                    "existía (dentro del propio lote o ya ingerido antes para la misma versión): "
                    "revisa la columna de identificador del fichero"
                )
            _purgar_fichero_en_bruto(dataset, df, project=project, mapping=mapping)
            dataset.status = "ingerido"
            session.add(dataset)
            session.flush()
            # la línea base se congela sola al ingerirla, en
            # la misma transacción; con la versión ya congelada solo se avisa.
            congelada = False
            if dataset.role == "baseline" and congelar_automatico:
                if model_version.frozen_at is None:
                    projects_service.freeze_baseline(
                        session,
                        model_version,
                        batch,
                        actor=Actor(kind=ACTOR_SISTEMA[0], id=ACTOR_SISTEMA[1]),
                        motivo="congelado automático al ingerir la línea base",
                        automatico=True,
                        commit=False,
                        correlation_id=correlation_id,
                        job_id=job.job_id if job is not None else None,
                        bus=bus,
                    )
                    congelada = True
                else:
                    avisos.append(
                        "la versión ya tiene una línea base congelada: este dataset se ingiere "
                        "como lote, pero la línea base congelada no cambia"
                    )
            record_event(
                session,
                actor_kind=quien.kind,
                actor_id=quien.id,
                role=quien.role,
                action="batch.ingerido",
                object_type="batch",
                object_id=batch.id,
                project_id=project.id,
                after={
                    "n_rows": batch.n_rows,
                    "n_labeled": n_labeled,
                    "orden_manipulado": orden_manipulado,
                    "motivo_manipulacion": motivo_manipulacion,
                    "raw_purged": dataset.raw_purged,
                    "n_id_duplicados": n_id_duplicados,
                },
                correlation_id=correlation_id,
                job_id=job.job_id if job is not None else None,
                bus=bus,
            )
            # deja un mensaje final distinto del último "ingiriendo
            # registros" del bucle. Antes del commit para que quede en la
            # misma transacción (`JobContext.progress` solo hace `flush`).
            if job is not None:
                job.progress(1.0, "lote ingerido")
            session.commit()
            return IngestResult(
                batch_id=batch.id,
                n_rows=batch.n_rows,
                n_labeled=n_labeled,
                n_matched=0,
                n_unmatched=0,
                privacy_applied=aplicado,
                avisos=avisos,
                n_id_duplicados=n_id_duplicados,
                linea_base_congelada=congelada,
            )

        resultado_emparejar = _ingest_emparejar(
            session, df, mapping, project=project, model_version=model_version, job=job, task=task
        )
        if resultado_emparejar.motivo_sin_id:
            avisos.append(resultado_emparejar.motivo_sin_id)
        if resultado_emparejar.n_unmatched and not resultado_emparejar.motivo_sin_id:
            avisos.append(
                f"{resultado_emparejar.n_unmatched} etiquetas no tienen pareja en ningún lote: "
                "revisa que la columna de identificador coincide con la del lote"
            )
        if resultado_emparejar.n_ambiguos:
            avisos.append(
                f"{resultado_emparejar.n_ambiguos} filas de feedback tenían más de un registro "
                "candidato: se aplicaron al del lote más reciente"
            )
        if resultado_emparejar.omitidas_linea_base:
            avisos.append(
                f"{resultado_emparejar.omitidas_linea_base} etiquetas son de filas de la línea base "
                "congelada que ya tenían etiqueta: no se aplicaron, porque la línea base no se "
                "corrige. Si necesitas otra, crea una versión nueva del modelo"
            )
        if resultado_emparejar.omitidas_registradas:
            avisos.append(
                f"{resultado_emparejar.omitidas_registradas} etiquetas son de filas que ya tenían "
                "etiqueta: no se aplicaron, porque una etiqueta registrada no se sobrescribe"
            )
        if resultado_emparejar.asignadas_sin_mayusculas:
            avisos.append(
                "Hay etiquetas de feedback que se asignaron a una clase sin distinguir "
                "mayúsculas: "
                f"{', '.join(resultado_emparejar.asignadas_sin_mayusculas[:5])}. Revisa que sean "
                "las clases que querías"
            )
        if resultado_emparejar.n_etiqueta_sin_alias:
            match task.task_type:
                case "multiclass":
                    avisos.append(
                        f"{resultado_emparejar.n_etiqueta_sin_alias} filas de feedback tienen una "
                        "etiqueta con una clase que no está entre las del proyecto "
                        f"({', '.join(str(c) for c in task.classes)}): "
                        f"{', '.join(resultado_emparejar.clases_desconocidas[:5])}. Se guardan sin "
                        "etiqueta y quedan fuera de la calidad"
                    )
                case "binary":
                    avisos.append(
                        f"{resultado_emparejar.n_etiqueta_sin_alias} filas de feedback tienen una "
                        "etiqueta que no coincide con la clase favorable ni sus alias: no se aplicaron"
                    )
                case "regression":
                    avisos.append(
                        f"{resultado_emparejar.n_etiqueta_sin_alias} filas de feedback no traen un "
                        "número en la etiqueta (texto o infinito): no se aplicaron. Si lleva la "
                        "unidad pegada («12 h»), quítala y vuelve a subir el fichero"
                    )
                case _:
                    raise ValueError(f"tipo de tarea no reconocido: {task.task_type!r}")
        _purgar_fichero_en_bruto(dataset, df, project=project, mapping=mapping)
        dataset.status = "ingerido"
        session.add(dataset)
        session.flush()
        record_event(
            session,
            actor_kind=quien.kind,
            actor_id=quien.id,
            role=quien.role,
            action="feedback.emparejado",
            object_type="dataset",
            object_id=dataset.id,
            project_id=project.id,
            after={
                "n_matched": resultado_emparejar.n_matched,
                "n_unmatched": resultado_emparejar.n_unmatched,
                "n_ambiguos": resultado_emparejar.n_ambiguos,
                "etiquetas_omitidas": resultado_emparejar.etiquetas_omitidas,
                "raw_purged": dataset.raw_purged,
            },
            correlation_id=correlation_id,
            job_id=job.job_id if job is not None else None,
            bus=bus,
        )
        if job is not None:
            job.progress(1.0, "etiquetas emparejadas")
        session.commit()
        return IngestResult(
            batch_id=None,
            n_rows=len(df),
            n_labeled=resultado_emparejar.n_matched,
            n_matched=resultado_emparejar.n_matched,
            n_unmatched=resultado_emparejar.n_unmatched,
            privacy_applied=aplicado,
            avisos=avisos,
            n_ambiguos=resultado_emparejar.n_ambiguos,
            lotes_con_verdad=resultado_emparejar.lotes_con_verdad,
            etiquetas_omitidas=resultado_emparejar.etiquetas_omitidas,
        )
    except JobCancelled:
        session.rollback()
        raise
    except Exception as exc:  # se relanza tras dejar el estado en firme
        _fallo_de_ingesta(session, dataset, exc, correlation_id=correlation_id, job=job, bus=bus)
        raise


# ---------------------------------------------------------------------------
# Borrado
# ---------------------------------------------------------------------------


def _unlink_dataset_file(dataset: Dataset) -> None:
    if not dataset.file_path:
        return
    try:
        Path(dataset.file_path).unlink(missing_ok=True)
    except OSError:
        pass


def delete_batch(
    session: Session, batch: Batch, *, actor: Actor, motivo: str, bus: EventBus | None = None
) -> None:
    """Borra un lote y lo que cuelga de él. 409 si es el baseline congelado de una versión."""
    es_baseline = session.exec(
        select(ModelVersion).where(ModelVersion.baseline_batch_id == batch.id)
    ).first()
    if es_baseline is not None:
        raise HTTPException(
            409,
            "este lote es la línea base congelada de una versión y no se puede borrar: "
            "crea una versión nueva si necesitas otra línea base",
        )

    batch_id = batch.id
    project_id = batch.project_id
    evaluation_ids = {
        e for e in session.exec(select(Evaluation.id).where(Evaluation.batch_id == batch_id)).all()
    }
    retiradas = alerting.retire_alerts_for_batch(
        session,
        project_id=project_id,
        batch_id=batch_id,
        batch_seq=batch.seq,
        evaluation_ids=evaluation_ids,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        bus=bus,
    )
    session.exec(sa_delete(Record).where(Record.batch_id == batch_id))  # type: ignore[arg-type]
    session.exec(sa_delete(UsageLog).where(UsageLog.batch_id == batch_id))  # type: ignore[arg-type]
    session.exec(sa_delete(Explanation).where(Explanation.batch_id == batch_id))  # type: ignore[arg-type]
    session.exec(sa_delete(Evaluation).where(Evaluation.batch_id == batch_id))  # type: ignore[arg-type]
    session.delete(batch)
    session.flush()

    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="batch.borrado",
        object_type="batch",
        object_id=batch_id,
        project_id=project_id,
        motivo=motivo,
        after={"alertas_retiradas": retiradas},
        bus=bus,
    )
    session.commit()


def delete_dataset(
    session: Session, dataset: Dataset, *, actor: Actor, bus: EventBus | None = None
) -> None:
    """Borra un dataset subido. 409 si tiene lotes ingeridos (bórralos primero)."""
    tiene_batches = session.exec(select(Batch).where(Batch.dataset_id == dataset.id)).first()
    if tiene_batches is not None:
        raise HTTPException(
            409,
            "estos datos ya tienen lotes ingeridos: borra primero esos lotes desde la lista de lotes",
        )

    _unlink_dataset_file(dataset)
    dataset_id = dataset.id
    project_id = dataset.project_id
    # Las filas del diario de uso de este fichero se van con él.
    session.exec(sa_delete(UsageLog).where(UsageLog.dataset_id == dataset_id))  # type: ignore[arg-type]
    session.delete(dataset)
    session.flush()
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="dataset.borrado",
        object_type="dataset",
        object_id=dataset_id,
        project_id=project_id,
        bus=bus,
    )
    session.commit()
