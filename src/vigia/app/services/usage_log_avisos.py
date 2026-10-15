"""Avisos de la subida del registro de uso.

Un aviso no rechaza nada: la subida se guarda igual. Vive aparte de
`human_layer.py` para no engordar ese fichero.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from sqlmodel import Session, col, select

from vigia.app.models import Batch, Dataset, ModelVersion, Record
from vigia.app.services.fechas import leer_fecha

__all__ = ["aviso_fechas_sin_lote", "fecha_ultimo_lote"]

_MAX_FECHAS_POR_LOTE = 50_000
_DIAS_SEMANA = 7


def fecha_ultimo_lote(session: Session, version: ModelVersion) -> tuple[date, str] | None:
    """Fecha del último lote de producción de `version` y de dónde sale.

    La fecha de un lote es la mayor de su columna de fecha (`timestamp_col`);
    sin ella, o si ninguna se lee, la de su ingesta. `None` si la versión no
    tiene lotes de producción (la línea base no cuenta).
    """
    filas = session.exec(
        select(Batch, Dataset.role)
        .join(Dataset, Dataset.id == Batch.dataset_id, isouter=True)  # type: ignore[arg-type]
        .where(Batch.model_version_id == version.id)
    ).all()
    ultima: tuple[date, str] | None = None
    for lote, rol in filas:
        if rol == "baseline":
            continue
        sellos = session.exec(
            select(Record.timestamp)
            .where(Record.batch_id == lote.id, col(Record.timestamp).is_not(None))
            .distinct()
            .limit(_MAX_FECHAS_POR_LOTE)
        ).all()
        fechas = [d for d in (leer_fecha(s) for s in sellos) if d is not None]
        if fechas and len(set(fechas)) == 1:
            # Un lote semanal lleva una sola fecha, la de su primer
            # día; el registro de uso trae los siete días. Se toma la semana
            # entera, no solo ese día.
            unica = fechas[0]
            candidata = (
                unica + timedelta(days=_DIAS_SEMANA - 1),
                f"la columna de fecha del lote, que lleva una sola fecha ({unica.isoformat()}): se toma la semana entera",
            )
        elif fechas:
            candidata = (max(fechas), "la columna de fecha del lote")
        else:
            ingesta = leer_fecha(lote.created_at)
            if ingesta is None:
                continue
            candidata = (ingesta, "la fecha de ingesta del lote")
        if ultima is None or candidata[0] > ultima[0]:
            ultima = candidata
    return ultima


def aviso_fechas_sin_lote(
    session: Session, version: ModelVersion, fechas_iso: Iterable[str]
) -> list[str]:
    """Aviso si el registro trae filas posteriores al último lote de producción."""
    ultimo = fecha_ultimo_lote(session, version)
    if ultimo is None:
        return []
    limite, origen = ultimo
    n = sum(1 for f in fechas_iso if (d := leer_fecha(f)) is not None and d > limite)
    if not n:
        return []
    cabeza = "1 fila es de una fecha sin lote del modelo" if n == 1 else f"{n} filas son de fechas sin lote del modelo"
    return [
        (
            f"{cabeza}: las reglas cruzadas las usan igual; sube antes los lotes de esas semanas "
            f"(el último lote es del {limite.isoformat()}, según {origen})"
        )
    ]
