"""Mutaciones de la matriz de riesgos.

Alta desde alerta o a mano, movimiento de celda, paso a en_seguimiento y
cierre (terminal). El listado, la serialización y el historial viven en
`risks_data.py`.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session

from vigia.app.bus import EventBus
from vigia.app.errores import no_encontrado
from vigia.app.events import Actor, record_event
from vigia.app.models import Alert, Project, Risk, RiskMovement, now_iso
from vigia.app.schemas.risks import RiskCloseBody, RiskCreateBody, RiskMoveBody, RiskStatusBody
from vigia.app.services.alerting import ESTADOS_ALERTA_FUERA
from vigia.app.services.risks_data import comprobar_propuesta, insertar_con_codigo
from vigia.human import risk_levels

__all__ = ["close_risk", "create_risk", "move_risk", "set_status"]


def create_risk(
    session: Session,
    project: Project,
    body: RiskCreateBody,
    *,
    actor: Actor,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
) -> Risk:
    """Alta de un riesgo: desde una alerta (`origin_alert_id`) o a mano."""
    alerta: Alert | None = None
    monitor_type: str | None = None
    propuesta_alerta: tuple[int, int] | None = None
    if body.origin_alert_id is not None:
        alerta = session.get(Alert, body.origin_alert_id)
        if alerta is None or alerta.project_id != project.id:
            raise no_encontrado("alerta", body.origin_alert_id, "alertas")
        if alerta.status in ESTADOS_ALERTA_FUERA:
            # un riesgo nace de una alerta viva, no de una ya cerrada o retirada.
            raise HTTPException(
                409,
                f"la alerta {alerta.id} está {alerta.status}: no se puede abrir un riesgo desde ella",
            )
        monitor_type = alerta.monitor_type
        propuesta = risk_levels.PROPUESTA_POR_MONITOR.get((alerta.monitor_type, alerta.severity))
        if propuesta is None:
            raise HTTPException(
                422,
                "sin propuesta de impacto/probabilidad para monitor "
                f"{alerta.monitor_type!r} y severidad {alerta.severity!r}",
            )
        propuesta_alerta = propuesta
        impact_level = body.impact_level if body.impact_level is not None else propuesta[0]
        probability_level = (
            body.probability_level if body.probability_level is not None else propuesta[1]
        )
    else:
        if body.impact_level is None or body.probability_level is None:
            raise HTTPException(
                422, "impact_level y probability_level son obligatorios sin alerta de origen"
            )
        impact_level = body.impact_level
        probability_level = body.probability_level

    traza_propuesta = comprobar_propuesta(propuesta_alerta, impact_level, probability_level, body.motivo)
    nivel_final = risk_levels.nivel(impact_level, probability_level)
    riesgo = insertar_con_codigo(
        session,
        project.id,
        impact_level=impact_level,
        probability_level=probability_level,
        level=nivel_final,
        title=body.title,
        description=body.description,
        origin_alert_id=alerta.id if alerta is not None else None,
        monitor_type=monitor_type,
        status="abierto",
    )
    code = riesgo.code
    session.add(
        RiskMovement(
            risk_id=riesgo.id,
            to_impact=impact_level,
            to_probability=probability_level,
            actor=actor.id,
            role=actor.role,
            motivo=body.motivo,
            correlation_id=correlation_id,
        )
    )
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="riesgo.creado",
        object_type="risk",
        object_id=riesgo.id,
        project_id=project.id,
        motivo=body.motivo,
        correlation_id=correlation_id,
        after={
            "code": code,
            "impact_level": impact_level,
            "probability_level": probability_level,
            "level": nivel_final,
            "origin_alert_id": riesgo.origin_alert_id,
            **traza_propuesta,
        },
        bus=bus,
    )
    session.commit()
    session.refresh(riesgo)
    return riesgo


def move_risk(
    session: Session,
    risk: Risk,
    body: RiskMoveBody,
    *,
    actor: Actor,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
) -> Risk:
    """Mueve un riesgo a otra celda de la matriz."""
    if risk.status == "cerrado":
        raise HTTPException(409, "el riesgo ya está cerrado")
    if body.impact_level == risk.impact_level and body.probability_level == risk.probability_level:
        raise HTTPException(422, "el movimiento no cambia la celda")
    from_impact, from_probability = risk.impact_level, risk.probability_level
    nuevo_nivel = risk_levels.nivel(body.impact_level, body.probability_level)
    risk.impact_level = body.impact_level
    risk.probability_level = body.probability_level
    risk.level = nuevo_nivel
    risk.updated_at = now_iso()
    session.add(risk)
    session.add(
        RiskMovement(
            risk_id=risk.id,
            from_impact=from_impact,
            from_probability=from_probability,
            to_impact=body.impact_level,
            to_probability=body.probability_level,
            actor=actor.id,
            role=actor.role,
            motivo=body.motivo,
            correlation_id=correlation_id,
        )
    )
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="riesgo.movido",
        object_type="risk",
        object_id=risk.id,
        project_id=risk.project_id,
        motivo=body.motivo,
        correlation_id=correlation_id,
        after={
            "from_impact": from_impact,
            "from_probability": from_probability,
            "to_impact": body.impact_level,
            "to_probability": body.probability_level,
            "level": nuevo_nivel,
            "code": risk.code,
        },
        bus=bus,
    )
    session.commit()
    session.refresh(risk)
    return risk


def set_status(
    session: Session,
    risk: Risk,
    body: RiskStatusBody,
    *,
    actor: Actor,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
) -> Risk:
    """Solo admite `abierto -> en_seguimiento`."""
    if body.status != "en_seguimiento" or risk.status != "abierto":
        raise HTTPException(409, "solo se admite el paso de abierto a en_seguimiento")
    from_status = risk.status
    risk.status = "en_seguimiento"
    risk.updated_at = now_iso()
    session.add(risk)
    session.add(
        RiskMovement(
            risk_id=risk.id,
            from_impact=risk.impact_level,
            from_probability=risk.probability_level,
            to_impact=risk.impact_level,
            to_probability=risk.probability_level,
            from_status=from_status,
            to_status="en_seguimiento",
            actor=actor.id,
            role=actor.role,
            motivo=body.motivo,
            correlation_id=correlation_id,
        )
    )
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="riesgo.en_seguimiento",
        object_type="risk",
        object_id=risk.id,
        project_id=risk.project_id,
        motivo=body.motivo,
        correlation_id=correlation_id,
        after={"code": risk.code},
        bus=bus,
    )
    session.commit()
    session.refresh(risk)
    return risk


def close_risk(
    session: Session,
    risk: Risk,
    body: RiskCloseBody,
    *,
    actor: Actor,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
) -> Risk:
    """Cierra un riesgo. Cerrar es terminal en v1."""
    if risk.status == "cerrado":
        raise HTTPException(409, "el riesgo ya está cerrado")
    from_status = risk.status
    risk.status = "cerrado"
    risk.updated_at = now_iso()
    session.add(risk)
    session.add(
        RiskMovement(
            risk_id=risk.id,
            from_impact=risk.impact_level,
            from_probability=risk.probability_level,
            to_impact=risk.impact_level,
            to_probability=risk.probability_level,
            from_status=from_status,
            to_status="cerrado",
            actor=actor.id,
            role=actor.role,
            motivo=body.motivo,
            correlation_id=correlation_id,
        )
    )
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="riesgo.cerrado",
        object_type="risk",
        object_id=risk.id,
        project_id=risk.project_id,
        motivo=body.motivo,
        correlation_id=correlation_id,
        after={"code": risk.code},
        bus=bus,
    )
    session.commit()
    session.refresh(risk)
    return risk
