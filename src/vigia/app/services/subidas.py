"""Lectura de ficheros subidos con un tope de bytes (413 con texto en español)."""

from __future__ import annotations

from typing import BinaryIO

from fastapi import HTTPException

__all__ = ["LIMITE_BYTES_SUBIDA", "leer_subida"]

LIMITE_BYTES_SUBIDA = 200 * 1024 * 1024


def leer_subida(fichero: BinaryIO, *, tope: int | None = None) -> bytes:
    """Lee el fichero subido entero; 413 si supera el tope (por defecto 200 MB)."""
    limite = LIMITE_BYTES_SUBIDA if tope is None else tope
    fichero.seek(0, 2)
    tamano = fichero.tell()
    fichero.seek(0)
    if tamano > limite:
        mb = limite // (1024 * 1024)
        raise HTTPException(
            413,
            f"el fichero pesa {tamano // (1024 * 1024)} MB y el máximo es {mb} MB: "
            "divídelo en ficheros más pequeños y súbelos uno a uno",
        )
    return fichero.read()
