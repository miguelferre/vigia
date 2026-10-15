"""Router de outcomes. resultados del sistema combinado."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlmodel import Session

from vigia.app.db import get_session
from vigia.app.events import Actor, get_actor, get_correlation_id
from vigia.app.schemas.outcomes import (
    OutcomeRow,
    OutcomeSeriePunto,
    OutcomesListResponse,
    OutcomeUploadResponse,
)
from vigia.app.services import outcomes as outcomes_service
from vigia.app.services import projects as projects_service
from vigia.app.services.subidas import leer_subida

router = APIRouter(tags=["capa-humana"])


@router.post("/projects/{project_id}/outcomes", response_model=OutcomeUploadResponse)
def upload_outcomes(
    project_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    file: Annotated[UploadFile, File()],
) -> OutcomeUploadResponse:
    """Sube el CSV de outcomes, hace upsert por `(period, metric_key, source)`."""
    project = projects_service.get_project(session, project_id)
    contenido = leer_subida(file.file)
    n_rows, n_creados, n_actualizados = outcomes_service.ingest_outcomes(
        session,
        project,
        file_bytes=contenido,
        actor=actor,
        bus=request.app.state.bus,
        correlation_id=correlation_id,
    )
    return OutcomeUploadResponse(
        dataset_id=None, n_rows=n_rows, n_creados=n_creados, n_actualizados=n_actualizados
    )


@router.get("/projects/{project_id}/outcomes", response_model=OutcomesListResponse)
def get_outcomes(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    metric_key: str | None = None,
) -> OutcomesListResponse:
    """Tabla y serie de outcomes; `baseline`/`target` siempre `null`."""
    project = projects_service.get_project(session, project_id)
    filas, series = outcomes_service.list_outcomes(session, project, metric_key=metric_key)
    return OutcomesListResponse(
        rows=[
            OutcomeRow(
                period=f.period,
                metric_key=f.metric_key,
                value=f.value,
                baseline=f.baseline,
                target=f.target,
                source=f.source,
            )
            for f in filas
        ],
        series={
            clave: [
                OutcomeSeriePunto(period=f.period, value=f.value, baseline=f.baseline, target=f.target)
                for f in puntos
            ]
            for clave, puntos in series.items()
        },
    )
