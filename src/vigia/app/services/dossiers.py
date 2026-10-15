"""Servicio del dossier de auditoría: crear un dossier con
las respuestas de los tres formularios de `interaction_review` y consultarlo.
Lanzar la revisión (job de la cola `rapida`/`llm`) vive en
`services/dossiers_review.py`.

Junto a `human/dossier_adapter.py` y `human/ir_adapter.py`, es de los pocos
sitios que tocan datos de la capa humana: las respuestas viven solo en la
fila `dossier`, nunca en el diario.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from vigia.app.bus import EventBus
from vigia.app.errores import no_encontrado
from vigia.app.events import Actor, record_event
from vigia.app.models import Dossier, DossierReview, ModelVersion, Project
from vigia.app.schemas.common import ActorBody, ListResponse
from vigia.app.schemas.dossiers import DossierCreateBody, DossierImportBody
from vigia.human import dossier_adapter, dossier_import, informe_revision, ir_adapter

__all__ = [
    "create_dossier",
    "get_dossier",
    "import_dossier",
    "informe_html",
    "list_dossiers",
    "plantillas_preguntas",
]


@lru_cache(maxsize=1)
def _plantillas_json() -> dict[str, Any]:
    ref = resources.files("vigia.content").joinpath("dossier-plantillas.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def plantillas_preguntas() -> dict[str, list[dict[str, str]]]:
    """`{clave: [preguntas]}` de las tres plantillas, para reconstruir el
    markdown (`dossier_adapter.assemble_markdown`)."""
    return {clave: valor["preguntas"] for clave, valor in _plantillas_json().items()}


def _dossier_a_dict(fila: Dossier) -> dict[str, Any]:
    return {
        "id": fila.id,
        "project_id": fila.project_id,
        "system_name": fila.system_name,
        "domain": fila.domain,
        "profile": fila.profile_json or {},
        "experience": fila.experience_json or {},
        "inventory": fila.inventory_json or {},
        "telemetry_included": fila.telemetry_included,
        "summary": fila.summary,
        "sha256": fila.sha256,
        "created_at": fila.created_at,
    }


def review_a_resumen(fila: DossierReview) -> dict[str, Any]:
    n_findings = len(fila.findings_json) if isinstance(fila.findings_json, list) else None
    return {
        "id": fila.id,
        "dossier_id": fila.dossier_id,
        "approach": fila.approach,
        "status": fila.status,
        "n_findings": n_findings,
        "package_version": fila.package_version,
        "job_id": fila.job_id,
        "error": fila.error,
        "created_at": fila.created_at,
        "finished_at": fila.finished_at,
    }


def _telemetria(session: Session, project: Project, incluir: bool) -> tuple[str | None, bool]:
    """Resumen de deskilling para anexar al dossier, si se pidió y hay datos."""
    if not incluir or project.active_version_id is None:
        return None, False
    version = session.get(ModelVersion, project.active_version_id)
    if version is None:
        return None, False
    resultado = ir_adapter.deskilling_view(session, project.id, version)
    if resultado.sin_datos or not resultado.summary_md:
        return None, False
    return resultado.summary_md, True


def _guardar_dossier(
    session: Session,
    project: Project,
    *,
    system_name: str,
    domain: str,
    profile: dict[str, str],
    experience: dict[str, str],
    inventory: dict[str, str],
    summary: str,
    telemetry_text: str | None,
    telemetry_included: bool,
    sha256: str,
    body: ActorBody,
    actor: Actor,
    correlation_id: str | None,
    bus: EventBus | None,
    extra_after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fila `dossier` y evento `dossier.creado` sin las respuestas en claro;
    lo comparten el alta normal y la importación de `dossier.json`."""
    fila = Dossier(
        project_id=project.id,
        system_name=system_name,
        domain=domain,
        profile_json=profile,
        experience_json=experience,
        inventory_json=inventory,
        telemetry_included=telemetry_included,
        telemetry_text=telemetry_text,
        summary=summary,
        sha256=sha256,
        actor=actor.id,
        role=actor.role,
        motivo=body.motivo,
    )
    session.add(fila)
    session.flush()
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="dossier.creado",
        object_type="dossier",
        object_id=fila.id,
        project_id=project.id,
        motivo=body.motivo,
        after={
            "system_name": system_name,
            "domain": domain,
            "telemetry_included": telemetry_included,
            **(extra_after or {}),
        },
        correlation_id=correlation_id,
        bus=bus,
    )
    session.commit()
    session.refresh(fila)
    return _dossier_a_dict(fila)


