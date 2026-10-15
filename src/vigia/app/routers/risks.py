"""Router de riesgos. matriz de riesgos por proyecto."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from vigia.app.db import get_session
from vigia.app.errores import no_encontrado
from vigia.app.events import Actor, get_actor, get_correlation_id
from vigia.app.models import Project, Risk
from vigia.app.schemas.risks import (
    RiskCloseBody,
    RiskCreateBody,
    RiskMoveBody,
    RiskMovementsListResponse,
    RiskOut,
    RisksListResponse,
    RiskStatusBody,
)
from vigia.app.services import risks as risks_service
from vigia.app.services import risks_data

router = APIRouter(tags=["riesgos"])


def _get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise no_encontrado("modelo", project_id, "modelos")
    return project


def _get_risk(session: Session, risk_id: int) -> Risk:
    risk = session.get(Risk, risk_id)
    if risk is None:
        raise no_encontrado("riesgo", risk_id, "riesgos")
    return risk


@router.get("/projects/{project_id}/risks", response_model=RisksListResponse)
def list_risks(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    status: str | None = None,
    impact: int | None = None,
    probability: int | None = None,
    offset: int = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Riesgos del proyecto para la matriz 5x5 (agregada en el frontend)."""
    project = _get_project(session, project_id)
    filas, total = risks_data.list_risks(
        session,
        project,
        status=status,
        impact=impact,
        probability=probability,
        offset=offset,
        limit=limit,
    )
    return {
        "items": [risks_data.risk_to_dict(session, r) for r in filas],
        "total": total,
    }


@router.get("/risks/{risk_id}", response_model=RiskOut)
def read_risk(risk_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Un riesgo por id, para el panel lateral (ya no depende de la lista sin filtrar)."""
    riesgo = _get_risk(session, risk_id)
    return risks_data.risk_to_dict(session, riesgo)


def _actor_final(actor: Actor, body: RiskCreateBody | RiskMoveBody | RiskStatusBody | RiskCloseBody) -> Actor:
    """Combina el `actor_kind` de la cabecera con el actor nominal y el rol
    del cuerpo (mismo patrón que `patch_monitor`, `routers/monitors.py`)."""
    return Actor(kind=actor.kind, id=body.actor, role=body.role or actor.role)


@router.post("/projects/{project_id}/risks", response_model=RiskOut)
def create_risk(
    project_id: int,
    body: RiskCreateBody,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Alta de un riesgo: desde una alerta o a mano (exactamente una vía)."""
    project = _get_project(session, project_id)
    riesgo = risks_service.create_risk(
        session, project, body, actor=_actor_final(actor, body), correlation_id=correlation_id
    )
    return risks_data.risk_to_dict(session, riesgo)


@router.patch("/risks/{risk_id}/move", response_model=RiskOut)
def move_risk(
    risk_id: int,
    body: RiskMoveBody,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Mueve un riesgo a otra celda de la matriz."""
    riesgo = _get_risk(session, risk_id)
    riesgo = risks_service.move_risk(
        session, riesgo, body, actor=_actor_final(actor, body), correlation_id=correlation_id
    )
    return risks_data.risk_to_dict(session, riesgo)


@router.patch("/risks/{risk_id}/status", response_model=RiskOut)
def set_risk_status(
    risk_id: int,
    body: RiskStatusBody,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Solo admite el paso de `abierto` a `en_seguimiento`."""
    riesgo = _get_risk(session, risk_id)
    riesgo = risks_service.set_status(
        session, riesgo, body, actor=_actor_final(actor, body), correlation_id=correlation_id
    )
    return risks_data.risk_to_dict(session, riesgo)


@router.post("/risks/{risk_id}/close", response_model=RiskOut)
def close_risk(
    risk_id: int,
    body: RiskCloseBody,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Cierra un riesgo (terminal en v1)."""
    riesgo = _get_risk(session, risk_id)
    riesgo = risks_service.close_risk(
        session, riesgo, body, actor=_actor_final(actor, body), correlation_id=correlation_id
    )
    return risks_data.risk_to_dict(session, riesgo)


@router.get("/risks/{risk_id}/movements", response_model=RiskMovementsListResponse)
def read_risk_movements(
    risk_id: int, session: Annotated[Session, Depends(get_session)]
) -> dict:
    """Historial completo de un riesgo, orden `created_at` asc."""
    riesgo = _get_risk(session, risk_id)
    items = risks_data.movements_for_risk(session, riesgo)
    return {"items": items, "total": len(items)}


@router.get(
    "/projects/{project_id}/risks/movements", response_model=RiskMovementsListResponse
)
def read_project_risk_movements(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    days: int = 7,
) -> dict:
    """«Movimiento · N días»: `RiskMovement` del proyecto en la ventana."""
    project = _get_project(session, project_id)
    items = risks_data.movements_for_project(session, project, days=days)
    return {"items": items, "total": len(items)}
