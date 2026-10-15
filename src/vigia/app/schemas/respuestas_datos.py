"""Respuestas de datasets, lotes, registros y composición.

Serializadores de origen: `services/ingest.py` (`dataset_to_dict`,
`batch_to_dict`, `record_to_dict`, `batch_composition`), `services/privacy.py`
(`privacy_report`, `mask_preview`) y el router `routers/datasets.py`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from vigia.app.schemas.respuestas_base import (
    DatasetKind,
    DatasetRole,
    DatasetStatus,
    Respuesta,
)
from vigia.core.schema import ProtectedKind

__all__ = [
    "Batch",
    "BatchComposition",
    "ColumnMappingOut",
    "CompositionRow",
    "CompositionTotal",
    "Dataset",
    "DatasetColumn",
    "DatasetDialect",
    "DatasetUpload",
    "PrivacyReport",
    "Record",
]


class DatasetColumn(Respuesta):
    """Columna del fichero subido. `sample` va enmascarado si privacidad la marca."""

    name: str
    dtype: str
    n_null: int
    sample: Any = None


class DatasetDialect(Respuesta):
    """Dialecto de un CSV detectado en la subida: codificación
    (`utf-8-sig` o `cp1252`), separador (`,`, `;` o `\\t`) y decimal (`,` o
    `.`). `None` para el resto de formatos. Solo viaja en `DatasetUpload`;
    `Dataset` no lo persiste todavía."""

    encoding: str
    separator: str
    decimal: str


class PrivacyReport(Respuesta):
    """Informe de privacidad de un dataset: Vigía no pseudonimiza,
    no detecta columnas identificadoras ni exige decisiones. `aplicado` es
    siempre `false`; `motivo` referencia la decisión (`services/privacy.empty_report`).
    """

    aplicado: bool
    motivo: str


class ColumnMappingOut(Respuesta):
    """Mapeo de columnas tal como se devuelve (mismos campos que `core.schema.ColumnMapping`).

    Modelo aparte del cuerpo de petición `ColumnMapping` porque el sugerido puede
    llevar `protected_attr_col` con los grupos aún vacíos, que el validador del
    cuerpo rechaza: una respuesta nunca debe fallar por eso. Los enumerados sí son
    los mismos que en el cuerpo (`probability_format` y `protected_kind`): los
    valores siempre salen de `core.schema.ColumnMapping` o del mapeo sugerido de
    `services/ingest._suggest_mapping`, así que el frontend no tiene que estrecharlos.
    """

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
    favorable_label: int | str | list[int | str] | None = None
    # Clases declaradas y una columna de probabilidad por clase.
    classes: list[int | str] = Field(default_factory=list)
    probability_cols: list[str] = Field(default_factory=list)
    # Unidad de la salida y rango favorable de una regresión.
    target_unit: str | None = None
    favorable_ranges: list[tuple[float | None, float | None]] = Field(default_factory=list)


class Dataset(Respuesta):
    """Dataset subido o generado. `file_path` nunca sale: solo el nombre y los hashes.

    `columns` es la lista de columnas con tipo y muestra en los ficheros de datos,
    y la lista de nombres a secas en el diario de uso (`services/human_layer.py`).
    """

    id: int | None
    project_id: int
    name: str
    source: str
    kind: DatasetKind
    role: DatasetRole
    format: str
    sha256: str
    sha256_privado: str | None
    raw_purged: bool
    n_rows: int
    columns: list[DatasetColumn] | list[str] | None
    mapping: ColumnMappingOut | None
    suggested_mapping: ColumnMappingOut | None
    # Solo en el registro de uso, qué valor del fichero se
    # declaró como decisión favorable (vive en `mapping_json`, no es un mapeo).
    valor_favorable: Literal["refer", "no-refer", "1", "0"] | None = None
    # Dialecto del CSV detectado al subir; nulo en JSON.
    dialect: DatasetDialect | None
    status: DatasetStatus
    created_at: str
    privacy_report: PrivacyReport | None
    privacy_decisions: dict[str, str] | None
    # Lotes ingeridos de este dataset: con alguno, borrarlo da 409 (bórralos primero).
    n_batches: int = 0


class DatasetUpload(Respuesta):
    """Respuesta de `POST /projects/{id}/datasets/upload`: nada en claro sin decidir."""

    dataset: Dataset
    preview: list[dict[str, Any]]
    privacy_report: PrivacyReport | None
    suggested_mapping: ColumnMappingOut | None
    dialect: DatasetDialect | None


class Batch(Respuesta):
    """Lote ingerido: unidad de evaluación y de orden dentro del proyecto."""

    id: int | None
    project_id: int
    dataset_id: int | None
    model_version_id: int
    seq: int
    phase_label: str | None
    n_rows: int
    n_labeled: int
    orden_manipulado: bool
    motivo_manipulacion: str | None
    demo_run_id: int | None
    created_at: str
    # Nombre del dataset de origen (fichero subido); nulo si el lote no lo tiene.
    dataset_name: str | None = None


class Record(Respuesta):
    """Fila canónica de un lote. `external_id` es el valor original del id de
    mapeo, sin transformar (Vigía no pseudonimiza).

    `features` solo viaja con `?with_features=true`; `group_label` sale del mapeo
    del dataset origen y es `null` si el lote no tiene mapeo.
    """

    id: int | None
    batch_id: int
    seq: int
    external_id: str | None
    timestamp: str | None
    prediction: int
    prob_favorable: float | None
    label: float | None
    # Clase predicha y clase real (texto) y las `k` probabilidades en el
    # orden de las clases del proyecto; nulos en binario y en las filas de antes.
    prediction_class: str | None = None
    label_class: str | None = None
    probabilities: list[float] | None = None
    # Valor continuo de la predicción y de la etiqueta en una regresión, en
    # la unidad del proyecto; `prediction` y `label` son entonces el 0/1 de pertenencia
    # al rango favorable. Nulos en clasificación.
    prediction_value: float | None = None
    label_value: float | None = None
    protected_value: str | None
    group_code: int
    group_label: str | None
    clinician_pseudonym: str | None
    subgroup: str | None
    features: dict[str, Any] | None = None


class CompositionRow(Respuesta):
    """Un grupo protegido dentro de la composición del lote.

    `pred_favorable_n`/`label_favorable_n` son
    los recuentos de los que salen las tasas correspondientes:
    `pred_favorable_n / n == pred_favorable_rate` y
    `label_favorable_n / n_labeled == label_favorable_rate`. `label_favorable_n`
    es `None` si el grupo no tiene ningún registro etiquetado (`n_labeled == 0`),
    igual que su tasa.
    """

    group_code: int
    group_label: str | None
    n: int
    pred_favorable_n: int | None
    pred_favorable_rate: float | None
    label_favorable_n: int | None
    label_favorable_rate: float | None
    n_labeled: int


class CompositionTotal(Respuesta):
    """Fila de totales de la composición: la misma sin `group_code` ni `group_label`."""

    n: int
    pred_favorable_rate: float | None
    label_favorable_rate: float | None
    n_labeled: int


class BatchComposition(Respuesta):
    """Composición por grupo del lote (`GET /batches/{id}/composition`)."""

    groups: list[CompositionRow]
    total: CompositionTotal
    # En una regresión sin rango favorable, por qué las tasas son nulas.
    motivo: str | None = None