def create_dossier(
    session: Session,
    project: Project,
    body: DossierCreateBody,
    *,
    actor: Actor,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
) -> dict[str, Any]:
    """Crea un dossier: al menos un formulario con una respuesta no
    en blanco, telemetría opcional de deskilling, evento `dossier.creado` sin las
    respuestas en claro."""
    system_name = (body.system_name or project.name or "").strip() or project.name
    domain = (body.domain or project.domain or "").strip() or project.domain
    telemetry_text, telemetry_included = _telemetria(session, project, body.include_telemetry)

    md = dossier_adapter.assemble_markdown(
        profile=body.profile,
        experience=body.experience,
        inventory=body.inventory,
        telemetry_text=telemetry_text,
        preguntas_por_formulario=plantillas_preguntas(),
    )
    try:
        dossier_adapter.assemble_dossier(
            md, telemetry_text=telemetry_text, system_name=system_name, domain=domain
        )
    except ValueError as exc:
        raise HTTPException(422, "rellena al menos una respuesta en algún formulario") from exc

    return _guardar_dossier(
        session,
        project,
        system_name=system_name,
        domain=domain,
        profile=body.profile,
        experience=body.experience,
        inventory=body.inventory,
        summary="",
        telemetry_text=telemetry_text,
        telemetry_included=telemetry_included,
        sha256=md.sha256,
        body=body,
        actor=actor,
        correlation_id=correlation_id,
        bus=bus,
    )


def import_dossier(
    session: Session,
    project: Project,
    body: DossierImportBody,
    *,
    actor: Actor,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
) -> dict[str, Any]:
    """Importa el `dossier.json` de `interaction_review`: lo valida
    con el `Dossier` del paquete, agrupa las fuentes por `kind` en las tres
    plantillas y deja `summary` y lo que no encaje en claves propias de
    `profile`. Mismo evento que el alta normal, con el actor de la petición.
    422 en español con el campo que falla."""
    datos = {
        "system_name": body.system_name,
        "domain": body.domain,
        "summary": body.summary,
        "sources": [f.model_dump() for f in body.sources],
    }
    try:
        dossier_adapter.validar_dossier_importado(datos)
    except dossier_adapter.DossierInvalido as exc:
        raise HTTPException(422, str(exc)) from exc

    agrupado = dossier_import.agrupar_fuentes(summary=body.summary, sources=datos["sources"])
    system_name = body.system_name.strip() or project.name
    domain = body.domain.strip() or project.domain
    telemetry_text, telemetry_included = _telemetria(session, project, body.include_telemetry)

    md = dossier_adapter.assemble_markdown(
        profile=agrupado.profile,
        experience=agrupado.experience,
        inventory=agrupado.inventory,
        telemetry_text=telemetry_text,
        preguntas_por_formulario=plantillas_preguntas(),
    )
    return _guardar_dossier(
        session,
        project,
        system_name=system_name,
        domain=domain,
        profile=agrupado.profile,
        experience=agrupado.experience,
        inventory=agrupado.inventory,
        summary=body.summary,
        telemetry_text=telemetry_text,
        telemetry_included=telemetry_included,
        sha256=md.sha256,
        body=body,
        actor=actor,
        correlation_id=correlation_id,
        bus=bus,
        extra_after={"origen": "dossier.json", "n_fuentes": len(body.sources)},
    )


def informe_html(session: Session, fila: DossierReview, *, modo: str = "auto") -> str:
    """Informe de una revisión terminada, redibujado al leer: las
    revisiones guardadas anteriores salen también en español y con el tema,
    sin migración. `report_html` de la fila queda como respaldo."""
    dossier = session.get(Dossier, fila.dossier_id)
    n_fuentes: int | None = None
    if dossier is not None:
        md = dossier_adapter.assemble_markdown(
            profile=dossier.profile_json or {},
            experience=dossier.experience_json or {},
            inventory=dossier.inventory_json or {},
            telemetry_text=dossier.telemetry_text,
            preguntas_por_formulario=plantillas_preguntas(),
        )
        try:
            n_fuentes = len(
                dossier_adapter.assemble_dossier(
                    md, telemetry_text=dossier.telemetry_text, system_name=dossier.system_name, domain=dossier.domain
                ).sources
            )
        except ValueError:
            n_fuentes = None
    return informe_revision.desde_guardada(
        system_name=dossier.system_name if dossier else "",
        domain=dossier.domain if dossier else "",
        approach=fila.approach,
        findings_json=fila.findings_json or [],
        incluir_crosswalk=bool(fila.crosswalk_json),
        n_fuentes=n_fuentes,
        fecha=fila.finished_at,
        version_paquete=fila.package_version,
        modelo=fila.model,
        modo=modo,
    )


def list_dossiers(session: Session, project: Project) -> ListResponse:
    filas = session.exec(
        select(Dossier).where(Dossier.project_id == project.id).order_by(Dossier.created_at.desc())
    ).all()
    items = [_dossier_a_dict(f) for f in filas]
    return ListResponse(items=items, total=len(items))


def get_dossier_row(session: Session, dossier_id: int) -> Dossier:
    fila = session.get(Dossier, dossier_id)
    if fila is None:
        raise no_encontrado("dossier", dossier_id, "dossiers")
    return fila


def get_dossier(session: Session, dossier_id: int) -> dict[str, Any]:
    fila = get_dossier_row(session, dossier_id)
    revisiones = session.exec(
        select(DossierReview)
        .where(DossierReview.dossier_id == dossier_id)
        .order_by(DossierReview.created_at.desc())
    ).all()
    return {**_dossier_a_dict(fila), "reviews": [review_a_resumen(r) for r in revisiones]}
