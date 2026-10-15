"""Servicio de proyectos, versiones de modelo, reinicio y estado.

Construye las respuestas como `dict` explícito (`project_to_dict`, `version_to_dict`,
`monitor_to_dict`) para exponer solo los campos previstos por el esquema.
"""

from __future__ import annotations

import logging
import math
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_
from sqlmodel import Session, select

from vigia.app.bus import EventBus
from vigia.app.content_loader import protocolo_hitos_plantilla
from vigia.app.errores import no_encontrado
from vigia.app.events import ACTOR_SISTEMA, Actor, record_event
from vigia.app.models import (
    Alert,
    Batch,
    Dataset,
    DemoRun,
    Dossier,
    Evaluation,
    Explanation,
    Job,
    Measurement,
    ModelVersion,
    Monitor,
    Outcome,
    Project,
    Record,
    UsageLog,
    now_iso,
)
from vigia.app.schemas.projects import DOMINIOS_SIMULADOR, MENSAJE_SIM_LOGISTIC
from vigia.app.services import tarea as tarea_service
from vigia.app.services.alerting import ESTADOS_ALERTA_FUERA
from vigia.app.services.dossiers import plantillas_preguntas
from vigia.core.schema import (
    MENSAJE_SIM_SOLO_BINARIO,
    PREFIJO_GRUPO_CLASE,
    ColumnMapping,
    DatosNoValidos,
    MappingTemplate,
    MonitorType,
    RangoFavorable,
    State,
    clave_clase,
    texto_rangos,
    validar_rangos,
    validar_unidad,
    worst,
)
from vigia.core.thresholds import (
    DEFAULT_DRIFT_CONFIG,
    DEFAULT_DRIFT_THRESHOLDS,
    DEFAULT_EXPLAIN_THRESHOLDS,
    DEFAULT_FAIRNESS_CONFIG,
    DEFAULT_FAIRNESS_THRESHOLDS,
    DEFAULT_QUALITY_CONFIG,
    DEFAULT_QUALITY_THRESHOLDS,
)
from vigia.human.cross_alerts import CrossConfig
from vigia.human.dossier_adapter import assemble_markdown

_log = logging.getLogger(__name__)

# Acción del diario cuando un borrado o un reinicio deja ficheros en disco.
# Su título en `events_titulos.py` lo añade el módulo de títulos.
ACCION_LIMPIEZA_INCOMPLETA = "sistema.limpieza_incompleta"

__all__ = [
    "AVISO_SIN_LINEA_BASE",
    "DOMINIOS",
    "MONITORES_POR_DEFECTO",
    "activate_version",
    "create_project",
    "create_version",
    "delete_project",
    "freeze_baseline",
    "get_project",
    "get_version",
    "linea_base_congelada",
    "monitor_to_dict",
    "project_detail",
    "project_state",
    "project_to_dict",
    "projects_summary",
    "reset_project",
    "update_project",
    "version_to_dict",
]

DOMINIOS = ("reuma", "digestivo", "libre")

MONITORES_POR_DEFECTO = ("fairness", "quality", "drift", "explain", "cross")

# Texto exacto del aviso cuando la versión activa no tiene
# línea base congelada, en `GET /projects/{id}` y en la cabecera del monitor
# de deriva (frontend).
AVISO_SIN_LINEA_BASE = "la versión activa no tiene línea base congelada: la deriva no se evalúa"

# `alerts_open_by_monitor` de `ProjectSummary`:
# sin `explain`, que no tiene tarjeta en el cuadro. Los monitores en sí se
# siguen creando los cinco (`MONITORES_POR_DEFECTO`); esto es solo el desglose
# de alertas abiertas por tipo que consume la rejilla de `/modelos`.
_MONITORES_ALERTAS_POR_TIPO = ("fairness", "quality", "drift", "cross")

_PROTOCOLOS: dict[str, str] = {
    "fairness": (
        "Reconocer la alerta. Investigar el subgrupo y la métrica de equidad afectada. "
        "Contener (revisión reforzada del subgrupo) si procede. Escalar al responsable "
        "si persiste. Cerrar con motivo cuando se resuelva."
    ),
    "quality": (
        "Reconocer la alerta. Investigar la métrica de calidad y el lote afectado. "
        "Contener (revisión de las predicciones recientes) si procede. Escalar si "
        "persiste. Cerrar con motivo cuando se resuelva."
    ),
    "drift": (
        "Reconocer la alerta. Investigar qué característica o la confianza del modelo "
        "se ha desplazado frente a la línea base. Contener si procede. Escalar (pedir "
        "reentrenamiento) si persiste. Cerrar con motivo cuando se resuelva."
    ),
    "explain": (
        "Reconocer. Investigar si la explicación coincide con el criterio del responsable. "
        "Escalar si no. Cerrar con motivo."
    ),
    "cross": (
        "Reconocer la alerta cruzada. Investigar el subgrupo o profesional señalado. "
        "Contener (revisión retrospectiva) si procede. Escalar si persiste. Cerrar "
        "con motivo cuando se resuelva."
    ),
}
_PROTOCOLO_GENERICO = "Reconocer. Investigar. Contener si procede. Escalar si persiste. Cerrar con motivo."


