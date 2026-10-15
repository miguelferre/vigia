"""Guiones y reproducciones de demo."""

from __future__ import annotations

import io
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlmodel import Session, select

from vigia.app.db import get_session
from vigia.app.errores import no_encontrado
from vigia.app.events import Actor, get_actor, get_correlation_id, record_event
from vigia.app.jobs import JobContext
from vigia.app.models import DemoRun, DemoScenario, Job, Project
from vigia.app.schemas import respuestas as resp
from vigia.app.schemas.demo import (
    CreateRunBody,
    LabRunBody,
    ResetRunBody,
    exigir_parametros_finitos,
)
from vigia.app.services import demo_files, demo_player
from vigia.sim.scenarios import clave_vigente, get_scenario

router = APIRouter(tags=["demo"])


def _fase_pedida(run: DemoRun) -> str | None:
    """Clave de la fase que tocaría reproducir, o `None` si el guion ya ha
    terminado: va en `after_json` del evento humano de solicitud."""
    try:
        scenario = get_scenario(run.scenario_key)
    except KeyError:
        return None
    if run.current_phase < len(scenario.phases):
        return scenario.phases[run.current_phase].key
    return None


def _get_run(session: Session, run_id: int) -> DemoRun:
    run = session.get(DemoRun, run_id)
    if run is None:
        raise no_encontrado("reproducción de demo", run_id, "reproducciones de demo")
    return run


def _job_to_dict(job: Job) -> dict[str, Any]:
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


def _lab_params_por_fase(scenario_key: str) -> dict[str, list[str]]:
    """`lab_params` (§3.4) de cada fase del guion `scenario_key`, por clave.

    `phases_json` (sembrado en `app/migrations.py::_fase_a_dict`) no guarda el
    generador de la fase, así que esto se calcula sobre el guion en memoria
    (`vigia.sim.scenarios`), no sobre lo sembrado en la base de datos.
    """
    try:
        scenario = get_scenario(scenario_key)
    except KeyError:
        return {}
    return {fase.key: demo_player.lab_params_for_phase(fase) for fase in scenario.phases}


def _upload_mapping_para(scenario_key: str) -> dict[str, Any] | None:
    """`upload_mapping` (`services/demo_files.py`) del guion, o `None` si
    su primera fase no tiene enlatado: mismo guardián que `_lab_params_por_fase`,
    sobre el guion en memoria (`vigia.sim.scenarios`), no sobre lo sembrado."""
    try:
        scenario = get_scenario(scenario_key)
    except KeyError:
        return None
    if not scenario.phases or scenario.phases[0].canned is None:
        return None
    return demo_files.upload_mapping(scenario_key)


def _scenario_to_dict(s: DemoScenario, clave: str | None = None) -> dict[str, Any]:
    clave = clave or s.key
    lab_params = _lab_params_por_fase(clave)
    fases = [
        {**fase, "lab_params": lab_params.get(fase.get("key"), [])} for fase in (s.phases_json or [])
    ]
    return {
        "key": clave,
        "title": s.title,
        "domain": s.domain,
        "description": s.description,
        "phases": fases,
        "default_params": s.default_params_json,
        "upload_mapping": _upload_mapping_para(clave),
    }


@router.get("/demo/scenarios", response_model=resp.ListResponse[resp.DemoScenario])
def list_scenarios(session: Annotated[Session, Depends(get_session)]) -> dict:
    """Guiones de demo sembrados, con sus fases y, por fase, `lab_params` (§3.4)."""
    filas = session.exec(select(DemoScenario).order_by(DemoScenario.id)).all()  # type: ignore[arg-type]
    # una base creada antes guarda la fila con la clave antigua (la siembra
    # solo corre en la migración 1). Se sirve con la clave vigente y sin duplicados.
    items: list[dict[str, Any]] = []
    vistas: set[str] = set()
    for fila in filas:
        clave = clave_vigente(fila.key)
        if clave in vistas:
            continue
        vistas.add(clave)
        items.append(_scenario_to_dict(fila, clave))
    return {"items": items, "total": len(items)}


