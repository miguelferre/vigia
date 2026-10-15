"""Lectura de fechas de ficheros subidos y avisos de fecha.

El motor no usa la fecha de fila: una fecha ilegible en un lote es un
aviso, nunca un rechazo. La fecha del registro de uso sí se normaliza y se
rechaza (`human_layer._normalize_date`), pero comparte el texto de formatos.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

__all__ = ["FORMATOS_FECHA", "aviso_fechas_ilegibles", "leer_fecha"]

FORMATOS_FECHA = "aaaa-mm-dd, dd/mm/aaaa o dd-mm-aaaa"

_RE_DMY = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?$")


def leer_fecha(valor: Any) -> date | None:
    """Fecha de `valor` si se lee en alguno de los formatos admitidos (ISO con o
    sin hora, `dd/mm/aaaa`, `dd-mm-aaaa`); `None` si está en blanco o no se lee."""
    texto = str(valor).strip()
    if not texto or texto.casefold() in ("nan", "nat", "none"):
        return None
    try:
        return datetime.fromisoformat(texto).date()
    except ValueError:
        pass
    hallazgo = _RE_DMY.match(texto)
    if hallazgo is None:
        return None
    dia, mes, anio = (int(x) for x in hallazgo.groups())
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def aviso_fechas_ilegibles(valores: Iterable[Any], columna: str) -> list[str]:
    """Aviso con el número de filas, un ejemplo y los formatos admitidos.

    Cuenta solo los valores con contenido: los vacíos ya los avisa la ingesta
    como nulos. Lista vacía si todas las fechas se leen."""
    ilegibles = 0
    ejemplo = ""
    for valor in valores:
        texto = str(valor).strip()
        if not texto or texto.casefold() in ("nan", "nat", "none"):
            continue
        if leer_fecha(texto) is None:
            ilegibles += 1
            ejemplo = ejemplo or texto
    if not ilegibles:
        return []
    filas = "1 fila tiene" if ilegibles == 1 else f"{ilegibles} filas tienen"
    return [
        (
            f"{filas} una fecha ilegible en la columna «{columna}» (por ejemplo «{ejemplo[:40]}»): "
            f"escríbela como {FORMATOS_FECHA}. Se guardan igual y el motor no usa la fecha de la fila"
        )
    ]
