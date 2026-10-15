"""Utilidades de tiempo y agregados vacíos de `alert_series`.

Sin dependencia de `Session`: solo fechas y diccionarios, para que
`alert_series.py` y `alert_series_tramos.py` compartan la misma lógica sin
importarse entre sí.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

__all__ = [
    "en_rango",
    "marca_a_zona",
    "monitor_vacio",
    "parse_limite",
    "severidad_vacia",
    "tramo_de",
    "zona_horaria",
]


def zona_horaria(tz: str) -> ZoneInfo:
    """`ZoneInfo(tz)`; 422 si `tz` no se reconoce."""
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(422, f"zona horaria desconocida: {tz!r}") from exc


def parse_limite(valor: str, *, campo: str, zona: ZoneInfo, fin_de_dia: bool) -> datetime:
    """`valor` en ISO 8601; sin hora (`aaaa-mm-dd`) es el inicio o el fin del día en `zona`."""
    crudo = valor.strip()
    try:
        if len(crudo) == 10:
            fecha = date.fromisoformat(crudo)
            hora = time(23, 59, 59, 999999) if fin_de_dia else time.min
            return datetime.combine(fecha, hora, tzinfo=zona)
        dt = datetime.fromisoformat(crudo)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=zona)
    except ValueError as exc:
        raise HTTPException(422, f"{campo} no es una fecha ISO 8601 válida: {valor!r}") from exc


def marca_a_zona(valor: str, zona: ZoneInfo) -> datetime:
    """`created_at`/`opened_at` (UTC, `models.now_iso`) como `datetime` en `zona`."""
    return datetime.fromisoformat(valor).astimezone(zona)


def en_rango(marca: datetime, desde: datetime | None, hasta: datetime | None) -> bool:
    if desde is not None and marca < desde:
        return False
    return not (hasta is not None and marca > hasta)


def tramo_de(marca: datetime, granularity: str) -> tuple[str, datetime, datetime, str]:
    """Clave, inicio, fin (exclusivo) y etiqueta del tramo día/hora de `marca`."""
    if granularity == "day":
        inicio = marca.replace(hour=0, minute=0, second=0, microsecond=0)
        return inicio.strftime("%Y-%m-%d"), inicio, inicio + timedelta(days=1), inicio.strftime("%d/%m")
    inicio = marca.replace(minute=0, second=0, microsecond=0)
    return (
        inicio.strftime("%Y-%m-%dT%H"),
        inicio,
        inicio + timedelta(hours=1),
        inicio.strftime("%d/%m %H:00"),
    )


def severidad_vacia() -> dict[str, int]:
    return {"alta": 0, "media": 0, "baja": 0}


def monitor_vacio() -> dict[str, int]:
    return {"fairness": 0, "quality": 0, "drift": 0, "cross": 0}
