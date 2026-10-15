"""Esquemas de alertas, acciones y protocolo."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from vigia.app.schemas.common import (
    MAX_ACTOR,
    MAX_ACTOR_DETALLE,
    MAX_MOTIVO,
    ActorBody,
    NombreActor,
    TextoLargo,
    TextoMotivo,
    no_blanco,
    recordar_actor_detalle,
)

__all__ = [
    "AlertActionBody",
    "AlertDecideBody",
    "AlertDecisionAction",
    "AlertInvestigateBody",
    "AlertsBulkBody",
    "ProtocolBody",
]


class AlertActionBody(BaseModel):
    """Cuerpo de `POST /alerts/{id}/actions`."""

    action: str = Field(min_length=1)
    actor: NombreActor
    role: str | None = Field(default=None, max_length=MAX_ACTOR)
    motivo: TextoMotivo
    attachment_path: str | None = Field(default=None, max_length=500)
    # Ver `ActorBody.actor_detalle`.
    actor_detalle: str | None = Field(default=None, max_length=MAX_ACTOR_DETALLE)

    _actor_no_blanco = field_validator("actor")(no_blanco)
    _motivo_no_blanco = field_validator("motivo")(no_blanco)

    @model_validator(mode="after")
    def _recordar_actor_detalle(self) -> AlertActionBody:
        recordar_actor_detalle(self.actor, self.actor_detalle)
        return self


class AlertInvestigateBody(ActorBody):
    """Cuerpo de `POST /alerts/{id}/investigate`: hito 3 del
    protocolo, no cambia `status`."""

    hallazgos: TextoLargo

    _hallazgos_no_blanco = field_validator("hallazgos")(no_blanco)


class AlertDecisionAction(BaseModel):
    """Una acción del catálogo de acciones elegida al decidir: `notes`
    es el motivo propio de esa acción, o el motivo general si no se da."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=MAX_MOTIVO)


class AlertDecideBody(ActorBody):
    """Cuerpo de `POST /alerts/{id}/decide`: hito 4 del
    protocolo, al menos una acción del catálogo; no cambia `status`."""

    acciones: list[AlertDecisionAction] = Field(min_length=1)


class AlertsBulkBody(BaseModel):
    """Cuerpo de `POST /projects/{id}/alerts/bulk`: mismo motivo y
    mismo `correlation_id` para todas las alertas del lote."""

    model_config = ConfigDict(extra="forbid")

    alert_ids: list[int] = Field(min_length=1)
    action: str = Field(min_length=1)
    actor: NombreActor
    role: str | None = Field(default=None, max_length=MAX_ACTOR)
    motivo: TextoMotivo

    _actor_no_blanco = field_validator("actor")(no_blanco)
    _motivo_no_blanco = field_validator("motivo")(no_blanco)


class ProtocolBody(BaseModel):
    """Cuerpo de `PUT /alerts/{id}/protocol`."""

    actor: NombreActor
    role: str | None = Field(default=None, max_length=MAX_ACTOR)
    motivo: TextoMotivo
    protocolo_md: TextoLargo

    _actor_no_blanco = field_validator("actor")(no_blanco)
    _motivo_no_blanco = field_validator("motivo")(no_blanco)
