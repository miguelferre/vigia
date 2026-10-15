"""Actor de la petición y escritura del diario de eventos.

El diario tiene tres carriles visibles (`humano`, `agente`, `modelo`) más el
carril técnico `sistema`. El `actor_kind` viene de la cabecera
`X-Vigia-Actor-Kind`; el `actor_id` nominal, de la cabecera `X-Vigia-Actor` o
del cuerpo de la mutación cuando esta exige actor y motivo.
"""

from __future__ import annotations

import hmac
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from vigia.app.bus import EventBus
from vigia.app.db import get_session
from vigia.app.events_titulos import titulo_evento
from vigia.app.models import Event, now_iso
from vigia.app.schemas.common import MAX_ACTOR
from vigia.core import CORE_VERSION

__all__ = [
    "ACTOR_KINDS_PETICION",
    "ACTOR_MODELO",
    "ACTOR_SISTEMA",
    "Actor",
    "event_to_dict",
    "fijar_actor_detalle",
    "get_actor",
    "get_correlation_id",
    "record_event",
]

CABECERA_ACTOR_KIND = "X-Vigia-Actor-Kind"
CABECERA_ACTOR = "X-Vigia-Actor"
CABECERA_ROL = "X-Vigia-Role"
CABECERA_CORRELACION = "X-Vigia-Correlation"

ACTOR_KINDS_PETICION = ("humano", "agente")

# Actores no humanos: el motor y la propia aplicación.
ACTOR_MODELO = ("modelo", f"vigia.core {CORE_VERSION}")
ACTOR_SISTEMA = ("sistema", "vigia.app")


# `actor_detalle` del cuerpo de la petición en curso, con el actor al que
# pertenece. Lo fija el validador de `ActorBody` y lo lee `record_event`.
_ACTOR_DETALLE: ContextVar[tuple[str, str] | None] = ContextVar("vigia_actor_detalle", default=None)


def fijar_actor_detalle(actor: str, detalle: str | None) -> None:
    """Recuerda el `actor_detalle` de la petición actual; `None` lo borra."""
    _ACTOR_DETALLE.set((actor, detalle) if detalle else None)


@dataclass(frozen=True)
class Actor:
    """Quién hace la petición: carril, nombre nominal y rol declarado."""

    kind: str = "humano"
    id: str = "anonimo"
    role: str | None = None


CABECERA_TOKEN = "X-Vigia-Token"


def get_actor(request: Request, session: Annotated[Session, Depends(get_session)]) -> Actor:
    """Dependencia de FastAPI: construye el `Actor` desde las cabeceras `X-Vigia-*`.

    Con `actor_kind=agente` exige `X-Vigia-Token` válido contra
    `ensure_mcp_token(session)`: es la única puerta de un servidor MCP externo,
    que nunca abre la base de datos directamente. `actor_kind=humano` no cambia.
    """
    kind = request.headers.get(CABECERA_ACTOR_KIND) or "humano"
    if kind not in ACTOR_KINDS_PETICION:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{CABECERA_ACTOR_KIND} debe ser "
                f"{' o '.join(ACTOR_KINDS_PETICION)}; se recibió {kind!r}"
            ),
        )
    if kind == "agente":
        from vigia.app.services.settings import ensure_mcp_token

        token = request.headers.get(CABECERA_TOKEN)
        if not token or not hmac.compare_digest(
            token.encode("utf-8"), ensure_mcp_token(session).encode("utf-8")
        ):
            raise HTTPException(
                status_code=401,
                detail=f"{CABECERA_TOKEN} inválido o ausente para actor_kind=agente",
            )
    actor_id = request.headers.get(CABECERA_ACTOR) or "anonimo"
    role = request.headers.get(CABECERA_ROL) or None
    # El nombre y el rol van al diario, que es de solo añadir; con tope.
    for cabecera, valor in ((CABECERA_ACTOR, actor_id), (CABECERA_ROL, role)):
        if valor is not None and len(valor) > MAX_ACTOR:
            raise HTTPException(
                status_code=422,
                detail=f"{cabecera} no puede pasar de {MAX_ACTOR} caracteres",
            )
    return Actor(kind=kind, id=actor_id, role=role)


def get_correlation_id(request: Request) -> str:
    """Dependencia de FastAPI: correlación de la petición (cabecera o una nueva)."""
    return request.headers.get(CABECERA_CORRELACION) or str(uuid.uuid4())


def event_to_dict(evento: Event) -> dict[str, Any]:
    """Serializa un evento a dict JSON, con el mismo nombre de campos que la API."""
    return {
        "id": evento.id,
        "ts": evento.ts,
        "actor_kind": evento.actor_kind,
        "actor_id": evento.actor_id,
        "role": evento.role,
        "action": evento.action,
        "titulo": titulo_evento(evento),
        "object_type": evento.object_type,
        "object_id": evento.object_id,
        "project_id": evento.project_id,
        "before": evento.before_json,
        "after": evento.after_json,
        "motivo": evento.motivo,
        "correlation_id": evento.correlation_id,
        "job_id": evento.job_id,
    }


def record_event(
    session: Session,
    *,
    actor_kind: str,
    actor_id: str,
    action: str,
    object_type: str,
    object_id: int | None = None,
    project_id: int | None = None,
    before: Any | None = None,
    after: Any | None = None,
    motivo: str | None = None,
    role: str | None = None,
    correlation_id: str | None = None,
    job_id: int | None = None,
    bus: EventBus | None = None,
) -> Event:
    """Inserta una fila en el diario, hace `flush` y la publica en el bus si se pasa.

    No hace `commit`: el llamador decide la transacción. El `flush` garantiza que
    el evento ya tiene `id` cuando se publica.

    Si la petición trae `actor_detalle`, se añade a `after` en los eventos
    de ese mismo actor y carril humano o agente; el nombre del diario no cambia.
    """
    pendiente = _ACTOR_DETALLE.get()
    if (
        pendiente is not None
        and actor_kind in ACTOR_KINDS_PETICION
        and actor_id == pendiente[0]
        and (after is None or isinstance(after, dict))
    ):
        after = {**(after or {}), "actor_detalle": pendiente[1]}
    evento = Event(
        ts=now_iso(),
        actor_kind=actor_kind,
        actor_id=actor_id,
        role=role,
        action=action,
        object_type=object_type,
        object_id=object_id,
        project_id=project_id,
        before_json=before,
        after_json=after,
        motivo=motivo,
        correlation_id=correlation_id,
        job_id=job_id,
    )
    session.add(evento)
    session.flush()
    if bus is not None:
        bus.publish({"type": "event", "event": event_to_dict(evento)})
    return evento
