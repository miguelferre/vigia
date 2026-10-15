"""Reevaluación de los lotes que reciben etiquetas tardías.

Un fichero de etiquetas no crea lote: añade la verdad a lotes ya ingeridos. La
calidad de esos lotes se calculó sin ella, así que hay que evaluarlos de nuevo.
`completar_salida` rellena la respuesta de la ingesta con los tres campos de la
forma fijada: `lotes_con_verdad`, y según `evaluate`, `lotes_reevaluados` o
`lotes_a_reevaluar` con su `evaluate_motivo`.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from vigia.app.bus import EventBus
from vigia.app.errores import texto_error_trabajo
from vigia.app.models import Batch

TRIGGER_TARDIO = "feedback_tardio"


def _lista_de_lotes(lotes: list[int]) -> str:
    return ", ".join(f"#{i}" for i in lotes)


def motivo_sin_reevaluar(lotes: list[int]) -> str:
    """Texto para `evaluate_motivo` cuando las etiquetas llegaron y no se reevalúa."""
    n = len(lotes)
    sufijo = "a 1 lote" if n == 1 else f"a {n} lotes"
    return (
        f"Las etiquetas llegaron {sufijo} ({_lista_de_lotes(lotes)}). "
        "Evalúa esos lotes para que la calidad use su verdad."
    )


def completar_salida(
    salida: dict[str, Any],
    session: Session,
    lotes: list[int],
    *,
    evaluate: bool,
    job: Any,
    bus: EventBus | None,
) -> dict[str, Any]:
    """Añade a `salida` el resultado de las etiquetas tardías y, con `evaluate`, reevalúa."""
    salida["lotes_con_verdad"] = list(lotes)
    salida["lotes_reevaluados"] = []
    salida["lotes_a_reevaluar"] = []
    if not lotes:
        return salida
    if not evaluate:
        salida["lotes_a_reevaluar"] = list(lotes)
        salida["evaluate_motivo"] = motivo_sin_reevaluar(lotes)
        return salida
    try:
        from vigia.app.services.evaluate import evaluate_batch
    except ImportError:
        salida["lotes_a_reevaluar"] = list(lotes)
        salida["evaluate_motivo"] = "el servicio de evaluación no está disponible"
        return salida
    fallos: list[int] = []
    motivos: list[str] = []
    for lote_id in lotes:
        batch = session.get(Batch, lote_id)
        if batch is None:
            fallos.append(lote_id)
            motivos.append(f"el lote #{lote_id} ha desaparecido antes de evaluarlo")
            continue
        try:
            evaluate_batch(
                session,
                batch,
                trigger=TRIGGER_TARDIO,
                job=job,
                correlation_id=job.correlation_id,
                bus=bus,
            )
            salida["lotes_reevaluados"].append(lote_id)
        except Exception as exc:  # noqa: BLE001  # un lote que falla no para los demás
            session.rollback()
            fallos.append(lote_id)
            motivos.append(f"lote #{lote_id}: {texto_error_trabajo(exc, 'evaluacion')}")
    salida["evaluated"] = bool(salida["lotes_reevaluados"])
    if fallos:
        salida["lotes_a_reevaluar"] = fallos
        salida["evaluate_motivo"] = " ".join(motivos)
    return salida
