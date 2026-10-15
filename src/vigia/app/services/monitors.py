"""Servicio de monitores: `MonitorSettings` desde la BD y edición con evento."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlmodel import Session, select

from vigia.app.content_loader import protocolo_hitos_plantilla
from vigia.app.errores import no_encontrado, traducir_validacion
from vigia.app.events import Actor, record_event
from vigia.app.models import Batch, ModelVersion, Monitor, Project, now_iso
from vigia.app.schemas.monitors import claves_fuera_de_rango, es_finito
from vigia.app.services.monitors_protocol import validar_protocol
from vigia.core.engine import MonitorSettings
from vigia.core.schema import (
    CLAVES_CALIDAD_REGRESION,
    PREFIJO_GRUPO_CLASE,
    ColumnMapping,
    DriftConfig,
    FairnessConfig,
    MonitorThresholds,
    QualityConfig,
    es_grupo_clase,
)
from vigia.core.thresholds import DEFAULT_QUALITY_THRESHOLDS
from vigia.human.cross_alerts import CrossConfig

__all__ = [
    "get_monitor",
    "list_monitors",
    "patch_monitor",
    "propose_thresholds",
    "protocol_for",
    "settings_for",
]

# Un umbral sin `origen` guardado es uno de antiguo y se
# enseña como de fábrica, sin calibrar.
AVISO_UMBRAL_FABRICA = "umbral de fábrica: no calibrado para este modelo"

_CONFIG_MODELS: dict[str, type] = {
    "fairness": FairnessConfig,
    "quality": QualityConfig,
    "drift": DriftConfig,
    "cross": CrossConfig,
}

# Claves de métrica de calidad válidas para `primary_metric` (las mismas
# que trae `DEFAULT_QUALITY_THRESHOLDS`, no un catálogo aparte que se pueda
# desincronizar).
_CLAVES_METRICA_CALIDAD: frozenset[str] = frozenset(
    t.metric_key for t in DEFAULT_QUALITY_THRESHOLDS.thresholds
)
# En regresión, los cuatro titulares con alerta.
_CLAVES_METRICA_CALIDAD_REGRESION: frozenset[str] = frozenset(CLAVES_CALIDAD_REGRESION)


def claves_metrica_calidad(task_type: str) -> frozenset[str]:
    """Claves válidas de `primary_metric` según el tipo de tarea del proyecto."""
    match task_type:
        case "binary" | "multiclass":
            return _CLAVES_METRICA_CALIDAD
        case "regression":
            return _CLAVES_METRICA_CALIDAD_REGRESION
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task_type!r}")


def get_monitor(session: Session, monitor_id: int) -> Monitor:
    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise no_encontrado("monitor", monitor_id, "monitores")
    return monitor


def list_monitors(session: Session, project_id: int) -> list[Monitor]:
    return list(
        session.exec(select(Monitor).where(Monitor.project_id == project_id)).all()
    )


def protocol_for(session: Session, project_id: int, monitor_type: str) -> list[dict[str, Any]]:
    """Los cinco hitos del protocolo del monitor `(project_id, monitor_type)`: `Monitor.protocol_json` si lo tiene, la plantilla de
    `content/protocolo-hitos.json` si el monitor no existe o es anterior a
    la migración 6. Lo lee `protocol_steps_for_alert` para dar a cada hito
    de la alerta su título, descripción, entregables, responsable y plazo."""
    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == monitor_type)
    ).first()
    if monitor is not None and monitor.protocol_json:
        return [dict(h) for h in monitor.protocol_json]
    return protocolo_hitos_plantilla()


def _get_active_version(session: Session, project_id: int) -> ModelVersion | None:
    from vigia.app.models import Project

    project = session.get(Project, project_id)
    if project is None or project.active_version_id is None:
        return None
    return session.get(ModelVersion, project.active_version_id)


def _config_sana(config: dict[str, Any] | None) -> dict[str, Any]:
    """Configuración guardada sin las claves fuera de rango o no finitas: una fila
    mala (de antes de las cotas) vuelve al valor de fábrica de esa clave y no
    impide evaluar a los demás monitores."""
    config = config or {}
    malas = set(claves_fuera_de_rango(config))
    return {k: v for k, v in config.items() if k not in malas}


def _umbrales_sanos(umbrales: dict[str, Any] | None) -> dict[str, Any]:
    """Umbrales guardados sin los de valor no finito (la fila ya envenenada se lee igual)."""
    umbrales = umbrales or {"thresholds": []}
    return {
        **umbrales,
        "thresholds": [t for t in (umbrales.get("thresholds") or []) if es_finito(t)],
    }


def settings_for(session: Session, project: Any, version: ModelVersion) -> MonitorSettings:
    """Construye `MonitorSettings` a partir de los monitores `fairness`/`quality`/`drift`.

    La ventana de equidad sale siempre de `version.fairness_window_n`,
    nunca del `config_json` guardado: es el monitor quien la refleja hacia
    fuera, pero la versión es la fuente de verdad.
    """
    monitores = {
        m.type: m
        for m in session.exec(
            select(Monitor).where(Monitor.project_id == project.id)
        ).all()
    }

    fairness_monitor = monitores.get("fairness")
    fairness_cfg = FairnessConfig(**_config_sana(fairness_monitor.config_json)) if fairness_monitor else FairnessConfig()
    fairness_cfg = fairness_cfg.model_copy(update={"min_records": version.fairness_window_n})
    fairness_thr = (
        MonitorThresholds(**_umbrales_sanos(fairness_monitor.thresholds_json))
        if fairness_monitor
        else MonitorThresholds()
    )

    quality_monitor = monitores.get("quality")
    quality_cfg = QualityConfig(**_config_sana(quality_monitor.config_json)) if quality_monitor else QualityConfig()
    quality_thr = (
        MonitorThresholds(**_umbrales_sanos(quality_monitor.thresholds_json))
        if quality_monitor
        else MonitorThresholds()
    )

    drift_monitor = monitores.get("drift")
    drift_cfg = DriftConfig(**_config_sana(drift_monitor.config_json)) if drift_monitor else DriftConfig()
    drift_thr = (
        MonitorThresholds(**_umbrales_sanos(drift_monitor.thresholds_json))
        if drift_monitor
        else MonitorThresholds()
    )

    explain_monitor = monitores.get("explain")
    explain_thr = (
        MonitorThresholds(**_umbrales_sanos(explain_monitor.thresholds_json))
        if explain_monitor
        else MonitorThresholds()
    )

    return MonitorSettings(
        fairness=fairness_cfg,
        quality=quality_cfg,
        drift=drift_cfg,
        thresholds={
            "fairness": fairness_thr,
            "quality": quality_thr,
            "drift": drift_thr,
            "explain": explain_thr,
        },
    )


def _resumen_validacion(exc: ValidationError) -> str:
    """Errores de pydantic en español y sin texto en inglés: «campo: texto»."""
    partes = []
    for e in traducir_validacion(exc.errors(include_url=False, include_input=False, include_context=True)):
        campo = ".".join(str(p) for p in e.get("loc", ()))
        partes.append(f"{campo}: {e['msg']}" if campo else str(e["msg"]))
    return "; ".join(partes)


def _validar_config(
    monitor_type: str, config: dict[str, Any], config_actual: dict[str, Any] | None
) -> dict[str, Any]:
    """Valida `config` fusionada con la persistida: un PATCH parcial no resetea a defaults."""
    modelo = _CONFIG_MODELS.get(monitor_type)
    if modelo is None:
        # explain u otros tipos sin modelo pydantic propio: se guarda tal cual.
        return config
    fusionado = {**(config_actual or {}), **config}
    try:
        return modelo(**fusionado).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(
            422, f"la configuración del monitor {monitor_type!r} no es válida: {_resumen_validacion(exc)}"
        ) from exc


MENSAJE_UMBRAL_POR_CLASE = (
    "Las medidas por clase no tienen umbral: se enseñan en la tabla por clase, sin alerta. "
    "Pon el umbral en una medida del monitor (exactitud, F1 macro, AUC macro) o en la "
    "deriva de la predicción"
)


def _es_umbral_por_clase(item: Any) -> bool:
    """Un umbral cuyo `group_code` o `metric_key` apunta a una medida
    por clase (`clase:<valor>`). `Threshold` no tiene `group_code` y pydantic
    descartaría la clave en silencio, así que se mira el cuerpo en bruto."""
    if not isinstance(item, dict):
        return False
    grupo = item.get("group_code")
    clave = item.get("metric_key")
    return es_grupo_clase(grupo if isinstance(grupo, str) else None) or (
        isinstance(clave, str) and PREFIJO_GRUPO_CLASE in clave
    )


def _validar_thresholds(thresholds: dict[str, Any]) -> dict[str, Any]:
    lista = thresholds.get("thresholds") if isinstance(thresholds, dict) else None
    if isinstance(lista, list) and any(_es_umbral_por_clase(t) for t in lista):
        raise HTTPException(422, MENSAJE_UMBRAL_POR_CLASE)
    try:
        return MonitorThresholds(**thresholds).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(422, f"los umbrales no son válidos: {_resumen_validacion(exc)}") from exc


def patch_monitor(
    session: Session,
    monitor: Monitor,
    *,
    actor: Actor,
    role: str | None,
    motivo: str,
    enabled: bool | None = None,
    config: dict[str, Any] | None = None,
    thresholds: dict[str, Any] | None = None,
    protocolo_md: str | None = None,
    protocol: list[dict[str, Any]] | None = None,
    laboratorio: bool = False,
    correlation_id: str | None = None,
    bus: Any | None = None,
) -> tuple[Monitor, int]:
    """Aplica los cambios pedidos, valida y escribe el evento `monitor.configurado`.

    Solo bloquea `min_records`: un cambio de `fairness.config.min_records`
    exige `laboratorio=True` y que la versión activa sea `sim_logistic`; en ese
    caso también actualiza `ModelVersion.fairness_window_n` y lo refleja en el
    mismo evento.
    """
    if config is not None and not es_finito(config):
        raise HTTPException(422, "la configuración del monitor solo admite números finitos")
    if thresholds is not None and not es_finito(thresholds):
        raise HTTPException(422, "los umbrales solo admiten números finitos")

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    if enabled is not None and enabled != monitor.enabled:
        before["enabled"], monitor.enabled, after["enabled"] = monitor.enabled, enabled, enabled

    if config is not None:
        # `primary_metric` no es un campo de `QualityConfig` (extra="ignore"
        # en pydantic la perdería en el `model_dump`), así que se valida y se
        # guarda aparte, preservando el valor persistido si el PATCH no la toca.
        config_sin_primary_metric = {k: v for k, v in config.items() if k != "primary_metric"}
        config_validado = _validar_config(
            monitor.type, config_sin_primary_metric, monitor.config_json
        )
        if monitor.type == "quality":
            if "primary_metric" in config:
                primary_metric = config["primary_metric"]
                proyecto_monitor = session.get(Project, monitor.project_id)
                validas = claves_metrica_calidad(
                    proyecto_monitor.task_type if proyecto_monitor is not None else "binary"
                )
                if primary_metric is not None and primary_metric not in validas:
                    raise HTTPException(
                        422,
                        f"la métrica principal {primary_metric!r} no es válida: elige una de "
                        f"{', '.join(sorted(validas))}",
                    )
            else:
                primary_metric = (monitor.config_json or {}).get("primary_metric")
            if primary_metric is not None:
                config_validado["primary_metric"] = primary_metric
        if monitor.type == "fairness":
            actual_min_records = (monitor.config_json or {}).get("min_records")
            nuevo_min_records = config_validado.get("min_records")
            if nuevo_min_records is not None and nuevo_min_records != actual_min_records:
                version = _get_active_version(session, monitor.project_id)
                if not laboratorio or version is None or version.model_kind != "sim_logistic":
                    raise HTTPException(
                        409,
                        "el mínimo de registros de equidad está fijado: solo se cambia "
                        "desde el laboratorio, con un modelo simulado como versión activa",
                    )
                before["fairness_window_n"] = version.fairness_window_n
                version.fairness_window_n = int(nuevo_min_records)
                session.add(version)
                after["fairness_window_n"] = version.fairness_window_n
        before["config"], monitor.config_json, after["config"] = (
            monitor.config_json,
            config_validado,
            config_validado,
        )

    if thresholds is not None:
        thresholds_validados = _validar_thresholds(thresholds)
        before["thresholds"], monitor.thresholds_json, after["thresholds"] = (
            monitor.thresholds_json,
            thresholds_validados,
            thresholds_validados,
        )

    if protocolo_md is not None and protocolo_md != monitor.protocolo_md:
        before["protocolo_md"], monitor.protocolo_md, after["protocolo_md"] = (
            monitor.protocolo_md,
            protocolo_md,
            protocolo_md,
        )

    if protocol is not None:
        protocol_validado = validar_protocol(protocol)
        protocol_actual = monitor.protocol_json or protocolo_hitos_plantilla()
        if protocol_validado != protocol_actual:
            before["protocol"], monitor.protocol_json, after["protocol"] = (
                monitor.protocol_json,
                protocol_validado,
                protocol_validado,
            )

    monitor.updated_at = now_iso()
    session.add(monitor)
    session.flush()

    evento = record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=role or actor.role,
        action="monitor.configurado",
        object_type="monitor",
        object_id=monitor.id,
        project_id=monitor.project_id,
        motivo=motivo,
        before=before,
        after=after,
        correlation_id=correlation_id,
        bus=bus,
    )
    session.commit()
    session.refresh(monitor)
    return monitor, int(evento.id or 0)


# Solo `fairness` y `quality` tienen umbral de fábrica calibrable (# `core/calibration.proponer_umbrales`); `drift`, `explain` y `cross` no.
_MONITORES_CON_PROPUESTA = ("fairness", "quality")


def _propuesta_multiclase(
    session: Session,
    project: Project,
    baseline_batch: Batch,
    baseline_df: Any,
    settings: MonitorSettings,
    *,
    tamano_lote: int,
) -> dict[str, Any]:
    """La propuesta de un proyecto multiclase es la de la línea base
    (`calibration.umbrales_linea_base_multiclase`, la misma que se aplica al
    congelar la línea base) con la forma de la binaria: `monitors` con sus
    `propuestas`. Solo `quality` (exactitud con suelo 1/k, F1 macro y AUC macro)
    y `drift` (deriva de la predicción) llevan propuesta; el monitor de equidad
    multiclase no tiene umbrales calibrables."""
    from vigia.app.models import Dataset
    from vigia.app.services import tarea as tarea_service
    from vigia.core.calibration import monitor_de_umbral, umbrales_linea_base_multiclase

    dataset = session.get(Dataset, baseline_batch.dataset_id) if baseline_batch.dataset_id else None
    if dataset is None or not dataset.mapping_json:
        raise HTTPException(
            409,
            "no encuentro el mapeo de la línea base de la versión activa: vuelve a subirla "
            "y congélala antes de pedir la propuesta de umbrales",
        )
    try:
        task = tarea_service.tarea_del_proyecto(project, ColumnMapping(**dataset.mapping_json))
        propuestas = umbrales_linea_base_multiclase(
            baseline_df, task, tamano_lote=tamano_lote, quality_config=settings.quality
        )
    except HTTPException:
        raise
    except (ValueError, ArithmeticError) as exc:  # datos de la línea base; un fallo de código sube como 500
        # Sin la cola de la excepción en el mensaje (lo comprueba `test_mensajes_error.py`).
        raise HTTPException(
            409,
            "no se pudo calcular la propuesta de umbrales con esta línea base. "
            "Revisa que tenga etiquetas de varias clases y filas de cada clase declarada",
        ) from exc
    monitores = {m.type: m for m in list_monitors(session, project.id)}
    por_monitor: dict[str, list[dict[str, Any]]] = {"quality": [], "drift": []}
    for p in propuestas:
        monitor_clave = monitor_de_umbral(p.metric_key)
        tipo = str(getattr(monitor_clave, "value", monitor_clave))
        monitor = monitores.get(tipo)
        actuales = {
            (t.get("metric_key"), str(getattr(t.get("kind"), "value", t.get("kind")))): t
            for t in ((monitor.thresholds_json or {}).get("thresholds") or [])
        } if monitor is not None else {}
        kind = str(getattr(p.kind, "value", p.kind))
        actual = actuales.get((p.metric_key, kind)) or {}
        origen_actual = actual.get("origen") or "fabrica"
        por_monitor.setdefault(tipo, []).append(
            {
                "metric_key": p.metric_key,
                "kind": p.kind,
                "value": p.value,
                "valor_linea_base": None,
                "motivo": p.nota,
                "umbral_actual": actual.get("value") if es_finito(actual.get("value")) else None,
                "origen_actual": origen_actual,
                "nota_actual": actual.get("nota"),
                "aviso": AVISO_UMBRAL_FABRICA if origen_actual == "fabrica" else None,
            }
        )
    # Con conjunto favorable, la equidad sobre el 0/1 de pertenencia tiene
    # propuesta desde la línea base (la binaria); sin conjunto, no se listan las medidas de
    # pertenencia (todas darían `sin_datos`).
    if not task.sin_conjunto_favorable:
        por_monitor.setdefault("fairness", []).extend(
            _filas_de_equidad_por_pertenencia(monitores, baseline_df, settings, tamano_lote=tamano_lote)
        )
    return {
        "baseline_batch_id": baseline_batch.id,
        "tamano_lote": tamano_lote,
        "monitors": [{"monitor_type": t, "propuestas": items} for t, items in por_monitor.items() if items],
    }


def _fila_de_umbral_propuesto(
    monitor: Monitor | None, metric_key: str, kind: Any, value: Any, valor_linea_base: Any, motivo: Any
) -> dict[str, Any]:
    """Una fila de la propuesta con el umbral que tiene hoy el monitor y su origen
    (por `(metrica, kind)`; `label_skew` tiene un mínimo y un máximo)."""
    umbrales_actuales = {
        (t["metric_key"], str(getattr(t.get("kind"), "value", t.get("kind")))): t
        for t in ((monitor.thresholds_json or {}).get("thresholds") or [])
    } if monitor is not None else {}
    actual = umbrales_actuales.get((metric_key, str(getattr(kind, "value", kind)))) or {}
    origen_actual = actual.get("origen") or "fabrica"
    return {
        "metric_key": metric_key,
        "kind": kind,
        "value": value,
        "valor_linea_base": valor_linea_base,
        "motivo": motivo,
        "umbral_actual": actual.get("value") if es_finito(actual.get("value")) else None,
        "origen_actual": origen_actual,
        "nota_actual": actual.get("nota"),
        "aviso": AVISO_UMBRAL_FABRICA if origen_actual == "fabrica" else None,
    }


def _filas_de_equidad_por_pertenencia(
    monitores: dict[str, Monitor],
    baseline_df: Any,
    settings: MonitorSettings,
    *,
    tamano_lote: int,
) -> list[dict[str, Any]]:
    """La propuesta de equidad sobre el 0/1 de pertenencia es
    `proponer_umbrales(MonitorType.fairness)`, la binaria. La usan multiclase con conjunto
    favorable y regresión con rango."""
    from vigia.core.calibration import proponer_umbrales
    from vigia.core.schema import MonitorType as CoreMonitorType

    propuestas = proponer_umbrales(
        baseline_df,
        CoreMonitorType.fairness,
        tamano_lote=tamano_lote,
        fairness_config=settings.fairness,
        quality_config=settings.quality,
    )
    monitor = monitores.get("fairness")
    return [
        _fila_de_umbral_propuesto(monitor, p.metric_key, p.kind, p.value, p.valor_linea_base, p.motivo)
        for p in propuestas
    ]


def _mapeo_de_la_linea_base(session: Session, baseline_batch: Batch) -> ColumnMapping:
    from vigia.app.models import Dataset

    dataset = session.get(Dataset, baseline_batch.dataset_id) if baseline_batch.dataset_id else None
    if dataset is None or not dataset.mapping_json:
        raise HTTPException(
            409,
            "no encuentro el mapeo de la línea base de la versión activa: vuelve a subirla "
            "y congélala antes de pedir la propuesta de umbrales",
        )
    return ColumnMapping(**dataset.mapping_json)


def _propuesta_regresion(
    session: Session,
    project: Project,
    baseline_batch: Batch,
    baseline_df: Any,
    settings: MonitorSettings,
    *,
    tamano_lote: int,
) -> dict[str, Any]:
    """La propuesta de un proyecto de regresión es la de
    `calibration.umbrales_linea_base_regresion` (la misma que se aplica al congelar la
    línea base) con la forma de la binaria. Calidad (MAE, RMSE, R², sesgo medio), deriva
    de la predicción y equidad por error de grupo salen de ella; con rango favorable,
    además la equidad sobre el 0/1 de pertenencia."""
    from vigia.app.services import tarea as tarea_service
    from vigia.core.calibration import monitor_de_umbral, umbrales_linea_base_regresion

    mapeo = _mapeo_de_la_linea_base(session, baseline_batch)
    try:
        task = tarea_service.tarea_del_proyecto(project, mapeo)
        propuestas = umbrales_linea_base_regresion(
            baseline_df,
            task,
            tamano_lote=tamano_lote,
            quality_config=settings.quality,
            fairness_config=settings.fairness,
        )
    except HTTPException:
        raise
    except (ValueError, ArithmeticError) as exc:  # datos de la línea base; un fallo de código sube como 500
        raise HTTPException(
            409,
            "no se pudo calcular la propuesta de umbrales con esta línea base. "
            "Revisa que tenga etiquetas (el valor real) y filas de cada grupo del atributo protegido",
        ) from exc
    monitores = {m.type: m for m in list_monitors(session, project.id)}
    por_monitor: dict[str, list[dict[str, Any]]] = {}
    for p in propuestas:
        monitor_clave = monitor_de_umbral(p.metric_key)
        tipo = str(getattr(monitor_clave, "value", monitor_clave))
        por_monitor.setdefault(tipo, []).append(
            _fila_de_umbral_propuesto(monitores.get(tipo), p.metric_key, p.kind, p.value, None, p.nota)
        )
    if not task.sin_rango_favorable:
        por_monitor.setdefault("fairness", []).extend(
            _filas_de_equidad_por_pertenencia(monitores, baseline_df, settings, tamano_lote=tamano_lote)
        )
    return {
        "baseline_batch_id": baseline_batch.id,
        "tamano_lote": tamano_lote,
        "monitors": [{"monitor_type": t, "propuestas": items} for t, items in por_monitor.items() if items],
    }


def propose_thresholds(session: Session, project: Project, *, tamano_lote: int = 1000) -> dict[str, Any]:
    """Propuesta de umbral de equidad y calidad sobre el marco
    canónico del lote de línea base de la versión activa, junto al umbral
    que tiene hoy cada monitor y su origen.

    409 si la versión activa no tiene línea base congelada: sin
    línea base no hay marco sobre el que remuestrear.
    """
    # Import diferido: `evaluate.py` importa `settings_for` de este módulo,
    # así que importarlo arriba crearía un ciclo.
    from vigia.app.services import evaluate as evaluate_service
    from vigia.core.calibration import proponer_umbrales
    from vigia.core.schema import MonitorType as CoreMonitorType

    if project.active_version_id is None:
        raise HTTPException(
            409, "el modelo no tiene versión activa: activa una versión antes de pedir la propuesta de umbrales"
        )
    version = session.get(ModelVersion, project.active_version_id)
    if version is None or version.baseline_batch_id is None:
        raise HTTPException(
            409,
            "la versión activa no tiene línea base congelada: sube y congela la línea base "
            "antes de pedir la propuesta de umbrales",
        )
    baseline_batch = session.get(Batch, version.baseline_batch_id)
    if baseline_batch is None:
        raise HTTPException(
            409,
            "la versión activa no tiene línea base congelada: sube y congela la línea base "
            "antes de pedir la propuesta de umbrales",
        )

    baseline_df = evaluate_service._frame_from_records(session, baseline_batch)
    settings = settings_for(session, project, version)
    match project.task_type:
        case "multiclass":
            return _propuesta_multiclase(
                session, project, baseline_batch, baseline_df, settings, tamano_lote=tamano_lote
            )
        case "regression":
            return _propuesta_regresion(
                session, project, baseline_batch, baseline_df, settings, tamano_lote=tamano_lote
            )
        case "binary":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")
    monitores = {m.type: m for m in list_monitors(session, project.id) if m.type in _MONITORES_CON_PROPUESTA}

    resultado_monitores: list[dict[str, Any]] = []
    for tipo in _MONITORES_CON_PROPUESTA:
        monitor = monitores.get(tipo)
        propuestas = proponer_umbrales(
            baseline_df,
            CoreMonitorType(tipo),
            tamano_lote=tamano_lote,
            fairness_config=settings.fairness,
            quality_config=settings.quality,
        )
        # Por (metrica, kind); `label_skew` tiene un minimo y un maximo
        # y, indexado solo por metrica, el minimo recibia el valor del maximo.
        umbrales_actuales = {
            (t["metric_key"], str(getattr(t.get("kind"), "value", t.get("kind")))): t
            for t in ((monitor.thresholds_json or {}).get("thresholds") or [])
        } if monitor is not None else {}
        items: list[dict[str, Any]] = []
        for p in propuestas:
            actual = umbrales_actuales.get((p.metric_key, str(getattr(p.kind, "value", p.kind)))) or {}
            origen_actual = actual.get("origen") or "fabrica"
            items.append(
                {
                    "metric_key": p.metric_key,
                    "kind": p.kind,
                    "value": p.value,
                    "valor_linea_base": p.valor_linea_base,
                    "motivo": p.motivo,
                    "umbral_actual": actual.get("value") if es_finito(actual.get("value")) else None,
                    "origen_actual": origen_actual,
                    "nota_actual": actual.get("nota"),
                    "aviso": AVISO_UMBRAL_FABRICA if origen_actual == "fabrica" else None,
                }
            )
        resultado_monitores.append({"monitor_type": tipo, "propuestas": items})

    return {
        "baseline_batch_id": baseline_batch.id,
        "tamano_lote": tamano_lote,
        "monitors": resultado_monitores,
    }
