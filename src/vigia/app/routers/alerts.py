"""Alertas, acciones y protocolo."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlmodel import Session, select

from vigia.app.db import get_session
from vigia.app.errores import no_encontrado
from vigia.app.events import Actor, get_actor, get_correlation_id
from vigia.app.models import Alert, AlertAction, Project
from vigia.app.schemas import respuestas as resp
from vigia.app.schemas.alerts import (
    AlertActionBody,
    AlertDecideBody,
    AlertInvestigateBody,
    AlertsBulkBody,
    ProtocolBody,
)
from vigia.app.schemas.common import ActorBody
from vigia.app.services import alerting, protocol_steps
from vigia.app.services.alert_series import alert_series
from vigia.app.services.projects import MONITORES_POR_DEFECTO

router = APIRouter(tags=["alertas"])


def _bus(request: Request):
    return request.app.state.bus


def _get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise no_encontrado("modelo", project_id, "modelos")
    return project


def _get_alert(session: Session, alert_id: int) -> Alert:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise no_encontrado("alerta", alert_id, "alertas")
    return alert


# El catálogo debe declararse antes de `/alerts/{alert_id}` para que la ruta
# estática no colisione con la dinámica.
@router.get("/alerts/catalog", response_model=resp.ListResponse[resp.AlertCatalogItem])
def read_catalog() -> dict:
    """Catálogo de acciones de alerta con su etiqueta en español."""
    return {"items": alerting.catalog(), "total": len(alerting.ETIQUETAS_ACCION)}


@router.get("/projects/{project_id}/alerts", response_model=resp.ListResponse[resp.Alert])
def list_alerts(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    status: str | None = None,
    severity: str | None = None,
    monitor_type: str | None = None,
    offset: int = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Alertas del proyecto, filtradas por estado, severidad y monitor (varios, separados por coma).

    Una severidad que no esté en `alerting.SEVERIDADES_ALERTA`, o un monitor que
    no esté en `MONITORES_POR_DEFECTO`, es 422: el filtro de la UI no debe poder
    vaciar la lista por una errata (`monitor_type`).
    """
    project = _get_project(session, project_id)
    consulta = select(Alert).where(Alert.project_id == project.id)
    estados = [s.strip() for s in (status or "").split(",") if s.strip()]
    if estados:
        consulta = consulta.where(Alert.status.in_(estados))  # type: ignore[attr-defined]
    else:
        # las retiradas (su lote se borró) solo salen si se piden.
        consulta = consulta.where(Alert.status != "retirada")
    if severity:
        severidades = [s.strip() for s in severity.split(",") if s.strip()]
        desconocidas = [s for s in severidades if s not in alerting.SEVERIDADES_ALERTA]
        if desconocidas:
            raise HTTPException(
                422,
                f"severidad no reconocida: {', '.join(desconocidas)}; "
                f"válidas: {', '.join(alerting.SEVERIDADES_ALERTA)}",
            )
        if severidades:
            consulta = consulta.where(Alert.severity.in_(severidades))  # type: ignore[attr-defined]
    if monitor_type:
        monitores = [m.strip() for m in monitor_type.split(",") if m.strip()]
        desconocidos = [m for m in monitores if m not in MONITORES_POR_DEFECTO]
        if desconocidos:
            raise HTTPException(
                422,
                f"monitor no reconocido: {', '.join(desconocidos)}; "
                f"válidos: {', '.join(MONITORES_POR_DEFECTO)}",
            )
        if monitores:
            consulta = consulta.where(Alert.monitor_type.in_(monitores))  # type: ignore[attr-defined]
    # Total por COUNT en SQL, no cargando las filas completas (con su
    # history_json) solo para contarlas.
    total = session.exec(
        select(func.count()).select_from(consulta.subquery())
    ).one()
    filas = session.exec(
        consulta.order_by(Alert.opened_at.desc()).offset(offset).limit(limit)  # type: ignore[attr-defined]
    ).all()
    return {"items": alerting.alerts_to_dict(session, list(filas)), "total": total}


@router.get("/projects/{project_id}/alerts/series", response_model=resp.AlertSeriesResponse)
def read_alert_series(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    granularity: str = "batch",
    since: str | None = None,
    until: str | None = None,
    tz: str = "Europe/Paris",
) -> dict:
    """Evolución de alertas por lote, día u hora para el panel del cuadro.

    Sin parámetros obligatorios: `granularity=batch` y `tz=Europe/Paris` por
    defecto, así el contrato de `test_contrato.py` la recorre sin más.
    """
    project = _get_project(session, project_id)
    return alert_series(session, project, granularity=granularity, since=since, until=until, tz=tz)


