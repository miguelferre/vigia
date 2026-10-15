"""Comparación de versiones de modelo.

Router propio para no inflar `routers/projects.py`: crear, activar y congelar
versiones siguen allí.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from vigia.app.db import get_session
from vigia.app.errores import no_encontrado
from vigia.app.models import Project
from vigia.app.schemas import respuestas as resp
from vigia.app.schemas.versiones import VentanaComparacion
from vigia.app.services import comparacion_versiones

router = APIRouter(tags=["proyectos"])


@router.get("/projects/{project_id}/versions/compare", response_model=resp.ComparacionVersiones)
def compare_versions(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    a: Annotated[int | None, Query(description="Versión de referencia; por defecto, la activa anterior")] = None,
    b: Annotated[int | None, Query(description="Versión comparada; por defecto, la activa")] = None,
    ventana: VentanaComparacion = "ultimo",
) -> dict:
    """Compara dos versiones del modelo, cada una contra su propia línea base.

    Para cada monitor, métrica y grupo con umbral devuelve el valor de cada
    versión, la diferencia y si la versión `b` mejora, empeora o queda igual.
    Las alertas vivas del proyecto van aparte, con la versión que las movió.
    """
    project = session.get(Project, project_id)
    if project is None:
        raise no_encontrado("modelo", project_id, "modelos")
    return comparacion_versiones.comparar_versiones(session, project, a=a, b=b, ventana=ventana)
