"""Diario de uso y alertas cruzadas."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlmodel import Session

from vigia.app.db import get_session
from vigia.app.events import Actor, get_actor, get_correlation_id, record_event
from vigia.app.models import Job
from vigia.app.schemas.human import (
    DeskillingResponse,
    DeskillingSignalOut,
    DeskillingTrendsOut,
    DeskillingWindowOut,
    JobAccepted,
    UsageLogUploadResponse,
    ValorFavorable,
)
from vigia.app.services import human_layer
from vigia.app.services import projects as projects_service
from vigia.app.services import tarea as tarea_service
from vigia.app.services.subidas import leer_subida
from vigia.human import ir_adapter
from vigia.human.deskilling_texto import motivo_es

router = APIRouter(tags=["capa-humana"])


def _job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "kind": job.kind,
        "queue": job.queue,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "result": job.result_json,
        "error": job.error,
    }


def _resolver_version(session: Session, project_id: int, model_version_id: int | None):
    project = projects_service.get_project(session, project_id)
    if model_version_id is not None:
        version = projects_service.get_version(session, model_version_id)
        if version.project_id != project.id:
            raise HTTPException(422, "esa versión no es de este modelo: elige una de las versiones del modelo")
        return project, version
    if project.active_version_id is None:
        raise HTTPException(409, "el modelo no tiene versión activa: activa una versión en la pantalla Versiones")
    version = projects_service.get_version(session, project.active_version_id)
    return project, version


_REFER_DESCRIPTION = (
    "CSV del diario de uso: date, human_decision, model_output, ground_truth "
    "(opcionales clinician_pseudonym, subgroup, record_seq). date admite ISO "
    "(aaaa-mm-dd), dd/mm/aaaa o dd-mm-aaaa y se normaliza a ISO; cualquier otro "
    "formato da 422 con la fila. human_decision, model_output y ground_truth son "
    "refer/no-refer (o 1/0): refer (o 1) es la decisión favorable para la persona "
    "afectada, en el mismo sentido que la etiqueta favorable del modelo. "
    "Separador (coma, punto y coma o tabulador) y codificación (UTF-8 con o sin BOM, "
    "Windows-1252) se detectan solos. En un modelo multiclase las tres columnas "
    "llevan nombres de clase, tal como se declararon al crear el modelo; refer/no-refer "
    "y 1/0 solo valen en un modelo binario. En un modelo de regresión con rango favorable "
    "las tres columnas llevan cifras (números con punto decimal y sin unidad; ground_truth "
    "puede ir en blanco): el sistema deriva la decisión dentro o fuera del rango."
)

_VALOR_FAVORABLE_DESCRIPTION = (
    "Qué valor del fichero es la decisión favorable para la persona: refer, no-refer, "
    "1 o 0 (por defecto refer). Con no-refer o 0 la subida "
    "recodifica human_decision, model_output y ground_truth antes de guardar. La "
    "respuesta trae comprobacion_codificacion: un aviso si las decisiones del modelo "
    "en el registro no casan con sus predicciones; nunca rechaza la subida. En un "
    "modelo multiclase no hay inversión: cualquier valor distinto de refer da 422. Sin "
    "valor se entiende refer. En un modelo de regresión el registro trae cifras y no se "
    "usa: cualquier valor da 422."
)


@router.post("/projects/{project_id}/usage-logs/upload", response_model=UsageLogUploadResponse)
def upload_usage_log(
    project_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    file: Annotated[UploadFile, File(description=_REFER_DESCRIPTION)],
    model_version_id: Annotated[int | None, Form()] = None,
    valor_favorable: Annotated[
        ValorFavorable | None, Form(description=_VALOR_FAVORABLE_DESCRIPTION)
    ] = None,
) -> UsageLogUploadResponse:
    """Sube el CSV de uso, lo valida y lo ingiere en `usage_log`.

    `date` se normaliza a ISO: ISO, `dd/mm/aaaa` o
    `dd-mm-aaaa`; cualquier otro formato da 422 con el número de fila (la
    subida entera falla, no se ingiere parcialmente).

    `human_decision`, `model_output` y `ground_truth` son refer/no-refer (o
    1/0). La frase siguiente va
    en una sola línea sin cortar, a propósito, porque el test la busca byte
    a byte en /openapi.json (antes llevaba comillas invertidas alrededor de
    `refer`/`1`, que rompían el texto exacto).

    refer (o 1) es la decisión favorable para la persona afectada, en el mismo sentido que la etiqueta favorable del modelo (`favorable_label`/`favorable_resuelto` de `core/schema.py`).
    """
    project, version = _resolver_version(session, project_id, model_version_id)
    # Ruta síncrona: FastAPI la corre en el pool de hilos, así que leer, validar e
    # ingerir un CSV grande no bloquea el bucle de eventos de la API.
    contenido = leer_subida(file.file)
    settings = request.app.state.settings
    upload_dir = settings.data_dir / "uploads" / str(project.id)
    dataset, n_rows, comprobacion, avisos = human_layer.ingest_usage_log(
        session,
        project,
        file_bytes=contenido,
        filename=file.filename or "usage_log.csv",
        model_version=version,
        upload_dir=upload_dir,
        actor=actor,
        bus=request.app.state.bus,
        valor_favorable=valor_favorable,
        correlation_id=correlation_id,
    )
    return UsageLogUploadResponse(
        dataset_id=dataset.id,
        n_rows=n_rows,
        # Lo que rigió en la subida: `refer` si no se declaró (clasificación), nulo en regresión.
        valor_favorable=(dataset.mapping_json or {}).get("valor_favorable"),
        comprobacion_codificacion=comprobacion,
        avisos=avisos,
    )


@router.get("/projects/{project_id}/usage-logs/export.csv")
def export_usage_log(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """CSV del diario de uso acumulado del proyecto."""
    project = projects_service.get_project(session, project_id)
    contenido = human_layer.export_usage_csv(session, project)
    return Response(
        content=contenido,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=usage_log.csv"},
    )


@router.post("/projects/{project_id}/cross/evaluate", response_model=JobAccepted)
def trigger_cross_evaluate(
    project_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> JobAccepted:
    """Encola la evaluación de alertas cruzadas (`kind="cruzadas"`, cola `rapida`).

    Si ya hay una evaluación de cruzadas pendiente o en curso del mismo modelo,
    devuelve ese trabajo en vez de encolar otro. La petición queda en el diario
    con quien la hace (persona o agente)."""
    project = projects_service.get_project(session, project_id)
    if project.active_version_id is None:
        raise HTTPException(409, "el modelo no tiene versión activa: activa una versión en la pantalla Versiones")
    manager = request.app.state.jobs
    job = manager.enqueue(
        "cruzadas",
        "rapida",
        human_layer.run_cross_evaluation_job,
        params={
            "project_id": project.id,
            "version_id": project.active_version_id,
            "trigger": "manual",
        },
        project_id=project.id,
        correlation_id=correlation_id,
        clave_dedup=f"cruzadas:proyecto:{project.id}",
    )
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="cruzadas.solicitadas",
        object_type="project",
        object_id=project.id,
        project_id=project.id,
        after={"trigger": "manual", "model_version_id": project.active_version_id},
        correlation_id=correlation_id,
        job_id=job.id,
        bus=request.app.state.bus,
    )
    session.commit()
    return JobAccepted(**_job_to_dict(job))


@router.get("/projects/{project_id}/deskilling", response_model=DeskillingResponse)
def get_deskilling(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    clinician: str | None = None,
    subgroup: str | None = None,
    model_version_id: int | None = None,
    n_windows: int = 4,
) -> DeskillingResponse:
    """Deskilling: ventanas, tendencias y señal sobre el diario de
    uso de una única versión de modelo (por defecto la activa)."""
    if not 1 <= n_windows <= 12:
        raise HTTPException(422, "el número de ventanas debe estar entre 1 y 12")
    project, version = _resolver_version(session, project_id, model_version_id)
    motivo_regresion = tarea_service.motivo_capa_humana(project)
    if motivo_regresion is not None:
        # el deskilling de una regresión no pasa por el camino binario.
        return DeskillingResponse(
            sin_datos=True,
            motivo=motivo_regresion,
            model_version_id=version.id,
            model_version_label=version.label,
            clinician=clinician,
            subgroup=subgroup,
            n_windows=n_windows,
            windows=[],
            trends=None,
            signal=None,
            summary_md=None,
            min_n=ir_adapter.MIN_N,
            ventanas_excluidas=0,
            eps=ir_adapter.EPS,
            package_version=ir_adapter.PACKAGE_VERSION,
            filas_excluidas_fecha=0,
        )
    resultado = ir_adapter.deskilling_view(
        session, project.id, version, clinician=clinician, subgroup=subgroup, n_windows=n_windows
    )
    return DeskillingResponse(
        sin_datos=resultado.sin_datos,
        motivo=resultado.motivo,
        model_version_id=version.id,
        model_version_label=version.label,
        clinician=clinician,
        subgroup=subgroup,
        n_windows=n_windows,
        windows=[
            DeskillingWindowOut(
                start=w.start.isoformat(),
                end=w.end.isoformat(),
                n=w.n,
                n_with_gt=w.n_with_gt,
                agreement_rate=w.agreement_rate,
                human_accuracy=w.human_accuracy,
                model_accuracy=w.model_accuracy,
                rescue_rate=w.rescue_rate,
                excluida_de_pendiente=w.n < resultado.min_n,
            )
            for w in resultado.windows
        ],
        trends=DeskillingTrendsOut(**resultado.trends.__dict__) if resultado.trends else None,
        signal=DeskillingSignalOut(fired=resultado.signal.fired, reason=motivo_es(resultado.signal.reason))
        if resultado.signal
        else None,
        summary_md=resultado.summary_md,
        min_n=resultado.min_n,
        ventanas_excluidas=resultado.ventanas_excluidas,
        eps=ir_adapter.EPS,
        package_version=ir_adapter.PACKAGE_VERSION,
        filas_excluidas_fecha=resultado.filas_excluidas_fecha,
    )
