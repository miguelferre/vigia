"""Sincronización de alertas y acciones humanas.

`sync_alerts` aplica el catálogo de acciones a las medidas de una evaluación de `fairness`,
`quality` o `drift`: abre o actualiza una alerta por (proyecto, monitor,
métrica, grupo) cuando el estado es `alerta`/`inestable`, y la pasa a
`en_observacion` cuando una evaluación posterior vuelve a `ok`/`aviso`.
`sin_datos` en la medida de una alerta viva la deja como está: sin transición,
sin evento y sin sumar a `observation_count`. Ninguna transición cierra
una alerta: eso exige actor y motivo (`close`).
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import update
from sqlmodel import Session, select

from vigia.app.bus import EventBus
from vigia.app.content_loader import metric_label
from vigia.app.errores import texto_no_encontrado
from vigia.app.events import ACTOR_MODELO, record_event
from vigia.app.models import (
    ACCIONES_ALERTA,
    Alert,
    AlertAction,
    Batch,
    Dataset,
    Evaluation,
    Monitor,
    Project,
    now_iso,
)
from vigia.app.models import Measurement as MeasurementRow
from vigia.core.schema import (
    HARNESS_FEEDBACK_MAPPING,
    ColumnMapping,
    Measurement,
    ProtectedKind,
    State,
)

__all__ = [
    "ESTADOS_ALERTA_FUERA",
    "ETIQUETAS_ACCION",
    "METRIC_LABELS",
    "SEVERIDADES_ALERTA",
    "acknowledge",
    "act",
    "alert_stage",
    "alert_to_dict",
    "alerts_to_dict",
    "bulk_action",
    "catalog",
    "close",
    "decide",
    "group_labels",
    "investigate",
    "label_for_group_code",
    "priv_group_labels",
    "retire_alerts_for_batch",
    "set_protocol",
    "sync_alerts",
    "sync_candidates",
]

# Vocabulario propio de la acción en lote: `acknowledge`/`close`
# son los nombres de los dos endpoints de flujo; el resto son las claves del
# catálogo de acciones (`ETIQUETAS_ACCION`, en español). No es `ACCIONES_ALERTA`
# (`app/models.py`), que además admite los sinónimos `reconocer`/`cerrar`.
_ACCIONES_LOTE_FLUJO = ("acknowledge", "close")

# Nombres de las reglas cruzadas: se leen por lo que pasa, no
# por el código CX-n (la `metric_key`). Son los mismos de `cruzadas-nombres.ts`
# y de `content/metricas-ayuda.json`; `tests/validacion/test_textos_interfaz_r8c_b2.py`
# compara los tres. CX-2 a CX-4 son las reglas cruzadas globales.
METRIC_LABELS: dict[str, str] = {
    "CX-1": "Tasa de correcciones en el grupo con más error",
    "CX-2": "Tasa de correcciones con la calidad en alerta",
    "CX-3": "Tasa de rescate de errores del modelo",
    "CX-4": "Pérdida de criterio profesional (deskilling)",
    "CX-5": "Diferencia de tasa de correcciones entre profesionales",
    "CX-6": "Diferencia de tasa de correcciones por grupo sin alerta de equidad",
    "human_review_zero": "Tasa de correcciones del modelo",
}


def _etiqueta_metrica(metric_key: str) -> str:
    """Etiqueta en español de `metric_key`: `content/metricas-ayuda.json`
    primero (las 45 métricas del motor), `METRIC_LABELS` de respaldo para las
    tres reglas cruzadas, la propia clave en último término."""
    return metric_label(metric_key) or METRIC_LABELS.get(metric_key, metric_key)

# Catálogo de acciones (sin las de flujo `reconocer`/`cerrar`, que tienen
# su propio endpoint) con la etiqueta en español para `GET /alerts/catalog`.
# `seguir_vigilando` es la última: la decisión sin medidas.
ETIQUETAS_ACCION: dict[str, str] = {
    "contener_subgrupo": "Contener el subgrupo",
    "cambiar_umbral": "Cambiar el umbral",
    "pedir_reentrenamiento": "Pedir reentrenamiento",
    "escalar": "Escalar",
    "retirar_modelo": "Retirar el modelo",
    "cribado_retrospectivo": "Revisión retrospectiva",
    "registrar_riesgo": "Registrar riesgo",
    "nota": "Añadir una nota",
    "seguir_vigilando": "Seguir vigilando",
}

# Una alerta `cerrada` o `retirada` no cuenta como activa (ni en listas
# activas, ni en recuentos, ni en `checks_by_state`, ni en las cruzadas).
ESTADOS_ALERTA_FUERA: tuple[str, ...] = ("cerrada", "retirada")

_ESTADOS_ALERTA = (State.alerta, State.inestable)
# `sin_datos` no es recuperación (no hay medida que cumpla): deja la alerta como está.
_ESTADOS_OBSERVACION = (State.ok, State.aviso)

# Severidades que abre la política de alertas: `alerta` a `alta`, `inestable` a `media`.
SEVERIDADES_ALERTA: tuple[str, ...] = ("alta", "media")


def catalog() -> list[dict[str, str]]:
    """Catálogo de acciones de alerta con su etiqueta en español."""
    return [{"action": accion, "label": etiqueta} for accion, etiqueta in ETIQUETAS_ACCION.items()]


def _numero_es(x: float) -> str:
    """Número en formato español para los textos de la UI: coma decimal, tres
    decimales, sin separador de miles (`0,089`, `1234,500`)."""
    return f"{float(x):.3f}".replace(".", ",")


def _numero_unidad_es(x: float) -> str:
    """Valor de una medida en la unidad de la salida, con los decimales
    que da la interfaz (`formatoMetrica`): 0 desde 100, 1 desde 10, 2 desde 0,1 y 3 debajo."""
    a = abs(float(x))
    d = 0 if a >= 100 else 1 if a >= 10 else 2 if a >= 0.1 or a == 0 else 3
    return f"{float(x):.{d}f}".replace(".", ",")


def _formato_rango(lo: float, hi: float) -> str:
    def _num(x: float) -> str:
        return str(int(x)) if float(x).is_integer() else str(x)

    return f"{_num(lo)}-{_num(hi)}"


def _etiquetas_de(mapping: ColumnMapping, grupos: list[Any]) -> list[str]:
    if mapping.protected_kind == ProtectedKind.categorical:
        return [str(g) for g in grupos]
    return [_formato_rango(rango[0], rango[1]) for rango in grupos]


def group_labels(mapping: ColumnMapping) -> list[str]:
    """Etiquetas de los grupos no privilegiados del mapeo: rango numérico
    `[lo, hi]` a `"lo-hi"` (por ejemplo `18-35`); categoría, su texto."""
    return _etiquetas_de(mapping, list(mapping.unpriv_groups))


def priv_group_labels(mapping: ColumnMapping) -> list[str]:
    """Etiquetas de los grupos privilegiados del mapeo, misma convención que `group_labels`."""
    return _etiquetas_de(mapping, list(mapping.priv_groups))


def label_for_group_code(mapping: ColumnMapping, group_code: int) -> str:
    """Etiqueta legible de un `group_code` de `record`.

    `0` (no privilegiado) y `1` (privilegiado) toman las etiquetas del mapeo
    unidas por `", "` (misma convención que `group_labels`); cualquier otro
    código (`-1`, fuera de ambos grupos) es `"otros"`.
    """
    if group_code == 0:
        etiquetas = group_labels(mapping)
    elif group_code == 1:
        etiquetas = priv_group_labels(mapping)
    else:
        return "otros"
    return ", ".join(etiquetas) if etiquetas else "otros"


def last_batch_mapping(session: Session, project: Project) -> ColumnMapping:
    """Mapeo del dataset origen del último batch del proyecto, o `HARNESS_FEEDBACK_MAPPING`
    si no hay batch o el dataset no tiene mapeo (mismo criterio que `services/evaluate.py`)."""
    batch = session.exec(
        select(Batch).where(Batch.project_id == project.id).order_by(Batch.seq.desc())  # type: ignore[attr-defined]
    ).first()
    if batch is not None and batch.dataset_id is not None:
        dataset = session.get(Dataset, batch.dataset_id)
        if dataset is not None and dataset.mapping_json:
            return ColumnMapping(**dataset.mapping_json)
    return HARNESS_FEEDBACK_MAPPING


def _fairness_group_label(session: Session, project: Project) -> str | None:
    etiquetas = group_labels(last_batch_mapping(session, project))
    return ", ".join(etiquetas) if etiquetas else None


# Medidas de una regresión que van en la unidad de la salida; su valor lleva la
# unidad en el título de la alerta («El MAE sube a 7,4 horas por semana (umbral 5,9)»). La
# comparación de versiones usa la misma lista. `r2`, la razón de errores y la deriva de
# la predicción no llevan unidad.
CLAVES_EN_UNIDAD = frozenset(
    {
        "mean_absolute_error",
        "root_mean_squared_error",
        "median_absolute_error",
        "mean_error",
        "mean_absolute_error_difference",
        "mean_error_difference",
    }
)


def _unidad_de_la_salida(project: Project) -> str | None:
    """Unidad de la salida de una regresión (la fijada o la de la plantilla); `None`
    en clasificación."""
    match project.task_type:
        case "binary" | "multiclass":
            return None
        case "regression":
            if project.target_unit:
                return project.target_unit
            plantilla = project.mapping_template_json
            return plantilla.get("target_unit") if isinstance(plantilla, dict) else None
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")


def _titulo(
    session: Session,
    project: Project,
    monitor_type: str,
    *,
    metric_key: str,
    group_code: str | None,
    value: float | None,
    threshold_low: float | None,
    threshold_high: float | None,
    detalle: str | None = None,
) -> str:
    """`"<etiqueta de la métrica> en <etiqueta del grupo>: <valor> (umbral <umbral>)"`.

    La etiqueta del grupo es el propio `group_code` cuando la medida lo trae (fairness
    por subgrupo, cruzadas); si no lo trae y el monitor es `fairness`, sale del mapeo
    del dataset origen (`_fairness_group_label`); en `quality`/`drift` se omite.

    Valor y umbrales van en formato español (`_numero_es`: coma decimal, tres
    decimales); los rangos de grupo (`18-35`) conservan su formato.

    `detalle` (`_detalle_deriva`) es la cola que nombra la variable de
    la deriva; va tras el umbral, así `_titulo_actual` la conserva.
    """
    etiqueta_metrica = _etiqueta_metrica(metric_key)
    if monitor_type in ("quality", "drift"):
        grupo_txt: str | None = None
    elif group_code is not None:
        grupo_txt = group_code
    elif monitor_type == "fairness":
        grupo_txt = _fairness_group_label(session, project)
    else:
        grupo_txt = None
    unidad = _unidad_de_la_salida(project) if metric_key in CLAVES_EN_UNIDAD else None
    sufijo = f" {unidad}" if unidad else ""
    num = _numero_unidad_es if metric_key in CLAVES_EN_UNIDAD else _numero_es
    valor_txt = "n/d" if value is None else num(value) + sufijo
    partes: list[str] = []
    if threshold_low is not None:
        partes.append(f">= {num(threshold_low)}")
    if threshold_high is not None:
        partes.append(f"<= {num(threshold_high)}")
    umbral_txt = " y ".join(partes) if partes else "n/d"
    base = etiqueta_metrica if grupo_txt is None else f"{etiqueta_metrica} en {grupo_txt}"
    cola = f", {detalle}" if detalle else ""
    return f"{base}: {valor_txt} (umbral {umbral_txt}){cola}"


def _detalle_deriva_clase(result: Any) -> str | None:
    """Cola del título de `prediction_drift_score` en multiclase.

    Lee `result.details.prediction.por_clase` (solo lo trae el motor multiclase) y
    nombra la clase que explica la deriva: una clase que la línea base no tenía
    (0 % en la base y más del 0 % en el lote) manda sobre `clase_mayor_cambio`,
    que en ese caso suele ser otra clase que cede lo que gana la nueva. Sin
    `por_clase` (binario) o sin cambio, `None` y el título queda como estaba."""
    if not isinstance(result, dict):
        return None
    detalles = result.get("details")
    pred = detalles.get("prediction") if isinstance(detalles, dict) else None
    por_clase = pred.get("por_clase") if isinstance(pred, dict) else None
    if not isinstance(por_clase, dict) or not por_clase:
        return None

    def _num(valor: Any) -> float | None:
        ok = isinstance(valor, (int, float)) and not isinstance(valor, bool)
        return float(valor) if ok and not math.isnan(valor) else None

    nuevas = [
        (str(clase), _num(v.get("actual")))
        for clase, v in por_clase.items()
        if isinstance(v, dict) and _num(v.get("base")) == 0.0 and (_num(v.get("actual")) or 0.0) > 0.0
    ]
    if nuevas:
        clase, actual = max(nuevas, key=lambda par: par[1] or 0.0)
        return f"clase {clase} nueva: 0 % en la línea base y {_pct_es(actual or 0.0)} en el lote"
    clase = pred.get("clase_mayor_cambio")
    cambio = _num(pred.get("cambio_mayor"))
    if not clase or cambio is None:
        return None
    signo = "+" if cambio >= 0 else "-"
    puntos = f"{abs(cambio) * 100:.1f}".replace(".", ",")
    return f"mayor cambio en la clase {clase} ({signo}{puntos} puntos)"


def _detalle_deriva(metric_key: str, result: Any) -> str | None:
    """Cola del título de una alerta de `feature_drift_score`.

    Lee `result.details.features[]` (el `EvaluationResult` guardado) y nombra
    la variable que da el máximo (el mismo criterio que `feature_drift_score`),
    su valor, la categoría nueva si la hay (recuento 0 en la base y mayor que 0
    en el lote) y `sin categorías comunes con la base` si la fila lo marca
    (`sin_valores_comunes`). Sin dato, `None` y el título queda como estaba.
    """
    if metric_key == "prediction_drift_score":
        return _detalle_deriva_clase(result)
    if metric_key != "feature_drift_score" or not isinstance(result, dict):
        return None
    detalles = result.get("details")
    filas = detalles.get("features") if isinstance(detalles, dict) else None
    if not isinstance(filas, list):
        return None
    mejor: dict[str, Any] | None = None
    for fila in filas:
        if not isinstance(fila, dict):
            continue
        score = fila.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or math.isnan(score):
            continue
        if mejor is None or score > mejor["score"]:
            mejor = fila
    if mejor is None or not mejor.get("feature"):
        return None
    partes = [f"máximo en {mejor['feature']} ({_numero_es(mejor['score'])})"]
    if mejor.get("sin_valores_comunes"):
        partes.append("sin categorías comunes con la base")
    else:
        categorias = mejor.get("categories") or []
        base = mejor.get("bin_counts_base") or []
        actual = mejor.get("bin_counts_actual") or []
        nuevas = [
            str(c)
            for c, b, a in zip(categorias, base, actual, strict=False)
            if b == 0 and a > 0
        ]
        if nuevas:
            visibles = ", ".join(nuevas[:3]) + (f" y {len(nuevas) - 3} más" if len(nuevas) > 3 else "")
            partes.append(f"categoría nueva: {visibles}" if len(nuevas) == 1 else f"categorías nuevas: {visibles}")
    return ", ".join(partes)


def _titulo_actual(session: Session, a: Alert) -> str:
    """Título de `a` con la etiqueta de la métrica recalculada (#1: hasta
    ahora `title` se fijaba solo al abrir la alerta, así que una alerta que
    sigue abierta mucho tiempo se quedaba con el wording viejo si
    `content/metricas-ayuda.json` o `METRIC_LABELS` cambiaban después).

    Reconstruye la base (`_etiqueta_metrica` + grupo, misma regla que
    `_titulo`) y conserva tal cual el resto del título ya guardado (valor y
    umbral, que `Alert` no repite en columnas propias): no se toca la fila,
    solo lo que se sirve. Un título con formato inesperado (sin `": "`, por
    ejemplo uno puesto a mano en un test) se devuelve sin tocar.
    """
    partes = a.title.split(": ", 1)
    if len(partes) != 2:
        return a.title
    _base_vieja, resto = partes
    etiqueta_metrica = _etiqueta_metrica(a.metric_key)
    if a.monitor_type in ("quality", "drift"):
        grupo_txt: str | None = None
    elif a.group_code is not None:
        grupo_txt = a.group_code
    elif a.monitor_type == "fairness":
        project = session.get(Project, a.project_id)
        grupo_txt = _fairness_group_label(session, project) if project is not None else None
    else:
        grupo_txt = None
    base = etiqueta_metrica if grupo_txt is None else f"{etiqueta_metrica} en {grupo_txt}"
    return f"{base}: {resto}"


def _pct_es(x: float) -> str:
    """Proporción como porcentaje en formato español: `0.098` -> `9,8 %`."""
    return f"{float(x) * 100:.1f} %".replace(".", ",")


def _z_es(z: float) -> str:
    return f"{float(z):.2f}".replace(".", ",")


def titulo_cruzada(
    regla: str,
    grupo: str | None,
    *,
    value: float | None,
    reference: float | None,
    z: float | None,
    n: int | None = None,
) -> str:
    """Título de una alerta cruzada con lo que compara y el
    estadístico que dispara, no el «valor (umbral <= referencia)» genérico, que
    se leía como dentro del umbral (el valor es la tasa del grupo y la
    referencia, la del resto, no un límite). Ejemplo CX-6: «Un grupo recibe más
    correcciones y equidad no avisa en urgencias: override 9,8 % frente a 15,0 %
    en el resto (z -6,18)»."""
    base = _etiqueta_metrica(regla)
    if grupo is not None:
        base = f"{base} en {grupo}"
    z_txt = f" (z {_z_es(z)})" if z is not None else ""
    if regla in ("CX-1", "CX-6") and value is not None and reference is not None:
        resto = f"override {_pct_es(value)} frente a {_pct_es(reference)} en el resto{z_txt}"
    elif regla == "CX-2" and value is not None and reference is not None:
        resto = f"override {_pct_es(value)} frente a {_pct_es(reference)} de la referencia{z_txt}"
    elif regla == "CX-5" and value is not None:
        p_txt = "< 0,0001" if value < 0.0001 else f"{value:.4f}".replace(".", ",")
        umbral = f", umbral < {_numero_es(reference)}" if reference is not None else ""
        chi = f", chi2 {_z_es(z)}" if z is not None else ""
        resto = f"override distinto entre profesionales, p {p_txt}{umbral}{chi}"
    elif regla == "CX-4":
        resto = "señal de erosión del criterio disparada" + (
            f" (z de nivel {_z_es(z)})" if z is not None else ""
        )
    else:
        resto = "n/d" + z_txt
    return f"{base}: {resto}"


def _titulo_vigente(
    session: Session,
    project: Project,
    monitor_type: str,
    candidate: dict[str, Any],
    metric_key: str,
    group_code: str | None,
    valor: float | None,
    threshold_low: float | None,
    threshold_high: float | None,
    evaluation: Evaluation | None = None,
) -> str:
    """Título con el último valor y el umbral vigente de la evaluación
    (el candidato trae su propio título, las cruzadas, y manda). con la
    evaluación, el de `feature_drift_score` nombra la variable del máximo."""
    detalle = _detalle_deriva(metric_key, evaluation.result_json) if evaluation is not None else None
    return candidate.get("title") or _titulo(
        session,
        project,
        monitor_type,
        metric_key=metric_key,
        group_code=group_code,
        value=valor,
        threshold_low=threshold_low,
        threshold_high=threshold_high,
        detalle=detalle,
    )


def _sync_one(
    session: Session,
    project: Project,
    monitor: Monitor,
    evaluation: Evaluation,
    candidate: dict[str, Any],
    *,
    correlation_id: str | None,
    job_id: int | None,
    bus: EventBus | None,
) -> Alert | None:
    """Aplica el catálogo de acciones a un candidato genérico: medida del motor o `CrossAlert`."""
    metric_key: str = candidate["metric_key"]
    group_code: str | None = candidate.get("group_code")
    estado = candidate["state"]
    if isinstance(estado, str):
        estado = State(estado)
    valor = candidate.get("value")
    threshold_low = candidate.get("threshold_low")
    threshold_high = candidate.get("threshold_high")
    motivo = candidate.get("motivo")

    existente = session.exec(
        select(Alert).where(
            Alert.project_id == project.id,
            Alert.monitor_type == monitor.type,
            Alert.metric_key == metric_key,
            Alert.group_code == group_code,
            Alert.status.notin_(ESTADOS_ALERTA_FUERA),  # type: ignore[attr-defined]
        )
    ).first()
    ahora = now_iso()

    # Un `aviso` cuyo valor cruza su umbral (lote pequeño) no baja una alerta
    # abierta ni la pasa a observación con «la medida ya cumple»: sigue el seguimiento de
    # `inestable`. No abre alertas nuevas (`existente is None` lo deja fuera).
    aviso_que_cruza = (
        estado == State.aviso
        and existente is not None
        and valor is not None
        and (
            (threshold_low is not None and valor < threshold_low)
            or (threshold_high is not None and valor > threshold_high)
        )
    )

    if estado in _ESTADOS_ALERTA or aviso_que_cruza:
        severidad = "alta" if estado == State.alerta else "media"
        # El título de una alerta de deriva de características se reescribe
        # con la variable del último lote; cada entrada del historial
        # guarda la suya para saber qué variable cruzó en cada lote.
        detalle_deriva = _detalle_deriva(metric_key, evaluation.result_json)
        if existente is None:
            titulo = _titulo_vigente(
                session, project, monitor.type, candidate, metric_key, group_code,
                valor, threshold_low, threshold_high, evaluation,
            )
            fila = Alert(
                project_id=project.id,
                monitor_type=monitor.type,
                metric_key=metric_key,
                group_code=group_code,
                severity=severidad,
                status="abierta",
                title=titulo,
                opened_at=ahora,
                updated_at=ahora,
                last_evaluation_id=evaluation.id,
                last_value=valor,
                origin_batch_id=evaluation.batch_id,
                origin_evaluation_id=evaluation.id,
                protocolo_md=monitor.protocolo_md,
                history_json=[
                    {
                        "ts": ahora,
                        "from": None,
                        "to": "abierta",
                        "evaluation_id": evaluation.id,
                        "batch_id": evaluation.batch_id,
                        "value": valor,
                        "actor": ACTOR_MODELO[1],
                        "actor_kind": ACTOR_MODELO[0],
                        "motivo": motivo,
                        "hito": "deteccion",
                        "detalle": detalle_deriva,
                    }
                ],
            )
            session.add(fila)
            session.flush()
            accion = "alerta.abierta"
        else:
            fila = existente
            historial = list(fila.history_json or [])
            estado_previo = fila.status
            fila.last_evaluation_id = evaluation.id
            fila.last_value = valor
            fila.severity = severidad
            fila.updated_at = ahora
            fila.title = _titulo_vigente(
                session, project, monitor.type, candidate, metric_key, group_code,
                valor, threshold_low, threshold_high, evaluation,
            )
            if estado_previo == "en_observacion":
                fila.status = "abierta"
                fila.reopen_count += 1
                accion = "alerta.reabierta"
            else:
                accion = "alerta.actualizada"
            historial.append(
                {
                    "ts": ahora,
                    "from": estado_previo,
                    "to": fila.status,
                    "evaluation_id": evaluation.id,
                    "batch_id": evaluation.batch_id,
                    "value": valor,
                    "actor": ACTOR_MODELO[1],
                    "actor_kind": ACTOR_MODELO[0],
                    "motivo": motivo,
                    "hito": None,
                    "detalle": detalle_deriva,
                }
            )
            fila.history_json = historial
            session.add(fila)
            session.flush()

        record_event(
            session,
            actor_kind=ACTOR_MODELO[0],
            actor_id=ACTOR_MODELO[1],
            action=accion,
            object_type="alert",
            object_id=fila.id,
            project_id=project.id,
            after={"metric_key": metric_key, "group_code": group_code, "value": valor, "state": estado.value},
            correlation_id=correlation_id,
            job_id=job_id,
            bus=bus,
        )
        return fila

    if estado in _ESTADOS_OBSERVACION and existente is not None and existente.status != "en_observacion":
        fila = existente
        historial = list(fila.history_json or [])
        estado_previo = fila.status
        fila.status = "en_observacion"
        fila.observation_count += 1
        fila.last_evaluation_id = evaluation.id
        fila.last_value = valor
        fila.updated_at = ahora
        # En observación la medida ya cumple y un título con ese valor se
        # leería como «sin incumplimiento»: se conserva el del último disparo
        # (`last_value` sí lleva el valor nuevo).
        historial.append(
            {
                "ts": ahora,
                "from": estado_previo,
                "to": "en_observacion",
                "evaluation_id": evaluation.id,
                "batch_id": evaluation.batch_id,
                "value": valor,
                "actor": ACTOR_MODELO[1],
                "actor_kind": ACTOR_MODELO[0],
                "motivo": motivo,
                "hito": None,
                "detalle": None,
            }
        )
        fila.history_json = historial
        session.add(fila)
        session.flush()

        record_event(
            session,
            actor_kind=ACTOR_MODELO[0],
            actor_id=ACTOR_MODELO[1],
            action="alerta.en_observacion",
            object_type="alert",
            object_id=fila.id,
            project_id=project.id,
            after={"metric_key": metric_key, "group_code": group_code, "state": estado.value},
            correlation_id=correlation_id,
            job_id=job_id,
            bus=bus,
        )
        return fila

    return None


def sync_candidates(
    session: Session,
    project: Project,
    monitor: Monitor,
    evaluation: Evaluation,
    candidates: list[dict[str, Any]],
    *,
    actor_kind: str = "modelo",
    correlation_id: str | None = None,
    job_id: int | None = None,
    bus: EventBus | None = None,
) -> list[Alert]:
    """Aplica el catálogo de acciones a una lista de candidatos genéricos, siempre actor `modelo`.

    Cada candidato es `{metric_key, group_code, state, value, threshold_low,
    threshold_high, motivo, title}` (los cuatro últimos opcionales); `sync_alerts`
    (medidas del motor) y `human_layer.evaluate_cross_for_project` (alertas cruzadas)
    construyen sus candidatos y pasan por aquí: una sola lógica de apertura,
    actualización, reapertura y paso a observación.
    """
    del actor_kind  # el motor siempre es el actor de las sincronizaciones automáticas.
    afectadas: list[Alert] = []
    for candidato in candidates:
        fila = _sync_one(
            session, project, monitor, evaluation, candidato, correlation_id=correlation_id, job_id=job_id, bus=bus
        )
        if fila is not None:
            afectadas.append(fila)
    return afectadas


def sync_alerts(
    session: Session,
    project: Project,
    monitor: Monitor,
    evaluation: Evaluation,
    measurements: list[Measurement],
    *,
    actor_kind: str = "modelo",
    correlation_id: str | None = None,
    job_id: int | None = None,
    bus: EventBus | None = None,
) -> list[Alert]:
    """Aplica el catálogo de acciones a cada medida de `measurements` (siempre actor `modelo`)."""
    candidatos = [
        {
            "metric_key": m.metric_key,
            "group_code": m.group_code,
            "state": m.state,
            "value": m.value,
            "threshold_low": m.threshold_low,
            "threshold_high": m.threshold_high,
            "motivo": m.motivo,
        }
        for m in measurements
    ]
    return sync_candidates(
        session,
        project,
        monitor,
        evaluation,
        candidatos,
        actor_kind=actor_kind,
        correlation_id=correlation_id,
        job_id=job_id,
        bus=bus,
    )


def _lote_de_evaluaciones(
    session: Session, evaluation_ids: set[int]
) -> dict[int, tuple[int | None, int | None, str | None]]:
    """`evaluation_id` -> `(batch_id, seq, phase_label)` para las evaluaciones dadas.

    Dos consultas en total (evaluación -> lote, lote -> datos), no una por
    alerta: la usan `alert_to_dict` (una alerta, resuelve ella misma su
    evaluación) y `alerts_to_dict` (una página entera, H1c)."""
    if not evaluation_ids:
        return {}
    batch_por_evaluacion = dict(
        session.exec(
            select(Evaluation.id, Evaluation.batch_id).where(Evaluation.id.in_(evaluation_ids))  # type: ignore[attr-defined]
        ).all()
    )
    batch_ids = {bid for bid in batch_por_evaluacion.values() if bid is not None}
    lotes = {
        b.id: b for b in session.exec(select(Batch).where(Batch.id.in_(batch_ids))).all()  # type: ignore[attr-defined]
    }
    resultado: dict[int, tuple[int | None, int | None, str | None]] = {}
    for evaluation_id, batch_id in batch_por_evaluacion.items():
        lote = lotes.get(batch_id) if batch_id is not None else None
        resultado[evaluation_id] = (lote.id, lote.seq, lote.phase_label) if lote is not None else (None, None, None)
    return resultado


def _lotes_por_id(session: Session, batch_ids: set[int]) -> dict[int, tuple[int, str | None]]:
    """`batch_id` -> `(seq, phase_label)` de los lotes que siguen vivos (lote de origen de las alertas). Un id ausente del resultado es un lote
    borrado."""
    if not batch_ids:
        return {}
    return {
        b.id: (b.seq, b.phase_label)
        for b in session.exec(select(Batch).where(Batch.id.in_(batch_ids))).all()  # type: ignore[attr-defined]
    }


def triaje_en_historial(history: list[dict[str, Any]] | None) -> bool:
    """El triaje humano dejó rastro en `history_json`: una entrada con
    `hito == "triaje"` o, en alertas antiguas, la transición a
    `reconocida`. Nunca depende del `status` actual: el motor puede haberla
    movido a `en_observacion` sin que nadie la mirase."""
    return any(
        entrada.get("hito") == "triaje" or entrada.get("to") == "reconocida"
        for entrada in (history or [])
    )


def alert_stage(status: str, history: list[dict[str, Any]] | None) -> str:
    """Etiqueta de estado de una alerta = el último hito hecho.

    Función pura, sin consultas: solo mira `status` e `history_json`, así
    `alerts_to_dict` la puede aplicar a una página entera sin ganar un N+1.
    Orden de prioridad: `cerrada` manda siempre; si no, `en_seguimiento`
    (decisión registrada); si no, `en_investigacion` (investigación
    registrada); si no, `en_observacion` (triaje hecho); si no, `detectada`.

    Solo cuentan los hitos humanos: que el motor haya movido `status` a
    `en_observacion` (la métrica volvió dentro del umbral antes de que nadie
    hiciera el triaje) no adelanta la etapa; ese rastro se lee en el
    historial (`alerta.en_observacion`) y en `observation_count`. Antes de
    esta regla una alerta recuperada sola salía «En seguimiento» con «1 de 5
    hitos», una contradicción en la pantalla.
    """
    historial = history or []
    if status in ESTADOS_ALERTA_FUERA:
        return "cerrada"
    if any(entrada.get("hito") == "decision" for entrada in historial):
        return "en_seguimiento"
    if any(entrada.get("hito") == "investigacion" for entrada in historial):
        return "en_investigacion"
    if status == "reconocida" or triaje_en_historial(historial):
        return "en_observacion"
    return "detectada"


def _evaluaciones_del_historial(alerts: list[Alert]) -> set[int]:
    """Ids de evaluación citados en el historial de las alertas dadas."""
    return {
        e["evaluation_id"]
        for a in alerts
        for e in (a.history_json or [])
        if e.get("evaluation_id") is not None
    }


def _historial_para_api(
    history: list[dict[str, Any]] | None,
    eval_info: dict[int, tuple[int | None, int | None, str | None]],
) -> list[dict[str, Any]] | None:
    """Completa cada entrada con `batch_id`, `batch_seq` y
    `evaluacion_borrada`. Si la evaluación citada vive, el lote sale de ella;
    si ya no existe, la entrada es «evaluación borrada» y conserva el lote que
    guardó al borrarse (o al escribirse). Las entradas sin evaluación (p. ej. la
    retirada) llevan solo lo guardado."""
    if history is None:
        return None
    salida: list[dict[str, Any]] = []
    for e in history:
        nueva = dict(e)
        evaluation_id = e.get("evaluation_id")
        if evaluation_id is not None and evaluation_id in eval_info:
            batch_id, batch_seq, _ = eval_info[evaluation_id]
            nueva["batch_id"] = batch_id if batch_id is not None else e.get("batch_id")
            nueva["batch_seq"] = batch_seq if batch_seq is not None else e.get("batch_seq")
            nueva["evaluacion_borrada"] = False
        else:
            nueva["batch_id"] = e.get("batch_id")
            nueva["batch_seq"] = e.get("batch_seq")
            nueva["evaluacion_borrada"] = bool(e.get("evaluacion_borrada")) or evaluation_id is not None
        salida.append(nueva)
    return salida


def alert_to_dict(
    session: Session,
    a: Alert,
    *,
    batch_info: tuple[int | None, int | None, str | None] | None = None,
    origin_info: tuple[int, str | None] | None = None,
    eval_info: dict[int, tuple[int | None, int | None, str | None]] | None = None,
) -> dict[str, Any]:
    """Serializa una alerta. `batch_info` (H1c) es `(batch_id, seq, phase_label)`
    ya resuelto por `alerts_to_dict` para una página entera; si no se pasa (una
    sola alerta), se resuelve aquí con dos consultas. `origin_info` es
    `(seq, phase_label)` del lote de origen, con la misma regla. `eval_info` es `_lote_de_evaluaciones` de las evaluaciones citadas en el
    historial; si no se pasa, se resuelve aquí."""
    if eval_info is None:
        eval_info = _lote_de_evaluaciones(session, _evaluaciones_del_historial([a]))
    if batch_info is None:
        if a.last_evaluation_id is None:
            batch_info = (None, None, None)
        else:
            batch_info = _lote_de_evaluaciones(session, {a.last_evaluation_id}).get(
                a.last_evaluation_id, (None, None, None)
            )
    batch_id, batch_seq, batch_phase_label = batch_info
    if origin_info is None and a.origin_batch_id is not None:
        origin_info = _lotes_por_id(session, {a.origin_batch_id}).get(a.origin_batch_id)
    origin_seq, origin_phase_label = origin_info if origin_info is not None else (None, None)
    return {
        "id": a.id,
        "project_id": a.project_id,
        "monitor_type": a.monitor_type,
        "metric_key": a.metric_key,
        "group_code": a.group_code,
        "severity": a.severity,
        "status": a.status,
        "stage": alert_stage(a.status, a.history_json),
        "title": _titulo_actual(session, a),
        "opened_at": a.opened_at,
        "updated_at": a.updated_at,
        "closed_at": a.closed_at,
        "last_evaluation_id": a.last_evaluation_id,
        "last_value": a.last_value,
        "observation_count": a.observation_count,
        "reopen_count": a.reopen_count,
        "protocolo_md": a.protocolo_md,
        "history": _historial_para_api(a.history_json, eval_info),
        "batch_id": batch_id,
        "batch_seq": batch_seq,
        "batch_phase_label": batch_phase_label,
        "origin_batch_id": a.origin_batch_id,
        "origin_batch_seq": origin_seq,
        "origin_phase_label": origin_phase_label,
        "retired_reason": a.retired_reason,
    }


def alerts_to_dict(session: Session, alerts: list[Alert]) -> list[dict[str, Any]]:
    """Serializa varias alertas con el lote resuelto en dos consultas (H1c):
    evita el N+1 de `GET /projects/{id}/alerts`."""
    evaluation_ids = {a.last_evaluation_id for a in alerts if a.last_evaluation_id is not None}
    lote_por_evaluacion = _lote_de_evaluaciones(session, evaluation_ids)
    lotes_origen = _lotes_por_id(session, {a.origin_batch_id for a in alerts if a.origin_batch_id is not None})
    eval_info = _lote_de_evaluaciones(session, _evaluaciones_del_historial(alerts))
    return [
        alert_to_dict(
            session,
            a,
            batch_info=lote_por_evaluacion.get(a.last_evaluation_id, (None, None, None))
            if a.last_evaluation_id is not None
            else (None, None, None),
            origin_info=lotes_origen.get(a.origin_batch_id) if a.origin_batch_id is not None else None,
            eval_info=eval_info,
        )
        for a in alerts
    ]


def retire_alerts_for_batch(
    session: Session,
    *,
    project_id: int,
    batch_id: int,
    batch_seq: int,
    evaluation_ids: set[int],
    actor_kind: str,
    actor_id: str,
    role: str | None = None,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
) -> list[int]:
    """Al borrar un lote pasa a `retirada` cada alerta que nació en él
    (`origin_batch_id`), con `closed_at`, `retired_reason`, entrada en el
    historial y evento `alerta.retirada`. Las alertas de otro origen cuya
    `last_evaluation_id` era de una evaluación del lote vuelven a su evaluación
    anterior que siga viva (según su historial) o se quedan sin ella; su estado
    no cambia. Sin commit: lo hace el llamador. Devuelve los ids retirados."""
    motivo = f"lote {batch_seq} borrado"
    ahora = now_iso()
    retiradas: list[int] = []
    alertas = session.exec(select(Alert).where(Alert.project_id == project_id)).all()
    for a in alertas:
        # Las entradas del historial que citan una evaluación del lote
        # borrado se marcan (`evaluacion_borrada`, `batch_id`, `batch_seq`) para
        # que la interfaz las pinte «evaluación borrada con el lote N».
        if any(e.get("evaluation_id") in evaluation_ids for e in (a.history_json or [])):
            a.history_json = [
                {**e, "evaluacion_borrada": True, "batch_id": batch_id, "batch_seq": batch_seq}
                if e.get("evaluation_id") in evaluation_ids
                else e
                for e in (a.history_json or [])
            ]
            session.add(a)
        if a.origin_batch_id == batch_id and a.status != "retirada":
            estado_previo = a.status
            historial = list(a.history_json or [])
            historial.append(
                {
                    "ts": ahora,
                    "from": estado_previo,
                    "to": "retirada",
                    "evaluation_id": None,
                    "batch_id": batch_id,
                    "value": a.last_value,
                    "actor": actor_id,
                    "actor_kind": actor_kind,
                    "motivo": motivo,
                    "hito": None,
                    "detalle": None,
                }
            )
            a.status = "retirada"
            a.retired_reason = motivo
            cierre_previo = a.closed_at
            a.closed_at = cierre_previo or ahora
            a.updated_at = ahora
            a.history_json = historial
            session.add(a)
            session.flush()
            record_event(
                session,
                actor_kind=actor_kind,
                actor_id=actor_id,
                role=role,
                action="alerta.retirada",
                object_type="alert",
                object_id=a.id,
                project_id=project_id,
                motivo=motivo,
                before={"status": estado_previo, "closed_at": cierre_previo},
                after={"status": "retirada", "retired_reason": motivo, "batch_id": batch_id},
                correlation_id=correlation_id,
                bus=bus,
            )
            retiradas.append(a.id)
        elif a.last_evaluation_id in evaluation_ids:
            vivas = [
                e
                for e in (a.history_json or [])
                if e.get("evaluation_id") is not None and e["evaluation_id"] not in evaluation_ids
            ]
            anterior = None
            for entrada in reversed(vivas):
                if session.get(Evaluation, entrada["evaluation_id"]) is not None:
                    anterior = entrada
                    break
            a.last_evaluation_id = anterior["evaluation_id"] if anterior is not None else None
            if anterior is None:
                a.last_value = None
            elif anterior.get("value") is not None:
                a.last_value = anterior["value"]
            if anterior is not None:
                # El título dice el valor y el umbral de la evaluación que
                # queda; se leen de la medida de esa evaluación. Sin medida (las
                # alertas cruzadas traen título propio y no tienen fila) se deja.
                medida = session.exec(
                    select(MeasurementRow).where(
                        MeasurementRow.evaluation_id == anterior["evaluation_id"],
                        MeasurementRow.metric_key == a.metric_key,
                        MeasurementRow.group_code == a.group_code,
                    )
                ).first()
                project = session.get(Project, a.project_id)
                if medida is not None and project is not None:
                    evaluacion_viva = session.get(Evaluation, anterior["evaluation_id"])
                    a.title = _titulo(
                        session,
                        project,
                        a.monitor_type,
                        metric_key=a.metric_key,
                        group_code=a.group_code,
                        value=medida.value,
                        threshold_low=medida.threshold_low,
                        threshold_high=medida.threshold_high,
                        detalle=_detalle_deriva(
                            a.metric_key, evaluacion_viva.result_json if evaluacion_viva else None
                        ),
                    )
            session.add(a)
    session.flush()
    return retiradas


def _exigir_no_retirada(alert: Alert) -> None:
    """Una alerta retirada (su lote se borró) no admite ninguna acción."""
    if alert.status == "retirada":
        raise HTTPException(
            409, f"la alerta está retirada ({alert.retired_reason or 'su lote se borró'}): no admite acciones"
        )


def _exigir_no_cerrada(alert: Alert) -> None:
    """Una alerta cerrada no admite acciones ni cambios de protocolo."""
    if alert.status == "cerrada":
        raise HTTPException(409, "la alerta ya está cerrada")


def _reclamar_hito(session: Session, alert: Alert) -> str:
    """Escritura condicional de un hito del flujo (triaje, investigación,
    decisión). Cambia `updated_at` solo si sigue siendo el que esta petición
    leyó; si otra petición concurrente ya escribió, la fila no coincide y se
    responde 409 en vez de duplicar el hito. Devuelve la marca nueva."""
    ahora = now_iso()
    anterior = alert.updated_at
    if anterior and ahora <= anterior:
        ahora = (datetime.fromisoformat(anterior) + timedelta(microseconds=1)).isoformat(
            timespec="microseconds"
        )
    tabla = Alert.__table__  # type: ignore[attr-defined]
    resultado = session.connection().execute(
        update(tabla).where(tabla.c.id == alert.id, tabla.c.updated_at == anterior).values(updated_at=ahora)
    )
    if resultado.rowcount != 1:
        raise HTTPException(
            409, "la alerta ha cambiado mientras se registraba este paso: recárgala y vuelve a intentarlo"
        )
    alert.updated_at = ahora
    return ahora


def acknowledge(
    session: Session,
    alert: Alert,
    *,
    actor: str,
    actor_kind: str = "humano",
    role: str | None = None,
    motivo: str,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
    commit: bool = True,
) -> Alert:
    # El triaje es el hito 2 y se hace una sola vez; se admite desde
    # `abierta` (pasa a `reconocida`) y desde `en_observacion` (el motor ya
    # vio volver la métrica dentro del umbral antes de que nadie la mirase:
    # el `status` del motor se conserva y el hito queda en el historial).
    _exigir_no_retirada(alert)
    if alert.status == "cerrada":
        raise HTTPException(409, "la alerta ya está cerrada")
    if alert.status == "reconocida" or triaje_en_historial(alert.history_json):
        raise HTTPException(409, "el triaje ya está hecho")
    ahora = _reclamar_hito(session, alert)
    historial = list(alert.history_json or [])
    estado_final = "reconocida" if alert.status == "abierta" else alert.status
    historial.append(
        {
            "ts": ahora,
            "from": alert.status,
            "to": estado_final,
            "evaluation_id": alert.last_evaluation_id,
            "value": alert.last_value,
            "actor": actor,
            "actor_kind": actor_kind,
            "motivo": motivo,
            "hito": "triaje",
            "detalle": None,
        }
    )
    alert.status = estado_final
    alert.updated_at = ahora
    alert.history_json = historial
    session.add(alert)
    session.flush()
    record_event(
        session,
        actor_kind=actor_kind,
        actor_id=actor,
        role=role,
        action="alerta.reconocida",
        object_type="alert",
        object_id=alert.id,
        project_id=alert.project_id,
        motivo=motivo,
        correlation_id=correlation_id,
        bus=bus,
    )
    if commit:
        session.commit()
    session.refresh(alert)
    return alert


def investigate(
    session: Session,
    alert: Alert,
    *,
    actor: str,
    actor_kind: str = "humano",
    role: str | None = None,
    motivo: str,
    hallazgos: str,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
    commit: bool = True,
) -> Alert:
    """Registra la investigación de una alerta (hito 3): exige el
    triaje hecho (`triaje_en_historial`, sea cual sea el `status` del motor)
    y que no se haya registrado antes; `status` no cambia.
    """
    _exigir_no_retirada(alert)
    if alert.status == "cerrada":
        raise HTTPException(409, "la alerta ya está cerrada")
    historial = list(alert.history_json or [])
    if not triaje_en_historial(historial):
        raise HTTPException(409, "primero hay que hacer el triaje de la alerta")
    if any(entrada.get("hito") == "investigacion" for entrada in historial):
        raise HTTPException(409, "la investigación ya está registrada")
    ahora = _reclamar_hito(session, alert)
    historial.append(
        {
            "ts": ahora,
            "from": alert.status,
            "to": alert.status,
            "evaluation_id": alert.last_evaluation_id,
            "value": alert.last_value,
            "actor": actor,
            "actor_kind": actor_kind,
            "motivo": motivo,
            "hito": "investigacion",
            "detalle": hallazgos,
        }
    )
    alert.updated_at = ahora
    alert.history_json = historial
    session.add(alert)
    session.flush()
    record_event(
        session,
        actor_kind=actor_kind,
        actor_id=actor,
        role=role,
        action="alerta.investigada",
        object_type="alert",
        object_id=alert.id,
        project_id=alert.project_id,
        motivo=motivo,
        after={"hallazgos": hallazgos},
        correlation_id=correlation_id,
        bus=bus,
    )
    if commit:
        session.commit()
    session.refresh(alert)
    return alert


def act(
    session: Session,
    alert: Alert,
    *,
    action: str,
    actor: str,
    actor_kind: str = "humano",
    role: str | None = None,
    motivo: str,
    attachment_path: str | None = None,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
    commit: bool = True,
) -> Alert:
    if action not in ACCIONES_ALERTA:
        raise HTTPException(422, f"acción no reconocida: {action!r}; válidas: {', '.join(ACCIONES_ALERTA)}")
    _exigir_no_retirada(alert)
    _exigir_no_cerrada(alert)
    fila = AlertAction(
        alert_id=alert.id,
        action=action,
        actor=actor,
        role=role,
        motivo=motivo,
        attachment_path=attachment_path,
    )
    session.add(fila)
    session.flush()
    record_event(
        session,
        actor_kind=actor_kind,
        actor_id=actor,
        role=role,
        action="alerta.accion",
        object_type="alert",
        object_id=alert.id,
        project_id=alert.project_id,
        motivo=motivo,
        after={"action": action, "attachment_path": attachment_path},
        correlation_id=correlation_id,
        bus=bus,
    )
    if commit:
        session.commit()
    session.refresh(alert)
    return alert


def decide(
    session: Session,
    alert: Alert,
    *,
    actor: str,
    actor_kind: str = "humano",
    role: str | None = None,
    motivo: str,
    acciones: list[dict[str, Any]],
    correlation_id: str | None = None,
    bus: EventBus | None = None,
) -> Alert:
    """Registra la decisión de una alerta (hito 4): al menos una acción
    del catálogo de acciones, cada una con su propio `AlertAction` y su evento
    `alerta.accion`, encadenadas al evento `alerta.decidida` por el
    mismo `correlation_id`; exige la investigación ya registrada y `status`
    no cambia. `acciones` es `[{"key": str, "notes": str | None}]`.
    """
    if not acciones:
        raise HTTPException(422, "la decisión exige al menos una acción del catálogo")
    claves = [accion["key"] for accion in acciones]
    desconocidas = [clave for clave in claves if clave not in ETIQUETAS_ACCION]
    if desconocidas:
        raise HTTPException(
            422,
            f"acción no reconocida: {', '.join(desconocidas)}; válidas: {', '.join(ETIQUETAS_ACCION)}",
        )
    _exigir_no_retirada(alert)
    if alert.status == "cerrada":
        raise HTTPException(409, "la alerta ya está cerrada")
    historial = list(alert.history_json or [])
    if not any(entrada.get("hito") == "investigacion" for entrada in historial):
        raise HTTPException(409, "primero hay que registrar la investigación")
    if any(entrada.get("hito") == "decision" for entrada in historial):
        raise HTTPException(409, "la decisión ya está registrada")
    _reclamar_hito(session, alert)

    cid = correlation_id or str(uuid.uuid4())
    for accion in acciones:
        act(
            session,
            alert,
            action=accion["key"],
            actor=actor,
            actor_kind=actor_kind,
            role=role,
            motivo=accion.get("notes") or motivo,
            correlation_id=cid,
            bus=bus,
            commit=False,
        )

    ahora = now_iso()
    historial = list(alert.history_json or [])
    etiquetas = " · ".join(ETIQUETAS_ACCION[clave] for clave in claves)
    historial.append(
        {
            "ts": ahora,
            "from": alert.status,
            "to": alert.status,
            "evaluation_id": alert.last_evaluation_id,
            "value": alert.last_value,
            "actor": actor,
            "actor_kind": actor_kind,
            "motivo": motivo,
            "hito": "decision",
            "detalle": etiquetas,
        }
    )
    alert.updated_at = ahora
    alert.history_json = historial
    session.add(alert)
    session.flush()
    record_event(
        session,
        actor_kind=actor_kind,
        actor_id=actor,
        role=role,
        action="alerta.decidida",
        object_type="alert",
        object_id=alert.id,
        project_id=alert.project_id,
        motivo=motivo,
        after={"acciones": claves},
        correlation_id=cid,
        bus=bus,
    )
    session.commit()
    session.refresh(alert)
    return alert


def close(
    session: Session,
    alert: Alert,
    *,
    actor: str,
    actor_kind: str = "humano",
    role: str | None = None,
    motivo: str,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
    commit: bool = True,
) -> Alert:
    _exigir_no_retirada(alert)
    if alert.status == "cerrada":
        raise HTTPException(409, "la alerta ya está cerrada")
    ahora = now_iso()
    historial = list(alert.history_json or [])
    estado_previo = alert.status
    historial.append(
        {
            "ts": ahora,
            "from": estado_previo,
            "to": "cerrada",
            "evaluation_id": alert.last_evaluation_id,
            "value": alert.last_value,
            "actor": actor,
            "actor_kind": actor_kind,
            "motivo": motivo,
            "hito": None,
            "detalle": None,
        }
    )
    alert.status = "cerrada"
    alert.closed_at = ahora
    alert.updated_at = ahora
    alert.history_json = historial
    session.add(alert)
    session.flush()
    record_event(
        session,
        actor_kind=actor_kind,
        actor_id=actor,
        role=role,
        action="alerta.cerrada",
        object_type="alert",
        object_id=alert.id,
        project_id=alert.project_id,
        motivo=motivo,
        before={"status": estado_previo},
        correlation_id=correlation_id,
        bus=bus,
    )
    if commit:
        session.commit()
    session.refresh(alert)
    return alert


def bulk_action(
    session: Session,
    project: Project,
    *,
    alert_ids: list[int],
    action: str,
    actor: str,
    actor_kind: str = "humano",
    role: str | None = None,
    motivo: str,
    bus: EventBus | None = None,
) -> dict[str, Any]:
    """Acción en lote sobre alertas del proyecto: `acknowledge`,
    `close` o una clave del catálogo de acciones, aplicada una a una con
    `acknowledge`/`close`/`act` en una única transacción (`commit=False` hasta
    el final) y un `correlation_id` común a los eventos humanos resultantes.

    Una alerta que no existe, que es de otro proyecto o que no admite la
    acción (ya cerrada, catálogo desconocido para ella) se salta con motivo,
    sin romper el resto del lote.
    """
    if action not in _ACCIONES_LOTE_FLUJO and action not in ETIQUETAS_ACCION:
        raise HTTPException(
            422,
            f"acción no reconocida: {action!r}; válidas: "
            f"{', '.join(_ACCIONES_LOTE_FLUJO)}, {', '.join(ETIQUETAS_ACCION)}",
        )
    correlation_id = str(uuid.uuid4())
    aplicadas = 0
    saltadas: list[dict[str, Any]] = []
    for alert_id in alert_ids:
        alert = session.get(Alert, alert_id)
        if alert is None:
            saltadas.append({"alert_id": alert_id, "reason": texto_no_encontrado("alerta", alert_id, "alertas")})
            continue
        if alert.project_id != project.id:
            saltadas.append({"alert_id": alert_id, "reason": "la alerta pertenece a otro proyecto"})
            continue
        try:
            if action == "acknowledge":
                acknowledge(
                    session, alert, actor=actor, actor_kind=actor_kind, role=role, motivo=motivo,
                    correlation_id=correlation_id, bus=bus, commit=False,
                )
            elif action == "close":
                close(
                    session, alert, actor=actor, actor_kind=actor_kind, role=role, motivo=motivo,
                    correlation_id=correlation_id, bus=bus, commit=False,
                )
            else:
                act(
                    session, alert, action=action, actor=actor, actor_kind=actor_kind, role=role,
                    motivo=motivo, correlation_id=correlation_id, bus=bus, commit=False,
                )
        except HTTPException as exc:
            saltadas.append({"alert_id": alert_id, "reason": str(exc.detail)})
            continue
        aplicadas += 1
    session.commit()
    return {"applied": aplicadas, "skipped": saltadas}


def set_protocol(
    session: Session,
    alert: Alert,
    *,
    actor: str,
    actor_kind: str = "humano",
    role: str | None = None,
    motivo: str,
    protocolo_md: str,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
) -> Alert:
    _exigir_no_retirada(alert)
    _exigir_no_cerrada(alert)
    before = alert.protocolo_md
    alert.protocolo_md = protocolo_md
    alert.updated_at = now_iso()
    session.add(alert)
    session.flush()
    record_event(
        session,
        actor_kind=actor_kind,
        actor_id=actor,
        role=role,
        action="alerta.protocolo_editado",
        object_type="alert",
        object_id=alert.id,
        project_id=alert.project_id,
        motivo=motivo,
        before={"protocolo_md": before},
        after={"protocolo_md": protocolo_md},
        correlation_id=correlation_id,
        bus=bus,
    )
    session.commit()
    session.refresh(alert)
    return alert
