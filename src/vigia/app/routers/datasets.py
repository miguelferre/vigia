"""Subida, mapeo e ingesta de datos."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlmodel import Session, select

from vigia.app.db import get_session
from vigia.app.errores import no_encontrado, texto_error_trabajo
from vigia.app.events import Actor, get_actor, get_correlation_id
from vigia.app.jobs import JobContext
from vigia.app.models import Batch, Dataset, Job, ModelVersion, Project
from vigia.app.schemas import respuestas as resp
from vigia.app.schemas.common import ActorBody
from vigia.app.schemas.datasets import IngestBody, MappingBody
from vigia.app.services import explain as explain_service
from vigia.app.services import ingest, reevaluar_tardias
from vigia.app.services.subidas import leer_subida
from vigia.core.schema import DatosNoValidos

router = APIRouter(tags=["datos"])


def _bus(request: Request):
    return request.app.state.bus


def _get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise no_encontrado("modelo", project_id, "modelos")
    return project


def _get_dataset(session: Session, dataset_id: int) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise no_encontrado("fichero de datos", dataset_id, "ficheros de datos")
    return dataset


def _get_batch(session: Session, batch_id: int) -> Batch:
    batch = session.get(Batch, batch_id)
    if batch is None:
        raise no_encontrado("lote", batch_id, "lotes")
    return batch


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


# ---------------------------------------------------------------------------
# Subida y mapeo
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/datasets/upload", response_model=resp.DatasetUpload)
def upload_dataset(
    project_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()],
    role: Annotated[str, Form()],
    name: Annotated[str | None, Form()] = None,
) -> dict:
    """Sube un fichero, detecta su formato y calcula privacidad y mapeo sugerido."""
    project = _get_project(session, project_id)
    contenido = leer_subida(file.file)
    dataset, preview = ingest.register_upload(
        session,
        project,
        file_bytes=contenido,
        filename=file.filename or "dataset",
        kind=kind,
        role=role,
        name=name,
        data_dir=request.app.state.settings.data_dir,
        actor=actor,
        correlation_id=correlation_id,
        bus=_bus(request),
    )
    # con `project=` la sugerencia trae la plantilla del modelo y la
    # interfaz no necesita un `GET /datasets/{id}` más.
    salida = ingest.dataset_to_dict(dataset, project=project)
    return {
        "dataset": salida,
        "preview": preview,
        "privacy_report": dataset.privacy_report_json,
        "suggested_mapping": salida["suggested_mapping"],
        # también en `dataset.dialect`; aquí por compatibilidad.
        "dialect": dataset.dialect_json,
    }


@router.get("/projects/{project_id}/datasets", response_model=resp.ListResponse[resp.Dataset])
def list_datasets(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Lista los datasets del proyecto (sin previsualización)."""
    _get_project(session, project_id)
    total = len(session.exec(select(Dataset).where(Dataset.project_id == project_id)).all())
    filas = session.exec(
        select(Dataset)
        .where(Dataset.project_id == project_id)
        .order_by(Dataset.id)  # type: ignore[arg-type]
        .offset(offset)
        .limit(limit)
    ).all()
    lotes_por_dataset: dict[int, int] = {}
    for dataset_id in session.exec(
        select(Batch.dataset_id).where(Batch.project_id == project_id)
    ).all():
        if dataset_id is not None:
            lotes_por_dataset[dataset_id] = lotes_por_dataset.get(dataset_id, 0) + 1
    return {
        "items": [
            ingest.dataset_to_dict(d, n_batches=lotes_por_dataset.get(d.id or 0, 0)) for d in filas
        ],
        "total": total,
    }


