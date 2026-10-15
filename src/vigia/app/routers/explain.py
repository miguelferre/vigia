"""Explicabilidad global y local."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session, select

from vigia.app.db import get_session
from vigia.app.errores import no_encontrado
from vigia.app.events import Actor, get_actor, get_correlation_id, record_event
from vigia.app.jobs import JobContext
from vigia.app.models import Batch, Explanation, ModelVersion
from vigia.app.routers.jobs import job_to_dict
from vigia.app.schemas import respuestas as resp
from vigia.app.schemas.explain import ExplainGlobalBody, ExplainLocalBody
from vigia.app.services import explain as explain_service
from vigia.app.services import projects as projects_service

router = APIRouter(tags=["explicabilidad"])


@router.get("/projects/{project_id}/explanations/summary", response_model=resp.ExplanationSummary)
def explanations_summary(
    project_id: int, session: Annotated[Session, Depends(get_session)]
) -> dict:
    """Resumen de explicabilidad para la tarjeta del cuadro de mando:
    las tres características más importantes de la última explicación global,
    la estabilidad de su ranking y cuándo cambió por última vez."""
    project = projects_service.get_project(session, project_id)
    return explain_service.explanations_summary(session, project)


def _get_version(session: Session, version_id: int) -> ModelVersion:
    version = session.get(ModelVersion, version_id)
    if version is None:
        raise no_encontrado("versión", version_id, "versiones")
    return version


def _get_explanation(session: Session, explanation_id: int) -> Explanation:
    explanation = session.get(Explanation, explanation_id)
    if explanation is None:
        raise no_encontrado("explicación", explanation_id, "explicaciones")
    return explanation


@router.post("/model-versions/{version_id}/explain/global", response_model=resp.Job)
def explain_global(
    version_id: int,
    body: ExplainGlobalBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Encola la explicabilidad global (permutación por defecto, o SHAP) del lote indicado."""
    version = _get_version(session, version_id)
    explain_service.check_explainable(version)
    batch = explain_service.resolve_batch(session, version, body.batch_id)
    explain_service.check_features_available(session, batch)
    explain_service.validar_clase(session, version, body.clase)
    bus = request.app.state.bus

    def _job_explain_global(
        ctx: JobContext,
        job_session: Session,
        *,
        version_id: int,
        kind: str,
        batch_id: int | None,
        clase: int | str | None = None,
    ) -> dict:
        mv = job_session.get(ModelVersion, version_id)
        if mv is None:
            raise no_encontrado("versión", version_id, "versiones")
        lote = job_session.get(Batch, batch_id) if batch_id is not None else None
        explanation = explain_service.explain_global(
            job_session,
            mv,
            kind=kind,
            batch=lote,
            job=ctx,
            correlation_id=ctx.correlation_id,
            bus=bus,
            clase=clase,
        )
        return explain_service.explanation_to_dict(explanation)

    job = request.app.state.jobs.enqueue(
        "explicacion",
        "rapida",
        _job_explain_global,
        params={
            "version_id": version_id,
            "kind": body.kind,
            "batch_id": batch.id if batch else None,
            **({"clase": body.clase} if body.clase is not None else {}),
        },
        project_id=version.project_id,
        correlation_id=correlation_id,
    )
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="explicacion.solicitada",
        object_type="model_version",
        object_id=version_id,
        project_id=version.project_id,
        after={
            "kind": f"global_{body.kind}",
            "scope": "global",
            "batch_id": batch.id if batch else None,
            **({"clase": body.clase} if body.clase is not None else {}),
        },
        correlation_id=correlation_id,
        job_id=job.id,
        bus=bus,
    )
    session.commit()
    return job_to_dict(job)


@router.post("/model-versions/{version_id}/explain/local", response_model=resp.Job)
def explain_local(
    version_id: int,
    body: ExplainLocalBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Encola la explicación LIME local de una fila del lote indicado."""
    version = _get_version(session, version_id)
    explain_service.check_explainable(version)
    batch = explain_service.resolve_batch(session, version, body.batch_id)
    explain_service.check_features_available(session, batch)
    explain_service.find_row(session, batch, body.row_seq)
    explain_service.validar_clase(session, version, body.clase)
    bus = request.app.state.bus

    def _job_explain_local(
        ctx: JobContext,
        job_session: Session,
        *,
        version_id: int,
        batch_id: int,
        row_seq: int,
        clase: int | str | None = None,
    ) -> dict:
        mv = job_session.get(ModelVersion, version_id)
        lote = job_session.get(Batch, batch_id)
        if mv is None:
            raise no_encontrado("versión", version_id, "versiones")
        if lote is None:
            raise no_encontrado("lote", batch_id, "lotes")
        explanation = explain_service.explain_local(
            job_session,
            mv,
            batch=lote,
            row_seq=row_seq,
            job=ctx,
            correlation_id=ctx.correlation_id,
            bus=bus,
            clase=clase,
        )
        return explain_service.explanation_to_dict(explanation)

    job = request.app.state.jobs.enqueue(
        "explicacion",
        "rapida",
        _job_explain_local,
        params={
            "version_id": version_id,
            "batch_id": batch.id,
            "row_seq": body.row_seq,
            **({"clase": body.clase} if body.clase is not None else {}),
        },
        project_id=version.project_id,
        correlation_id=correlation_id,
    )
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="explicacion.solicitada",
        object_type="model_version",
        object_id=version_id,
        project_id=version.project_id,
        after={
            "kind": "local_lime",
            "scope": "local",
            "batch_id": batch.id,
            "row_seq": body.row_seq,
            **({"clase": body.clase} if body.clase is not None else {}),
        },
        correlation_id=correlation_id,
        job_id=job.id,
        bus=bus,
    )
    session.commit()
    return job_to_dict(job)


@router.get("/model-versions/{version_id}/explanations", response_model=resp.ListResponse[resp.Explanation])
def list_explanations(
    version_id: int,
    session: Annotated[Session, Depends(get_session)],
    offset: int = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Explicaciones calculadas de la versión, de la más reciente a la más antigua."""
    _get_version(session, version_id)
    consulta = select(Explanation).where(Explanation.model_version_id == version_id)
    total = len(session.exec(consulta).all())
    filas = session.exec(
        consulta.order_by(Explanation.id.desc()).offset(offset).limit(limit)  # type: ignore[attr-defined]
    ).all()
    return {"items": [explain_service.explanation_to_dict(e) for e in filas], "total": total}


@router.get("/explanations/{explanation_id}", response_model=resp.Explanation)
def read_explanation(explanation_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Una explicación por id."""
    return explain_service.explanation_to_dict(_get_explanation(session, explanation_id))
