"""Generador asíncrono para los flujos SSE.

La espera del mensaje es asíncrona (`Subscription.get_async`): un flujo abierto
no ocupa ningún hilo del pool, así que decenas de flujos no frenan el resto de
la API. Si vence el tiempo sin mensajes se emite un `heartbeat` (mantiene viva
la conexión y detecta clientes caídos).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import HTTPException, Request

from vigia.app.bus import BusLleno, Subscription

__all__ = ["comprobar_cupo", "sse_stream", "suscribir"]


def comprobar_cupo(request: Request) -> None:
    """503 en español si el bus ya tiene el máximo de suscripciones (antes de abrir el flujo)."""
    if request.app.state.bus.lleno:
        raise HTTPException(
            503, "hay demasiadas conexiones de seguimiento abiertas: cierra alguna pestaña de Vigía y reintenta"
        )


def suscribir(request: Request) -> Subscription | None:
    """Suscripción nueva; se pide dentro del generador, para que `finally` la libere siempre.

    Devuelve `None` si el bus se llenó entre la comprobación y la suscripción."""
    try:
        return request.app.state.bus.subscribe()
    except BusLleno:
        return None


async def sse_stream(
    request: Request,
    subscription: Subscription,
    *,
    heartbeat_s: float = 15.0,
    filtro: Callable[[dict[str, Any]], bool] | None = None,
    until: Callable[[dict[str, Any]], bool] | None = None,
) -> AsyncIterator[dict[str, str]]:
    """Emite los mensajes del bus como eventos SSE hasta que el cliente se va.

    - `filtro`: si devuelve falso, el mensaje no se emite.
    - `until`: si devuelve verdadero, se emite el mensaje y se cierra el flujo.
    """
    try:
        while True:
            if await request.is_disconnected():
                return
            msg = await subscription.get_async(heartbeat_s)
            if msg is None:
                yield {"event": "heartbeat", "data": ""}
                continue
            if filtro is not None and not filtro(msg):
                continue
            yield {
                "event": str(msg.get("type", "message")),
                "data": json.dumps(msg, ensure_ascii=False, default=str),
            }
            if until is not None and until(msg):
                return
    finally:
        subscription.close()