@router.get("/datasets/{dataset_id}", response_model=resp.Dataset)
def read_dataset(dataset_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Un dataset, sin previsualización.

    `suggested_mapping` sale rellenado desde `project.mapping_template_json`
    (lo que la plantilla no fija lo sigue proponiendo `_suggest_mapping`).
    """
    dataset = _get_dataset(session, dataset_id)
    project = session.get(Project, dataset.project_id)
    n_batches = len(session.exec(select(Batch).where(Batch.dataset_id == dataset.id)).all())
    return ingest.dataset_to_dict(dataset, project=project, n_batches=n_batches)


@router.put("/datasets/{dataset_id}/mapping", response_model=resp.Dataset)
def put_mapping(
    dataset_id: int,
    body: MappingBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Fija el mapeo de columnas y las decisiones de privacidad del dataset."""
    dataset = _get_dataset(session, dataset_id)
    dataset = ingest.set_mapping(
        session,
        dataset,
        body.mapping,
        body.privacy_decisions,
        actor=actor,
        correlation_id=correlation_id,
        bus=_bus(request),
    )
    return ingest.dataset_to_dict(dataset)


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    confirm: bool = False,
) -> None:
    """Borra un dataset subido. Exige `?confirm=true`; 409 si tiene lotes ingeridos."""
    if not confirm:
        raise HTTPException(400, "hace falta ?confirm=true para borrar un dataset")
    dataset = _get_dataset(session, dataset_id)
    ingest.delete_dataset(session, dataset, actor=actor, bus=_bus(request))


# ---------------------------------------------------------------------------
# Ingesta
# ---------------------------------------------------------------------------


