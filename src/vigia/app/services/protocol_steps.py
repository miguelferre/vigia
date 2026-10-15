"""Hitos del protocolo de una alerta (se derivan de eventos
propios, no del cierre): cinco pasos fijos derivados del historial y de las
evaluaciones posteriores a la apertura, sin fecha objetivo (`target_date`
siempre `None` por ahora); añade a cada paso el título, la descripción,
los entregables, el responsable y el plazo del protocolo de su monitor
(`Monitor.protocol_json`, `services/monitors.protocol_for`).

La derivación vive en funciones puras (`_pasos`, `_estado_seguimiento`),
testables con casos sintéticos sin tocar la base de datos; `protocol_steps_for_alert`
es el único punto que consulta `AlertAction`/`Measurement`/`Monitor` (la usa
`GET /alerts/{id}`, `routers/alerts.py`). Triaje se deriva de `_triaje_hecho`
(reconocer, cerrar directamente o cualquier acción del catálogo);
investigación y decisión, de que el historial traiga una entrada con
`hito == "investigacion"` / `"decision"` (eventos `alerta.investigada` /
`alerta.decidida` de `services/alerting.investigate`/`.decide`), nunca del
cierre.
"""

from __future__ import annotations

from typing import Any, Literal

from sqlmodel import Session, select

from vigia.app.content_loader import protocolo_hitos_plantilla
from vigia.app.models import Alert, AlertAction, Measurement
from vigia.app.services import monitors as monitors_service
from vigia.app.services.monitors_protocol import intercalar_hitos_extra

__all__ = ["protocol_steps_for_alert"]

# `to` del historial que implica que un humano ya trió la alerta: reconocerla
# o cerrarla directamente (sin pasar por reconocer). Las acciones del
# catálogo de acciones (`act`) no tocan `history_json`, solo `alert_action`: por eso
# `_triaje_hecho` también mira esa tabla.
_ESTADOS_TRIAJE_HISTORIAL = ("reconocida", "cerrada")

# "informativo": hito extra del protocolo del monitor,
# sin evento propio que lo marque "hecho"; nunca mueve `alert_stage`.
StepStatus = Literal["done", "current", "pending", "informativo"]


def _estado_seguimiento(decision_hecha: bool, estados_posteriores: list[str]) -> StepStatus:
    """`seguimiento` depende primero de la decisión, hito 4: sin
    decisión no hay nada que seguir, así que es `pending` aunque ya existan
    medidas posteriores en `ok`. Con la decisión hecha, se deriva de los
    estados (`Measurement.state`, en orden cronológico) de las medidas
    posteriores a la apertura sobre la misma métrica y grupo de la alerta:
    `current` sin medidas o con las dos últimas sin ser ambas `ok`, `done`
    con las dos últimas en `ok`."""
    if not decision_hecha:
        return "pending"
    ultimas_dos = estados_posteriores[-2:]
    if len(ultimas_dos) == 2 and all(e == "ok" for e in ultimas_dos):
        return "done"
    return "current"


def _pasos(
    *,
    cerrada: bool,
    triaje_hecho: bool,
    investigacion_hecha: bool,
    decision_hecha: bool,
    estado_seguimiento: StepStatus,
) -> list[dict[str, Any]]:
    """Los cinco hitos. Función pura, testable con casos
    sintéticos: detección siempre `done`; triaje `done` con `triaje_hecho`,
    si no `current` (`pending` si `cerrada`, ningún hito queda
    `current` en una alerta cerrada); investigación `done` si
    `investigacion_hecha`, `current` con triaje hecho y sin cerrar, si no
    `pending`; decisión igual pero sobre `decision_hecha`/investigación;
    seguimiento llega ya calculado (`_estado_seguimiento`) y se coloca
    tal cual.
    """
    if triaje_hecho:
        triaje: StepStatus = "done"
    else:
        triaje = "pending" if cerrada else "current"
    if investigacion_hecha:
        investigacion: StepStatus = "done"
    elif triaje_hecho and not cerrada:
        investigacion = "current"
    else:
        investigacion = "pending"
    if decision_hecha:
        decision: StepStatus = "done"
    elif investigacion_hecha and not cerrada:
        decision = "current"
    else:
        decision = "pending"
    return [
        {"key": "deteccion", "status": "done", "target_date": None},
        {"key": "triaje", "status": triaje, "target_date": None},
        {"key": "investigacion", "status": investigacion, "target_date": None},
        {"key": "decision", "status": decision, "target_date": None},
        {"key": "seguimiento", "status": estado_seguimiento, "target_date": None},
    ]


