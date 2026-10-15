"""Lanzar y ejecutar la revisión del dossier: cola `rapida` para
`b0` (sin LLM) o `llm` para `p3`/`auto`. La ejecución del trabajo vive en
`dossiers_review_job.py`; ambos partidos de `services/dossiers.py` por el
límite de 9 KB.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from vigia.app.bus import EventBus
from vigia.app.events import Actor, record_event
from vigia.app.jobs import JobContext
from vigia.app.models import Dossier, DossierReview, Event, Setting
from vigia.app.schemas.dossiers import DossierReviewCreateBody
from vigia.app.services.dossiers_review_job import ejecutar_review
from vigia.human import dossier_adapter

__all__ = ["launch_review"]

_BACKENDS_NO_LOCAL = ("anthropic",)


def _llm_setting(session: Session) -> dict[str, Any]:
    fila = session.get(Setting, "llm")
    if fila is None or not isinstance(fila.value_json, dict):
        return {"backend": "none", "model": "", "base_url": "", "api_key": ""}
    return fila.value_json


def _confirmacion_anthropic_vigente(session: Session) -> bool:
    """Existe un `ajuste.llm_confirmado` con `after.backend == "anthropic"`
    y ningún `ajuste.cambiado` posterior cambia `llm.backend` a otro valor."""
    ultimo = session.exec(
        select(Event).where(Event.action == "ajuste.llm_confirmado").order_by(Event.id.desc())
    ).first()
    if ultimo is None or ultimo.id is None:
        return False
    posteriores = session.exec(
        select(Event).where(Event.action == "ajuste.cambiado", Event.id > ultimo.id)
    ).all()
    for e in posteriores:
        llm = (e.after_json or {}).get("llm") if isinstance(e.after_json, dict) else None
        if isinstance(llm, dict) and llm.get("backend") not in (None, "anthropic"):
            return False
    return True


def launch_review(
    session: Session,
    dossier: Dossier,
    body: DossierReviewCreateBody,
    *,
    actor: Actor,
    correlation_id: str,
    bus: EventBus | None,
    jobs: Any,
) -> dict[str, Any]:
    """Valida las reglas de la revisión, crea la fila `dossier_review` y encola
    `revision_dossier`. Devuelve el `Job` encolado (forma de `JobResumen`)."""
    if body.approach not in dossier_adapter.REVIEW_APPROACHES:
        raise HTTPException(422, f"approach debe ser uno de {dossier_adapter.REVIEW_APPROACHES}")

    llm = _llm_setting(session)
    backend_actual = llm.get("backend", "none")
    if body.approach in ("p3", "auto"):
        if backend_actual == "none":
            raise HTTPException(
                409, "configura un backend en /ajustes antes de pedir una revisión con LLM"
            )
        if backend_actual in _BACKENDS_NO_LOCAL and not _confirmacion_anthropic_vigente(session):
            raise HTTPException(
                422,
                "activa el backend LLM en /ajustes con la confirmación explícita "
                "antes de pedir esta revisión",
            )

    fila = DossierReview(
        dossier_id=dossier.id,
        approach=body.approach,
        status="pendiente",
        actor=actor.id,
        role=actor.role,
        motivo=body.motivo,
    )
    session.add(fila)
    session.flush()
    review_id = fila.id
    # `dossier.revision_lanzada` se registra dentro de `_job_review`, con
    # `ctx.job_id`: antes de `enqueue` el job no existe, y tras `enqueue`
    # `fila.job_id` aún no está persistido si `jobs_inline=True`.
    session.commit()

    backend_job = "none" if body.approach == "b0" else backend_actual
    llm_conf = dict(llm)
    approach = body.approach
    corpus = body.corpus
    dedup = body.dedup
    incluir_crosswalk = body.crosswalk
    motivo = body.motivo
    dossier_id = dossier.id
    project_id = dossier.project_id
    actor_kind = actor.kind
    actor_id = actor.id
    actor_role = actor.role

    def _job_review(ctx: JobContext, job_session: Session, *, review_id: int) -> dict[str, Any]:
        record_event(
            job_session,
            actor_kind=actor_kind,
            actor_id=actor_id,
            role=actor_role,
            action="dossier.revision_lanzada",
            object_type="dossier_review",
            object_id=review_id,
            project_id=project_id,
            motivo=motivo,
            after={"dossier_id": dossier_id, "approach": approach},
            correlation_id=correlation_id,
            job_id=ctx.job_id,
            bus=bus,
        )
        job_session.commit()
        return ejecutar_review(
            job_session,
            review_id,
            approach=approach,
            corpus=corpus,
            dedup=dedup,
            incluir_crosswalk=incluir_crosswalk,
            backend=backend_job,
            llm_conf=llm_conf,
            correlation_id=correlation_id,
            job_id=ctx.job_id,
            bus=bus,
        )

    cola = "rapida" if body.approach == "b0" else "llm"
    job = jobs.enqueue(
        "revision_dossier",
        cola,
        _job_review,
        params={"review_id": review_id},
        project_id=dossier.project_id,
        correlation_id=correlation_id,
    )
    fila.job_id = job.id
    session.add(fila)
    session.commit()

    return {
        "id": job.id,
        "kind": job.kind,
        "queue": job.queue,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "result": job.result_json,
        "error": job.error,
        "project_id": job.project_id,
        "correlation_id": job.correlation_id,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }
