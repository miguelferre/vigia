"""Respuestas de alertas, acciones y catálogo.

Serializadores de origen: `services/alerting.py` (`alert_to_dict`, `catalog`,
historial de `history_json`) y el router `routers/alerts.py` (las acciones).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from vigia.app.schemas.respuestas_base import (
    AlertSeverity,
    AlertStage,
    AlertStatus,
    MonitorType,
    ProtocolStepStatus,
    Respuesta,
)

__all__ = [
    "Alert",
    "AlertAction",
    "AlertBulkSkipped",
    "AlertCatalogItem",
    "AlertDetail",
    "AlertHistoryEntry",
    "AlertsBulkResult",
    "ProtocolStep",
]


class AlertHistoryEntry(Respuesta):
    """Transición del historial de una alerta: quién la movió, desde dónde y por qué.

    `hito` y `detalle` son del protocolo por hitos: las entradas
    escritas antes de esta sesión no las traen, así que llevan `None` por
    defecto (el modelo es `extra="forbid"`, pero un campo ausente con valor
    por defecto no rompe la validación de una entrada antigua)."""

    ts: str
    from_: AlertStatus | None = Field(alias="from")
    to: AlertStatus
    evaluation_id: int | None
    value: float | None
    actor: str
    # Las entradas nuevas traen `actor_kind`
    # (`services/alerting.py`), para que el historial no tenga que adivinar el
    # carril por el prefijo del actor; las de antes de este cambio no lo
    # traen, `None` por defecto (mismo patrón que `hito`/`detalle`).
    actor_kind: Literal["humano", "agente", "modelo", "sistema"] | None = None
    motivo: str | None
    hito: Literal["deteccion", "triaje", "investigacion", "decision"] | None = None
    detalle: str | None = None
    # lote de la evaluación citada (entradas nuevas). Si ese lote
    # se borró, `evaluacion_borrada` y `batch_seq` (entradas marcadas al borrar).
    batch_id: int | None = None
    batch_seq: int | None = None
    evaluacion_borrada: bool = False


class Alert(Respuesta):
    """Alerta abierta por el motor. Nunca se cierra sola."""

    id: int | None
    project_id: int
    monitor_type: MonitorType
    metric_key: str
    group_code: str | None
    severity: AlertSeverity
    status: AlertStatus
    # Etiqueta de estado = último hito hecho; no confundir con
    # `status`, que son los cuatro valores internos del motor.
    stage: AlertStage
    title: str
    opened_at: str
    updated_at: str
    closed_at: str | None
    last_evaluation_id: int | None
    last_value: float | None
    observation_count: int
    reopen_count: int
    protocolo_md: str
    history: list[AlertHistoryEntry] | None
    # H1c: derivados de `last_evaluation_id` -> `Evaluation.batch_id` -> `Batch`;
    # los tres `None` sin evaluación (o con una evaluación sin lote, como las
    # cruzadas). Columna «Lote» y gráfico por lote.
    batch_id: int | None
    batch_seq: int | None
    batch_phase_label: str | None
    # lote con el que se abrió la alerta, fijado al abrir
    # (`Alert.origin_batch_id`); `batch_*` sigue siendo el de la última
    # evaluación. Con el lote borrado, `origin_batch_id` conserva el id y
    # `origin_batch_seq` y `origin_phase_label` salen `None`.
    origin_batch_id: int | None
    origin_batch_seq: int | None
    origin_phase_label: str | None
    # motivo de la retirada («lote N borrado»); solo con `status="retirada"`.
    retired_reason: str | None


class AlertAction(Respuesta):
    """Acción humana sobre una alerta: siempre con actor y motivo."""

    id: int | None
    action: str
    actor: str
    role: str | None
    motivo: str
    attachment_path: str | None
    ts: str


class ProtocolStep(Respuesta):
    """Hito del protocolo por alerta (los textos del
    protocolo del monitor, editable por `PATCH /monitors/{id}`): cinco pasos
    derivados del historial, con el título, la descripción, los entregables,
    el responsable y el plazo del protocolo de su monitor; `target_date`
    sigue siempre `None` hasta que existan."""

    # `str`, no `ProtocolStepKey`: la lista trae también los hitos
    # extra del monitor (`status="informativo"`), con clave libre.
    key: str
    status: ProtocolStepStatus
    target_date: str | None
    titulo: str
    descripcion: str
    entregables: list[str]
    responsable: str | None
    plazo_dias: int | None


class AlertDetail(Alert):
    """Alerta con su historial de acciones y sus hitos de protocolo (`GET /alerts/{id}`)."""

    actions: list[AlertAction]
    protocol_steps: list[ProtocolStep]


class AlertCatalogItem(Respuesta):
    """Entrada de `GET /alerts/catalog`: acción del catálogo de acciones y su etiqueta."""

    action: str
    label: str


class AlertBulkSkipped(Respuesta):
    """Alerta saltada en `POST /projects/{id}/alerts/bulk`: no rompe el lote."""

    alert_id: int
    reason: str


class AlertsBulkResult(Respuesta):
    """Resultado de la acción en lote sobre alertas."""

    applied: int
    skipped: list[AlertBulkSkipped]