@router.get("/demo/scenarios/{key}/files/{phase}")
def download_scenario_file(key: str, phase: str) -> StreamingResponse:
    """CSV combinado (payload + feedback enlatados) de una fase, para subirlo a mano (§3.3).

    Lectura pura: sin actor ni evento, ni `response_model` (no es JSON, como
    el resto de descargas de la API: `GET /events/export`,
    `GET /projects/{id}/usage-logs/export.csv`). 404 si el guion o la fase no
    existen, o si la fase no tiene fichero enlatado.
    """
    contenido = demo_files.combined_csv_bytes(key, phase)
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type="text/csv",
        # Nombre fijo por contrato (§3.3): no depende de `key` ni de `phase`.
        # El único uso real hoy es la línea base de `caso_digestivo` (
        # `GET .../caso_digestivo/files/b1`); otro guion/fase enlatados
        # también responden 200 con este mismo nombre.
        headers={"Content-Disposition": 'attachment; filename="caso-digestivo-linea-base.csv"'},
    )


def _exigir_cupo_de_demos(session: Session, tope: int) -> None:
    """409 si ya hay `tope` proyectos de demo vivos: cada reproducción sin
    `project_id` crea un proyecto con sus versiones y los de demo no se borran solos."""
    vivos = session.exec(
        select(func.count()).select_from(Project).where(Project.is_demo == True)
    ).one()
    if vivos >= tope:
        raise HTTPException(
            409,
            f"ya hay {vivos} proyectos de demo y el máximo es {tope}: "
            "borra alguno antes de crear otra demo",
        )


