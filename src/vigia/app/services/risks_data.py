"""Lectura de la matriz de riesgos: listado, serialización
e historial. Separado de `services/risks.py` (las mutaciones) para mantener
cada fichero por debajo de 9 KB."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from vigia.app.models import Alert, Project, Risk, RiskMovement
from vigia.app.services.risks_texto import movement_to_dict
from vigia.human import risk_levels

__all__ = [
    "ESTADOS_RIESGO",
    "MAX_DIAS_MOVIMIENTOS",
    "comprobar_propuesta",
    "insertar_con_codigo",
    "list_risks",
    "movements_for_project",
    "movements_for_risk",
    "risk_to_dict",
    "siguiente_codigo",
]

ESTADOS_RIESGO: tuple[str, ...] = ("abierto", "en_seguimiento", "cerrado")

# cien años; con más, `timedelta` se desborda.
MAX_DIAS_MOVIMIENTOS = 36_500
_INTENTOS_CODIGO = 5
# longitud mínima del motivo cuando el riesgo baja de la celda propuesta.
MOTIVO_MIN_BAJADA = 15


def siguiente_codigo(session: Session, project_id: int) -> str:
    """`R-{n:03d}` con `n` = máximo número existente en el proyecto + 1.

    Un riesgo cerrado no libera su número: se parsean los códigos ya
    existentes, nunca se cuentan filas.
    """
    codigos = session.exec(select(Risk.code).where(Risk.project_id == project_id)).all()
    maximo = 0
    for codigo in codigos:
        try:
            n = int(codigo.split("-", 1)[1])
        except (IndexError, ValueError):
            continue
        maximo = max(maximo, n)
    return f"R-{maximo + 1:03d}"


def insertar_con_codigo(session: Session, project_id: int, **campos: Any) -> Risk:
    """Crea el riesgo con el siguiente código libre. Si otra alta se lleva el número
    entre el cálculo y la escritura (`uq_risk_project_code`), lo recalcula."""
    for _intento in range(_INTENTOS_CODIGO):
        riesgo = Risk(project_id=project_id, code=siguiente_codigo(session, project_id), **campos)
        try:
            with session.begin_nested():
                session.add(riesgo)
                session.flush()
            return riesgo
        except IntegrityError:
            continue
    raise HTTPException(409, "no se pudo asignar un código al riesgo: inténtalo otra vez")


def comprobar_propuesta(
    propuesta: tuple[int, int] | None, impacto: int, probabilidad: int, motivo: str
) -> dict[str, Any]:
    """bajar impacto o probabilidad por debajo de la propuesta de la alerta
    pide un motivo con contenido (422). Devuelve lo que el evento de alta añade a
    `after`: la propuesta y la marca, o nada si el alta no se aparta de ella."""
    if propuesta is None or (impacto >= propuesta[0] and probabilidad >= propuesta[1]):
        return {}
    if len(motivo.strip()) < MOTIVO_MIN_BAJADA:
        raise HTTPException(
            422,
            "el nivel elegido queda por debajo del que propone la alerta: explica el motivo "
            f"con al menos {MOTIVO_MIN_BAJADA} caracteres",
        )
    return {
        "propuesta": {"impact_level": propuesta[0], "probability_level": propuesta[1]},
        "por_debajo_de_la_propuesta": True,
    }


def list_risks(
    session: Session,
    project: Project,
    *,
    status: str | None = None,
    impact: int | None = None,
    probability: int | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Risk], int]:
    """Riesgos del proyecto, filtrados por estado (coma-separado), impacto y probabilidad."""
    consulta = select(Risk).where(Risk.project_id == project.id)
    if status:
        estados = [s.strip() for s in status.split(",") if s.strip()]
        desconocidos = [s for s in estados if s not in ESTADOS_RIESGO]
        if desconocidos:
            raise HTTPException(
                422,
                f"estado no reconocido: {', '.join(desconocidos)}; "
                f"válidos: {', '.join(ESTADOS_RIESGO)}",
            )
        if estados:
            consulta = consulta.where(Risk.status.in_(estados))  # type: ignore[attr-defined]
    if impact is not None:
        if not 1 <= impact <= 5:
            raise HTTPException(422, "impact debe estar entre 1 y 5")
        consulta = consulta.where(Risk.impact_level == impact)
    if probability is not None:
        if not 1 <= probability <= 5:
            raise HTTPException(422, "probability debe estar entre 1 y 5")
        consulta = consulta.where(Risk.probability_level == probability)
    total = session.exec(select(func.count()).select_from(consulta.subquery())).one()
    filas = session.exec(
        consulta.order_by(Risk.created_at.desc()).offset(offset).limit(limit)  # type: ignore[attr-defined]
    ).all()
    return list(filas), total


def risk_to_dict(session: Session, risk: Risk) -> dict[str, Any]:
    """Serializa un riesgo con las etiquetas de eje y el título de su alerta."""
    origin_alert_title = None
    if risk.origin_alert_id is not None:
        alerta = session.get(Alert, risk.origin_alert_id)
        if alerta is not None:
            origin_alert_title = alerta.title
    return {
        "id": risk.id,
        "project_id": risk.project_id,
        "code": risk.code,
        "impact_level": risk.impact_level,
        "probability_level": risk.probability_level,
        "impact_label": risk_levels.IMPACTO_LABELS[risk.impact_level],
        "probability_label": risk_levels.PROBABILIDAD_LABELS[risk.probability_level],
        "level": risk.level,
        "title": risk.title,
        "description": risk.description,
        "origin_alert_id": risk.origin_alert_id,
        "origin_alert_title": origin_alert_title,
        "monitor_type": risk.monitor_type,
        "status": risk.status,
        "created_at": risk.created_at,
        "updated_at": risk.updated_at,
    }


def movements_for_risk(session: Session, risk: Risk) -> list[dict[str, Any]]:
    """Historial completo de un riesgo, orden `created_at` asc, texto compuesto."""
    filas = session.exec(
        select(RiskMovement)
        .where(RiskMovement.risk_id == risk.id)
        .order_by(RiskMovement.created_at)  # type: ignore[arg-type]
    ).all()
    return [movement_to_dict(session, risk, mov) for mov in filas]


def movements_for_project(
    session: Session, project: Project, *, days: int = 7
) -> list[dict[str, Any]]:
    """`RiskMovement` del proyecto en los últimos `days` días, orden `created_at` desc."""
    if not 1 <= days <= MAX_DIAS_MOVIMIENTOS:
        raise HTTPException(
            422, f"days debe ser un entero entre 1 y {MAX_DIAS_MOVIMIENTOS}"
        )
    limite = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="microseconds")
    filas = session.exec(
        select(RiskMovement, Risk)
        .join(Risk, RiskMovement.risk_id == Risk.id)  # type: ignore[arg-type]
        .where(Risk.project_id == project.id, RiskMovement.created_at >= limite)  # type: ignore[operator]
        .order_by(RiskMovement.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [movement_to_dict(session, risk, mov) for mov, risk in filas]
