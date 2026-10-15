"""Ejecución del trabajo `revision_dossier`: ensambla el dossier,
corre la revisión dentro de `llm_environment` y deja la fila `dossier_review`
en `terminada` o `error`, nunca un 500. Partido de `dossiers_review.py`
(que valida y encola) por el límite de 9 KB.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from vigia.app.bus import EventBus
from vigia.app.errores import no_encontrado, texto_error_trabajo
from vigia.app.events import ACTOR_SISTEMA, record_event
from vigia.app.models import Batch, Dossier, DossierReview, now_iso
from vigia.human import dossier_adapter

__all__ = ["ejecutar_review"]


# Primer segmento de `__module__`. Los errores de la copia vendorizada de
# `interaction_review` (`vigia.human._vendor...`: `LLMNotConfigured`, los
# `RuntimeError` de `llm.py`) empiezan por `vigia` y no cuentan, igual que
# antes con `interaction_review`; los de `anthropic` y `httpx` sí.
_MODULOS_DE_PROVEEDOR = (
    "openai",
    "anthropic",
    "httpx",
    "httpcore",
    "requests",
    "urllib3",
    "ssl",
    "socket",
)


def _es_fallo_de_proveedor(exc: BaseException) -> bool:
    """Fallo de red o del cliente del proveedor, por tipo; un error interno no cuenta."""
    if isinstance(exc, OSError):
        return True
    return any(
        (c.__module__ or "").split(".")[0] in _MODULOS_DE_PROVEEDOR for c in type(exc).__mro__
    )


def _texto_error_revision(exc: BaseException, *, en_proveedor: bool) -> str:
    """`fila.error` de una revisión fallida. Un dossier inválido dice su
    motivo tal cual; un fallo durante la llamada al modelo de lenguaje va
    precedido de quién habló; el resto, el texto genérico sin texto de librería."""
    if isinstance(exc, dossier_adapter.DossierInvalido):
        return str(exc)
    if en_proveedor and _es_fallo_de_proveedor(exc):
        detalle = str(exc).strip() or exc.__class__.__name__
        return f"el proveedor del modelo de lenguaje respondió: {detalle}"
    return texto_error_trabajo(exc, "revision_dossier")


def ejecutar_review(
    job_session: Session,
    review_id: int,
    *,
    approach: str,
    corpus: str,
    dedup: bool,
    incluir_crosswalk: bool,
    backend: str,
    llm_conf: dict[str, Any],
    correlation_id: str,
    job_id: int,
    bus: EventBus | None,
) -> dict[str, Any]:
    from vigia.app.services.dossiers import plantillas_preguntas

    fila = job_session.get(DossierReview, review_id)
    if fila is None:
        raise no_encontrado("revisión", review_id, "revisiones")
    dossier = job_session.get(Dossier, fila.dossier_id)
    if dossier is None:
        raise no_encontrado("dossier", fila.dossier_id, "dossiers")
    fila.status = "en_curso"
    job_session.add(fila)
    job_session.commit()

    md = dossier_adapter.assemble_markdown(
        profile=dossier.profile_json or {},
        experience=dossier.experience_json or {},
        inventory=dossier.inventory_json or {},
        telemetry_text=dossier.telemetry_text,
        preguntas_por_formulario=plantillas_preguntas(),
    )
    # Referencia de línea base del proyecto: el mismo lote de
    # `seq` mínimo que `ProjectState.first_batch`, para que la revisión diga
    # contra qué se comparó todo lo que cuenta el dossier.
    primer_batch = job_session.exec(
        select(Batch)
        .where(Batch.project_id == dossier.project_id)
        .order_by(Batch.seq.asc())  # type: ignore[attr-defined]
        .limit(1)
    ).first()
    baseline_batch = (
        {"id": primer_batch.id, "seq": primer_batch.seq, "phase_label": primer_batch.phase_label}
        if primer_batch is not None
        else None
    )

    en_proveedor = False
    try:
        dossier_obj = dossier_adapter.assemble_dossier(
            md,
            telemetry_text=dossier.telemetry_text,
            system_name=dossier.system_name,
            domain=dossier.domain,
            baseline_batch=baseline_batch,
        )
        with dossier_adapter.llm_environment(
            backend=backend,
            model=llm_conf.get("model", ""),
            base_url=llm_conf.get("base_url", ""),
            api_key=llm_conf.get("api_key", ""),
        ):
            en_proveedor = approach != "b0"
            resultado = dossier_adapter.run_review(
                dossier_obj,
                approach=approach,
                corpus=corpus,
                dedup=dedup,
                incluir_crosswalk=incluir_crosswalk,
            )
    except Exception as exc:  # noqa: BLE001 - cualquier fallo del paquete es "error", nunca un 500
        fila.status = "error"
        fila.error = _texto_error_revision(exc, en_proveedor=en_proveedor)
        fila.finished_at = now_iso()
        job_session.add(fila)
        record_event(
            job_session,
            actor_kind=ACTOR_SISTEMA[0],
            actor_id=ACTOR_SISTEMA[1],
            action="dossier.revision_terminada",
            object_type="dossier_review",
            object_id=review_id,
            project_id=dossier.project_id,
            after={"dossier_id": dossier.id, "status": "error", "n_findings": None},
            correlation_id=correlation_id,
            job_id=job_id,
            bus=bus,
        )
        job_session.commit()
        return {"status": "error", "error": fila.error, "review_id": fila.id}

    fila.status = "terminada"
    fila.findings_json = resultado.findings
    fila.crosswalk_json = resultado.crosswalk
    fila.report_html = resultado.report_html
    fila.package_version = dossier_adapter.PACKAGE_VERSION
    fila.corpus_hash = resultado.corpus_hash
    fila.dossier_sha256 = dossier.sha256
    fila.prompt_sha256 = resultado.prompt_sha256
    fila.llm_backend = backend if approach != "b0" else None
    fila.model = resultado.model
    fila.finished_at = now_iso()
    job_session.add(fila)
    record_event(
        job_session,
        actor_kind=ACTOR_SISTEMA[0],
        actor_id=ACTOR_SISTEMA[1],
        action="dossier.revision_terminada",
        object_type="dossier_review",
        object_id=review_id,
        project_id=dossier.project_id,
        after={"dossier_id": dossier.id, "status": "terminada", "n_findings": resultado.n_findings},
        correlation_id=correlation_id,
        job_id=job_id,
        bus=bus,
    )
    job_session.commit()
    return {"status": "terminada", "n_findings": resultado.n_findings, "review_id": fila.id}
