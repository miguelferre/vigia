"""Proyectos, versiones de modelo y estado."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session, select

from vigia.app.db import get_session
from vigia.app.errores import no_encontrado
from vigia.app.events import Actor, get_actor, get_correlation_id
from vigia.app.models import Batch, Project
from vigia.app.schemas import respuestas as resp
from vigia.app.schemas.projects import (
    ActivateVersionBody,
    BaselineBody,
    ProjectCreate,
    ProjectPatch,
    ProjectResetBody,
    VersionCreate,
)
from vigia.app.services import projects as projects_service
from vigia.app.services import tarea as tarea_service

router = APIRouter(tags=["proyectos"])


def _bus(request: Request):
    return request.app.state.bus


def _get_batch(session: Session, batch_id: int) -> Batch:
    batch = session.get(Batch, batch_id)
    if batch is None:
        raise no_encontrado("lote", batch_id, "lotes")
    return batch


@router.get("/projects", response_model=resp.ListResponse[resp.ProjectListItem])
def list_projects(
    session: Annotated[Session, Depends(get_session)],
    offset: int = 0,
    limit: Annotated[int, Query(le=500)] = 50,
    summary: bool = False,
) -> dict:
    """Lista de proyectos, paginada. `summary=true` añade el resumen de la
    rejilla de `/modelos`: una consulta agrupada, no una por fila."""
    total = len(session.exec(select(Project)).all())
    filas = session.exec(
        select(Project).order_by(Project.id).offset(offset).limit(limit)  # type: ignore[arg-type]
    ).all()
    items = [projects_service.project_to_dict(p) for p in filas]
    if summary:
        resumenes = projects_service.projects_summary(session, list(filas))
        for item, proyecto in zip(items, filas, strict=True):
            item["summary"] = resumenes.get(proyecto.id)
    return {"items": items, "total": total}


@router.post("/projects", response_model=resp.ProjectDetail)
def create_project(
    body: ProjectCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Crea un proyecto con su versión `v1` activa y sus cinco monitores por defecto.

    El método del intervalo de equidad de la v1 es "lote" salvo
    que el cuerpo diga otra cosa; el servicio conserva "ventanas" por defecto
    para la demo y las llamadas internas, así que aquí se resuelve el valor
    antes de llamarlo.
    """
    # Una regresión no tiene clase favorable (lo favorable va en `favorable_ranges`).
    # El `1` es el valor de compatibilidad que manda el MCP y el defecto de siempre.
    match body.task_type:
        case "regression":
            if body.favorable_label not in (None, 1):
                raise HTTPException(
                    422,
                    "Un modelo de regresión no tiene clase favorable: quita favorable_label del "
                    "cuerpo. Lo favorable, si lo hay, va en favorable_ranges.",
                )
        case "binary" | "multiclass":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {body.task_type!r}")
    project = projects_service.create_project(
        session,
        name=body.name,
        domain=body.domain,
        # `favorable_label` es opcional; sin él, el `1` de compatibilidad de la
        # columna (en regresión no se usa y `GET` lo devuelve nulo).
        favorable_label=body.favorable_label if body.favorable_label is not None else 1,
        store_features=body.store_features,
        model_kind=body.model_kind,
        deployment_stage=body.deployment_stage,
        mapping_template=body.mapping_template,
        acepta_feedback=body.acepta_feedback,
        # "lote" para los modelos del usuario; el modelo del simulador
        # (`sim_logistic`) sigue en "ventanas", como la demo y los números de referencia.
        fairness_interval_method=body.fairness_interval_method
        or ("ventanas" if body.model_kind == "sim_logistic" else "lote"),
        task_type=body.task_type,
        classes=body.classes or None,
        target_unit=body.target_unit,
        favorable_ranges=body.favorable_ranges or None,
        actor=actor,
        bus=_bus(request),
        correlation_id=correlation_id,
    )
    return projects_service.project_detail(session, project)


