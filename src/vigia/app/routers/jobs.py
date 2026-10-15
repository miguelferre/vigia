"""Trabajos de las dos colas."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from vigia.app.db import get_session
from vigia.app.errores import no_encontrado
from vigia.app.events import Actor, get_actor, record_event
from vigia.app.models import Job
from vigia.app.schemas import respuestas as resp
from vigia.app.sse import comprobar_cupo, sse_stream, suscribir

router = APIRouter(tags=["jobs"])

ESTADOS_FINALES = ("terminado", "error", "cancelado")


def job_to_dict(job: Job) -> dict[str, Any]:
    """Serializa un trabajo tal como lo ve la API."""
    return {
        "id": job.id,
        "kind": job.kind,
        "queue": job.queue,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "params": job.params_json,
        "result": job.result_json,
        "error": job.error,
        "cancel_requested": job.cancel_requested,
        "project_id": job.project_id,
        "correlation_id": job.correlation_id,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def _get_job(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise no_encontrado("trabajo", job_id, "trabajos")
    return job


def _leer_job(engine: Any, job_id: int) -> dict[str, Any]:
    """Lee un trabajo con su propia sesión. Es síncrona a propósito: el stream la llama
    con `run_in_threadpool` para no hacer E/S de SQLite en el bucle de eventos."""
    with Session(engine) as session:
        return job_to_dict(_get_job(session, job_id))


@router.get("/jobs", response_model=resp.ListResponse[resp.Job])
def list_jobs(
    session: Annotated[Session, Depends(get_session)],
    status: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Trabajos, del más reciente al más antiguo, con filtro opcional de estado."""
    consulta = select(Job)
    if status is not None:
        consulta = consulta.where(Job.status == status)
    total = len(session.exec(consulta).all())
    filas = session.exec(
        consulta.order_by(Job.created_at.desc()).offset(offset).limit(limit)  # type: ignore[attr-defined]
    ).all()
    return {"items": [job_to_dict(j) for j in filas], "total": total}


@router.get("/jobs/{job_id}", response_model=resp.Job)
def read_job(job_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Un trabajo por id."""
    return job_to_dict(_get_job(session, job_id))


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: int, request: Request):
    """SSE del trabajo: envía primero el estado actual y termina al llegar a un estado final."""
    heartbeat_s = getattr(request.app.state.settings, "sse_heartbeat_s", 15.0)

    estado_inicial = await run_in_threadpool(_leer_job, request.app.state.engine, job_id)
    if estado_inicial["status"] not in ESTADOS_FINALES:
        comprobar_cupo(request)

    async def _generador():
        if estado_inicial["status"] in ESTADOS_FINALES:
            yield {"event": "job", "data": _dumps(estado_inicial)}
            return
        # La suscripción nace aquí, no en la ruta: si el flujo no llega a abrirse
        # no queda ninguna viva, y `sse_stream` la libera en su `finally`.
        subscription = suscribir(request)
        if subscription is None:
            return
        try:
            # Releer tras suscribirse: ningún cambio de estado se pierde entre la lectura y la espera.
            actual = await run_in_threadpool(_leer_job, request.app.state.engine, job_id)
            yield {"event": "job", "data": _dumps(actual)}
            if actual["status"] in ESTADOS_FINALES:
                return
            async for evento in sse_stream(
                request,
                subscription,
                heartbeat_s=heartbeat_s,
                filtro=lambda msg: msg.get("type") == "job" and msg.get("job_id") == job_id,
                until=lambda msg: msg.get("status") in ESTADOS_FINALES,
            ):
                yield evento
        finally:
            subscription.close()

    return EventSourceResponse(_generador())


def _dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


@router.post("/jobs/{job_id}/cancel", response_model=resp.Job)
def cancel_job(
    job_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Pide la cancelación cooperativa de un trabajo y registra el evento con quien la pide."""
    job = _get_job(session, job_id)
    manager = request.app.state.jobs
    job = manager.cancel(job_id)
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="job.cancelado",
        object_type="job",
        object_id=job_id,
        project_id=job.project_id,
        after={"status": job.status},
        correlation_id=job.correlation_id,
        job_id=job_id,
        bus=request.app.state.bus,
    )
    session.commit()
    return job_to_dict(job)
