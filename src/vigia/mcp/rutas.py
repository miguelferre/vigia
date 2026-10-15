"""Control de las rutas que reciben las tools de subida del MCP.

Una ruta de red (UNC) o de dispositivo no se abre, y un fichero de más de
200 MB no se lee entero en memoria.
"""

from __future__ import annotations

import os

__all__ = ["MAX_BYTES_FICHERO", "comprobar_ruta_de_subida"]

MAX_BYTES_FICHERO = 200 * 1024 * 1024


def comprobar_ruta_de_subida(ruta: str, *, max_bytes: int = MAX_BYTES_FICHERO) -> None:
    """Lanza `ValueError` si la ruta es de red o de dispositivo, o si el fichero
    supera `max_bytes`. Se llama antes de abrir el fichero."""
    normal = ruta.replace("/", "\\")
    if normal.startswith("\\\\"):
        raise ValueError(
            "la ruta es de red o de dispositivo (empieza por \\\\): copia el fichero a una carpeta "
            "local y pasa esa ruta"
        )
    try:
        tamano = os.stat(ruta).st_size
    except OSError:
        return  # la tool informa del fallo al abrir, con el motivo del sistema
    if tamano > max_bytes:
        raise ValueError(
            f"el fichero pesa {tamano // (1024 * 1024)} MB y el límite es {max_bytes // (1024 * 1024)} MB"
        )
