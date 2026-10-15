"""Respuestas de evaluaciones, medidas, series y explicabilidad.

Serializadores de origen: `routers/evaluations.py` (`evaluation_to_dict`, con la
poda de `result` del hueco 3), `services/evaluate.py` (`timeline`) y
`services/explain.py` (`explanation_to_dict`).
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from vigia.app.schemas.respuestas_base import (
    EstadoMotor,
    ExplanationKind,
    MonitorType,
    Respuesta,
)

__all__ = [
    "Evaluation",
    "EvaluationDetail",
    "Explanation",
    "ExplanationFeatureResumen",
    "ExplanationRankingDelta",
    "ExplanationSummary",
    "Measurement",
    "TimelinePoint",
]


class Measurement(Respuesta):
    """Medida individual de una evaluación (fila de `EvaluationResult.measurements`)."""

    metric_key: str
    value: float | None
    interval_low: float | None
    interval_high: float | None
    threshold_low: float | None
    threshold_high: float | None
    state: EstadoMotor
    group_code: str | None
    motivo: str | None
    extra: dict[str, Any] | None


class Evaluation(Respuesta):
    """Evaluación en forma ligera (`GET /projects/{id}/evaluations`): sin `result`."""

    id: int | None
    monitor_id: int
    monitor_type: MonitorType | None
    project_id: int
    model_version_id: int
    batch_id: int | None
    trigger: str
    window: dict[str, Any] | None
    app_version: str
    core_version: str
    status: str
    worst_state: EstadoMotor | None
    job_id: int | None
    created_at: str


class EvaluationDetail(Evaluation):
    """Evaluación completa (`GET /evaluations/{id}`): la ligera más medidas y `result`.

    `result` viene podado de `measurements`, `window` y `config_snapshot`, que la
    respuesta ya sirve en la raíz.
    """

    config_snapshot: dict[str, Any] | None
    result: dict[str, Any] | None
    measurements: list[Measurement]


class TimelinePoint(Respuesta):
    """Punto de la serie temporal de una o varias medidas (`GET /projects/{id}/timeline`).

    `metric_key` y `group_code` identifican de qué medida es el punto: con
    varias `metric_key` (o varios `group_code`) en la petición, la respuesta
    sigue siendo una única lista plana y el frontend agrupa por estas claves.
    """

    evaluation_id: int | None
    # Versión de la evaluación: marca el cambio de versión en la serie.
    model_version_id: int
    batch_id: int | None
    batch_seq: int | None
    ts: str
    value: float | None
    interval_low: float | None
    interval_high: float | None
    threshold_low: float | None
    threshold_high: float | None
    state: EstadoMotor
    metric_key: str
    group_code: str | None


class ExplanationFeatureResumen(Respuesta):
    """Una característica del ranking de importancia (`GET /projects/{id}/explanations/summary`)."""

    feature: str
    importance: float


class ExplanationRankingDelta(Respuesta):
    """Cambio de puesto de una variable entre la explicación de referencia y
    la actual, recortado al top 10 de cada una
    (mismo `p` que `explain_stability_ndcg`). `from_`/`to` son el
    puesto (1 = la más importante) en la referencia/actual respectivamente;
    `None` cuando la variable no entra en ese top 10 (entra o sale del
    ranking). Solo se listan las variables cuyo puesto difiere entre las dos.
    """

    feature: str
    from_: int | None = Field(alias="from")
    to: int | None


class ExplanationSummary(Respuesta):
    """Resumen de explicabilidad para la tarjeta del cuadro de mando.

    Todo el resumen es sobre la versión activa del proyecto
    (`project.active_version_id`); nunca mezcla versiones distintas del
    modelo. `top_features`: las tres características más importantes de la
    última explicación global disponible de esa versión (vacío si no hay
    ninguna, o si no hay versión activa). `stability` y `stability_state`:
    valor y estado de la última medida `explain_stability_ndcg` cuya
    evaluación pertenece a la versión activa. `ranking_changed_at`: fecha de
    la última explicación de la versión activa cuyo ranking de las tres
    primeras difiere del de la anterior (`None` si no hay al menos dos
    explicaciones, o si nunca ha cambiado). `n_explanations`: total de
    explicaciones globales disponibles de la versión activa; con menos de
    dos, `stability` es `None` y `stability_state` es `sin_datos` aunque
    exista una medida (se compararía consigo misma).

    `reference_top_features`/`ranking_delta`: comparan la última
    explicación con su explicación de referencia, la MISMA que usa
    `explain_stability_ndcg` para calcular `stability`
    (`_explain_reference_for_version`: la primera explicación global
    disponible de la versión activa) para que la tarjeta no cuente dos
    historias distintas. `reference_top_features` es el top 10 de esa
    referencia; `None` sin referencia (una única explicación, o ninguna).
    `ranking_delta` recoge las variables cuyo puesto cambia entre ese top 10
    y el top 10 de la explicación actual; `[]` sin referencia o si ninguna
    cambia de puesto.
    """

    top_features: list[ExplanationFeatureResumen]
    stability: float | None
    stability_state: EstadoMotor | None
    ranking_changed_at: str | None
    n_explanations: int
    reference_top_features: list[ExplanationFeatureResumen] | None
    ranking_delta: list[ExplanationRankingDelta]


class Explanation(Respuesta):
    """Resultado de explicabilidad. `available=False` cuando no se pudo calcular."""

    id: int | None
    project_id: int
    model_version_id: int
    batch_id: int | None
    kind: ExplanationKind
    row_seq: int | None
    params: dict[str, Any] | None
    result: dict[str, Any] | None
    available: bool
    motivo: str | None
    job_id: int | None
    created_at: str
    # aviso si el modelo es un pickle subido antes de la corrección de tipos.
    aviso_tipos: str | None = None
