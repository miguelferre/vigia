"""Router de dossiers: las seis rutas del dossier.

`POST/GET /projects/{id}/dossiers`, `GET /dossiers/{id}`,
`POST /dossiers/{id}/reviews`, `GET /reviews/{id}`, `GET /reviews/{id}/report`.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from sqlmodel import Session

from vigia.app.db import get_session
from vigia.app.errores import no_encontrado
from vigia.app.events import Actor, get_actor, get_correlation_id
from vigia.app.models import Dossier, DossierReview, Project
from vigia.app.schemas import dossiers as dsch
from vigia.app.schemas import respuestas as resp
from vigia.app.schemas.dossiers import (
    RUTA_DOSSIER_IMPORT,
    DossierCreateBody,
    DossierImportBody,
    DossierReviewCreateBody,
)
from vigia.app.services import dossiers as dossiers_service
from vigia.app.services import dossiers_review
from vigia.human.dossier_import import traducir_errores

# Los modelos de respuesta del dossier se referencian directamente desde
# `schemas/dossiers.py`, no vía `resp.*`.

router = APIRouter(tags=["auditoria"])


class _RutaValidacionEs(APIRoute):
    """Ruta cuyo 422 de validación del cuerpo sale en español y con el campo
    que falla, en el formato `{"detail": "texto"}` de la API."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def manejador(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                raise HTTPException(422, traducir_errores(exc.errors())) from exc

        return manejador


router_import = APIRouter(tags=["auditoria"], route_class=_RutaValidacionEs)


def _get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise no_encontrado("modelo", project_id, "modelos")
    return project


def _get_dossier(session: Session, dossier_id: int) -> Dossier:
    fila = session.get(Dossier, dossier_id)
    if fila is None:
        raise no_encontrado("dossier", dossier_id, "dossiers")
    return fila


def _get_review(session: Session, review_id: int) -> DossierReview:
    fila = session.get(DossierReview, review_id)
    if fila is None:
        raise no_encontrado("revisión", review_id, "revisiones")
    return fila


@router.post("/projects/{project_id}/dossiers", response_model=dsch.Dossier)
def create_dossier(
    project_id: int,
    body: DossierCreateBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    project = _get_project(session, project_id)
    return dossiers_service.create_dossier(
        session, project, body, actor=actor, correlation_id=correlation_id, bus=request.app.state.bus
    )


@router_import.post(RUTA_DOSSIER_IMPORT, response_model=dsch.Dossier)
def import_dossier(
    project_id: int,
    body: DossierImportBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Importa el `dossier.json` de `interaction_review`."""
    project = _get_project(session, project_id)
    return dossiers_service.import_dossier(
        session, project, body, actor=actor, correlation_id=correlation_id, bus=request.app.state.bus
    )


@router.get("/projects/{project_id}/dossiers", response_model=resp.ListResponse[dsch.Dossier])
def list_dossiers(project_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    project = _get_project(session, project_id)
    return dossiers_service.list_dossiers(session, project).model_dump()


@router.get("/dossiers/{dossier_id}", response_model=dsch.DossierConReviews)
def read_dossier(dossier_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    _get_dossier(session, dossier_id)
    return dossiers_service.get_dossier(session, dossier_id)


@router.post("/dossiers/{dossier_id}/reviews", response_model=resp.JobResumen)
def create_review(
    dossier_id: int,
    body: DossierReviewCreateBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    dossier = _get_dossier(session, dossier_id)
    return dossiers_review.launch_review(
        session,
        dossier,
        body,
        actor=actor,
        correlation_id=correlation_id,
        bus=request.app.state.bus,
        jobs=request.app.state.jobs,
    )


@router.get("/reviews/{review_id}", response_model=dsch.DossierReviewDetalle)
def read_review(review_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    fila = _get_review(session, review_id)
    return {
        "id": fila.id,
        "dossier_id": fila.dossier_id,
        "approach": fila.approach,
        "status": fila.status,
        "findings": fila.findings_json or [],
        "crosswalk": fila.crosswalk_json or {},
        "package_version": fila.package_version,
        "corpus_hash": fila.corpus_hash,
        "dossier_sha256": fila.dossier_sha256,
        "prompt_sha256": fila.prompt_sha256,
        "llm_backend": fila.llm_backend,
        "model": fila.model,
        "error": fila.error,
        "created_at": fila.created_at,
        "finished_at": fila.finished_at,
    }


# El informe es HTML dibujado con texto del dossier: se sirve sin scripts, sin
# recursos externos y en un contexto aislado, también al abrirlo en pestaña nueva.
CSP_INFORME = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"


@router.get("/reviews/{review_id}/report", response_class=HTMLResponse)
def read_review_report(
    review_id: int,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    modo: Literal["auto", "claro", "oscuro"] = "auto",
) -> str:
    """Sirve el informe para un `<iframe sandbox>`, redibujado al leer
    en español; `modo` fija claro u oscuro porque el iframe no hereda
    el tema de la app. 409 si la revisión no ha terminado."""
    fila = _get_review(session, review_id)
    if fila.status != "terminada" or not fila.report_html:
        raise HTTPException(
            409, "la revisión aún no tiene informe: espera a que termine o lánzala otra vez"
        )
    response.headers["Content-Security-Policy"] = CSP_INFORME
    response.headers["X-Content-Type-Options"] = "nosniff"
    return dossiers_service.informe_html(session, fila, modo=modo)


router.include_router(router_import)
