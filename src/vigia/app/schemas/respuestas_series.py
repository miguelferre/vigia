"""Respuestas de la serie de alertas por lote/día/hora.

Serializador de origen: `services/alert_series.py` (`alert_series`).
"""

from __future__ import annotations

from vigia.app.schemas.respuestas_base import Respuesta, SeriesGranularity
from vigia.app.schemas.respuestas_proyectos import AlertasAbiertasPorSeveridad

__all__ = [
    "AlertSeriesBatchRef",
    "AlertSeriesByMonitor",
    "AlertSeriesItem",
    "AlertSeriesResponse",
]


class AlertSeriesBatchRef(Respuesta):
    """Lote incluido en un tramo de la serie."""

    id: int
    seq: int
    phase_label: str | None
    # Nombre del lote (el del dataset de origen); nulo si no lo tiene.
    name: str | None = None


class AlertSeriesByMonitor(Respuesta):
    """Recuento de alertas por monitor en un tramo. Sin `explain`: el panel
    «Alertas por lote» no lo dibuja."""

    fairness: int
    quality: int
    drift: int
    cross: int


class AlertSeriesItem(Respuesta):
    """Un tramo de la serie: un lote (`granularity=batch`) o una ventana de
    tiempo (`day`/`hour`) con al menos un lote evaluado, o solo cruzadas."""

    key: str
    start: str
    end: str
    label: str
    batches: list[AlertSeriesBatchRef]
    n_batches: int
    n_checks: int
    by_monitor: AlertSeriesByMonitor
    by_severity: AlertasAbiertasPorSeveridad
    total: int
    # Ids de las alertas contadas en el tramo (una vez cada una aunque toquen
    # varios lotes): la tabla «Alertas que requieren acción» filtra con ellos
    # al pulsar un tramo, con la misma semántica que la gráfica.
    alert_ids: list[int]


class AlertSeriesResponse(Respuesta):
    """Respuesta de `GET /projects/{id}/alerts/series`."""

    granularity: SeriesGranularity
    since: str | None
    until: str | None
    tz: str
    items: list[AlertSeriesItem]
    total: int
    cross_unbatched: AlertasAbiertasPorSeveridad