@router.get("/projects/{project_id}", response_model=resp.ProjectDetail)
def read_project(project_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Proyecto con sus versiones, monitores y recuentos."""
    project = projects_service.get_project(session, project_id)
    return projects_service.project_detail(session, project)


@router.patch("/projects/{project_id}", response_model=resp.ProjectDetail)
def patch_project(
    project_id: int,
    body: ProjectPatch,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Cambia nombre, calibración o `store_features` de un proyecto."""
    project = projects_service.get_project(session, project_id)
    actor_final = Actor(kind=actor.kind, id=body.actor, role=body.role or actor.role)
    if body.positive_label_descartado is not None:
        tarea_service.registrar_positive_label_entrante(
            session, project, body.positive_label_descartado, bus=_bus(request)
        )
    projects_service.update_project(
        session,
        project,
        actor=actor_final,
        motivo=body.motivo,
        name=body.name,
        description=body.description,
        clear_description=body.clear_description,
        calibration_until=body.calibration_until,
        clear_calibration=body.clear_calibration,
        store_features=body.store_features,
        explain_auto=body.explain_auto,
        explain_method=body.explain_method,
        deployment_stage=body.deployment_stage,
        mapping_template=body.mapping_template,
        acepta_feedback=body.acepta_feedback,
        task_type=body.task_type,
        bus=_bus(request),
    )
    return projects_service.project_detail(session, project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    confirm: bool = False,
) -> None:
    """Borra el proyecto y todo lo que cuelga de él. Exige `?confirm=true`."""
    if not confirm:
        raise HTTPException(400, "hace falta ?confirm=true para borrar un proyecto")
    project = projects_service.get_project(session, project_id)
    projects_service.delete_project(
        session,
        project,
        actor=actor,
        bus=_bus(request),
        data_dir=request.app.state.settings.data_dir,
    )


@router.post("/projects/{project_id}/reset", response_model=resp.ProjectResetResult)
def reset_project(
    project_id: int,
    body: ProjectResetBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Deja el proyecto virgen: conserva proyecto, versiones y monitores."""
    if not body.confirm:
        raise HTTPException(400, "confirm debe ser true para reiniciar el proyecto")
    project = projects_service.get_project(session, project_id)
    actor_final = Actor(kind=actor.kind, id=body.actor, role=body.role or actor.role)
    counts = projects_service.reset_project(
        session,
        project,
        actor=actor_final,
        motivo=body.motivo,
        bus=_bus(request),
        data_dir=request.app.state.settings.data_dir,
    )
    return {"project_id": project.id, "deleted": counts}


@router.get("/projects/{project_id}/state", response_model=resp.ProjectState)
def read_project_state(project_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Estado operativo del proyecto: versiones, monitores, alertas abiertas y jobs."""
    project = projects_service.get_project(session, project_id)
    return projects_service.project_state(session, project)


@router.post("/projects/{project_id}/versions", response_model=resp.ModelVersion)
def create_version(
    project_id: int,
    body: VersionCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Crea una nueva versión de modelo dentro del proyecto."""
    project = projects_service.get_project(session, project_id)
    actor_final = Actor(kind=actor.kind, id=body.actor, role=body.role or actor.role)
    version = projects_service.create_version(
        session,
        project,
        label=body.label,
        model_kind=body.model_kind,
        fairness_window_n=body.fairness_window_n,
        fairness_interval_method=body.fairness_interval_method,
        actor=actor_final,
        motivo=body.motivo,
        bus=_bus(request),
    )
    return projects_service.version_to_dict(version)


@router.post("/model-versions/{version_id}/activate", response_model=resp.ModelVersion)
def activate_version(
    version_id: int,
    body: ActivateVersionBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Activa una versión de modelo del proyecto; `congelar_linea_base` la
    congela en el mismo paso."""
    version = projects_service.get_version(session, version_id)
    actor_final = Actor(kind=actor.kind, id=body.actor, role=body.role or actor.role)
    version = projects_service.activate_version(
        session,
        version,
        actor=actor_final,
        motivo=body.motivo,
        congelar_linea_base=body.congelar_linea_base,
        bus=_bus(request),
    )
    return projects_service.version_to_dict(version)


@router.post("/model-versions/{version_id}/baseline", response_model=resp.ModelVersion)
def freeze_baseline(
    version_id: int,
    body: BaselineBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Congela el baseline de una versión sobre un lote ya ingerido."""
    version = projects_service.get_version(session, version_id)
    batch = _get_batch(session, body.batch_id)
    actor_final = Actor(kind=actor.kind, id=body.actor, role=body.role or actor.role)
    version = projects_service.freeze_baseline(
        session,
        version,
        batch,
        actor=actor_final,
        motivo=body.motivo,
        laboratorio=body.laboratorio,
        bus=_bus(request),
    )
    return projects_service.version_to_dict(version)
