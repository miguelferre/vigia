"""Evaluaciones, medidas y series temporales."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session, select

from vigia.app.db import get_session
from vigia.app.errores import no_encontrado
from vigia.app.events import Actor, get_actor, get_correlation_id, record_event
from vigia.app.jobs import JobContext
from vigia.app.models import Batch, Evaluation, Measurement, ModelVersion, Monitor, Project
from vigia.app.schemas import respuestas as resp
from vigia.app.schemas.evaluations import EvaluateBody
from vigia.app.services import evaluate as evaluate_service
from vigia.app.services import explain as explain_service

router = APIRouter(tags=["evaluaciones"])


def _get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise no_encontrado("modelo", project_id, "modelos")
    return project


def _get_batch(session: Session, batch_id: int) -> Batch:
    batch = session.get(Batch, batch_id)
    if batch is None:
        raise no_encontrado("lote", batch_id, "lotes")
    return batch


def _get_evaluation(session: Session, evaluation_id: int) -> Evaluation:
    evaluation = session.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise no_encontrado("evaluación", evaluation_id, "evaluaciones")
    return evaluation


# Claves de `EvaluationResult.to_dict()` (`core/schema.py`) que la respuesta de
# la API ya sirve fuera de `result`: se podan de la copia devuelta para no
# mandar el mismo bloque dos veces. Lo guardado en
# `evaluation.result_json` no se toca.
_CLAVES_PODADAS_RESULT = ("measurements", "window", "config_snapshot")

# Máximo de `metric_key` por petición al timeline: evita
# que una query mal construida arrastre el catálogo entero de medidas.
_MAX_METRIC_KEYS_TIMELINE = 20


def _claves_de_metricas(valor: str) -> list[str]:
    """`metric_key` separado por comas, limpio de espacios; 422 si viene vacío o excede el máximo."""
    claves = [c.strip() for c in valor.split(",") if c.strip()]
    if not claves:
        raise HTTPException(422, "metric_key no puede estar vacío tras limpiar espacios")
    if len(claves) > _MAX_METRIC_KEYS_TIMELINE:
        raise HTTPException(
            422,
            f"metric_key admite como máximo {_MAX_METRIC_KEYS_TIMELINE} valores separados "
            f"por coma; llegaron {len(claves)}",
        )
    return claves


def _grupos_o_ninguno(valor: str | None) -> list[str] | None:
    """`group_code` separado por comas, o `None` para "todos los grupos" (ausente o vacío)."""
    if valor is None:
        return None
    grupos = [g.strip() for g in valor.split(",") if g.strip()]
    return grupos or None


def _fecha_valida(valor: str, *, campo: str, fin_de_dia: bool = False) -> datetime:
    """`valor` como fecha ISO 8601 (`aaaa-mm-dd` o con hora); 422 si el formato no es válido.

    Se normaliza a UTC porque el servicio compara contra `Evaluation.created_at`
    como texto (`models.now_iso`, siempre UTC): una fecha con otro huso
    compararía mal en lexicográfico aunque el instante fuera correcto.

    `fin_de_dia` es para `until`: una fecha sin hora nombra el día entero, así
    que `until=2026-09-10` tiene que incluir ese 10, no cortarlo a medianoche.
    Sin esto, el periodo "hoy" del selector no devolvería ni un punto.
    """
    crudo = valor.strip()
    try:
        fecha = datetime.fromisoformat(crudo)
    except ValueError:
        raise HTTPException(
            422,
            f"{campo} no es una fecha ISO 8601 válida: {valor!r}; usa aaaa-mm-dd o aaaa-mm-ddThh:mm:ss",
        ) from None
    fecha = fecha.replace(tzinfo=UTC) if fecha.tzinfo is None else fecha.astimezone(UTC)
    if fin_de_dia and len(crudo) == 10:
        fecha = fecha.replace(hour=23, minute=59, second=59, microsecond=999999)
    return fecha


def _result_podado(result_json: Any) -> Any:
    """`result_json` sin las claves que la respuesta ya trae en la raíz."""
    if not isinstance(result_json, dict):
        return result_json
    return {k: v for k, v in result_json.items() if k not in _CLAVES_PODADAS_RESULT}


def evaluation_to_dict(session: Session, e: Evaluation, *, light: bool = True) -> dict[str, Any]:
    monitor = session.get(Monitor, e.monitor_id)
    data: dict[str, Any] = {
        "id": e.id,
        "monitor_id": e.monitor_id,
        "monitor_type": monitor.type if monitor is not None else None,
        "project_id": e.project_id,
        "model_version_id": e.model_version_id,
        "batch_id": e.batch_id,
        "trigger": e.trigger,
        "window": e.window_json,
        "app_version": e.app_version,
        "core_version": e.core_version,
        "status": e.status,
        "worst_state": e.worst_state,
        "job_id": e.job_id,
        "created_at": e.created_at,
    }
    if not light:
        data["config_snapshot"] = e.config_snapshot_json
        data["result"] = _result_podado(e.result_json)
        medidas = session.exec(
            select(Measurement).where(Measurement.evaluation_id == e.id)  # type: ignore[arg-type]
        ).all()
        data["measurements"] = [
            {
                "metric_key": m.metric_key,
                "value": m.value,
                "interval_low": m.interval_low,
                "interval_high": m.interval_high,
                "threshold_low": m.threshold_low,
                "threshold_high": m.threshold_high,
                "state": m.state,
                "group_code": m.group_code,
                "motivo": m.motivo,
                "extra": m.extra_json,
            }
            for m in medidas
        ]
    return data


@router.post("/batches/{batch_id}/evaluate", response_model=resp.JobResumen)
def evaluate_batch_endpoint(
    batch_id: int,
    body: EvaluateBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Encola la evaluación de un lote ya ingerido en los tres monitores del motor."""
    batch = _get_batch(session, batch_id)
    version = session.get(ModelVersion, batch.model_version_id)
    if version is None or version.project_id != batch.project_id:
        raise HTTPException(409, "el lote pertenece a otro proyecto")
    bus = request.app.state.bus

    def _job_evaluacion(ctx: JobContext, job_session: Session, *, batch_id: int, trigger: str) -> dict:
        lote = job_session.get(Batch, batch_id)
        if lote is None:
            raise no_encontrado("lote", batch_id, "lotes")
        # Explicación global automática ANTES de evaluar, si el
        # proyecto la tiene activada; nunca rompe la evaluación. El motor solo
        # calcula la estabilidad del ranking (explain_stability_ndcg) cuando
        # evaluate_batch recibe explanation=, así que hay que calcularla aquí.
        version_evaluada = job_session.get(ModelVersion, lote.model_version_id)
        proyecto = job_session.get(Project, lote.project_id)
        explicacion = None
        if version_evaluada is not None and proyecto is not None:
            explicacion = explain_service.maybe_auto_explain(
                job_session,
                lote,
                version_evaluada,
                proyecto,
                job=ctx,
                correlation_id=ctx.correlation_id,
                bus=bus,
            )
        # Si `evaluate_batch` lanza `DatosNoValidos` (la valida
        # `core/quality.py`), no hace falta traducirla aquí: el mensaje ya
        # viene en español y sin traza, y el runner de trabajos
        # (`app/jobs.py`) hace `job.error = str(exc)`, así que el trabajo
        # queda en "error" con ese texto tal cual, nunca con la excepción
        # cruda de una librería.
        evaluaciones = evaluate_service.evaluate_batch(
            job_session,
            lote,
            trigger=trigger,
            job=ctx,
            correlation_id=ctx.correlation_id,
            bus=bus,
            explanation=explicacion,
        )
        return {
            "evaluations": {tipo: ev.id for tipo, ev in evaluaciones.items()},
            "worst_states": {tipo: ev.worst_state for tipo, ev in evaluaciones.items()},
        }

    job = request.app.state.jobs.enqueue(
        "evaluacion",
        "rapida",
        _job_evaluacion,
        params={"batch_id": batch.id, "trigger": body.trigger},
        project_id=batch.project_id,
        correlation_id=correlation_id,
        clave_dedup=f"evaluacion:lote:{batch.id}",
    )
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="evaluacion.solicitada",
        object_type="batch",
        object_id=batch.id,
        project_id=batch.project_id,
        after={"batch_id": batch.id, "batch_seq": batch.seq, "trigger": body.trigger},
        correlation_id=correlation_id,
        job_id=job.id,
        bus=bus,
    )
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


