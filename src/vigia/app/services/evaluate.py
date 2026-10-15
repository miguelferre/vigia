"""Reconstrucción del histórico y evaluación de lotes.

`build_history` reconstruye un `vigia.core.engine.History` desde las tablas
`batch`/`record` (mismo contrato que el motor usa en memoria); `evaluate_batch`
evalúa un lote ya ingerido en los tres monitores habilitados, inserta
`evaluation`/`measurement`, sincroniza alertas (`services/alerting.py`) y, si
procede, dispara la evaluación de alertas cruzadas del carril C3
(`services/human_layer.py`, importado de forma tolerante a su ausencia).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import func
from sqlmodel import Session, select

from vigia import __version__ as APP_VERSION
from vigia.app.bus import EventBus
from vigia.app.errores import no_encontrado
from vigia.app.events import ACTOR_MODELO, record_event
from vigia.app.models import (
    Alert,
    Batch,
    Dataset,
    Evaluation,
    Explanation,
    Measurement,
    ModelVersion,
    Monitor,
    Project,
    Record,
    UsageLog,
)
from vigia.app.services import alerting
from vigia.app.services import tarea as tarea_service
from vigia.app.services.monitors import settings_for
from vigia.core import CORE_VERSION
from vigia.core.engine import History
from vigia.core.engine import evaluate_batch as _engine_evaluate_batch
from vigia.core.schema import (
    COL_CLINICIAN,
    COL_GROUP,
    COL_ID,
    COL_LABEL,
    COL_LABEL_CLASS,
    COL_LABEL_VALUE,
    COL_PREDICTION,
    COL_PREDICTION_CLASS,
    COL_PREDICTION_VALUE,
    COL_PROB,
    COL_PROTECTED,
    COL_SEQ,
    COL_SUBGROUP,
    COL_TS,
    HARNESS_FEEDBACK_MAPPING,
    ColumnMapping,
    ExplanationResult,
    col_prob,
)
from vigia.human.cross_alerts import CrossReference

__all__ = ["build_history", "evaluate_batch", "timeline"]

# "explain" solo se evalúa si evaluate_batch recibe explanation=: sin explicación calculada para el lote no hay nada que comparar,
# así que el bucle de abajo la salta cuando no está en `resultados`.
_MONITORES_MOTOR = ("fairness", "quality", "drift", "explain")
_EXPLAIN_KINDS_GLOBALES = ("global_permutation", "global_shap")

_COLUMNAS_BASE = (
    COL_SEQ,
    COL_ID,
    COL_TS,
    COL_PREDICTION,
    COL_PROB,
    COL_LABEL,
    COL_PROTECTED,
    COL_GROUP,
    COL_CLINICIAN,
    COL_SUBGROUP,
)


def _mapping_for_batch(session: Session, batch: Batch) -> ColumnMapping:
    """Mapeo del dataset origen del lote, o `HARNESS_FEEDBACK_MAPPING` si no lo hay."""
    if batch.dataset_id is not None:
        dataset = session.get(Dataset, batch.dataset_id)
        if dataset is not None and dataset.mapping_json:
            return ColumnMapping(**dataset.mapping_json)
    return HARNESS_FEEDBACK_MAPPING


def _frame_from_records(session: Session, batch: Batch) -> pd.DataFrame:
    """Reconstruye el frame canónico crudo de un lote desde sus `record` (orden de ingesta).

    Las columnas de variables se ordenan como `mapping.feature_cols`,
    no alfabético. El orden alfabético desalineaba la posición de cada
    variable frente al orden en el que el motor evalúa `feature_cols`, y
    `feature_drift_score` perdía el `NaN` según esa posición. Las claves que
    aparezcan en los registros pero no estén en el mapeo (datos sueltos, sin
    declarar) van después, en orden alfabético para que el resultado sea
    determinista.
    """
    # filas de columnas, no instancias ORM. Hidratar y soltar 100 000
    # `Record` por lote retenía el GIL durante segundos (identity map, `_cleanup`
    # de sus referencias débiles) y frenaba `/api/health` mientras se evaluaba.
    registros = session.exec(
        select(
            Record.seq,
            Record.external_id,
            Record.timestamp,
            Record.prediction,
            Record.prob_favorable,
            Record.label,
            Record.protected_value,
            Record.group_code,
            Record.clinician_pseudonym,
            Record.subgroup,
            Record.features_json,
            Record.prediction_class,
            Record.label_class,
            Record.probabilities_json,
            Record.prediction_value,
            Record.label_value,
        )
        .where(Record.batch_id == batch.id)  # type: ignore[arg-type]
        .order_by(Record.seq)  # type: ignore[arg-type]
    ).all()

    claves_features: set[str] = set()
    for r in registros:
        if r.features_json:
            claves_features.update(r.features_json.keys())
    mapping = _mapping_for_batch(session, batch)
    en_mapeo = [c for c in mapping.feature_cols if c in claves_features]
    fuera_de_mapeo = sorted(claves_features - set(mapping.feature_cols))
    columnas_features = en_mapeo + fuera_de_mapeo

    # Por columnas, no lista de dicts: construir el frame desde 100 000 dicts
    # hacía una sola llamada larga de pandas que retenía el GIL.
    datos: dict[str, list[Any]] = {
        COL_SEQ: [], COL_ID: [], COL_TS: [], COL_PREDICTION: [], COL_PROB: [],
        COL_LABEL: [], COL_PROTECTED: [], COL_GROUP: [], COL_CLINICIAN: [], COL_SUBGROUP: [],
    }
    for clave in columnas_features:
        datos[clave] = []
    for r in registros:
        datos[COL_SEQ].append(r.seq)
        datos[COL_ID].append(r.external_id)
        datos[COL_TS].append(r.timestamp)
        datos[COL_PREDICTION].append(r.prediction)
        datos[COL_PROB].append(r.prob_favorable)
        datos[COL_LABEL].append(r.label if r.label is not None else float("nan"))
        datos[COL_PROTECTED].append(r.protected_value)
        datos[COL_GROUP].append(r.group_code)
        datos[COL_CLINICIAN].append(r.clinician_pseudonym)
        datos[COL_SUBGROUP].append(r.subgroup)
        features = r.features_json or {}
        for clave in columnas_features:
            datos[clave].append(features.get(clave))

    # Clase predicha, clase real y las `k` probabilidades
    # vuelven al frame como `prediction_class`, `label_class` y `prob__i`. Un lote
    # binario sin esas columnas guardadas da el frame de siempre.
    extras: dict[str, list[Any]] = {}
    if any(r.probabilities_json for r in registros):
        k = max(len(r.probabilities_json) for r in registros if r.probabilities_json)
        for i in range(k):
            extras[col_prob(i)] = [
                (r.probabilities_json[i] if r.probabilities_json and i < len(r.probabilities_json)
                 else float("nan"))
                for r in registros
            ]
    if any(r.prediction_class is not None or r.label_class is not None for r in registros):
        extras[COL_PREDICTION_CLASS] = [r.prediction_class for r in registros]
        extras[COL_LABEL_CLASS] = [r.label_class for r in registros]
    # El valor continuo de una regresión vuelve al frame como
    # `prediction_value` y `label_value` (NaN sin etiqueta); `prediction` y `label`
    # siguen siendo el 0/1 de pertenencia al rango favorable.
    if any(r.prediction_value is not None or r.label_value is not None for r in registros):
        extras[COL_PREDICTION_VALUE] = [
            r.prediction_value if r.prediction_value is not None else float("nan") for r in registros
        ]
        extras[COL_LABEL_VALUE] = [
            r.label_value if r.label_value is not None else float("nan") for r in registros
        ]
    datos.update(extras)

    columnas = [*_COLUMNAS_BASE, *extras, *columnas_features]
    df = pd.DataFrame(datos, columns=columnas)
    if df.empty:
        return df
    for clave in extras:
        if clave.startswith("prob__") or clave in (COL_PREDICTION_VALUE, COL_LABEL_VALUE):
            df[clave] = pd.to_numeric(df[clave], errors="coerce")
    df[COL_PROB] = pd.to_numeric(df[COL_PROB], errors="coerce")
    df[COL_LABEL] = pd.to_numeric(df[COL_LABEL], errors="coerce")
    df[COL_PREDICTION] = pd.to_numeric(df[COL_PREDICTION], errors="coerce").astype(int)
    df[COL_GROUP] = pd.to_numeric(df[COL_GROUP], errors="coerce").fillna(-1).astype(int)
    return df


def build_history(session: Session, project: Project) -> History:
    """Reconstruye el `History` completo del proyecto desde `batch`/`record`."""
    history = History()
    versiones = {
        v.id: v
        for v in session.exec(select(ModelVersion).where(ModelVersion.project_id == project.id)).all()
    }
    lotes = session.exec(
        select(Batch).where(Batch.project_id == project.id).order_by(Batch.seq)  # type: ignore[arg-type]
    ).all()
    for batch in lotes:
        version = versiones.get(batch.model_version_id)
        if version is None:
            continue
        mapping = _mapping_for_batch(session, batch)
        df = _frame_from_records(session, batch)
        if df.empty:
            continue
        history.add_batch(
            df,
            mapping=mapping,
            model_version=version.label,
            batch_seq=batch.seq,
            phase_label=batch.phase_label,
            orden_manipulado=batch.orden_manipulado,
            motivo=batch.motivo_manipulacion,
        )

    for version in versiones.values():
        if version.baseline_batch_id is not None:
            baseline_batch = session.get(Batch, version.baseline_batch_id)
            if baseline_batch is not None:
                history.freeze_baseline(baseline_batch.seq, version.label)
        if version.cross_reference_json:
            history.set_reference(version.label, CrossReference(**version.cross_reference_json))

    return history


_TODOS_LOS_OBJETIVOS: Any = object()


def objetivo_de(params: Any) -> tuple[Any, ...] | None:
    """Qué explica una explicación global guardada. `None` en binario y
    en regresión; en multiclase, la clase pedida o el conjunto favorable. Dos
    rankings solo se comparan si tienen el mismo objetivo."""
    p = params if isinstance(params, dict) else {}
    if p.get("objetivo") == "clase":
        return ("clase", p.get("clase"))
    if p.get("objetivo") == "favorables":
        return ("favorables", tuple(p.get("clases") or ()))
    return None


def _explain_reference_for_version(
    session: Session,
    version: ModelVersion,
    *,
    excluir_explanation_id: int | None,
    objetivo: Any = _TODOS_LOS_OBJETIVOS,
) -> ExplanationResult | None:
    """Explicación global de referencia de una versión.

    Con `objetivo` (el de la explicación que se evalúa, ver
    `objetivo_de`), solo cuentan las explicaciones del mismo objetivo: en
    multiclase, un ranking de otra clase no es referencia.

    Regla: la referencia es la PRIMERA explicación global disponible que se
    calculó para la versión, en orden cronológico (`Explanation.id`
    creciente, que coincide con el orden de inserción). No hay ningún campo
    nuevo en `ModelVersion` que la guarde: se deriva por consulta en cada llamada, igual que
    `History.baseline_for`/`reference_for` se reconstruyen desde columnas ya
    persistidas, salvo que aquí la fuente es la propia tabla `explanation` en
    vez de un campo dedicado.

    `excluir_explanation_id` descarta la explicación que se está evaluando en
    esta misma llamada: si es la primera de la versión, no hay ninguna
    anterior que excluir y la referencia sale `None`, así que
    `core.explain.evaluate_explain` clasifica el lote como `sin_datos` con
    motivo, nunca un error. A partir de la segunda explicación global de la
    versión, la primera pasa a ser la referencia de todas las siguientes.
    """
    consulta = (
        select(Explanation)
        .where(
            Explanation.model_version_id == version.id,
            Explanation.kind.in_(_EXPLAIN_KINDS_GLOBALES),  # type: ignore[attr-defined]
        )
        .order_by(Explanation.id)  # type: ignore[arg-type]
    )
    for candidata in session.exec(consulta).all():
        if candidata.id == excluir_explanation_id or not candidata.available:
            continue
        if objetivo is not _TODOS_LOS_OBJETIVOS and objetivo_de(candidata.params_json) != objetivo:
            continue
        leida = _releer_explicacion(candidata)
        if leida is None:
            continue
        return leida
    return None


def _releer_explicacion(explicacion: Explanation) -> ExplanationResult | None:
    """Relee el resultado guardado de una explicación. Si no se puede
    validar (por ejemplo, una importancia sin número guardada antes), devuelve
    `None` y quien llama la trata como no disponible: no tumba la evaluación."""
    try:
        return ExplanationResult.model_validate(explicacion.result_json)
    except ValidationError:
        return None


def _marca_de_lote_anterior(session: Session, batch: Batch) -> str | None:
    """Marca de tiempo para la evaluación de un lote que ya no es el último
    evaluado del proyecto, o `None` si sí lo es.

    Solo el lote más reciente decide el estado vigente: la evaluación se guarda,
    pero se sitúa en la historia justo antes de la primera evaluación de un lote
    posterior (mismo criterio de orden que la demo con `created_at` retrasado), y
    no toca las alertas."""
    primera = session.exec(
        select(func.min(Evaluation.created_at))
        .join(Batch, Evaluation.batch_id == Batch.id)  # type: ignore[arg-type]
        .where(Evaluation.project_id == batch.project_id, Batch.seq > batch.seq)
    ).one()
    if primera is None:
        return None
    return (datetime.fromisoformat(primera) - timedelta(microseconds=1)).isoformat(
        timespec="microseconds"
    )


def evaluate_batch(
    session: Session,
    batch: Batch,
    *,
    trigger: str,
    job: Any | None = None,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
    with_cross: bool = True,
    explanation: Explanation | None = None,
) -> dict[str, Evaluation]:
    """Evalúa `batch` en los monitores del motor habilitados y sincroniza sus alertas.

    `with_cross=False` omite la evaluación de cruzadas: lo usa el reproductor
    de demo con decisiones humanas, que inserta el diario de uso de la fase
    después de evaluar el lote y lanza las cruzadas él mismo (una por fase).

    `explanation` es la fila `Explanation` ya
    calculada y guardada para este lote (típicamente por
    `services.explain.explain_global`, llamada por quien orquesta antes de
    invocar esta función: el motor no sabe calcular explicaciones, solo
    compararlas). Si se pasa y `explanation.available`, se evalúa también el
    monitor `explain` contra su referencia (`_explain_reference_for_version`,
    la regla de "primera explicación global de la versión"); si no se pasa,
    o la explicación no está disponible (p.ej. SHAP sin instalar), el
    comportamiento es el de siempre: sin clave `"explain"` en el resultado.

    Inserta `evaluation`/`measurement` por monitor, deja evento
    `evaluacion.completada` por monitor y, si el proyecto tiene diario de uso
    para la versión del lote y el monitor `cross` está habilitado, dispara
    también la evaluación de cruzadas (carril C3, importado de forma
    tolerante a su ausencia).
    """
    project = session.get(Project, batch.project_id)
    if project is None:
        raise no_encontrado("modelo", batch.project_id, "modelos")
    version = session.get(ModelVersion, batch.model_version_id)
    if version is None:
        raise no_encontrado("versión", batch.model_version_id, "versiones")

    history = build_history(session, project)
    settings = settings_for(session, project, version)

    explanation_result: ExplanationResult | None = None
    if explanation is not None and explanation.available:
        explanation_result = _releer_explicacion(explanation)
        referencia = (
            _explain_reference_for_version(
                session,
                version,
                excluir_explanation_id=explanation.id,
                objetivo=objetivo_de(explanation.params_json),
            )
            if explanation_result is not None
            else None
        )
        if referencia is not None:
            history.set_explain_reference(version.label, referencia)

    # El método del intervalo de la versión y el nombre de la
    # columna de probabilidad del fichero llegan al motor; con "ventanas" el
    # cálculo es el de siempre, byte a byte.
    mapeo_lote = _mapping_for_batch(session, batch)
    # El `TaskSpec` del proyecto con el mapeo del lote. En
    # binario el motor se llama como siempre; en multiclase recibe
    # `task=`.
    task = tarea_service.tarea_del_proyecto(project, mapeo_lote)
    match task.task_type:
        case "binary":
            extra_motor: dict[str, Any] = {}
        case "multiclass" | "regression":
            extra_motor = {"task": task}
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task.task_type!r}")
    resultados = _engine_evaluate_batch(
        history,
        batch.seq,
        settings,
        explanation=explanation_result,
        fairness_interval_method=version.fairness_interval_method or "ventanas",
        columna_probabilidad=mapeo_lote.probability_col,
        **extra_motor,
    )

    monitores = {
        m.type: m for m in session.exec(select(Monitor).where(Monitor.project_id == project.id)).all()
    }
    config_snapshot = settings.model_dump(mode="json")
    correlacion = correlation_id or (job.correlation_id if job is not None else None)
    job_id = job.job_id if job is not None else None
    marca_anterior = _marca_de_lote_anterior(session, batch)
    # Las alertas del proyecto se identifican sin versión, así que solo
    # el lote de la versión activa las mueve; el de otra versión se evalúa y se
    # guarda igual, pero no toca su estado.
    mueve_alertas = project.active_version_id in (None, version.id)

    evaluaciones: dict[str, Evaluation] = {}
    for monitor_type in _MONITORES_MOTOR:
        if monitor_type not in resultados:
            continue
        monitor = monitores.get(monitor_type)
        if monitor is None or not monitor.enabled:
            continue
        resultado = resultados[monitor_type]

        evaluation = Evaluation(
            monitor_id=monitor.id,
            project_id=project.id,
            model_version_id=version.id,
            batch_id=batch.id,
            trigger=trigger,
            window_json=resultado.window.model_dump(mode="json"),
            config_snapshot_json=config_snapshot,
            app_version=APP_VERSION,
            core_version=CORE_VERSION,
            status="ok",
            worst_state=resultado.worst_state.value,
            result_json=resultado.to_dict(),
            job_id=job_id,
        )
        if marca_anterior is not None:
            evaluation.created_at = marca_anterior
        session.add(evaluation)
        session.flush()

        for m in resultado.measurements:
            session.add(
                Measurement(
                    evaluation_id=evaluation.id,
                    project_id=project.id,
                    monitor_type=monitor_type,
                    metric_key=m.metric_key,
                    value=m.value,
                    interval_low=m.interval_low,
                    interval_high=m.interval_high,
                    threshold_low=m.threshold_low,
                    threshold_high=m.threshold_high,
                    state=m.state.value,
                    group_code=m.group_code,
                    motivo=m.motivo,
                    extra_json=m.extra,
                )
            )
        session.flush()

        if marca_anterior is None and mueve_alertas:
            alerting.sync_alerts(
                session,
                project,
                monitor,
                evaluation,
                resultado.measurements,
                correlation_id=correlacion,
                job_id=job_id,
                bus=bus,
            )

        record_event(
            session,
            actor_kind=ACTOR_MODELO[0],
            actor_id=ACTOR_MODELO[1],
            action="evaluacion.completada",
            object_type="evaluation",
            object_id=evaluation.id,
            project_id=project.id,
            after={
                "monitor_type": monitor_type,
                **{m.metric_key: m.state.value for m in resultado.measurements},
            },
            correlation_id=correlacion,
            job_id=job_id,
            bus=bus,
        )
        evaluaciones[monitor_type] = evaluation

    cross_monitor = monitores.get("cross")
    if with_cross and cross_monitor is not None and cross_monitor.enabled:
        tiene_uso = session.exec(
            select(UsageLog)
            .where(UsageLog.project_id == project.id, UsageLog.model_version_id == version.id)
            .limit(1)
        ).first()
        if tiene_uso is not None:
            try:
                from vigia.app.services.human_layer import evaluate_cross_for_project
            except ImportError:
                evaluate_cross_for_project = None  # type: ignore[assignment]
            if evaluate_cross_for_project is not None:
                evaluate_cross_for_project(
                    session, project, version=version, trigger=trigger, job=job, bus=bus
                )

    if version.baseline_batch_id == batch.id and evaluaciones:
        _sustituir_evaluaciones_previas(session, batch, evaluaciones)

    session.commit()
    for evaluation in evaluaciones.values():
        session.refresh(evaluation)
    return evaluaciones


def _sustituir_evaluaciones_previas(
    session: Session, batch: Batch, nuevas: dict[str, Evaluation]
) -> None:
    """Reevaluar la línea base sustituye sus evaluaciones y medidas en vez
    de sumar otra tanda (el lote 0 salía con las medidas duplicadas). Las
    alertas que citaban una evaluación sustituida (`origin_evaluation_id`,
    `last_evaluation_id` e historial) pasan a la nueva del mismo monitor. Un
    lote de producción sí acumula evaluaciones: cada una es un punto del
    historial, y la línea base es la referencia, no una serie."""
    nueva_por_monitor = {ev.monitor_id: ev.id for ev in nuevas.values()}
    previas = session.exec(
        select(Evaluation).where(
            Evaluation.batch_id == batch.id,
            Evaluation.monitor_id.in_(list(nueva_por_monitor)),  # type: ignore[attr-defined]
            Evaluation.id.notin_([ev.id for ev in nuevas.values()]),  # type: ignore[attr-defined]
        )
    ).all()
    if not previas:
        return
    destino = {ev.id: nueva_por_monitor[ev.monitor_id] for ev in previas}
    for alerta in session.exec(select(Alert).where(Alert.project_id == batch.project_id)).all():
        cambiada = False
        if alerta.origin_evaluation_id in destino:
            alerta.origin_evaluation_id = destino[alerta.origin_evaluation_id]
            cambiada = True
        if alerta.last_evaluation_id in destino:
            alerta.last_evaluation_id = destino[alerta.last_evaluation_id]
            cambiada = True
        if any(e.get("evaluation_id") in destino for e in (alerta.history_json or [])):
            alerta.history_json = [
                {**e, "evaluation_id": destino[e["evaluation_id"]]}
                if e.get("evaluation_id") in destino
                else e
                for e in (alerta.history_json or [])
            ]
            cambiada = True
        if cambiada:
            session.add(alerta)
    session.flush()
    for ev in previas:
        session.delete(ev)  # las medidas caen por `ondelete="CASCADE"`
    session.flush()


def timeline(
    session: Session,
    project: Project,
    *,
    monitor_type: str,
    metric_key: list[str],
    group_code: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    model_version_id: int | None = None,
) -> list[dict[str, Any]]:
    """Serie temporal de una o varias medidas, ordenada por fecha de evaluación.

    `model_version_id` deja solo los puntos de esa versión; cada
    punto lleva siempre la versión de su evaluación.

    `metric_key` y `group_code` (si se pasa) filtran por lista; `group_code=None`
    sigue siendo "todos los grupos". `since`/`until` acotan `Evaluation.created_at`
    por comparación de texto, igual criterio que `services/evidence.select_events`
    con `Event.ts`: vale porque el formato es ISO 8601 de anchura fija
    (`models.now_iso`), donde el orden lexicográfico coincide con el cronológico.
    El router valida el formato de `since`/`until` antes de llamar aquí.

    Con varias `metric_key`/`group_code` el orden por fecha no basta para que la
    salida sea determinista: se añade `metric_key` y `group_code` como criterio
    secundario estable.
    """
    consulta = (
        select(Measurement, Evaluation)
        .join(Evaluation, Measurement.evaluation_id == Evaluation.id)  # type: ignore[arg-type]
        .where(
            Measurement.project_id == project.id,
            Measurement.monitor_type == monitor_type,
            Measurement.metric_key.in_(metric_key),  # type: ignore[attr-defined]
        )
    )
    if group_code is not None:
        consulta = consulta.where(Measurement.group_code.in_(group_code))  # type: ignore[attr-defined]
    if since is not None:
        consulta = consulta.where(Evaluation.created_at >= since)  # type: ignore[arg-type]
    if until is not None:
        consulta = consulta.where(Evaluation.created_at <= until)  # type: ignore[arg-type]
    if model_version_id is not None:
        consulta = consulta.where(Evaluation.model_version_id == model_version_id)
    consulta = consulta.order_by(  # type: ignore[arg-type]
        Evaluation.created_at, Measurement.metric_key, Measurement.group_code
    )

    lote_seq: dict[int, int | None] = {}
    salida: list[dict[str, Any]] = []
    for medida, evaluacion in session.exec(consulta).all():
        batch_seq = None
        if evaluacion.batch_id is not None:
            if evaluacion.batch_id not in lote_seq:
                lote = session.get(Batch, evaluacion.batch_id)
                lote_seq[evaluacion.batch_id] = lote.seq if lote is not None else None
            batch_seq = lote_seq[evaluacion.batch_id]
        salida.append(
            {
                "evaluation_id": evaluacion.id,
                "model_version_id": evaluacion.model_version_id,
                "batch_id": evaluacion.batch_id,
                "batch_seq": batch_seq,
                "ts": evaluacion.created_at,
                "value": medida.value,
                "interval_low": medida.interval_low,
                "interval_high": medida.interval_high,
                "threshold_low": medida.threshold_low,
                "threshold_high": medida.threshold_high,
                "state": medida.state,
                "metric_key": medida.metric_key,
                "group_code": medida.group_code,
            }
        )
    return salida
