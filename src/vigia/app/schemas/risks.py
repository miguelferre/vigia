"""Esquemas de la matriz de riesgos."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from vigia.app.schemas.common import MAX_DESCRIPCION, MAX_NOMBRE, ActorBody, no_blanco
from vigia.app.schemas.respuestas_base import Respuesta

__all__ = [
    "RiskCloseBody",
    "RiskCreateBody",
    "RiskLevel",
    "RiskMoveBody",
    "RiskMovementKind",
    "RiskMovementTexto",
    "RiskMovementsListResponse",
    "RiskOut",
    "RiskStatus",
    "RiskStatusBody",
    "RisksListResponse",
]

type RiskLevel = Literal["bajo", "medio", "alto", "critico"]
type RiskStatus = Literal["abierto", "en_seguimiento", "cerrado"]
type RiskMovementKind = Literal["alta", "celda", "estado", "cierre"]


class RiskCreateBody(ActorBody):
    """Cuerpo de `POST /projects/{id}/risks`. Exactamente una vía de origen:
    con `origin_alert_id`, `impact_level`/`probability_level` son opcionales
    (sustituyen a la propuesta si vienen); sin él, son obligatorios."""

    model_config = ConfigDict(extra="forbid")

    origin_alert_id: int | None = None
    impact_level: int | None = Field(default=None, ge=1, le=5)
    probability_level: int | None = Field(default=None, ge=1, le=5)
    title: str = Field(min_length=1, max_length=MAX_NOMBRE)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPCION)

    _title_no_blanco = field_validator("title")(no_blanco)


class RiskMoveBody(ActorBody):
    """Cuerpo de `PATCH /risks/{id}/move`: los dos niveles obligatorios."""

    model_config = ConfigDict(extra="forbid")

    impact_level: int = Field(ge=1, le=5)
    probability_level: int = Field(ge=1, le=5)


class RiskStatusBody(ActorBody):
    """Cuerpo de `PATCH /risks/{id}/status`: solo `abierto -> en_seguimiento`."""

    model_config = ConfigDict(extra="forbid")

    status: RiskStatus


class RiskCloseBody(ActorBody):
    """Cuerpo de `POST /risks/{id}/close`."""

    model_config = ConfigDict(extra="forbid")


class RiskOut(Respuesta):
    """Un riesgo serializado."""

    id: int
    project_id: int
    code: str
    impact_level: int
    probability_level: int
    impact_label: str
    probability_label: str
    level: RiskLevel
    title: str
    description: str | None
    origin_alert_id: int | None
    origin_alert_title: str | None
    monitor_type: str | None
    status: RiskStatus
    created_at: str
    updated_at: str


class RiskMovementTexto(Respuesta):
    """Una fila de `GET /projects/{id}/risks/movements`: el texto compuesto
    más el código y el tipo de movimiento, para el panel «Movimiento · N días»."""

    id: int
    risk_id: int
    code: str
    kind: RiskMovementKind
    texto: str
    actor: str
    role: str | None
    motivo: str
    created_at: str
    from_impact: int | None
    from_probability: int | None
    to_impact: int | None
    to_probability: int | None
    from_status: RiskStatus | None
    to_status: RiskStatus | None


class RisksListResponse(Respuesta):
    """Respuesta de `GET /projects/{id}/risks`."""

    items: list[RiskOut]
    total: int


class RiskMovementsListResponse(Respuesta):
    """Respuesta de `GET /risks/{id}/movements` y `GET /projects/{id}/risks/movements`."""

    items: list[RiskMovementTexto]
    total: int
