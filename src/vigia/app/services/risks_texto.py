"""Textos compuestos del historial de riesgos.

El backend compone la frase una vez, para que frontend y MCP lean la misma
(igual que `titulo_evento`). Separado de `services/risks.py` para mantener
cada fichero por debajo de 9 KB.
"""

from __future__ import annotations

from sqlmodel import Session

from vigia.app.models import Alert, Risk, RiskMovement
from vigia.app.services import alerting
from vigia.human import risk_levels

__all__ = ["kind_de_movimiento", "movement_to_dict"]


def kind_de_movimiento(mov: RiskMovement) -> str:
    """`alta|celda|estado|cierre` según qué campos cambia la fila."""
    if mov.to_status == "cerrado":
        return "cierre"
    if mov.to_status == "en_seguimiento":
        return "estado"
    if mov.from_impact is None and mov.from_status is None:
        return "alta"
    return "celda"


def _texto_alta(session: Session, risk: Risk) -> str:
    if risk.origin_alert_id is None:
        return f"{risk.code} nuevo · Creado a mano"
    monitor_label = risk_levels.MONITOR_LABELS.get(risk.monitor_type or "", risk.monitor_type or "?")
    base = f"{risk.code} nuevo · Creado desde la alerta de {monitor_label}"
    alerta = session.get(Alert, risk.origin_alert_id)
    if alerta is None or alerta.last_evaluation_id is None:
        return base
    lote = alerting._lote_de_evaluaciones(session, {alerta.last_evaluation_id}).get(
        alerta.last_evaluation_id
    )
    if lote is None or lote[1] is None:
        return base
    return f"{base} del lote #{lote[1] + 1}"


def _texto_celda(code: str, mov: RiskMovement) -> str:
    assert mov.from_impact is not None
    assert mov.from_probability is not None
    assert mov.to_impact is not None
    assert mov.to_probability is not None
    nivel_from = risk_levels.nivel(mov.from_impact, mov.from_probability)
    nivel_to = risk_levels.nivel(mov.to_impact, mov.to_probability)
    orden_from = risk_levels.ORDEN_NIVEL[nivel_from]
    orden_to = risk_levels.ORDEN_NIVEL[nivel_to]
    if orden_to > orden_from:
        verbo = "subió"
    elif orden_to < orden_from:
        verbo = "bajó"
    else:
        verbo = "movido"
    impacto_from = risk_levels.IMPACTO_LABELS[mov.from_impact]
    prob_from = risk_levels.PROBABILIDAD_LABELS[mov.from_probability]
    impacto_to = risk_levels.IMPACTO_LABELS[mov.to_impact]
    prob_to = risk_levels.PROBABILIDAD_LABELS[mov.to_probability]
    return (
        f"{code} {verbo} · {impacto_from}×{prob_from} → "
        f"{impacto_to}×{prob_to} · {mov.motivo}"
    )


def _texto_estado(code: str, mov: RiskMovement) -> str:
    return f"{code} en seguimiento · {mov.motivo}"


def _texto_cierre(code: str, mov: RiskMovement) -> str:
    return f"{code} cerrado · {mov.motivo}"


def texto_movimiento(session: Session, risk: Risk, mov: RiskMovement) -> str:
    """Frase compuesta de una fila de `RiskMovement`, según su tipo."""
    kind = kind_de_movimiento(mov)
    if kind == "alta":
        return _texto_alta(session, risk)
    if kind == "celda":
        return _texto_celda(risk.code, mov)
    if kind == "estado":
        return _texto_estado(risk.code, mov)
    return _texto_cierre(risk.code, mov)


def movement_to_dict(session: Session, risk: Risk, mov: RiskMovement) -> dict:
    """Fila de `RiskMovementTexto`: código, tipo y texto ya compuestos."""
    return {
        "id": mov.id,
        "risk_id": mov.risk_id,
        "code": risk.code,
        "kind": kind_de_movimiento(mov),
        "texto": texto_movimiento(session, risk, mov),
        "actor": mov.actor,
        "role": mov.role,
        "motivo": mov.motivo,
        "created_at": mov.created_at,
        "from_impact": mov.from_impact,
        "from_probability": mov.from_probability,
        "to_impact": mov.to_impact,
        "to_probability": mov.to_probability,
        "from_status": mov.from_status,
        "to_status": mov.to_status,
    }