@router.post("/datasets/{dataset_id}/ingest", response_model=resp.JobResumen)
def ingest_dataset_endpoint(
    dataset_id: int,
    body: IngestBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Encola la ingesta del dataset (y, si `evaluate`, la evaluación del lote resultante).

    409 si una ingesta anterior falló: ese dataset ya no tiene fichero en bruto
    (`ingest.ensure_ingestible`), hay que volver a subirlo.
    """
    dataset = _get_dataset(session, dataset_id)
    ingest.ensure_ingestible(dataset)
    project = _get_project(session, dataset.project_id)

    model_version_id = body.model_version_id or project.active_version_id
    if model_version_id is None:
        raise HTTPException(422, "el modelo no tiene versión activa: elige una versión antes de ingerir")
    version = session.get(ModelVersion, model_version_id)
    if version is None:
        raise no_encontrado("versión", model_version_id, "versiones")
    if version.project_id != dataset.project_id:
        raise HTTPException(
            422,
            f"la versión {version.id} es de otro modelo: elige una versión de este modelo",
        )

    bus = _bus(request)

    def _job_ingesta(
        ctx: JobContext,
        job_session: Session,
        *,
        dataset_id: int,
        model_version_id: int,
        phase_label: str | None,
        orden_manipulado: bool,
        motivo_manipulacion: str | None,
        mode: str | None,
        evaluate: bool,
    ) -> dict:
        ds = job_session.get(Dataset, dataset_id)
        mv = job_session.get(ModelVersion, model_version_id)
        if ds is None:
            raise no_encontrado("fichero de datos", dataset_id, "ficheros de datos")
        if mv is None:
            raise no_encontrado("versión", model_version_id, "versiones")
        resultado = ingest.ingest_dataset(
            job_session,
            ds,
            model_version=mv,
            phase_label=phase_label,
            orden_manipulado=orden_manipulado,
            motivo_manipulacion=motivo_manipulacion,
            mode=mode,
            job=ctx,
            correlation_id=ctx.correlation_id,
            bus=bus,
            actor=actor,
        )
        salida: dict[str, Any] = {
            "batch_id": resultado.batch_id,
            "n_rows": resultado.n_rows,
            "n_labeled": resultado.n_labeled,
            "n_matched": resultado.n_matched,
            "n_unmatched": resultado.n_unmatched,
            # filas de feedback con más de un registro candidato (se
            # aplicaron al lote más reciente) y, en un lote nuevo, ids que ya
            # existían (dentro del lote o en la versión). Avisos de
            # cardinalidad. Ninguno bloquea la ingesta.
            "n_ambiguos": resultado.n_ambiguos,
            "n_id_duplicados": resultado.n_id_duplicados,
            # etiquetas que no se aplicaron (línea base o ya registradas).
            "etiquetas_omitidas": resultado.etiquetas_omitidas,
            "avisos": resultado.avisos,
            "privacy_applied": resultado.privacy_applied,
            "evaluated": False,
            "baseline_congelado_automatico": resultado.linea_base_congelada,
        }
        # un fichero de etiquetas no crea lote; los que recibieron verdad
        # se reevalúan (o se avisan) con el trigger de las etiquetas tardías.
        if resultado.batch_id is None:
            return reevaluar_tardias.completar_salida(
                salida, job_session, resultado.lotes_con_verdad, evaluate=evaluate, job=ctx, bus=bus
            )
        # la línea base no se evalúa al ingerirla, aunque llegue
        # `evaluate=true`; se evalúa al confirmar los umbrales del alta o a mano.
        if evaluate and resultado.batch_id is not None and ds.role == "baseline":
            salida["evaluate_motivo"] = (
                "la línea base no se evalúa al ingerirla ni al fijar los umbrales: "
                "se evalúa al confirmar el paso «Umbrales» del alta o al pedir la evaluación del lote"
            )
            return salida
        if not (evaluate and resultado.batch_id is not None):
            return salida
        try:
            from vigia.app.services.evaluate import evaluate_batch
        except ImportError:
            salida["evaluate_motivo"] = "el servicio de evaluación no está disponible"
            return salida
        batch = job_session.get(Batch, resultado.batch_id)
        if batch is None:
            salida["evaluate_motivo"] = "el lote ha desaparecido antes de evaluarlo"
            return salida
        # explicación global automática ANTES de evaluar, si el
        # proyecto la tiene activada; nunca rompe la ingesta. El motor solo
        # calcula la estabilidad del ranking (explain_stability_ndcg) cuando
        # evaluate_batch recibe explanation=, así que hay que calcularla aquí.
        proyecto = job_session.get(Project, ds.project_id)
        explicacion = None
        if proyecto is not None:
            explicacion = explain_service.maybe_auto_explain(
                job_session, batch, mv, proyecto, job=ctx, correlation_id=ctx.correlation_id, bus=bus
            )
            if explicacion is not None:
                # la explicación ya calculada se confirma antes de evaluar, para
                # que el `rollback()` de una evaluación fallida no se la lleve.
                job_session.commit()
        try:
            evaluate_batch(
                job_session,
                batch,
                trigger="ingesta",
                job=ctx,
                correlation_id=ctx.correlation_id,
                explanation=explicacion,
            )
            salida["evaluated"] = True
        except DatosNoValidos as exc:
            # mensaje ya limpio (sin traza ni texto de scikit-learn);
            # se captura por tipo antes del genérico de abajo.
            job_session.rollback()  # ni evaluaciones ni alertas a medias
            salida["evaluate_revertida"] = True
            salida["evaluate_motivo"] = texto_error_trabajo(exc, "evaluacion")
            return salida
        except Exception as exc:  # noqa: BLE001  # el fallo de evaluación no rompe la ingesta
            job_session.rollback()  # el lote ya está confirmado; lo volcado a medias no
            salida["evaluate_revertida"] = True
            salida["evaluate_motivo"] = texto_error_trabajo(exc, "evaluacion")
            return salida
        return salida

    job = request.app.state.jobs.enqueue(
        "ingesta",
        "rapida",
        _job_ingesta,
        params={
            "dataset_id": dataset_id,
            "model_version_id": version.id,
            "phase_label": body.phase_label,
            "orden_manipulado": body.orden_manipulado,
            "motivo_manipulacion": body.motivo_manipulacion,
            "mode": body.mode,
            "evaluate": body.evaluate,
        },
        project_id=dataset.project_id,
        correlation_id=correlation_id,
    )
    return _job_to_dict(job)


# ---------------------------------------------------------------------------
# Lotes y registros
# ---------------------------------------------------------------------------


def _nombres_de_dataset(session: Session, ids: list[int | None]) -> dict[int, str]:
    """Nombre del dataset de origen por id, en una sola consulta."""
    validos = {i for i in ids if i is not None}
    if not validos:
        return {}
    filas = session.exec(select(Dataset).where(Dataset.id.in_(validos))).all()  # type: ignore[union-attr]
    return {d.id: d.name for d in filas if d.id is not None}


@router.get("/projects/{project_id}/batches", response_model=resp.ListResponse[resp.Batch])
def list_batches(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    model_version_id: int | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Lotes ingeridos del proyecto, en orden de ingesta.

    `model_version_id` deja solo los lotes de esa versión."""
    _get_project(session, project_id)
    consulta = select(Batch).where(Batch.project_id == project_id)
    if model_version_id is not None:
        consulta = consulta.where(Batch.model_version_id == model_version_id)
    total = len(session.exec(consulta).all())
    filas = session.exec(
        consulta
        .order_by(Batch.seq)  # type: ignore[arg-type]
        .offset(offset)
        .limit(limit)
    ).all()
    nombres = _nombres_de_dataset(session, [b.dataset_id for b in filas])
    return {
        "items": [ingest.batch_to_dict(b, dataset_name=nombres.get(b.dataset_id or 0)) for b in filas],
        "total": total,
    }


@router.get("/batches/{batch_id}", response_model=resp.Batch)
def read_batch(batch_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Un lote."""
    batch = _get_batch(session, batch_id)
    nombres = _nombres_de_dataset(session, [batch.dataset_id])
    return ingest.batch_to_dict(batch, dataset_name=nombres.get(batch.dataset_id or 0))


# `response_model_exclude_unset`: sin `?with_features=true`, `features` no viaja
# siquiera como `null` (lo comprueba `test_datasets.py`).
@router.get(
    "/batches/{batch_id}/records",
    response_model=resp.ListResponse[resp.Record],
    response_model_exclude_unset=True,
)
def list_records(
    batch_id: int,
    session: Annotated[Session, Depends(get_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    with_features: bool = False,
) -> dict:
    """Registros de un lote, paginados. `external_id` es el id de mapeo sin transformar.

    `group_label` sale del mapeo del dataset origen, resuelto una sola vez por
    petición (`ingest.group_labeller`); sin mapeo, `null`.
    """
    from vigia.app.models import Record

    batch = _get_batch(session, batch_id)
    total = len(session.exec(select(Record).where(Record.batch_id == batch.id)).all())
    filas = session.exec(
        select(Record)
        .where(Record.batch_id == batch.id)
        .order_by(Record.seq)  # type: ignore[arg-type]
        .offset(offset)
        .limit(limit)
    ).all()
    etiqueta = ingest.group_labeller(session, batch)
    return {
        "items": [
            ingest.record_to_dict(
                r, with_features=with_features, group_label=etiqueta(r.group_code)
            )
            for r in filas
        ],
        "total": total,
    }


@router.get("/batches/{batch_id}/composition", response_model=resp.BatchComposition)
def read_batch_composition(batch_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Composición por grupo del lote: n, tasas de favorable, etiquetadas."""
    batch = _get_batch(session, batch_id)
    return ingest.batch_composition(session, batch)


@router.delete("/batches/{batch_id}", status_code=204)
def delete_batch_endpoint(
    batch_id: int,
    body: ActorBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    confirm: bool = False,
) -> None:
    """Borra un lote. Exige `?confirm=true`; 409 si es el baseline congelado de una versión."""
    if not confirm:
        raise HTTPException(400, "hace falta ?confirm=true para borrar un lote")
    batch = _get_batch(session, batch_id)
    actor_final = Actor(kind=actor.kind, id=body.actor, role=body.role or actor.role)
    ingest.delete_batch(session, batch, actor=actor_final, motivo=body.motivo, bus=_bus(request))
