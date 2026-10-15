"""Configuración de monitores."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from vigia.app.db import get_session
from vigia.app.events import Actor, get_actor, get_correlation_id
from vigia.app.schemas import respuestas as resp
from vigia.app.schemas.monitors import MonitorPatch
from vigia.app.services import monitors as monitors_service
from vigia.app.services.projects import get_project, monitor_to_dict

router = APIRouter(tags=["monitores"])


def _bus(request: Request):
    return request.app.state.bus


@router.get("/projects/{project_id}/monitors", response_model=resp.ListResponse[resp.Monitor])
def list_monitors(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    offset: int = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Monitores de un proyecto, paginados."""
    filas = monitors_service.list_monitors(session, project_id)
    pagina = filas[offset : offset + limit]
    return {"items": [monitor_to_dict(m, session) for m in pagina], "total": len(filas)}


@router.get("/projects/{project_id}/thresholds/proposal", response_model=resp.ThresholdsProposal)
def propose_thresholds(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    tamano_lote: Annotated[int, Query(ge=1, le=100_000)] = 1000,
) -> dict:
    """Propuesta de umbral de equidad y calidad sobre la línea base de la
    versión activa; 409 si no hay línea base congelada."""
    project = get_project(session, project_id)
    return monitors_service.propose_thresholds(session, project, tamano_lote=tamano_lote)


@router.get("/monitors/{monitor_id}", response_model=resp.Monitor)
def read_monitor(monitor_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Un monitor por id."""
    monitor = monitors_service.get_monitor(session, monitor_id)
    return monitor_to_dict(monitor, session)


@router.patch("/monitors/{monitor_id}", response_model=resp.MonitorPatchResult)
def patch_monitor(
    monitor_id: int,
    body: MonitorPatch,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Cambia configuración, umbrales, activación, protocolo por hitos o notas de un monitor."""
    monitor = monitors_service.get_monitor(session, monitor_id)
    actor_final = Actor(kind=actor.kind, id=body.actor, role=body.role or actor.role)
    protocol = (
        [hito.model_dump() for hito in body.protocol] if body.protocol is not None else None
    )
    monitor, event_id = monitors_service.patch_monitor(
        session,
        monitor,
        actor=actor_final,
        role=body.role or actor.role,
        motivo=body.motivo,
        enabled=body.enabled,
        config=body.config,
        thresholds=body.thresholds,
        protocolo_md=body.protocolo_md,
        protocol=protocol,
        laboratorio=body.laboratorio,
        correlation_id=correlation_id,
        bus=_bus(request),
    )
    return {"monitor": monitor_to_dict(monitor, session), "event_id": event_id}
