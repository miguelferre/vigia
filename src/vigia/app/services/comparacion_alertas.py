"""Alertas vivas de la comparación de versiones."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from vigia.app.models import Alert, Evaluation, Measurement, ModelVersion, Project
from vigia.app.services.human_layer import ESTADOS_ALERTA_VIVOS


def _version_de_la_clave(session: Session, alerta: Alert) -> int | None:
    """Versión de la última medida en `alerta` o `inestable` de la clave de la alerta.

    Mismo patrón que `human_layer._cx1_alert_groups`: se busca en las medidas, no
    en `Alert.last_evaluation_id` (no se mueve si ya estaba en observación).
    """
    grupo = (
        Measurement.group_code.is_(None)  # type: ignore[union-attr]
        if alerta.group_code is None
        else Measurement.group_code == alerta.group_code
    )
    if alerta.monitor_type == "cross" and alerta.metric_key.upper().startswith("CX-"):
        # La alerta cruzada se llama por regla (CX-1) y sus medidas por métrica
        # (`cx1_override_z:<g>`): se casan por el prefijo de la regla.
        prefijo = alerta.metric_key.lower().replace("-", "") + "_"
        clave = Measurement.metric_key.startswith(prefijo)  # type: ignore[attr-defined]
    else:
        clave = Measurement.metric_key == alerta.metric_key
    return session.exec(
        select(Evaluation.model_version_id)
        .join(Measurement, Measurement.evaluation_id == Evaluation.id)  # type: ignore[arg-type]
        .where(
            Measurement.project_id == alerta.project_id,
            Measurement.monitor_type == alerta.monitor_type,
            clave,
            grupo,
            Measurement.state.in_(("alerta", "inestable")),  # type: ignore[attr-defined]
        )
        .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())  # type: ignore[union-attr]
    ).first()


def alertas_vivas(session: Session, project: Project) -> list[dict[str, Any]]:
    vivas = session.exec(
        select(Alert)
        .where(Alert.project_id == project.id, Alert.status.in_(ESTADOS_ALERTA_VIVOS))  # type: ignore[attr-defined]
        .order_by(Alert.id)  # type: ignore[arg-type]
    ).all()
    etiquetas = {
        v.id: v.label
        for v in session.exec(select(ModelVersion).where(ModelVersion.project_id == project.id)).all()
    }
    salida = []
    for al in vivas:
        version_id = _version_de_la_clave(session, al)
        salida.append(
            {
                "alert_id": al.id,
                "monitor_type": al.monitor_type,
                "metric_key": al.metric_key,
                "group_code": al.group_code,
                "status": al.status,
                "title": al.title,
                "model_version_id": version_id,
                "version_label": etiquetas.get(version_id) if version_id is not None else None,
                "motivo": None
                if version_id is not None
                else "ninguna medida de esta alerta llegó a alerta o inestable",
            }
        )
    return salida
