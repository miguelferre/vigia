"""Construcción de los ítems de `alert_series` por lote o por tramo.

Separado de `alert_series.py` para que ningún fichero pase de 9 KB; ambos
comparten `alert_series_util.py`.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from vigia.app.models import Batch
from vigia.app.services.alert_series_util import (
    marca_a_zona,
    monitor_vacio,
    severidad_vacia,
    tramo_de,
)

__all__ = ["items_por_lote", "items_por_tramo"]


def _ref_lote(lote: Batch, nombres: dict[int, str]) -> dict:
    return {
        "id": lote.id,
        "seq": lote.seq,
        "phase_label": lote.phase_label,
        "name": nombres.get(lote.id),
    }


def items_por_lote(
    batch_ids: list[int],
    lotes: dict[int, Batch],
    marca_por_batch: dict[int, str],
    zona: ZoneInfo,
    por_batch: dict[int, list[tuple[int, str, str]]],
    n_checks_por_batch: dict[int, int],
    nombres: dict[int, str] | None = None,
) -> list[dict]:
    """Un ítem por lote evaluado, ordenado por `seq` (`granularity=batch`).
    `nombres` (`batch_id -> nombre del dataset`) rellena `batches[].name`."""
    nombres = nombres or {}
    items = []
    for batch_id in sorted(batch_ids, key=lambda bid: lotes[bid].seq):
        lote = lotes[batch_id]
        marca = marca_a_zona(marca_por_batch[batch_id], zona)
        by_monitor = monitor_vacio()
        by_severity = severidad_vacia()
        alert_ids: set[int] = set()
        for alert_id, monitor_type, severidad in por_batch.get(batch_id, []):
            alert_ids.add(alert_id)
            if monitor_type in by_monitor:
                by_monitor[monitor_type] += 1
            if severidad in by_severity:
                by_severity[severidad] += 1
        marca_iso = marca.isoformat()
        items.append(
            {
                "key": str(batch_id),
                "start": marca_iso,
                "end": marca_iso,
                "label": f"#{lote.seq}",
                "batches": [_ref_lote(lote, nombres)],
                "n_batches": 1,
                "n_checks": n_checks_por_batch.get(batch_id, 0),
                "by_monitor": by_monitor,
                "by_severity": by_severity,
                "total": sum(by_severity.values()),
                "alert_ids": sorted(alert_ids),
            }
        )
    return items


def items_por_tramo(
    granularity: str,
    batch_ids: list[int],
    lotes: dict[int, Batch],
    marca_por_batch: dict[int, str],
    zona: ZoneInfo,
    por_batch: dict[int, list[tuple[int, str, str]]],
    n_checks_por_batch: dict[int, int],
    cross_en_rango: list[tuple[datetime, int, str]],
    nombres: dict[int, str] | None = None,
) -> list[dict]:
    """Un ítem por tramo (día u hora) con al menos un lote o una alerta cruzada."""
    nombres = nombres or {}
    tramos: dict[str, dict] = {}

    def _tramo_de_marca(marca: datetime) -> dict:
        key, inicio, fin, label = tramo_de(marca, granularity)
        if key not in tramos:
            tramos[key] = {
                "key": key,
                "start": inicio,
                "end": fin,
                "label": label,
                "batches": [],
                "n_checks": 0,
                "by_monitor": monitor_vacio(),
                "by_severity": severidad_vacia(),
                "alert_ids": set(),
            }
        return tramos[key]

    for batch_id in batch_ids:
        lote = lotes[batch_id]
        tramo = _tramo_de_marca(marca_a_zona(marca_por_batch[batch_id], zona))
        tramo["batches"].append(_ref_lote(lote, nombres))
        tramo["n_checks"] += n_checks_por_batch.get(batch_id, 0)
        for alert_id, monitor_type, severidad in por_batch.get(batch_id, []):
            tramo["alert_ids"].add(alert_id)
            if monitor_type in tramo["by_monitor"]:
                tramo["by_monitor"][monitor_type] += 1
            if severidad in tramo["by_severity"]:
                tramo["by_severity"][severidad] += 1

    for marca, alert_id, severidad in cross_en_rango:
        tramo = _tramo_de_marca(marca)
        tramo["alert_ids"].add(alert_id)
        tramo["by_monitor"]["cross"] += 1
        if severidad in tramo["by_severity"]:
            tramo["by_severity"][severidad] += 1

    items = []
    for tramo in sorted(tramos.values(), key=lambda t: t["start"]):
        items.append(
            {
                "key": tramo["key"],
                "start": tramo["start"].isoformat(),
                "end": tramo["end"].isoformat(),
                "label": tramo["label"],
                "batches": sorted(tramo["batches"], key=lambda b: b["seq"]),
                "n_batches": len(tramo["batches"]),
                "n_checks": tramo["n_checks"],
                "by_monitor": tramo["by_monitor"],
                "by_severity": tramo["by_severity"],
                "total": sum(tramo["by_severity"].values()),
                "alert_ids": sorted(tramo["alert_ids"]),
            }
        )
    return items