def _triaje_hecho(session: Session, alert: Alert) -> bool:
    """Reconocer (entrada con `hito == "triaje"`, o `to == "reconocida"` en
    alertas antiguas), cerrar directamente (`to == "cerrada"`) o
    cualquier acción del catálogo de acciones (solo en `alert_action`, que `act()`
    no añade al historial). Misma lectura del historial que
    `alerting.triaje_en_historial` y `alerting.alert_stage`."""
    if alert.status == "cerrada":
        return True
    historial = alert.history_json or []
    if any(
        entrada.get("hito") == "triaje" or entrada.get("to") in _ESTADOS_TRIAJE_HISTORIAL
        for entrada in historial
    ):
        return True
    return (
        session.exec(
            select(AlertAction.id).where(AlertAction.alert_id == alert.id).limit(1)  # type: ignore[arg-type]
        ).first()
        is not None
    )


def _investigacion_hecha(alert: Alert) -> bool:
    """La investigación está registrada si el historial trae una entrada con
    `hito == "investigacion"` (evento `alerta.investigada`): no del
    cierre."""
    historial = alert.history_json or []
    return any(entrada.get("hito") == "investigacion" for entrada in historial)


def _decision_hecha(alert: Alert) -> bool:
    """La decisión está registrada si el historial trae una entrada con
    `hito == "decision"` (evento `alerta.decidida`): no del cierre."""
    historial = alert.history_json or []
    return any(entrada.get("hito") == "decision" for entrada in historial)


def _estados_posteriores(session: Session, alert: Alert) -> list[str]:
    """`Measurement.state`, en orden cronológico, de las medidas de la misma
    métrica y grupo que la alerta, creadas después de que se abriera."""
    medidas = session.exec(
        select(Measurement)
        .where(
            Measurement.project_id == alert.project_id,
            Measurement.monitor_type == alert.monitor_type,
            Measurement.metric_key == alert.metric_key,
            Measurement.group_code == alert.group_code,
            Measurement.created_at > alert.opened_at,
        )
        .order_by(Measurement.created_at)  # type: ignore[arg-type]
    ).all()
    return [m.state for m in medidas]


def _con_textos_del_protocolo(
    session: Session, alert: Alert, pasos: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Añade a cada paso `titulo`, `descripcion`, `entregables`, `responsable`
    y `plazo_dias`: del protocolo del monitor
    (`monitors_service.protocol_for`), emparejados por `key`; si esa clave no
    está en el protocolo del monitor, cae a la plantilla de
    `content_loader.protocolo_hitos_plantilla()`."""
    protocolo = {h["key"]: h for h in monitors_service.protocol_for(session, alert.project_id, alert.monitor_type)}
    plantilla = {h["key"]: h for h in protocolo_hitos_plantilla()}
    resultado = []
    for paso in pasos:
        hito = protocolo.get(paso["key"]) or plantilla.get(paso["key"], {})
        resultado.append(
            {
                **paso,
                "titulo": hito.get("titulo", ""),
                "descripcion": hito.get("descripcion", ""),
                "entregables": list(hito.get("entregables") or []),
                "responsable": hito.get("responsable"),
                "plazo_dias": hito.get("plazo_dias"),
            }
        )
    return resultado


def protocol_steps_for_alert(session: Session, alert: Alert) -> list[dict[str, Any]]:
    """Los hitos de `alert` para `AlertDetail.protocol_steps`:
    triaje/investigación/decisión por sus propios eventos, nunca del cierre.
    Añade los textos del protocolo del monitor y, para los hitos extra, una entrada `status: "informativo"` por hito extra de
    `Monitor.protocol_json`, intercalada en su posición: sin evento propio,
    fuera de `alert_stage`, que sigue mirando solo las tres claves fijas.
    """
    cerrada = alert.status in ("cerrada", "retirada")
    decision_hecha = _decision_hecha(alert)
    pasos = _pasos(
        cerrada=cerrada,
        triaje_hecho=_triaje_hecho(session, alert),
        investigacion_hecha=_investigacion_hecha(alert),
        decision_hecha=decision_hecha,
        estado_seguimiento=_estado_seguimiento(decision_hecha, _estados_posteriores(session, alert)),
    )
    protocolo = monitors_service.protocol_for(session, alert.project_id, alert.monitor_type)
    pasos_con_extra = intercalar_hitos_extra(pasos, protocolo)
    return _con_textos_del_protocolo(session, alert, pasos_con_extra)