def _monitor_defaults(
    monitor_type: str, task_type: str = "binary", *, con_rango: bool = False
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Configuración y umbrales de fábrica de un monitor, por tipo de tarea.

    - `binary`: los de siempre.
    - `multiclass`: los de siempre salvo la calidad, que nace sin umbrales:
      los de la línea base añaden los titulares con origen `linea_base`.
    - `regression`: calidad vacía; equidad, deriva y explicabilidad desde
      `core.thresholds.defaults_regresion` (equidad con las medidas de pertenencia solo
      si hay rango, `con_rango`). Las cruzadas siguen vacías.
    """
    match task_type:
        case "binary" | "multiclass" | "regression":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task_type!r}")
    if monitor_type == "cross":
        return CrossConfig().model_dump(mode="json"), {"thresholds": []}
    if monitor_type == "fairness":
        config = DEFAULT_FAIRNESS_CONFIG.model_dump(mode="json")
        umbrales = DEFAULT_FAIRNESS_THRESHOLDS
    elif monitor_type == "quality":
        config = DEFAULT_QUALITY_CONFIG.model_dump(mode="json")
        umbrales = DEFAULT_QUALITY_THRESHOLDS
    elif monitor_type == "drift":
        config = DEFAULT_DRIFT_CONFIG.model_dump(mode="json")
        umbrales = DEFAULT_DRIFT_THRESHOLDS
    elif monitor_type == "explain":
        config = {"kind": "global_permutation"}
        umbrales = DEFAULT_EXPLAIN_THRESHOLDS
    else:
        raise ValueError(f"sin configuración por defecto para el monitor {monitor_type!r}")
    match task_type:
        case "binary":
            return config, umbrales.model_dump(mode="json")
        case "multiclass":
            if monitor_type == "quality":
                return config, {"thresholds": []}
            return config, umbrales.model_dump(mode="json")
        case _:
            # Import diferido.
            from vigia.core.thresholds import defaults_regresion

            return config, defaults_regresion(
                MonitorType(monitor_type), con_rango=con_rango
            ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Serialización
# ---------------------------------------------------------------------------


def _favorable_de_plantilla(p: Project) -> Any:
    """La verdad del conjunto favorable es la plantilla; la columna
    `Project.favorable_label` (un entero) queda como compatibilidad."""
    plantilla = p.mapping_template_json or {}
    valor = plantilla.get("favorable_label") if isinstance(plantilla, dict) else None
    if valor is None or valor == []:
        match p.task_type:
            case "multiclass":
                # Multiclase sin conjunto favorable: la lista vacía, no el `1` de compatibilidad.
                return []
            case "regression":
                # Una regresión no tiene clase favorable; su rango va en
                # `favorable_ranges`.
                return None
            case "binary":
                return p.favorable_label
            case _:
                raise ValueError(f"tipo de tarea no reconocido: {p.task_type!r}")
    return valor


def _clases_de_proyecto(p: Project) -> list[Any] | None:
    if p.classes_json:
        return list(p.classes_json)
    plantilla = p.mapping_template_json or {}
    clases = plantilla.get("classes") if isinstance(plantilla, dict) else None
    return list(clases) if clases else None


def _unidad_y_rangos_de_proyecto(p: Project) -> tuple[str | None, list[list[float | None]]]:
    """Unidad y rango favorable de una regresión: los fijados en el proyecto o, antes
    de fijarlos, los de la plantilla de mapeo. Nulo y vacío fuera de la regresión."""
    match p.task_type:
        case "binary" | "multiclass":
            return None, []
        case "regression":
            plantilla = p.mapping_template_json if isinstance(p.mapping_template_json, dict) else {}
            unidad = p.target_unit if p.target_unit is not None else plantilla.get("target_unit")
            rangos = (
                p.favorable_ranges_json
                if p.favorable_ranges_json is not None
                else plantilla.get("favorable_ranges")
            )
            return unidad, [list(r) for r in (rangos or [])]
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {p.task_type!r}")


def project_to_dict(p: Project) -> dict[str, Any]:
    unidad, rangos = _unidad_y_rangos_de_proyecto(p)
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "domain": p.domain,
        "task_type": p.task_type,
        "favorable_label": _favorable_de_plantilla(p),
        "classes": _clases_de_proyecto(p),
        "target_unit": unidad,
        "favorable_ranges": rangos,
        "active_version_id": p.active_version_id,
        "calibration_until": p.calibration_until,
        "store_features": p.store_features,
        "explain_auto": p.explain_auto,
        "explain_method": p.explain_method,
        "is_demo": p.is_demo,
        "deployment_stage": p.deployment_stage,
        "mapping_template_json": p.mapping_template_json,
        "acepta_feedback": p.acepta_feedback,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def version_to_dict(v: ModelVersion) -> dict[str, Any]:
    return {
        "id": v.id,
        "project_id": v.project_id,
        "label": v.label,
        "is_active": v.is_active,
        "model_kind": v.model_kind,
        "baseline_batch_id": v.baseline_batch_id,
        "fairness_window_n": v.fairness_window_n,
        "frozen_at": v.frozen_at,
        "cross_reference_json": v.cross_reference_json,
        "fairness_interval_method": v.fairness_interval_method,
        "artifact_kind": v.artifact_kind,
        "artifact_sha256": v.artifact_sha256,
        "artifact_inputs_json": v.artifact_inputs_json,
        "artifact_uploaded_at": v.artifact_uploaded_at,
        "created_at": v.created_at,
    }


def _formato_rango(lo: float, hi: float) -> str:
    """Límite de rango sin el `.0` de los enteros: copiado de
    `services/alerting.py:_formato_rango` (no se importa; si cambia
    uno, cambiar el otro)."""

    def _num(x: float) -> str:
        return str(int(x)) if float(x).is_integer() else str(x)

    return f"{_num(lo)}-{_num(hi)}"


def _group_labels(groups: list[Any]) -> list[str]:
    """Valores de `unpriv_groups`/`priv_groups` como texto: rangos `[a, b]`
    a `a-b`, limpiando el `.0` de los enteros, el resto tal cual."""
    etiquetas: list[str] = []
    for g in groups:
        if isinstance(g, list) and len(g) == 2:
            etiquetas.append(_formato_rango(g[0], g[1]))
        else:
            etiquetas.append(str(g))
    return etiquetas


def _group_context_for_fairness(session: Session, monitor: Monitor) -> dict[str, Any] | None:
    """`group_context` del monitor `fairness`: desde el `mapping_json` del
    dataset del último lote de la versión activa. `None` si no hay mapping o el
    monitor no es de equidad."""
    if monitor.type != "fairness":
        return None
    project = session.get(Project, monitor.project_id)
    if project is None or project.active_version_id is None:
        return None
    ultimo_batch = session.exec(
        select(Batch)
        .where(Batch.model_version_id == project.active_version_id)
        .order_by(Batch.seq.desc())  # type: ignore[attr-defined]
        .limit(1)
    ).first()
    if ultimo_batch is None or ultimo_batch.dataset_id is None:
        return None
    dataset = session.get(Dataset, ultimo_batch.dataset_id)
    if dataset is None or not dataset.mapping_json:
        return None
    mapping = dataset.mapping_json
    protected_attr = mapping.get("protected_attr_col")
    if not protected_attr:
        return None
    return {
        "protected_attr": protected_attr,
        "supervised": _group_labels(mapping.get("unpriv_groups") or []),
        "reference": _group_labels(mapping.get("priv_groups") or []),
    }


def _umbrales_con_origen(umbrales: dict[str, Any] | None) -> dict[str, Any] | None:
    """Un umbral que nunca se ha tocado sale de la API con
    `origen: "fabrica"` explícito (no se toca lo guardado, solo lo que se sirve)."""
    if not isinstance(umbrales, dict) or not isinstance(umbrales.get("thresholds"), list):
        return umbrales
    return {
        **umbrales,
        "thresholds": [
            {
                **{k: _finito_o_none(v) for k, v in t.items()},
                "origen": t.get("origen") or "fabrica",
            }
            if isinstance(t, dict)
            else t
            for t in umbrales["thresholds"]
        ],
    }


def _finito_o_none(valor: Any) -> Any:
    """Un número no finito ya guardado sale como `None` (el JSON no lo admite)."""
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    return valor


def monitor_to_dict(m: Monitor, session: Session | None = None) -> dict[str, Any]:
    return {
        "id": m.id,
        "project_id": m.project_id,
        "type": m.type,
        "enabled": m.enabled,
        "config": m.config_json,
        "thresholds": _umbrales_con_origen(m.thresholds_json),
        "protocolo_md": m.protocolo_md,
        # Nunca `None` hacia fuera; un monitor anterior a la migración 6
        # (o creado a mano sin protocolo) enseña la plantilla.
        "protocol": m.protocol_json or protocolo_hitos_plantilla(),
        "group_context": _group_context_for_fairness(session, m) if session is not None else None,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


def _batch_to_dict(b: Batch) -> dict[str, Any]:
    return {
        "id": b.id,
        "seq": b.seq,
        "phase_label": b.phase_label,
        "n_rows": b.n_rows,
        "n_labeled": b.n_labeled,
        "orden_manipulado": b.orden_manipulado,
        "created_at": b.created_at,
    }


def _rows(session: Session, model: type, project_id: int) -> list[Any]:
    return list(session.exec(select(model).where(model.project_id == project_id)).all())


# ---------------------------------------------------------------------------
# Lecturas
# ---------------------------------------------------------------------------


def get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise no_encontrado("modelo", project_id, "modelos")
    return project


def get_version(session: Session, version_id: int) -> ModelVersion:
    version = session.get(ModelVersion, version_id)
    if version is None:
        raise no_encontrado("versión", version_id, "versiones")
    return version


def project_detail(session: Session, project: Project) -> dict[str, Any]:
    """Proyecto con sus versiones, monitores y recuentos (para `GET /projects/{id}`)."""
    versiones = session.exec(
        select(ModelVersion).where(ModelVersion.project_id == project.id)
    ).all()
    monitores = session.exec(select(Monitor).where(Monitor.project_id == project.id)).all()
    alertas = _rows(session, Alert, project.id)
    data = project_to_dict(project)
    data["versions"] = [version_to_dict(v) for v in versiones]
    data["monitors"] = [monitor_to_dict(m, session) for m in monitores]
    data["counts"] = {
        "batches": len(_rows(session, Batch, project.id)),
        "records": len(_rows(session, Record, project.id)),
        "evaluations": len(_rows(session, Evaluation, project.id)),
        "datasets": len(_rows(session, Dataset, project.id)),
        "alerts_open": len([a for a in alertas if a.status not in ESTADOS_ALERTA_FUERA]),
    }
    # Aviso persistente cuando la versión activa no tiene
    # línea base congelada, para que el proyecto lo diga sin esperar al
    # monitor de deriva.
    version_activa = next((v for v in versiones if v.id == project.active_version_id), None)
    data["aviso_linea_base"] = (
        AVISO_SIN_LINEA_BASE
        if version_activa is not None and version_activa.frozen_at is None
        else None
    )
    return data


def project_state(session: Session, project: Project) -> dict[str, Any]:
    """Estado operativo del proyecto: versiones, monitores, alertas abiertas, jobs."""
    versiones = session.exec(
        select(ModelVersion).where(ModelVersion.project_id == project.id)
    ).all()
    monitores = session.exec(select(Monitor).where(Monitor.project_id == project.id)).all()
    monitor_calidad = next((m for m in monitores if m.type == "quality"), None)

    monitores_estado: list[dict[str, Any]] = []
    for m in monitores:
        ultima = session.exec(
            select(Evaluation)
            .where(Evaluation.monitor_id == m.id)
            .order_by(Evaluation.created_at.desc())  # type: ignore[attr-defined]
            .limit(1)
        ).first()
        monitores_estado.append(
            {
                "id": m.id,
                "type": m.type,
                "enabled": m.enabled,
                "worst_state": ultima.worst_state if ultima else None,
                "last_evaluated_at": ultima.created_at if ultima else None,
            }
        )

    alertas = [a for a in _rows(session, Alert, project.id) if a.status not in ESTADOS_ALERTA_FUERA]
    por_severidad: dict[str, int] = {}
    for a in alertas:
        por_severidad[a.severity] = por_severidad.get(a.severity, 0) + 1

    ultimo_batch = session.exec(
        select(Batch)
        .where(Batch.project_id == project.id)
        .order_by(Batch.seq.desc())  # type: ignore[attr-defined]
        .limit(1)
    ).first()

    # `first_batch`: línea base por `seq` mínimo, para que el
    # cuadro no tenga que pedir hasta 500 lotes solo para deducirla en el
    # cliente (`frontend/src/pages/dashboard/index.tsx`, `useBatches(...,
    # {limit: 500})`, retirado).
    primer_batch = session.exec(
        select(Batch)
        .where(Batch.project_id == project.id)
        .order_by(Batch.seq.asc())  # type: ignore[attr-defined]
        .limit(1)
    ).first()

    jobs_en_curso = session.exec(
        select(Job).where(Job.project_id == project.id, Job.status.in_(("pendiente", "en_curso")))  # type: ignore[attr-defined]
    ).all()

    return {
        "project_id": project.id,
        "name": project.name,
        "active_version_id": project.active_version_id,
        "versions": [version_to_dict(v) for v in versiones],
        "monitors": monitores_estado,
        "alerts_open_by_severity": por_severidad,
        "alerts_open_total": len(alertas),
        "last_batch": _batch_to_dict(ultimo_batch) if ultimo_batch else None,
        "first_batch": _batch_to_dict(primer_batch) if primer_batch else None,
        "jobs_running": [j.id for j in jobs_en_curso],
        "quality_primary_metric": _resolve_primary_metric(
            monitor_calidad.config_json if monitor_calidad else None,
            monitor_calidad.thresholds_json if monitor_calidad else None,
            project.task_type,
        ),
    }


# H1b: la métrica de calidad que sale en `BatchKpi.metrics` es la primera con
# umbral del monitor (`accuracy` por defecto, `core/thresholds.py`); la de
# explicabilidad es siempre la estabilidad del ranking.
_METRIC_QUALITY_DEFAULT = "accuracy"
# En multiclase el titular por defecto es el F1 macro; la exactitud
# queda para el binario como hasta ahora.
_METRIC_QUALITY_DEFAULT_MULTICLASE = "f1_measure"
# En regresión, el error absoluto medio.
_METRIC_QUALITY_DEFAULT_REGRESION = "mean_absolute_error"
_METRIC_EXPLAIN = "explain_stability_ndcg"
# `explain` fuera de `states_by_monitor` y de
# `checks_by_state` de `BatchKpi` (y de `alerts_open_by_monitor` más abajo),
# porque ninguna pantalla lo pinta (`TarjetasMonitor.tsx` solo tiene
# `fairness`/`quality`/`drift`/`cross`). `BatchKpi.metrics` sigue incluyendo
# su métrica: eso lo decide `_MONITORES_CON_METRICA`, no esta constante.
_CLAVES_ESTADOS_MONITOR = ("fairness", "quality", "drift")


def _resolve_primary_metric(
    config_json: dict[str, Any] | None,
    thresholds_json: dict[str, Any] | None,
    task_type: str = "binary",
) -> str:
    """Métrica principal de calidad: `config.primary_metric` si está fijada,
    si no la primera con umbral, si no `accuracy`. En multiclase sin
    `primary_metric` es `f1_measure` y en regresión `mean_absolute_error`: el
    orden de los umbrales no decide."""
    primary = (config_json or {}).get("primary_metric")
    if primary:
        return primary
    match task_type:
        case "multiclass":
            return _METRIC_QUALITY_DEFAULT_MULTICLASE
        case "regression":
            return _METRIC_QUALITY_DEFAULT_REGRESION
        case "binary":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task_type!r}")
    umbrales = (thresholds_json or {}).get("thresholds") or []
    if umbrales:
        clave = umbrales[0].get("metric_key")
        if clave:
            return clave
    return _METRIC_QUALITY_DEFAULT


_MONITORES_CON_METRICA = ("fairness", "quality", "drift", "explain")


def _clave_principal(tipo: str, monitor: Monitor | None, task_type: str = "binary") -> str | None:
    """Métrica principal de cada monitor para `BatchKpi.metrics`: calidad por
    `_resolve_primary_metric`; explicabilidad, la estabilidad del ranking;
    equidad y deriva, la primera métrica con umbral del monitor."""
    if tipo == "quality":
        return _resolve_primary_metric(
            monitor.config_json if monitor else None,
            monitor.thresholds_json if monitor else None,
            task_type,
        )
    if tipo == "explain":
        return _METRIC_EXPLAIN
    umbrales = ((monitor.thresholds_json if monitor else None) or {}).get("thresholds") or []
    return umbrales[0].get("metric_key") if umbrales else None


def _metric_kpi(m: Measurement) -> dict[str, Any]:
    """`MetricKpi` desde una medida ya evaluada: el umbral sale de la propia
    medida (`threshold_low`/`threshold_high`, ya resueltos en la evaluación),
    no de la configuración actual del monitor, que pudo cambiar desde entonces."""
    if m.threshold_low is not None:
        kind, valor_umbral = "lower", m.threshold_low
    elif m.threshold_high is not None:
        kind, valor_umbral = "upper", m.threshold_high
    else:
        kind, valor_umbral = None, None
    return {
        "monitor_type": m.monitor_type,
        "metric_key": m.metric_key,
        "value": m.value,
        "threshold_kind": kind,
        "threshold_value": valor_umbral,
        "state": m.state,
    }


# CX-3 y `human_review_zero` no están en esta lista: nunca
# abren `Alert`, así que la consulta de más abajo no las vería nunca; se cuentan
# aparte, sobre `Measurement`, con `_aviso_sin_alerta_por_proyecto`. CX-4 sí abre `Alert`
# como CX-2, así que entra aquí igual.
_CLAVES_CROSS = ("CX-1", "CX-2", "CX-4", "CX-5", "CX-6")
_CHECKS_VACIOS: dict[str, int] = {"ok": 0, "aviso": 0, "alerta": 0, "inestable": 0, "sin_datos": 0}


def _checks_vacios() -> dict[str, int]:
    return dict(_CHECKS_VACIOS)


def _cx3_aviso_por_proyecto(session: Session, project_ids: list[int]) -> set[int]:
    """Proyectos cuya evaluación `cross` más reciente tiene CX-3 en `aviso`."""
    return _aviso_sin_alerta_por_proyecto(session, project_ids, ("cx3_override_z", "cx3_rescue_z"))


def _aviso_sin_alerta_por_proyecto(
    session: Session, project_ids: list[int], metric_keys: tuple[str, ...]
) -> set[int]:
    """Proyectos cuya evaluación `cross` más reciente tiene alguna de `metric_keys`
    en `aviso`.

    CX-3 y `human_review_zero` nunca abren `Alert`
    (`cross_alerts.py`): la consulta a `Alert` de `_cross_checks_por_proyecto` no
    las vería nunca y `checks_by_state["cross"]["aviso"]` las perdería por omisión.
    Se leen de `Measurement`, filtrando la evaluación `cross` más reciente por
    proyecto (`cross` no tiene lote: `Evaluation.batch_id=None`)."""
    if not project_ids:
        return set()
    ultima_evaluacion: dict[int, int] = {}
    for project_id, evaluation_id in session.exec(
        select(Evaluation.project_id, Evaluation.id)
        .join(Monitor, Monitor.id == Evaluation.monitor_id)  # type: ignore[arg-type]
        .where(Evaluation.project_id.in_(project_ids), Monitor.type == "cross")  # type: ignore[attr-defined]
        .order_by(Evaluation.project_id, Evaluation.created_at.desc(), Evaluation.id.desc())  # type: ignore[union-attr]
    ).all():
        ultima_evaluacion.setdefault(project_id, evaluation_id)
    if not ultima_evaluacion:
        return set()
    evaluation_ids = list(ultima_evaluacion.values())
    con_aviso = set(
        session.exec(
            select(Measurement.evaluation_id).where(
                Measurement.evaluation_id.in_(evaluation_ids),  # type: ignore[attr-defined]
                Measurement.metric_key.in_(metric_keys),  # type: ignore[attr-defined]
                Measurement.state == "aviso",
            )
        ).all()
    )
    return {pid for pid, eval_id in ultima_evaluacion.items() if eval_id in con_aviso}


def _cross_en_calibracion_por_proyecto(session: Session, project_ids: list[int]) -> set[int]:
    """Proyectos cuya evaluación `cross` más reciente está en modo `calibracion`: mismo criterio que `human_layer.cross_latest`
    (`Evaluation.result_json["mode"]`, sin tocar ese módulo). Durante
    calibración el motor no dispara reglas nuevas (`/capa-humana` avisa
    "todavía sin reglas"), así que una alerta que siga abierta de ANTES de
    empezar a calibrar es ruido de una versión anterior, no una señal viva."""
    if not project_ids:
        return set()
    ultima_evaluacion: dict[int, dict[str, Any] | None] = {}
    vistos: set[int] = set()
    for project_id, result_json in session.exec(
        select(Evaluation.project_id, Evaluation.result_json)
        .join(Monitor, Monitor.id == Evaluation.monitor_id)  # type: ignore[arg-type]
        .where(Evaluation.project_id.in_(project_ids), Monitor.type == "cross")  # type: ignore[attr-defined]
        .order_by(Evaluation.project_id, Evaluation.created_at.desc(), Evaluation.id.desc())  # type: ignore[union-attr]
    ).all():
        if project_id in vistos:
            continue
        vistos.add(project_id)
        ultima_evaluacion[project_id] = result_json
    return {
        pid for pid, result_json in ultima_evaluacion.items() if (result_json or {}).get("mode") == "calibracion"
    }


def _cross_checks_por_proyecto(session: Session, project_ids: list[int]) -> dict[int, dict[str, int]]:
    """`checks_by_state["cross"]` de cada proyecto: 7 comprobaciones (CX-1, CX-2, CX-4 a CX-6 por sus alertas abiertas
    -`alerta` si hay alguna alta, `aviso` si solo media, `ok` en el resto-; CX-3 y
    `human_review_zero` pueden quedarse en `ok` aunque estén en `aviso`, si su última
    evaluación no lo muestra o todavía no hay ninguna). Si la última evaluación cruzada está en calibración, las
    cinco reglas de arriba cuentan `ok` sin mirar alertas abiertas previas (CX-3 ya se
    autocorrige, porque solo mira su propia última evaluación)."""
    resultado = {pid: _checks_vacios() for pid in project_ids}
    proyectos_en_calibracion = _cross_en_calibracion_por_proyecto(session, project_ids)
    severidades_por_regla: dict[tuple[int, str], set[str]] = {}
    for project_id, metric_key, severity in session.exec(
        select(Alert.project_id, Alert.metric_key, Alert.severity).where(
            Alert.project_id.in_(project_ids),  # type: ignore[attr-defined]
            Alert.monitor_type == "cross",
            Alert.status.notin_(ESTADOS_ALERTA_FUERA),  # type: ignore[attr-defined]
        )
    ).all():
        severidades_por_regla.setdefault((project_id, metric_key), set()).add(severity)
    for project_id in project_ids:
        for clave in _CLAVES_CROSS:
            severidades = (
                set() if project_id in proyectos_en_calibracion else severidades_por_regla.get((project_id, clave), set())
            )
            if "alta" in severidades:
                resultado[project_id]["alerta"] += 1
            elif "media" in severidades:
                resultado[project_id]["aviso"] += 1
            else:
                resultado[project_id]["ok"] += 1

    # CX-3 y `human_review_zero`: una comprobación cada una, desde la
    # última evaluación cruzada (se autocorrigen en calibración).
    for con_aviso in (
        _cx3_aviso_por_proyecto(session, project_ids),
        _aviso_sin_alerta_por_proyecto(session, project_ids, ("human_review_zero",)),
    ):
        for project_id in project_ids:
            if project_id in con_aviso:
                resultado[project_id]["aviso"] += 1
            else:
                resultado[project_id]["ok"] += 1
    return resultado


def _batches_kpi(session: Session, project_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """Los dos últimos lotes con evaluación de cada proyecto, por `Batch.seq`
    (H1b, `ProjectSummary.last_batch`/`previous_batch`).

    Todo en una tanda de consultas agrupadas por tabla (evaluaciones, lotes,
    medidas, umbral de calidad, alertas), nunca una por proyecto ni por lote.
    """
    resultado: dict[int, list[dict[str, Any]]] = {pid: [] for pid in project_ids}

    filas_evaluacion = session.exec(
        select(
            Evaluation.id,
            Evaluation.project_id,
            Evaluation.monitor_id,
            Evaluation.batch_id,
            Evaluation.worst_state,
            Evaluation.created_at,
        ).where(Evaluation.project_id.in_(project_ids), Evaluation.batch_id.is_not(None))  # type: ignore[attr-defined]
    ).all()
    if not filas_evaluacion:
        return resultado

    evals_por_batch: dict[int, list[tuple[int, int, str | None, str]]] = {}
    for eval_id, _project_id, monitor_id, batch_id, worst_state, created_at in filas_evaluacion:
        evals_por_batch.setdefault(batch_id, []).append((eval_id, monitor_id, worst_state, created_at))

    tipo_por_monitor = dict(
        session.exec(select(Monitor.id, Monitor.type).where(Monitor.project_id.in_(project_ids))).all()  # type: ignore[attr-defined]
    )
    lotes_por_proyecto: dict[int, list[Batch]] = {}
    for lote in session.exec(select(Batch).where(Batch.id.in_(evals_por_batch.keys()))).all():  # type: ignore[attr-defined]
        lotes_por_proyecto.setdefault(lote.project_id, []).append(lote)

    # Medidas de conjunto (sin grupo) de los cuatro monitores con métrica
    # principal, una entrada por monitor en `BatchKpi.metrics` (la
    # tarjeta de pestañas del cuadro y la tarjeta de modelo las consumen).
    medidas_por_evaluacion: dict[int, list[Measurement]] = {}
    for m in session.exec(
        select(Measurement).where(
            Measurement.evaluation_id.in_([f[0] for f in filas_evaluacion]),  # type: ignore[attr-defined]
            Measurement.monitor_type.in_(tuple(_MONITORES_CON_METRICA)),  # type: ignore[attr-defined]
            Measurement.group_code.is_(None),  # type: ignore[attr-defined]
        )
    ).all():
        medidas_por_evaluacion.setdefault(m.evaluation_id, []).append(m)

    # `checks_by_state`: recuento por estado de TODAS las filas
    # de `Measurement` de cada evaluación (sin filtrar `group_code`: en equidad
    # cada grupo cuenta como una comprobación), agrupado en una sola consulta.
    # Las medidas por clase (`clase:<valor>`) son informativas, sin
    # umbral ni alerta, y no cuentan como comprobación: una clase rara en
    # `sin_datos` no es una comprobación fallida.
    estados_por_evaluacion: dict[int, dict[str, int]] = {}
    for eval_id, estado, n in session.exec(
        select(Measurement.evaluation_id, Measurement.state, func.count())
        .where(
            Measurement.evaluation_id.in_([f[0] for f in filas_evaluacion]),  # type: ignore[attr-defined]
            or_(
                Measurement.group_code.is_(None),  # type: ignore[union-attr]
                ~Measurement.group_code.startswith(PREFIJO_GRUPO_CLASE),  # type: ignore[union-attr]
            ),
        )
        .group_by(Measurement.evaluation_id, Measurement.state)
    ).all():
        estados_por_evaluacion.setdefault(eval_id, {})[estado] = n

    monitores_por_proyecto: dict[tuple[int, str], Monitor] = {
        (m.project_id, m.type): m
        for m in session.exec(
            select(Monitor).where(
                Monitor.project_id.in_(project_ids),  # type: ignore[attr-defined]
                Monitor.type.in_(tuple(_MONITORES_CON_METRICA)),  # type: ignore[attr-defined]
            )
        ).all()
    }

    # `alerts_opened` (H1b): alertas cuya primera entrada de `history_json`
    # apunta a una evaluación del lote, resuelto en Python sobre las alertas
    # del proyecto (una sola consulta, no una por lote).
    primera_evaluacion_por_alerta: list[tuple[int, int | None]] = []
    for project_id, historial in session.exec(
        select(Alert.project_id, Alert.history_json).where(Alert.project_id.in_(project_ids))  # type: ignore[attr-defined]
    ).all():
        primera = historial[0] if historial else None
        eval_id = primera.get("evaluation_id") if isinstance(primera, dict) else None
        primera_evaluacion_por_alerta.append((project_id, eval_id))

    cross_checks_por_proyecto = _cross_checks_por_proyecto(session, project_ids)

    tipo_de_tarea = dict(
        session.exec(select(Project.id, Project.task_type).where(Project.id.in_(project_ids))).all()  # type: ignore[attr-defined]
    )
    for project_id, lotes in lotes_por_proyecto.items():
        claves_por_tipo = {
            tipo: _clave_principal(
                tipo,
                monitores_por_proyecto.get((project_id, tipo)),
                tipo_de_tarea.get(project_id, "binary"),
            )
            for tipo in _MONITORES_CON_METRICA
        }

        for lote in sorted(lotes, key=lambda b: b.seq, reverse=True)[:2]:
            evals = evals_por_batch.get(lote.id, [])
            eval_ids = {eval_id for eval_id, _mid, _ws, _ts in evals}
            estados: dict[str, str | None] = dict.fromkeys(_CLAVES_ESTADOS_MONITOR)
            metrics: list[dict[str, Any]] = []
            checks_by_state: dict[str, dict[str, int]] = {
                tipo: _checks_vacios() for tipo in _CLAVES_ESTADOS_MONITOR
            }
            for eval_id, monitor_id, worst_state, _ts in evals:
                tipo = tipo_por_monitor.get(monitor_id)
                if tipo in estados:
                    estados[tipo] = worst_state
                if tipo in checks_by_state:
                    for estado, n in estados_por_evaluacion.get(eval_id, {}).items():
                        if estado in checks_by_state[tipo]:
                            checks_by_state[tipo][estado] += n
                clave = claves_por_tipo.get(tipo) if tipo else None
                if clave is None:
                    continue
                medida = next(
                    (m for m in medidas_por_evaluacion.get(eval_id, []) if m.metric_key == clave), None
                )
                if medida is not None:
                    metrics.append(_metric_kpi(medida))
            checks_by_state["cross"] = cross_checks_por_proyecto.get(project_id, _checks_vacios())
            resultado.setdefault(project_id, []).append(
                {
                    "batch_id": lote.id,
                    "seq": lote.seq,
                    "phase_label": lote.phase_label,
                    "evaluated_at": max((ts for _eid, _mid, _ws, ts in evals), default=None),
                    "n_rows": lote.n_rows,
                    "monitors_total": len(evals),
                    "monitors_in_alert": sum(1 for _eid, _mid, ws, _ts in evals if ws == "alerta"),
                    "states_by_monitor": estados,
                    "alerts_opened": sum(
                        1
                        for pid, eval_id in primera_evaluacion_por_alerta
                        if pid == project_id and eval_id in eval_ids
                    ),
                    "metrics": metrics,
                    "checks_by_state": checks_by_state,
                }
            )
    return resultado


def projects_summary(session: Session, projects: list[Project]) -> dict[int, dict[str, Any]]:
    """Resumen por proyecto para `GET /projects?summary=true`.

    Una consulta agrupada por tabla (alertas, evaluaciones, lotes, peor
    estado), no una por proyecto: evita el patrón N+1 que hoy fuerza al
    frontend a pedir `GET /projects/{id}` fila a fila (`useQueries`).
    """
    project_ids = [p.id for p in projects if p.id is not None]
    resumen: dict[int, dict[str, Any]] = {
        pid: {
            "worst_state": None,
            "alerts_open_by_severity": {"alta": 0, "media": 0, "baja": 0},
            "alerts_open_by_monitor": {
                tipo: {"alta": 0, "media": 0, "baja": 0} for tipo in _MONITORES_ALERTAS_POR_TIPO
            },
            "last_evaluation_at": None,
            "first_batch_at": None,
            "active_version_label": None,
            "last_batch": None,
            "previous_batch": None,
        }
        for pid in project_ids
    }
    if not project_ids:
        return resumen

    for project_id, severity, n in session.exec(
        select(Alert.project_id, Alert.severity, func.count())
        .where(Alert.project_id.in_(project_ids), Alert.status.notin_(ESTADOS_ALERTA_FUERA))  # type: ignore[attr-defined]
        .group_by(Alert.project_id, Alert.severity)
    ).all():
        if severity in resumen[project_id]["alerts_open_by_severity"]:
            resumen[project_id]["alerts_open_by_severity"][severity] = n

    # El mismo recuento, desglosado también por monitor
    # (incluido `cross`), en una única consulta agrupada para toda la rejilla.
    for project_id, monitor_type, severity, n in session.exec(
        select(Alert.project_id, Alert.monitor_type, Alert.severity, func.count())
        .where(Alert.project_id.in_(project_ids), Alert.status.notin_(ESTADOS_ALERTA_FUERA))  # type: ignore[attr-defined]
        .group_by(Alert.project_id, Alert.monitor_type, Alert.severity)
    ).all():
        por_monitor = resumen[project_id]["alerts_open_by_monitor"].get(monitor_type)
        if por_monitor is not None and severity in por_monitor:
            por_monitor[severity] = n

    for project_id, ultima in session.exec(
        select(Evaluation.project_id, func.max(Evaluation.created_at))
        .where(Evaluation.project_id.in_(project_ids))  # type: ignore[attr-defined]
        .group_by(Evaluation.project_id)
    ).all():
        resumen[project_id]["last_evaluation_at"] = ultima

    for project_id, primero in session.exec(
        select(Batch.project_id, func.min(Batch.created_at))
        .where(Batch.project_id.in_(project_ids))  # type: ignore[attr-defined]
        .group_by(Batch.project_id)
    ).all():
        resumen[project_id]["first_batch_at"] = primero

    # Peor estado: la última evaluación de cada monitor, con el mismo
    # orden que usa el motor (`core.schema.worst`).
    ultima_por_monitor = (
        select(Evaluation.monitor_id, func.max(Evaluation.created_at).label("max_ts"))
        .where(Evaluation.project_id.in_(project_ids))  # type: ignore[attr-defined]
        .group_by(Evaluation.monitor_id)
        .subquery()
    )
    estados_por_proyecto: dict[int, list[State]] = {}
    for project_id, worst_state in session.exec(
        select(Evaluation.project_id, Evaluation.worst_state).join(
            ultima_por_monitor,
            (Evaluation.monitor_id == ultima_por_monitor.c.monitor_id)
            & (Evaluation.created_at == ultima_por_monitor.c.max_ts),
        )
    ).all():
        if worst_state:
            estados_por_proyecto.setdefault(project_id, []).append(State(worst_state))
    for project_id, estados in estados_por_proyecto.items():
        # Un monitor sin datos (p. ej. `explain` con la primera explicación de
        # la versión) no oscurece el estado de los que sí evaluaron:
        # `sin_datos` solo si ninguno tiene datos.
        con_datos = [s for s in estados if s is not State.sin_datos]
        resumen[project_id]["worst_state"] = worst(con_datos or estados).value

    version_ids = {p.active_version_id for p in projects if p.active_version_id is not None}
    if version_ids:
        etiquetas = dict(
            session.exec(
                select(ModelVersion.id, ModelVersion.label).where(
                    ModelVersion.id.in_(version_ids)  # type: ignore[attr-defined]
                )
            ).all()
        )
        for p in projects:
            if p.id is not None and p.active_version_id is not None:
                resumen[p.id]["active_version_label"] = etiquetas.get(p.active_version_id)

    for project_id, lotes in _batches_kpi(session, project_ids).items():
        resumen[project_id]["last_batch"] = lotes[0] if lotes else None
        resumen[project_id]["previous_batch"] = lotes[1] if len(lotes) > 1 else None

    return resumen


# ---------------------------------------------------------------------------
# Mutaciones
# ---------------------------------------------------------------------------


def create_project(
    session: Session,
    *,
    name: str,
    domain: str = "libre",
    favorable_label: int = 1,
    store_features: bool = True,
    model_kind: str = "external_files",
    deployment_stage: str = "desarrollo",
    # Plantilla de mapeo, si el proyecto recibe feedback y
    # método del intervalo de equidad de la v1. `fairness_interval_method`
    # conserva "ventanas" por defecto (la demo y las llamadas internas no
    # cambian); es el router quien pone "lote" en el alta pública si el
    # cuerpo no dice otra cosa (§7.2, interfaz D).
    mapping_template: MappingTemplate | None = None,
    acepta_feedback: bool = True,
    fairness_interval_method: str = "ventanas",
    # Tipo de tarea y clases declaradas. `classes` manda sobre
    # las de la plantilla; sin ninguna, el proyecto multiclase las toma de la
    # línea base al congelarla.
    task_type: str = "binary",
    classes: list[int | str] | None = None,
    # Unidad de la salida y rango favorable de una regresión; mandan sobre
    # los de la plantilla.
    target_unit: str | None = None,
    favorable_ranges: list[Any] | None = None,
    actor: Actor,
    bus: EventBus | None = None,
    # El evento de alta lleva la correlación de la llamada del MCP.
    correlation_id: str | None = None,
) -> Project:
    """Crea el proyecto, la versión `v1` activa y los cinco monitores por defecto."""
    if domain not in DOMINIOS:
        raise HTTPException(422, f"domain debe ser uno de {', '.join(DOMINIOS)}; se recibió {domain!r}")
    if model_kind == "sim_logistic" and domain not in DOMINIOS_SIMULADOR:
        raise HTTPException(422, MENSAJE_SIM_LOGISTIC)
    tarea_service.validar_tipo_http(task_type)
    if model_kind == "sim_logistic":
        # El modelo simulado es de clasificación binaria.
        match task_type:
            case "regression":
                raise HTTPException(422, MENSAJE_SIM_SOLO_BINARIO)
            case "binary" | "multiclass":
                pass
            case _:
                raise ValueError(f"tipo de tarea no reconocido: {task_type!r}")
    mapping_template, clases = _plantilla_y_clases_del_alta(
        task_type, mapping_template, classes, unidad=target_unit, rangos=favorable_ranges
    )
    unidad, rangos = _unidad_y_rangos_de_plantilla(task_type, mapping_template)
    if session.exec(select(Project).where(Project.name == name)).first() is not None:
        raise HTTPException(409, f"ya existe un proyecto llamado {name!r}")

    project = Project(
        name=name,
        domain=domain,
        task_type=task_type,
        favorable_label=favorable_label,
        classes_json=clases or None,
        target_unit=unidad,
        favorable_ranges_json=[list(r) for r in rangos] if rangos else None,
        store_features=store_features,
        deployment_stage=deployment_stage,
        mapping_template_json=mapping_template.model_dump(mode="json") if mapping_template else None,
        acepta_feedback=acepta_feedback,
    )
    session.add(project)
    session.flush()

    version = ModelVersion(
        project_id=project.id,
        label="v1",
        is_active=True,
        model_kind=model_kind,
        fairness_interval_method=fairness_interval_method,
    )
    session.add(version)
    session.flush()
    project.active_version_id = version.id
    session.add(project)

    for tipo in MONITORES_POR_DEFECTO:
        # En multiclase y en regresión la calidad nace sin umbrales; la línea
        # base congelada añade los titulares con origen `linea_base`. El despacho
        # por tipo vive en `_monitor_defaults`.
        config, thresholds = _monitor_defaults(tipo, task_type, con_rango=bool(rangos))
        session.add(
            Monitor(
                project_id=project.id,
                type=tipo,
                enabled=True,
                config_json=config,
                thresholds_json=thresholds,
                protocolo_md=_PROTOCOLOS.get(tipo, _PROTOCOLO_GENERICO),
                protocol_json=protocolo_hitos_plantilla(),
            )
        )
    session.flush()

    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="proyecto.creado",
        object_type="project",
        object_id=project.id,
        project_id=project.id,
        after={
            "name": project.name,
            "domain": project.domain,
            "model_kind": model_kind,
            **_after_tipo_de_tarea(task_type, clases, unidad),
        },
        correlation_id=correlation_id,
        bus=bus,
    )
    if rangos:
        _evento_rango_fijado(
            session, project, unidad, rangos, actor=actor, motivo=None,
            correlation_id=correlation_id, job_id=None, bus=bus,
        )
    session.commit()
    session.refresh(project)
    return project


def _after_tipo_de_tarea(
    task_type: str, clases: list[int | str], unidad: str | None
) -> dict[str, Any]:
    """Lo que el evento `proyecto.creado` dice del tipo de tarea: nada en binario sin
    clases (el defecto de siempre), el tipo y las clases en multiclase, el tipo y la
    unidad en regresión."""
    match task_type:
        case "binary":
            return {"task_type": task_type, "classes": clases or None} if clases else {}
        case "multiclass":
            return {"task_type": task_type, "classes": clases or None}
        case "regression":
            return {"task_type": task_type, "target_unit": unidad}
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task_type!r}")


def _unidad_y_rangos_de_plantilla(
    task_type: str, plantilla: MappingTemplate | None
) -> tuple[str | None, tuple[RangoFavorable, ...]]:
    """Unidad y rango favorable que fija el alta (regresión). Vacíos en clasificación."""
    match task_type:
        case "binary" | "multiclass":
            return None, ()
        case "regression":
            if plantilla is None:
                return None, ()
            try:
                return validar_unidad(plantilla.target_unit), validar_rangos(plantilla.favorable_ranges)
            except DatosNoValidos as exc:
                raise HTTPException(422, tarea_service.texto_validacion(exc)) from exc
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task_type!r}")


def _evento_rango_fijado(
    session: Session,
    project: Project,
    unidad: str | None,
    rangos: Any,
    *,
    actor: Actor,
    motivo: str | None,
    correlation_id: str | None,
    job_id: int | None,
    bus: EventBus | None,
) -> None:
    """«Rango favorable fijado: de 40 a 81 horas por semana». Sin commit."""
    lista = [list(r) for r in rangos]
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="proyecto.rango_favorable_fijado",
        object_type="project",
        object_id=project.id,
        project_id=project.id,
        motivo=motivo,
        after={
            "favorable_ranges": lista,
            "target_unit": unidad,
            "texto": texto_rangos([tuple(r) for r in lista], unidad),
        },
        correlation_id=correlation_id,
        job_id=job_id,
        bus=bus,
    )


def linea_base_congelada(session: Session, project: Project) -> bool:
    """Alguna versión del proyecto ya tiene la línea base congelada."""
    return (
        session.exec(
            select(ModelVersion.id)
            .where(ModelVersion.project_id == project.id, ModelVersion.frozen_at.is_not(None))  # type: ignore[union-attr]
            .limit(1)
        ).first()
        is not None
    )


def _plantilla_y_clases_del_alta(
    task_type: str,
    plantilla: MappingTemplate | None,
    classes: list[int | str] | None,
    *,
    unidad: str | None = None,
    rangos: list[Any] | None = None,
) -> tuple[MappingTemplate | None, list[int | str]]:
    """Reglas por tipo en el alta y las clases efectivas.

    `classes` del cuerpo manda sobre las de la plantilla; la plantilla guardada
    lleva las clases efectivas para que ambas no se contradigan. Un multiclase
    sin clases es válido: salen de la línea base al congelarla.

    `unidad` y `rangos` del cuerpo mandan sobre los de la plantilla y la
    plantilla guardada los lleva; en clasificación, `validar_mapeo_por_tipo` los
    rechaza con un mensaje que nombra el campo."""
    try:
        base = MappingTemplate(classes=list(classes)) if classes else None
    except ValueError as exc:
        raise HTTPException(422, tarea_service.texto_validacion(exc)) from exc
    clases = list(base.classes) if base else list(plantilla.classes if plantilla else [])
    if plantilla is not None and classes:
        try:
            plantilla = MappingTemplate(**{**plantilla.model_dump(mode="json"), "classes": clases})
        except ValueError as exc:
            raise HTTPException(422, tarea_service.texto_validacion(exc)) from exc
    if unidad is not None or rangos:
        try:
            plantilla = MappingTemplate(
                **{
                    **(plantilla.model_dump(mode="json") if plantilla is not None else {}),
                    **({"classes": clases} if clases else {}),
                    **({"target_unit": unidad} if unidad is not None else {}),
                    **({"favorable_ranges": [list(r) for r in rangos]} if rangos else {}),
                }
            )
        except ValueError as exc:
            raise HTTPException(422, tarea_service.texto_validacion(exc)) from exc
    comprobable = plantilla if plantilla is not None else MappingTemplate(classes=clases)
    match task_type:
        case "binary":
            if not (plantilla is None and not clases):
                tarea_service.validar_mapeo_http("binary", comprobable, clases or None)
        case "multiclass":
            tarea_service.validar_plantilla_http("multiclass", comprobable, clases or None)
        case "regression":
            tarea_service.validar_plantilla_http("regression", comprobable, clases or None)
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task_type!r}")
    return plantilla, clases


def _unidad_y_rango_en_el_cambio(
    session: Session, project: Project, plantilla: MappingTemplate
) -> MappingTemplate:
    """Antes de congelar la línea base, la unidad y el rango de la plantilla nueva
    pasan al proyecto (la plantilla se sustituye entera); después de congelar no cambian
    y un valor distinto da 409. Una plantilla que no los dice conserva los fijados.
    Devuelve la plantilla que se guarda. Sin efecto en clasificación."""
    match project.task_type:
        case "binary" | "multiclass":
            return plantilla
        case "regression":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")
    try:
        unidad = validar_unidad(plantilla.target_unit)
        rangos = validar_rangos(plantilla.favorable_ranges)
    except DatosNoValidos as exc:
        raise HTTPException(422, tarea_service.texto_validacion(exc)) from exc
    if linea_base_congelada(session, project):
        fijados = tarea_service.rangos_del_proyecto(project) or ()
        if (unidad is not None and unidad != project.target_unit) or (rangos and rangos != fijados):
            raise HTTPException(409, tarea_service.MENSAJE_CAMBIO_UNIDAD_O_RANGO)
        return plantilla.model_copy(
            update={"target_unit": project.target_unit, "favorable_ranges": list(fijados)}
        )
    project.target_unit = unidad
    project.favorable_ranges_json = [list(r) for r in rangos] if rangos else None
    session.add(project)
    return plantilla


_FECHA_ISO = re.compile(
    r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?$"
)


def _validar_fecha_calibracion(valor: str) -> None:
    """422 si `calibration_until` no es una fecha ISO 8601 (`2026-12-31` o con hora).
    Se compara con `now_iso()` como texto: un valor que no empiece por la fecha dejaría
    el monitor cruzado en calibración para siempre."""
    try:
        if not _FECHA_ISO.match(valor):
            raise ValueError(valor)
        datetime.fromisoformat(valor)
    except ValueError as exc:
        raise HTTPException(
            422,
            f"calibration_until ({valor!r}) no es una fecha válida: usa el formato "
            "AAAA-MM-DD, por ejemplo 2026-12-31",
        ) from exc


def update_project(
    session: Session,
    project: Project,
    *,
    actor: Actor,
    motivo: str,
    name: str | None = None,
    description: str | None = None,
    calibration_until: str | None = None,
    store_features: bool | None = None,
    explain_auto: bool | None = None,
    explain_method: str | None = None,
    deployment_stage: str | None = None,
    # `None` es "no tocar"; `mapping_template` sustituye la
    # plantilla entera y deja su propio evento `proyecto.plantilla_actualizada`.
    mapping_template: MappingTemplate | None = None,
    acepta_feedback: bool | None = None,
    bus: EventBus | None = None,
    clear_calibration: bool = False,
    clear_description: bool = False,
    task_type: str | None = None,
) -> Project:
    """Actualiza nombre, descripción, calibración, `store_features`, la
    plantilla de mapeo o si el proyecto acepta feedback.

    `calibration_until=None` significa "no tocar"; para vaciar la fecha se pasa
    `clear_calibration=True` (hueco destapado por la pantalla de configuración).
    `description` sigue el mismo convenio (`clear_description=True` para vaciarla).
    """
    # La fecha de calibración se valida al guardarla.
    if calibration_until is not None:
        _validar_fecha_calibracion(calibration_until)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    plantilla_before: dict[str, Any] | None = None
    plantilla_after: dict[str, Any] | None = None
    # El tipo de tarea no cambia después del alta.
    if task_type is not None and task_type != project.task_type:
        raise HTTPException(409, tarea_service.MENSAJE_CAMBIO_TIPO)
    # Una plantilla guardada con `positive_label` deja un aviso y lo pierde.
    limpio = tarea_service.limpiar_positive_label(session, project, bus=bus)
    clases_nuevas: list[Any] | None = None
    if mapping_template is not None:
        tarea_service.validar_plantilla_http(project, mapping_template)
        if mapping_template.classes and not project.classes_json:
            clases_nuevas = list(mapping_template.classes)
        mapping_template = _unidad_y_rango_en_el_cambio(session, project, mapping_template)
        nueva_plantilla = mapping_template.model_dump(mode="json")
        if nueva_plantilla != (project.mapping_template_json or None):
            plantilla_before = project.mapping_template_json
            project.mapping_template_json = nueva_plantilla
            plantilla_after = nueva_plantilla
    if clases_nuevas is not None:
        project.classes_json = clases_nuevas
        session.add(project)
        record_event(
            session,
            actor_kind=actor.kind,
            actor_id=actor.id,
            role=actor.role,
            action="proyecto.clases_fijadas",
            object_type="project",
            object_id=project.id,
            project_id=project.id,
            motivo=motivo,
            after={"classes": clases_nuevas},
            bus=bus,
        )
    if acepta_feedback is not None and acepta_feedback != project.acepta_feedback:
        before["acepta_feedback"] = project.acepta_feedback
        project.acepta_feedback = acepta_feedback
        after["acepta_feedback"] = acepta_feedback
    if name is not None and name != project.name:
        if session.exec(
            select(Project).where(Project.name == name, Project.id != project.id)
        ).first():
            raise HTTPException(409, f"ya existe un proyecto llamado {name!r}")
        before["name"], project.name, after["name"] = project.name, name, name
    if clear_description and project.description is not None:
        before["description"] = project.description
        project.description = None
        after["description"] = None
    elif description is not None and description != project.description:
        before["description"] = project.description
        project.description = description
        after["description"] = description
    if clear_calibration and project.calibration_until is not None:
        before["calibration_until"] = project.calibration_until
        project.calibration_until = None
        after["calibration_until"] = None
    elif calibration_until is not None and calibration_until != project.calibration_until:
        before["calibration_until"] = project.calibration_until
        project.calibration_until = calibration_until
        after["calibration_until"] = calibration_until
    if store_features is not None and store_features != project.store_features:
        before["store_features"] = project.store_features
        project.store_features = store_features
        after["store_features"] = store_features
        if not store_features:
            # Desmarcar retira también las variables ya guardadas.
            from vigia.app.services.ingest import retirar_variables_guardadas

            retirar_variables_guardadas(session, project)
    if explain_auto is not None and explain_auto != project.explain_auto:
        before["explain_auto"] = project.explain_auto
        project.explain_auto = explain_auto
        after["explain_auto"] = explain_auto
    if explain_method is not None and explain_method != project.explain_method:
        if explain_method not in ("permutation", "shap"):
            raise HTTPException(
                422, f"explain_method debe ser permutation o shap; se recibió {explain_method!r}"
            )
        before["explain_method"] = project.explain_method
        project.explain_method = explain_method
        after["explain_method"] = explain_method
    if deployment_stage is not None and deployment_stage != project.deployment_stage:
        before["deployment_stage"] = project.deployment_stage
        project.deployment_stage = deployment_stage
        after["deployment_stage"] = deployment_stage

    if not after and plantilla_after is None and clases_nuevas is None:
        if limpio:
            session.commit()
            session.refresh(project)
        return project

    project.updated_at = now_iso()
    session.add(project)
    session.flush()
    if after:
        record_event(
            session,
            actor_kind=actor.kind,
            actor_id=actor.id,
            role=actor.role,
            action="proyecto.actualizado",
            object_type="project",
            object_id=project.id,
            project_id=project.id,
            motivo=motivo,
            before=before,
            after=after,
            bus=bus,
        )
    if plantilla_after is not None:
        record_event(
            session,
            actor_kind=actor.kind,
            actor_id=actor.id,
            role=actor.role,
            action="proyecto.plantilla_actualizada",
            object_type="project",
            object_id=project.id,
            project_id=project.id,
            motivo=motivo,
            before={"mapping_template": plantilla_before},
            after={"mapping_template": plantilla_after},
            bus=bus,
        )
    session.commit()
    session.refresh(project)
    return project


def create_version(
    session: Session,
    project: Project,
    *,
    label: str,
    model_kind: str = "external_files",
    fairness_window_n: int | None = None,
    # `None` hereda el método de la versión activa.
    fairness_interval_method: str | None = None,
    actor: Actor,
    motivo: str,
    bus: EventBus | None = None,
) -> ModelVersion:
    # `sim_logistic` solo en los dominios del simulador; aquí,
    # no en el esquema, porque solo el servicio conoce el dominio del proyecto.
    if model_kind == "sim_logistic" and project.domain not in DOMINIOS_SIMULADOR:
        raise HTTPException(422, MENSAJE_SIM_LOGISTIC)
    if model_kind == "sim_logistic":
        # El modelo simulado es de clasificación binaria.
        match project.task_type:
            case "regression":
                raise HTTPException(422, MENSAJE_SIM_SOLO_BINARIO)
            case "binary" | "multiclass":
                pass
            case _:
                raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")
    if session.exec(
        select(ModelVersion).where(
            ModelVersion.project_id == project.id, ModelVersion.label == label
        )
    ).first():
        raise HTTPException(409, f"ya existe una versión llamada {label!r} en este proyecto")

    if fairness_interval_method is None:
        version_activa = (
            session.get(ModelVersion, project.active_version_id)
            if project.active_version_id
            else None
        )
        fairness_interval_method = (
            version_activa.fairness_interval_method if version_activa is not None else "ventanas"
        )

    if fairness_window_n is None:
        monitor_fairness = session.exec(
            select(Monitor).where(Monitor.project_id == project.id, Monitor.type == "fairness")
        ).first()
        fairness_window_n = 200
        if monitor_fairness is not None and monitor_fairness.config_json:
            fairness_window_n = int(monitor_fairness.config_json.get("min_records", 200))

    version = ModelVersion(
        project_id=project.id,
        label=label,
        model_kind=model_kind,
        fairness_window_n=fairness_window_n,
        fairness_interval_method=fairness_interval_method,
    )
    session.add(version)
    session.flush()
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="version.creada",
        object_type="model_version",
        object_id=version.id,
        project_id=project.id,
        motivo=motivo,
        after={
            "label": label,
            "model_kind": model_kind,
            "fairness_window_n": fairness_window_n,
            "fairness_interval_method": fairness_interval_method,
        },
        bus=bus,
    )
    session.commit()
    session.refresh(version)
    return version


def _resolver_lote_para_congelar(session: Session, version: ModelVersion, referencia: int) -> Batch:
    """`congelar_linea_base` acepta el id de un lote o de un dataset
    con lotes de esta versión: primero se prueba como lote, si no encaja
    (u otra versión), como dataset."""
    batch = session.get(Batch, referencia)
    if batch is not None and batch.project_id == version.project_id and batch.model_version_id == version.id:
        return batch
    batch = session.exec(
        select(Batch).where(Batch.model_version_id == version.id, Batch.dataset_id == referencia)
    ).first()
    if batch is None:
        raise HTTPException(
            422,
            "congelar_linea_base debe ser el id de un lote o de un dataset con lotes de esta versión",
        )
    return batch


def activate_version(
    session: Session,
    version: ModelVersion,
    *,
    actor: Actor,
    motivo: str,
    correlation_id: str | None = None,
    job_id: int | None = None,
    congelar_linea_base: int | None = None,
    bus: EventBus | None = None,
) -> ModelVersion:
    project = session.get(Project, version.project_id)
    if project is None:
        raise no_encontrado("modelo", version.project_id, "modelos")

    # Se resuelve el lote antes de tocar nada: un `congelar_linea_base`
    # inválido no debe dejar la versión activada a medias. Lo mismo si
    # la versión ya tiene un baseline congelado: `freeze_baseline` daría 409
    # más abajo, pero para entonces la activación ya estaría confirmada
    # (commit en la línea de más abajo), así que se comprueba aquí también.
    if congelar_linea_base is not None and version.frozen_at is not None:
        raise HTTPException(409, "la versión ya tiene un baseline congelado")
    lote_a_congelar = (
        _resolver_lote_para_congelar(session, version, congelar_linea_base)
        if congelar_linea_base is not None
        else None
    )

    before_id = project.active_version_id
    for otra in session.exec(
        select(ModelVersion).where(ModelVersion.project_id == project.id)
    ).all():
        if otra.is_active and otra.id != version.id:
            otra.is_active = False
            session.add(otra)
    version.is_active = True
    session.add(version)
    project.active_version_id = version.id
    project.updated_at = now_iso()
    session.add(project)
    session.flush()

    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="version.activada",
        object_type="model_version",
        object_id=version.id,
        project_id=project.id,
        motivo=motivo,
        before={"active_version_id": before_id},
        after={"active_version_id": version.id},
        correlation_id=correlation_id,
        job_id=job_id,
        bus=bus,
    )
    session.commit()
    session.refresh(version)
    if lote_a_congelar is not None:
        # La activación congela en el mismo paso si se pide; la API sigue
        # permitiendo activar sin congelar (`congelar_linea_base=None`).
        version = freeze_baseline(
            session,
            version,
            lote_a_congelar,
            actor=actor,
            motivo=motivo,
            correlation_id=correlation_id,
            job_id=job_id,
            bus=bus,
        )
    return version


def freeze_baseline(
    session: Session,
    version: ModelVersion,
    batch: Batch,
    *,
    actor: Actor,
    motivo: str,
    laboratorio: bool = False,
    automatico: bool = False,
    commit: bool = True,
    correlation_id: str | None = None,
    job_id: int | None = None,
    bus: EventBus | None = None,
) -> ModelVersion:
    """Congela la línea base. `automatico` marca `after.automatico` en
    el evento; `commit=False` deja la transacción al llamador (la ingesta)."""
    if version.frozen_at is not None and not laboratorio:
        raise HTTPException(409, "la versión ya tiene un baseline congelado")
    if batch.project_id != version.project_id or batch.model_version_id != version.id:
        raise HTTPException(422, "el lote debe pertenecer al proyecto y a la versión indicados")

    before = {"baseline_batch_id": version.baseline_batch_id, "frozen_at": version.frozen_at}
    version.baseline_batch_id = batch.id
    version.frozen_at = now_iso()
    session.add(version)
    session.flush()
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="version.baseline_congelado",
        object_type="model_version",
        object_id=version.id,
        project_id=version.project_id,
        motivo=motivo,
        before=before,
        after={
            "baseline_batch_id": batch.id,
            "frozen_at": version.frozen_at,
            **({"automatico": True} if automatico else {}),
        },
        correlation_id=correlation_id,
        job_id=job_id,
        bus=bus,
    )
    proyecto = session.get(Project, version.project_id)
    tipo = proyecto.task_type if proyecto is not None else "binary"
    # Despacho exhaustivo por tipo. La regresión no corre
    # `_sincronizar_favorable_con_linea_base` (copiaría el `1` heredado a la plantilla).
    match tipo:
        case "binary":
            _sincronizar_favorable_con_linea_base(
                session, version, batch, actor=actor, motivo=motivo,
                correlation_id=correlation_id, bus=bus,
            )
        case "multiclass":
            _sincronizar_favorable_con_linea_base(
                session, version, batch, actor=actor, motivo=motivo,
                correlation_id=correlation_id, bus=bus,
            )
            _fijar_clases_y_umbrales_multiclase(
                session, version, batch, actor=actor, motivo=motivo,
                correlation_id=correlation_id, job_id=job_id, bus=bus,
            )
        case "regression":
            _fijar_regresion_con_linea_base(
                session, version, batch, actor=actor, motivo=motivo,
                correlation_id=correlation_id, job_id=job_id, bus=bus,
            )
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    if commit:
        session.commit()
        session.refresh(version)
    else:
        session.flush()
    return version


# Origen de un umbral que fijó una persona o una política: la propuesta de la
# línea base no lo pisa.
_ORIGENES_DE_PERSONA = ("fabricante", "criterio_clinico", "politica_organizacion")


def _soporte_por_clase(session: Session, batch: Batch, clases: list[Any]) -> dict[str, int]:
    """Filas de la línea base por clase real (`label_class`) o, si ninguna fila
    trae etiqueta, por clase predicha. Una clase declarada sin filas queda en 0."""
    soporte = {clave_clase(c): 0 for c in clases}
    filas = session.exec(
        select(Record.label_class, Record.prediction_class).where(Record.batch_id == batch.id)  # type: ignore[arg-type]
    ).all()
    hay_etiquetas = any(real is not None for real, _ in filas)
    for real, predicha in filas:
        # Con etiquetas, solo cuenta la clase real: una fila sin etiqueta no
        # suma por su clase predicha.
        clave = real if hay_etiquetas else predicha
        if clave is not None and clave in soporte:
            soporte[clave] += 1
    return soporte


def _fusionar_umbrales_monitor(
    monitor: Monitor, nuevos: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """Fusiona `nuevos` en los umbrales del monitor por `(metric_key, kind)`; no
    pisa uno fijado por una persona o una política. Devuelve (aplicados,
    conservados) como texto."""
    actuales = list((monitor.thresholds_json or {}).get("thresholds") or [])
    indice = {(t.get("metric_key"), t.get("kind")): i for i, t in enumerate(actuales)}
    aplicados: list[str] = []
    conservados: list[str] = []
    for t in nuevos:
        clave = (t["metric_key"], t["kind"])
        i = indice.get(clave)
        if i is not None and actuales[i].get("origen") in _ORIGENES_DE_PERSONA:
            conservados.append(f"{t['metric_key']} ({monitor.type})")
            continue
        if i is None:
            indice[clave] = len(actuales)
            actuales.append(t)
        else:
            actuales[i] = t
        aplicados.append(f"{t['metric_key']} {monitor.type} {t['value']:.4g}")
    monitor.thresholds_json = {**(monitor.thresholds_json or {}), "thresholds": actuales}
    monitor.updated_at = now_iso()
    return aplicados, conservados


def _fijar_clases_y_umbrales_multiclase(
    session: Session,
    version: ModelVersion,
    batch: Batch,
    *,
    actor: Actor,
    motivo: str,
    correlation_id: str | None,
    job_id: int | None,
    bus: EventBus | None,
) -> None:
    """Al congelar la línea base de un proyecto multiclase.

    1. fija (o confirma) `Project.classes_json` con las clases del mapeo
       de la línea base, en su orden, y anota el soporte de cada una (una clase
       sin filas se conserva con soporte 0). Evento `proyecto.clases_fijadas`.
    2. aplica la propuesta de umbrales de la línea base
       (`core.calibration.umbrales_linea_base_multiclase`) a los monitores
       `quality` y `drift`, fusionada por `(metric_key, kind)`, con el evento
       `proyecto.umbrales_linea_base_aplicados`. Un fallo del cálculo no
       rompe el congelado: deja un evento con el motivo.
    """
    project = session.get(Project, version.project_id)
    if project is None or batch.dataset_id is None:
        return
    dataset = session.get(Dataset, batch.dataset_id)
    if dataset is None or not dataset.mapping_json:
        return
    mapeo = ColumnMapping(**dataset.mapping_json)
    clases = list(project.classes_json or mapeo.classes)
    if not clases:
        return
    project.classes_json = clases
    session.add(project)
    session.flush()
    soporte = _soporte_por_clase(session, batch, clases)
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="proyecto.clases_fijadas",
        object_type="project",
        object_id=project.id,
        project_id=project.id,
        motivo=motivo,
        after={"classes": clases, "soporte": soporte, "batch_id": batch.id},
        correlation_id=correlation_id,
        job_id=job_id,
        bus=bus,
    )

    from vigia.core.calibration import umbrales_linea_base_multiclase as propuesta

    try:
        from vigia.app.services import evaluate as evaluate_service

        task = tarea_service.tarea_del_proyecto(project, mapeo)
        baseline_df = evaluate_service._frame_from_records(session, batch)
        umbrales = propuesta(baseline_df, task)
        if not task.sin_conjunto_favorable:
            # Con conjunto favorable, la equidad sobre el 0/1 de pertenencia.
            umbrales = [
                *umbrales,
                *_umbrales_de_equidad_desde_linea_base(
                    session, project, version, baseline_df, task,
                    correlation_id=correlation_id, job_id=job_id, bus=bus,
                ),
            ]
    except Exception as exc:  # noqa: BLE001  # no debe romper el congelado
        _evento_umbrales_fallidos(session, project, exc, correlation_id=correlation_id, job_id=job_id, bus=bus)
        return
    _aplicar_umbrales_linea_base(
        session, project, umbrales, batch, actor=actor, motivo=motivo,
        correlation_id=correlation_id, job_id=job_id, bus=bus,
    )


def _evento_umbrales_fallidos(
    session: Session,
    project: Project,
    exc: BaseException,
    *,
    correlation_id: str | None,
    job_id: int | None,
    bus: EventBus | None,
) -> None:
    """Un fallo del cálculo de umbrales no rompe el congelado: deja un evento con el motivo
    (y `proyecto.umbrales_linea_base_fallidos`, que la interfaz lee)."""
    record_event(
        session,
        actor_kind=ACTOR_SISTEMA[0],
        actor_id=ACTOR_SISTEMA[1],
        action="proyecto.umbrales_linea_base_fallidos",
        object_type="project",
        object_id=project.id,
        project_id=project.id,
        after={"error": str(exc)[:300]},
        correlation_id=correlation_id,
        job_id=job_id,
        bus=bus,
    )


def _umbrales_de_equidad_desde_linea_base(
    session: Session,
    project: Project,
    version: ModelVersion,
    baseline_df: Any,
    task: Any,
    *,
    correlation_id: str | None,
    job_id: int | None,
    bus: EventBus | None,
) -> list[Any]:
    """Umbrales de las medidas de pertenencia de equidad (`proponer_umbrales`
    sobre el 0/1 de `prediction` y `label`), como `Threshold` con origen `linea_base`.
    Los usan multiclase con conjunto favorable y regresión con rango. Una medida sin
    valor propuesto (grupo pequeño, sin etiquetas) no aparece. Un fallo de este cálculo
    deja `proyecto.umbrales_linea_base_fallidos` y no quita los demás umbrales."""
    from vigia.app.services.monitors import settings_for
    from vigia.core.calibration import proponer_umbrales
    from vigia.core.schema import Threshold

    try:
        settings = settings_for(session, project, version)
        propuestas = proponer_umbrales(
            baseline_df,
            MonitorType.fairness,
            fairness_config=settings.fairness,
            quality_config=settings.quality,
            task=task,
        )
    except Exception as exc:  # noqa: BLE001  # no debe romper el congelado
        _evento_umbrales_fallidos(session, project, exc, correlation_id=correlation_id, job_id=job_id, bus=bus)
        return []
    return [
        Threshold(
            metric_key=p.metric_key,
            kind=p.kind,
            value=p.value,
            origen="linea_base",
            nota=p.motivo,
        )
        for p in propuestas
        if p.value is not None
    ]


def _aplicar_umbrales_linea_base(
    session: Session,
    project: Project,
    umbrales: list[Any],
    batch: Batch,
    *,
    actor: Actor,
    motivo: str,
    correlation_id: str | None,
    job_id: int | None,
    bus: EventBus | None,
) -> None:
    """Fusiona `umbrales` (con origen `linea_base`) en sus monitores por `(metric_key,
    kind)` sin pisar un origen de persona y deja el evento
    `proyecto.umbrales_linea_base_aplicados` con los valores."""
    from vigia.core.calibration import monitor_de_umbral as monitor_de

    por_monitor: dict[str, list[dict[str, Any]]] = {}
    for t in umbrales:
        tipo_monitor = monitor_de(t.metric_key)
        por_monitor.setdefault(str(getattr(tipo_monitor, "value", tipo_monitor)), []).append(
            t.model_dump(mode="json")
        )
    monitores = {
        m.type: m
        for m in session.exec(select(Monitor).where(Monitor.project_id == project.id)).all()
    }
    aplicados: list[str] = []
    conservados: list[str] = []
    for tipo, lista in por_monitor.items():
        monitor = monitores.get(tipo)
        if monitor is None:
            continue
        a, c = _fusionar_umbrales_monitor(monitor, lista)
        aplicados.extend(a)
        conservados.extend(c)
        session.add(monitor)
    session.flush()
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="proyecto.umbrales_linea_base_aplicados",
        object_type="project",
        object_id=project.id,
        project_id=project.id,
        motivo=motivo,
        after={"umbrales": aplicados, "conservados": conservados, "batch_id": batch.id},
        correlation_id=correlation_id,
        job_id=job_id,
        bus=bus,
    )


def _fijar_regresion_con_linea_base(
    session: Session,
    version: ModelVersion,
    batch: Batch,
    *,
    actor: Actor,
    motivo: str,
    correlation_id: str | None,
    job_id: int | None,
    bus: EventBus | None,
) -> None:
    """Al congelar la línea base de un proyecto de regresión.

    1. Completa la plantilla con las columnas estables de la línea base (predicción,
       etiqueta y fecha), como en clasificación, pero sin la clase favorable ni la
       probabilidad (`_sincronizar_favorable_con_linea_base` no corre en regresión).
    2. Fija la unidad y el rango favorable del proyecto (`target_unit`,
       `favorable_ranges_json`) con los del proyecto, la plantilla o el mapeo de la línea
       base, por ese orden; desde aquí no cambian. Evento
       `proyecto.rango_favorable_fijado` si hay rango nuevo.
    3. Aplica los umbrales de la línea base (`umbrales_linea_base_regresion`, origen
       `linea_base`) y, con rango, los de equidad sobre el 0/1 de pertenencia,
       fusionados por `(metric_key, kind)` sin pisar un origen de persona. Un fallo del
       cálculo no impide congelar: deja `proyecto.umbrales_linea_base_fallidos`.
    """
    project = session.get(Project, version.project_id)
    if project is None or batch.dataset_id is None:
        return
    dataset = session.get(Dataset, batch.dataset_id)
    if dataset is None or not dataset.mapping_json:
        return
    mapeo_dict = dataset.mapping_json
    mapeo = ColumnMapping(**mapeo_dict)
    plantilla = MappingTemplate(**(project.mapping_template_json or {}))

    columnas = {
        campo: mapeo_dict[campo]
        for campo in ("prediction_col", "label_col", "timestamp_col")
        if getattr(plantilla, campo) is None and mapeo_dict.get(campo)
    }
    if columnas.get("timestamp_col") in plantilla.feature_cols:
        del columnas["timestamp_col"]

    unidad = project.target_unit
    if unidad is None:
        unidad = validar_unidad(plantilla.target_unit) or validar_unidad(mapeo.target_unit)
    fijados = tarea_service.rangos_del_proyecto(project)
    if fijados is not None:
        rangos = fijados
    else:
        rangos = validar_rangos(plantilla.favorable_ranges) or validar_rangos(mapeo.favorable_ranges)
    antes = project.mapping_template_json
    project.target_unit = unidad
    project.favorable_ranges_json = [list(r) for r in rangos]
    nueva = plantilla.model_copy(
        update={**columnas, "target_unit": unidad, "favorable_ranges": list(rangos)}
    )
    project.mapping_template_json = nueva.model_dump(mode="json")
    project.updated_at = now_iso()
    session.add(project)
    session.flush()
    if columnas:
        record_event(
            session,
            actor_kind=actor.kind,
            actor_id=actor.id,
            role=actor.role,
            action="proyecto.plantilla_actualizada",
            object_type="project",
            object_id=project.id,
            project_id=project.id,
            motivo=motivo,
            before={"mapping_template": antes},
            after={"mapping_template": project.mapping_template_json},
            correlation_id=correlation_id,
            bus=bus,
        )
    if rangos and fijados != rangos:
        _evento_rango_fijado(
            session, project, unidad, rangos, actor=actor, motivo=motivo,
            correlation_id=correlation_id, job_id=job_id, bus=bus,
        )

    try:
        from vigia.app.services import evaluate as evaluate_service
        from vigia.app.services.monitors import settings_for
        from vigia.core.calibration import umbrales_linea_base_regresion

        task = tarea_service.tarea_del_proyecto(project, mapeo)
        baseline_df = evaluate_service._frame_from_records(session, batch)
        settings = settings_for(session, project, version)
        umbrales = umbrales_linea_base_regresion(
            baseline_df,
            task,
            quality_config=settings.quality,
            fairness_config=settings.fairness,
        )
        if not task.sin_rango_favorable:
            # Con rango, la equidad sobre el 0/1 de pertenencia.
            umbrales = [
                *umbrales,
                *_umbrales_de_equidad_desde_linea_base(
                    session, project, version, baseline_df, task,
                    correlation_id=correlation_id, job_id=job_id, bus=bus,
                ),
            ]
    except Exception as exc:  # noqa: BLE001  # no debe romper el congelado
        _evento_umbrales_fallidos(session, project, exc, correlation_id=correlation_id, job_id=job_id, bus=bus)
        return
    _aplicar_umbrales_linea_base(
        session, project, umbrales, batch, actor=actor, motivo=motivo,
        correlation_id=correlation_id, job_id=job_id, bus=bus,
    )


def _sincronizar_favorable_con_linea_base(
    session: Session,
    version: ModelVersion,
    batch: Batch,
    *,
    actor: Actor,
    motivo: str,
    correlation_id: str | None,
    bus: EventBus | None,
) -> None:
    """Si la plantilla del proyecto no tiene `favorable_label`, lo copia
    del mapeo del dataset de la línea base recién congelada y, si es entero,
    también a `Project.favorable_label`. Evento `proyecto.favorable_sincronizado`.

    Con la misma regla copia `prediction_col`, `probability_col`,
    `label_col` y `timestamp_col` que la plantilla no fije (evento
    `proyecto.plantilla_actualizada`), para que el segundo lote no vuelva a
    pedirlas."""
    project = session.get(Project, version.project_id)
    if project is None or batch.dataset_id is None:
        return
    plantilla = MappingTemplate(**(project.mapping_template_json or {}))
    dataset = session.get(Dataset, batch.dataset_id)
    if dataset is None or not dataset.mapping_json:
        return
    mapeo = dataset.mapping_json
    favorable_dataset = mapeo.get("favorable_label") if plantilla.favorable_label is None else None
    columnas = {
        campo: mapeo[campo]
        for campo in ("prediction_col", "probability_col", "label_col", "timestamp_col")
        if getattr(plantilla, campo) is None and mapeo.get(campo)
    }
    # Las clases y las columnas de probabilidad por clase también son
    # estables entre lotes.
    columnas.update(
        {
            campo: list(mapeo[campo])
            for campo in ("classes", "probability_cols")
            if not getattr(plantilla, campo) and mapeo.get(campo)
        }
    )
    # Una plantilla antigua que trae la fecha entre sus variables no
    # puede recibirla también como columna de fecha (`MappingTemplate` lo rechaza).
    if columnas.get("timestamp_col") in plantilla.feature_cols:
        del columnas["timestamp_col"]
    if favorable_dataset is None and not columnas:
        return
    antes = project.mapping_template_json
    cambios: dict[str, Any] = dict(columnas)
    if favorable_dataset is not None:
        cambios["favorable_label"] = favorable_dataset
    plantilla_nueva = plantilla.model_copy(update=cambios)
    project.mapping_template_json = plantilla_nueva.model_dump(mode="json")
    # `Project.favorable_label` es solo compatibilidad (entero); un conjunto
    # o una favorable de texto viven en la plantilla.
    if isinstance(favorable_dataset, list) and len(favorable_dataset) == 1:
        favorable_dataset_simple = favorable_dataset[0]
    else:
        favorable_dataset_simple = favorable_dataset
    if isinstance(favorable_dataset_simple, int) and not isinstance(favorable_dataset_simple, bool):
        project.favorable_label = favorable_dataset_simple
    project.updated_at = now_iso()
    session.add(project)
    session.flush()
    if favorable_dataset is not None:
        record_event(
            session,
            actor_kind=actor.kind,
            actor_id=actor.id,
            role=actor.role,
            action="proyecto.favorable_sincronizado",
            object_type="project",
            object_id=project.id,
            project_id=project.id,
            motivo=motivo,
            after={"favorable_label": favorable_dataset},
            correlation_id=correlation_id,
            bus=bus,
        )
    if columnas:
        record_event(
            session,
            actor_kind=actor.kind,
            actor_id=actor.id,
            role=actor.role,
            action="proyecto.plantilla_actualizada",
            object_type="project",
            object_id=project.id,
            project_id=project.id,
            motivo=motivo,
            before={"mapping_template": antes},
            after={"mapping_template": project.mapping_template_json},
            correlation_id=correlation_id,
            bus=bus,
        )


def _unlink_dataset_file(dataset: Dataset) -> None:
    """Intenta retirar el fichero del dataset; si falla, `_limpiar_ficheros` lo
    reintenta con la carpeta entera y deja constancia de lo que siga en disco."""
    if not dataset.file_path:
        return
    try:
        Path(dataset.file_path).unlink(missing_ok=True)
    except OSError:
        pass


def _carpeta_de(data_dir: Path | str, *partes: str | int) -> Path:
    """Carpeta bajo `data_dir` con ids numéricos; nunca sale de `data_dir`."""
    raiz = Path(data_dir).resolve()
    destino = raiz.joinpath(*(str(p) for p in partes)).resolve()
    if raiz not in destino.parents:
        raise ValueError("carpeta fuera de la carpeta de datos")
    return destino


def _limpiar_ficheros(
    data_dir: Path | str | None,
    project_id: int,
    demo_run_ids: list[int],
    artefactos: list[str],
    *,
    con_artefactos: bool,
    ficheros_dataset: list[str] | None = None,
) -> list[str]:
    """Retira del disco lo que el proyecto dejó fuera de la base: subidas, carpetas
    de las reproducciones de demo y, si se borra el proyecto, los artefactos de modelo.
    Va después del `commit`: un fallo de la base no pierde ficheros.

    Devuelve los ficheros que no se pudieron retirar, con la ruta relativa a
    `data_dir`: quien llama los deja en el log y en el diario."""
    if data_dir is None:
        return []
    raiz = Path(data_dir).resolve()
    quedan: set[str] = set()
    carpetas: list[Path] = [_carpeta_de(data_dir, "uploads", project_id)]
    carpetas += [_carpeta_de(data_dir, "demo", run_id) for run_id in demo_run_ids]
    if con_artefactos:
        raiz_artefactos = _carpeta_de(data_dir, "artifacts", project_id)
        for ruta in artefactos:
            try:
                fichero = Path(ruta).resolve()
                if raiz_artefactos in fichero.parents:
                    fichero.unlink(missing_ok=True)
            except OSError:
                pass
        carpetas.append(raiz_artefactos)
    for carpeta in carpetas:
        shutil.rmtree(carpeta, ignore_errors=True)
        if carpeta.exists():
            ficheros = [f.resolve() for f in carpeta.rglob("*") if f.is_file()]
            quedan.update(_relativa(f, raiz) for f in (ficheros or [carpeta.resolve()]))
    for ruta in ficheros_dataset or []:
        fichero = Path(ruta)
        if fichero.exists():
            quedan.add(_relativa(fichero.resolve(), raiz))
    return sorted(quedan)


def _relativa(ruta: Path, raiz: Path) -> str:
    """Ruta relativa a `data_dir`: el diario no lleva rutas absolutas del usuario."""
    try:
        return ruta.relative_to(raiz).as_posix()
    except ValueError:
        return ruta.name


def _avisar_limpieza_incompleta(
    session: Session, project_id: int, accion: str, quedan: list[str], bus: EventBus | None
) -> None:
    """Deja en el log y en el diario los ficheros que siguen en disco tras un
    borrado o un reinicio, para que el dato no quede retirado solo en apariencia."""
    if not quedan:
        return
    _log.warning(
        "proyecto %s: %s dejó %d fichero(s) sin retirar: %s", project_id, accion, len(quedan), quedan
    )
    record_event(
        session,
        actor_kind=ACTOR_SISTEMA[0],
        actor_id=ACTOR_SISTEMA[1],
        action="sistema.limpieza_incompleta",
        object_type="project",
        object_id=project_id,
        project_id=project_id,
        after={"origen": accion, "ficheros_sin_retirar": quedan},
        motivo="no se pudieron borrar; ciérralos en el programa que los tenga abiertos y bórralos a mano",
        bus=bus,
    )
    session.commit()


def _terminados(session: Session, project_id: int | None) -> list[Job]:
    """Trabajos del proyecto que ya acabaron (`terminado`, `error`, `cancelado`)."""
    from vigia.app.jobs import ESTADOS_FINALES

    return list(
        session.exec(
            select(Job).where(Job.project_id == project_id, Job.status.in_(ESTADOS_FINALES))  # type: ignore[attr-defined]
        ).all()
    )


def reset_project(
    session: Session,
    project: Project,
    *,
    actor: Actor,
    motivo: str,
    bus: EventBus | None = None,
    data_dir: Path | str | None = None,
) -> dict[str, int]:
    """Deja el proyecto virgen: conserva el proyecto, sus versiones y sus monitores.
    Con `data_dir` retira también sus subidas y las carpetas de sus demos."""
    datasets = _rows(session, Dataset, project.id)
    demo_run_ids = [r.id for r in _rows(session, DemoRun, project.id) if r.id is not None]
    counts = {
        "datasets": len(datasets),
        "batches": len(_rows(session, Batch, project.id)),
        "records": len(_rows(session, Record, project.id)),
        "evaluations": len(_rows(session, Evaluation, project.id)),
        "alerts": len(_rows(session, Alert, project.id)),
        "explanations": len(_rows(session, Explanation, project.id)),
        "usage_logs": len(_rows(session, UsageLog, project.id)),
        "demo_runs": len(_rows(session, DemoRun, project.id)),
    }

    ficheros_dataset = [d.file_path for d in datasets if d.file_path]
    for dataset in datasets:
        _unlink_dataset_file(dataset)

    # También lo que lleva `project_id` sin clave foránea y el reinicio no
    # cubría. Los trabajos en curso se quedan: su worker aún actualiza la fila.
    extras = {
        "outcomes": len(_rows(session, Outcome, project.id)),
        "jobs": len(_terminados(session, project.id)),
    }
    session.exec(sa_delete(Outcome).where(Outcome.project_id == project.id))  # type: ignore[arg-type]
    for trabajo in _terminados(session, project.id):
        session.delete(trabajo)
    # El resumen de uso copiado en un dossier deriva del diario que se borra.
    for dossier in session.exec(select(Dossier).where(Dossier.project_id == project.id)).all():
        if dossier.telemetry_text is not None or dossier.telemetry_included:
            dossier.telemetry_text = None
            dossier.telemetry_included = False
            # La huella se recalcula como al crear, sin la telemetría.
            dossier.sha256 = assemble_markdown(
                profile=dossier.profile_json or {},
                experience=dossier.experience_json or {},
                inventory=dossier.inventory_json or {},
                telemetry_text=None,
                preguntas_por_formulario=plantillas_preguntas(),
            ).sha256
            session.add(dossier)
            extras["dossiers_sin_telemetria"] = extras.get("dossiers_sin_telemetria", 0) + 1

    session.exec(sa_delete(Explanation).where(Explanation.project_id == project.id))  # type: ignore[arg-type]
    session.exec(sa_delete(UsageLog).where(UsageLog.project_id == project.id))  # type: ignore[arg-type]
    session.exec(sa_delete(DemoRun).where(DemoRun.project_id == project.id))  # type: ignore[arg-type]
    session.exec(sa_delete(Alert).where(Alert.project_id == project.id))  # type: ignore[arg-type]
    session.exec(sa_delete(Evaluation).where(Evaluation.project_id == project.id))  # type: ignore[arg-type]
    session.exec(sa_delete(Batch).where(Batch.project_id == project.id))  # type: ignore[arg-type]
    session.exec(sa_delete(Dataset).where(Dataset.project_id == project.id))  # type: ignore[arg-type]
    session.flush()

    for version in session.exec(
        select(ModelVersion).where(ModelVersion.project_id == project.id)
    ).all():
        version.baseline_batch_id = None
        version.frozen_at = None
        version.cross_reference_json = None
        session.add(version)

    # Congelar fija el rango del proyecto aunque sea «sin rango» (`[]`). Un proyecto
    # reiniciado vuelve a estar antes de congelar: ese `[]` pasa a nulo (como al crearlo) para
    # que el rango del mapeo nuevo rija y no se ignore en silencio.
    match project.task_type:
        case "binary" | "multiclass":
            pass
        case "regression":
            if not project.favorable_ranges_json:
                project.favorable_ranges_json = None
                session.add(project)
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")

    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="proyecto.reiniciado",
        object_type="project",
        object_id=project.id,
        project_id=project.id,
        motivo=motivo,
        before={**counts, **extras},
        bus=bus,
    )
    session.commit()
    quedan = _limpiar_ficheros(
        data_dir, project.id, demo_run_ids, [], con_artefactos=False, ficheros_dataset=ficheros_dataset
    )
    _avisar_limpieza_incompleta(session, project.id, "reinicio", quedan, bus)
    return counts


def delete_project(
    session: Session,
    project: Project,
    *,
    actor: Actor,
    bus: EventBus | None = None,
    data_dir: Path | str | None = None,
) -> None:
    """Borra el proyecto y todo lo que cuelga de él (menos los eventos, que no tienen FK).
    Con `data_dir` retira también sus subidas, artefactos de modelo y carpetas de demo."""
    project_id = project.id
    project_name = project.name
    demo_run_ids = [r.id for r in _rows(session, DemoRun, project.id) if r.id is not None]
    artefactos = [
        v.artifact_path
        for v in session.exec(select(ModelVersion).where(ModelVersion.project_id == project.id)).all()
        if v.artifact_path
    ]
    ficheros_dataset = []
    for dataset in _rows(session, Dataset, project.id):
        if dataset.file_path:
            ficheros_dataset.append(dataset.file_path)
        _unlink_dataset_file(dataset)
    session.exec(sa_delete(Outcome).where(Outcome.project_id == project.id))  # type: ignore[arg-type]
    for trabajo in _terminados(session, project.id):  # `job` no cuelga de `project`
        session.delete(trabajo)
    session.delete(project)
    session.flush()
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="proyecto.borrado",
        object_type="project",
        object_id=project_id,
        project_id=project_id,
        before={"name": project_name},
        bus=bus,
    )
    session.commit()
    quedan = _limpiar_ficheros(
        data_dir,
        project_id,
        demo_run_ids,
        artefactos,
        con_artefactos=True,
        ficheros_dataset=ficheros_dataset,
    )
    _avisar_limpieza_incompleta(session, project_id, "borrado", quedan, bus)