@router.post("/projects/{project_id}/alerts/bulk", response_model=resp.AlertsBulkResult)
def bulk_alert_action(
    project_id: int,
    body: AlertsBulkBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Acción en lote sobre alertas del proyecto: `acknowledge`, `close` o una
    clave del catálogo de acciones. Mismo motivo y mismo `correlation_id`
    para todas; una alerta que no admite la acción se salta sin romper el lote."""
    project = _get_project(session, project_id)
    return alerting.bulk_action(
        session,
        project,
        alert_ids=body.alert_ids,
        action=body.action,
        actor=body.actor,
        actor_kind=actor.kind,
        role=body.role,
        motivo=body.motivo,
        bus=_bus(request),
    )


@router.get("/alerts/{alert_id}", response_model=resp.AlertDetail)
def read_alert(alert_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Una alerta con sus acciones, su historial y los hitos de su protocolo."""
    alert = _get_alert(session, alert_id)
    acciones = session.exec(
        select(AlertAction).where(AlertAction.alert_id == alert.id).order_by(AlertAction.ts)  # type: ignore[arg-type]
    ).all()
    data = alerting.alert_to_dict(session, alert)
    data["actions"] = [
        {
            "id": a.id,
            "action": a.action,
            "actor": a.actor,
            "role": a.role,
            "motivo": a.motivo,
            "attachment_path": a.attachment_path,
            "ts": a.ts,
        }
        for a in acciones
    ]
    data["protocol_steps"] = protocol_steps.protocol_steps_for_alert(session, alert)
    return data


@router.post("/alerts/{alert_id}/acknowledge", response_model=resp.Alert)
def acknowledge_alert(
    alert_id: int,
    body: ActorBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Reconoce una alerta abierta."""
    alert = _get_alert(session, alert_id)
    alert = alerting.acknowledge(
        session,
        alert,
        actor=body.actor,
        actor_kind=actor.kind,
        role=body.role,
        motivo=body.motivo,
        correlation_id=correlation_id,
        bus=_bus(request),
    )
    return alerting.alert_to_dict(session, alert)


@router.post("/alerts/{alert_id}/investigate", response_model=resp.Alert)
def investigate_alert(
    alert_id: int,
    body: AlertInvestigateBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Registra la investigación de una alerta (hito 3): el triaje ya
    tiene que estar hecho; no cambia el estado del motor."""
    alert = _get_alert(session, alert_id)
    alert = alerting.investigate(
        session,
        alert,
        actor=body.actor,
        actor_kind=actor.kind,
        role=body.role,
        motivo=body.motivo,
        hallazgos=body.hallazgos,
        correlation_id=correlation_id,
        bus=_bus(request),
    )
    return alerting.alert_to_dict(session, alert)


@router.post("/alerts/{alert_id}/decide", response_model=resp.Alert)
def decide_alert(
    alert_id: int,
    body: AlertDecideBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Registra la decisión de una alerta (hito 4): al menos una acción
    del catálogo de acciones; la investigación ya tiene que estar registrada."""
    alert = _get_alert(session, alert_id)
    alert = alerting.decide(
        session,
        alert,
        actor=body.actor,
        actor_kind=actor.kind,
        role=body.role,
        motivo=body.motivo,
        acciones=[accion.model_dump() for accion in body.acciones],
        correlation_id=correlation_id,
        bus=_bus(request),
    )
    return alerting.alert_to_dict(session, alert)


@router.post("/alerts/{alert_id}/close", response_model=resp.Alert)
def close_alert(
    alert_id: int,
    body: ActorBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Cierra una alerta (en cualquier estado no cerrado). Exige actor y motivo."""
    alert = _get_alert(session, alert_id)
    alert = alerting.close(
        session,
        alert,
        actor=body.actor,
        actor_kind=actor.kind,
        role=body.role,
        motivo=body.motivo,
        correlation_id=correlation_id,
        bus=_bus(request),
    )
    return alerting.alert_to_dict(session, alert)


@router.post("/alerts/{alert_id}/actions", response_model=resp.Alert)
def act_on_alert(
    alert_id: int,
    body: AlertActionBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Registra una acción del catálogo de acciones sobre una alerta."""
    alert = _get_alert(session, alert_id)
    alert = alerting.act(
        session,
        alert,
        action=body.action,
        actor=body.actor,
        actor_kind=actor.kind,
        role=body.role,
        motivo=body.motivo,
        attachment_path=body.attachment_path,
        correlation_id=correlation_id,
        bus=_bus(request),
    )
    return alerting.alert_to_dict(session, alert)


@router.put("/alerts/{alert_id}/protocol", response_model=resp.Alert)
def set_alert_protocol(
    alert_id: int,
    body: ProtocolBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Edita el protocolo (`protocolo_md`) de una alerta."""
    alert = _get_alert(session, alert_id)
    alert = alerting.set_protocol(
        session,
        alert,
        actor=body.actor,
        actor_kind=actor.kind,
        role=body.role,
        motivo=body.motivo,
        protocolo_md=body.protocolo_md,
        correlation_id=correlation_id,
        bus=_bus(request),
    )
    return alerting.alert_to_dict(session, alert)
