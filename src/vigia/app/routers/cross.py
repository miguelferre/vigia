"""Router de cross estado del monitor cruzado.

`GET /projects/{id}/cross/latest`, mismo patrón que
`GET /projects/{id}/explanations/summary`: la tarjeta de
cruzadas del cuadro lo consume, no `StatesByMonitor` (`cross` no tiene lote).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from vigia.app.db import get_session
from vigia.app.schemas.cross import CrossLatestOut
from vigia.app.services import human_layer
from vigia.app.services import projects as projects_service

router = APIRouter(tags=["capa-humana"])


@router.get("/projects/{project_id}/cross/latest", response_model=CrossLatestOut)
def cross_latest(
    project_id: int, session: Annotated[Session, Depends(get_session)]
) -> dict:
    """Última evaluación del monitor `cross` del proyecto, con sus reglas (§6.3)."""
    project = projects_service.get_project(session, project_id)
    return human_layer.cross_latest(session, project)