@router.get("/projects/{project_id}/evaluations", response_model=resp.ListResponse[resp.Evaluation])
def list_evaluations(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    monitor_type: str | None = None,
    batch_id: int | None = None,
    model_version_id: int | None = None,
    offset: int = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    order: str = "asc",
) -> dict:
    """Evaluaciones del proyecto (sin `result_json`), con filtros opcionales.

    `order` (H1a): `asc` (por defecto, como hasta ahora) o `desc`; con
    `order=desc&limit=2` se obtienen las dos últimas evaluaciones del filtro
    (delta del cuadro de mando frente al lote anterior)."""
    if order not in ("asc", "desc"):
        raise HTTPException(422, f"order debe ser asc o desc; se recibió {order!r}")
    project = _get_project(session, project_id)
    consulta = select(Evaluation).where(Evaluation.project_id == project.id)
    if monitor_type is not None:
        ids_monitor = [
            m.id
            for m in session.exec(
                select(Monitor).where(Monitor.project_id == project.id, Monitor.type == monitor_type)
            ).all()
        ]
        consulta = consulta.where(Evaluation.monitor_id.in_(ids_monitor))  # type: ignore[attr-defined]
    if batch_id is not None:
        consulta = consulta.where(Evaluation.batch_id == batch_id)
    if model_version_id is not None:
        consulta = consulta.where(Evaluation.model_version_id == model_version_id)
    todas = session.exec(consulta).all()
    total = len(todas)
    columna_orden = Evaluation.created_at.desc() if order == "desc" else Evaluation.created_at  # type: ignore[attr-defined]
    filas = session.exec(
        consulta.order_by(columna_orden).offset(offset).limit(limit)  # type: ignore[arg-type]
    ).all()
    return {"items": [evaluation_to_dict(session, e, light=True) for e in filas], "total": total}