@router.post("/demo/runs", response_model=resp.DemoRun)
def create_run(
    body: CreateRunBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Crea la reproducción, en estado `lista`.

    Sin `project_id`, crea el proyecto de demo. Con `project_id`, la
    ata a un proyecto que el usuario ya ha creado con el formulario real (y,
    si tiene línea base sin lotes de producción, se reproduce `b2..b5`
    enlatados de forma síncrona antes de responder).
    """
    exigir_parametros_finitos(body.params)
    if body.project_id is None:
        _exigir_cupo_de_demos(session, request.app.state.settings.max_proyectos_demo)
    run = demo_player.create_run(
        session,
        scenario_key=body.scenario_key,
        source=body.source,
        with_human=body.with_human,
        params=body.params,
        project_name=body.project_name,
        project_id=body.project_id,
        data_dir=request.app.state.settings.data_dir,
        actor=actor,
        bus=request.app.state.bus,
    )
    return demo_player.run_to_dict(run)


@router.get("/demo/runs", response_model=resp.ListResponse[resp.DemoRun])
def list_runs(
    session: Annotated[Session, Depends(get_session)],
    offset: int = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Reproducciones de demo, más recientes primero."""
    total = len(session.exec(select(DemoRun)).all())
    filas = session.exec(
        select(DemoRun).order_by(DemoRun.id.desc()).offset(offset).limit(limit)  # type: ignore[union-attr]
    ).all()
    return {"items": [demo_player.run_to_dict(r) for r in filas], "total": total}


@router.get("/demo/runs/{run_id}", response_model=resp.DemoRun)
def read_run(run_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Una reproducción de demo, con su `result` y `project_id`."""
    run = _get_run(session, run_id)
    return demo_player.run_to_dict(run)


@router.post("/demo/runs/{run_id}/next", response_model=resp.JobResumen)
def next_phase(
    run_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Encola la reproducción de la siguiente fase pendiente del guion."""
    run = _get_run(session, run_id)
    bus = request.app.state.bus
    data_dir = request.app.state.settings.data_dir

    # quien pide avanzar deja rastro humano ANTES de que las fases,
    # que van como actor `sistema`, se reproduzcan.
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="demo.avance_solicitado",
        object_type="demo_run",
        object_id=run.id,
        project_id=run.project_id,
        after={"solicitud": "next", "phase_key": _fase_pedida(run)},
        correlation_id=correlation_id,
        bus=bus,
    )
    session.commit()

    def _job_next(ctx: JobContext, job_session: Session, *, run_id: int) -> dict:
        r = job_session.get(DemoRun, run_id)
        if r is None:
            raise no_encontrado("reproducción de demo", run_id, "reproducciones de demo")
        return demo_player.next_phase(job_session, r, data_dir=data_dir, job=ctx, bus=bus)

    job = request.app.state.jobs.enqueue(
        "demo",
        "rapida",
        _job_next,
        params={"run_id": run.id},
        project_id=run.project_id,
        correlation_id=correlation_id,
    )
    return _job_to_dict(job)


@router.post("/demo/runs/{run_id}/play", response_model=resp.JobResumen)
def play_run(
    run_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Encola la reproducción de todas las fases pendientes del guion."""
    run = _get_run(session, run_id)
    bus = request.app.state.bus
    data_dir = request.app.state.settings.data_dir

    # mismo rastro humano que `next`, antes de encadenar las fases.
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="demo.avance_solicitado",
        object_type="demo_run",
        object_id=run.id,
        project_id=run.project_id,
        after={"solicitud": "play", "phase_key": _fase_pedida(run)},
        correlation_id=correlation_id,
        bus=bus,
    )
    session.commit()

    def _job_play(ctx: JobContext, job_session: Session, *, run_id: int) -> dict:
        r = job_session.get(DemoRun, run_id)
        if r is None:
            raise no_encontrado("reproducción de demo", run_id, "reproducciones de demo")
        reproducida = demo_player.play(job_session, r, data_dir=data_dir, job=ctx, bus=bus)
        return demo_player.run_to_dict(reproducida)

    job = request.app.state.jobs.enqueue(
        "demo",
        "rapida",
        _job_play,
        params={"run_id": run.id},
        project_id=run.project_id,
        correlation_id=correlation_id,
    )
    return _job_to_dict(job)


@router.post("/demo/runs/{run_id}/lab", response_model=resp.JobResumen)
def lab_run(
    run_id: int,
    body: LabRunBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Encola una fase generada a la carta sobre el proyecto de la reproducción (§6.1).

    No avanza el guion: valida `phase_key` y `params` antes de encolar, para
    que una fase desconocida (404) o un parámetro que el generador no acepta
    (422) lleguen como error HTTP real, no como un job terminado en `error`.
    """
    exigir_parametros_finitos(body.params)
    run = _get_run(session, run_id)
    demo_player.resolve_lab_phase(run, body.phase_key, body.params)
    bus = request.app.state.bus
    data_dir = request.app.state.settings.data_dir
    actor_final = Actor(kind=actor.kind, id=body.actor, role=body.role or actor.role)

    def _job_lab(ctx: JobContext, job_session: Session, *, run_id: int, phase_key: str) -> dict:
        r = job_session.get(DemoRun, run_id)
        if r is None:
            raise no_encontrado("reproducción de demo", run_id, "reproducciones de demo")
        return demo_player.run_lab(
            job_session,
            r,
            phase_key=body.phase_key,
            params=body.params,
            seed=body.seed,
            actor=actor_final,
            motivo=body.motivo,
            data_dir=data_dir,
            job=ctx,
            bus=bus,
        )

    job = request.app.state.jobs.enqueue(
        "demo_lab",
        "rapida",
        _job_lab,
        params={"run_id": run.id, "phase_key": body.phase_key},
        project_id=run.project_id,
        correlation_id=correlation_id,
    )
    return _job_to_dict(job)


@router.post("/demo/runs/{run_id}/reset", response_model=resp.DemoRun)
def reset_run(
    run_id: int,
    body: ResetRunBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Reinicia el proyecto de demo (§3.9). Exige `confirm: true`."""
    if not body.confirm:
        raise HTTPException(400, "hace falta confirm=true para reiniciar la demo")
    run = _get_run(session, run_id)
    actor_final = Actor(kind=actor.kind, id=body.actor, role=body.role or actor.role)
    run = demo_player.reset(
        session,
        run,
        actor=actor_final,
        motivo=body.motivo,
        bus=request.app.state.bus,
        data_dir=request.app.state.settings.data_dir,
    )
    return demo_player.run_to_dict(run)