@router.get("/evaluations/{evaluation_id}", response_model=resp.EvaluationDetail)
def read_evaluation(evaluation_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Una evaluación completa, con sus medidas y el `result_json` del motor."""
    evaluation = _get_evaluation(session, evaluation_id)
    return evaluation_to_dict(session, evaluation, light=False)


@router.get("/projects/{project_id}/timeline", response_model=resp.ListResponse[resp.TimelinePoint])
def read_timeline(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    monitor_type: str,
    metric_key: str,
    group_code: str | None = None,
    since: str | None = None,
    until: str | None = None,
    model_version_id: int | None = None,
) -> dict:
    """Serie temporal de una o varias medidas del proyecto, con rango de fechas opcional.

    `model_version_id` deja solo los puntos de esa versión.

    `metric_key` admite varias claves separadas por coma (máximo 20).
    `group_code` admite varias, separadas por coma; ausente sigue siendo "todos
    los grupos". `since`/`until` acotan por `Evaluation.created_at` (ISO 8601,
    fecha sola o con hora); `until` anterior a `since` es 422.
    """
    project = _get_project(session, project_id)
    claves = _claves_de_metricas(metric_key)
    grupos = _grupos_o_ninguno(group_code)
    since_fecha = _fecha_valida(since, campo="since") if since is not None else None
    until_fecha = _fecha_valida(until, campo="until", fin_de_dia=True) if until is not None else None
    if since_fecha is not None and until_fecha is not None and until_fecha < since_fecha:
        raise HTTPException(422, f"until ({until!r}) es anterior a since ({since!r})")
    serie = evaluate_service.timeline(
        session,
        project,
        monitor_type=monitor_type,
        metric_key=claves,
        group_code=grupos,
        # Normalizadas al formato de `models.now_iso` (UTC con microsegundos):
        # el servicio compara como texto, así que la cadena que llega del
        # cliente no vale tal cual.
        since=since_fecha.isoformat(timespec="microseconds") if since_fecha is not None else None,
        until=until_fecha.isoformat(timespec="microseconds") if until_fecha is not None else None,
        model_version_id=model_version_id,
    )
    return {"items": serie, "total": len(serie)}
