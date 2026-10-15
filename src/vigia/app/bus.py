"""Bus de eventos en memoria: publicación a todas las suscripciones vivas.

Cada suscriptor tiene su propia `queue.Queue`, así un cliente SSE lento no
bloquea al resto. `publish` nunca lanza: si una cola está llena, descarta el
mensaje para ese suscriptor y lo deja anotado en el log.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import Any, Self

__all__ = ["BusLleno", "EventBus", "Subscription"]

_log = logging.getLogger("vigia.app.bus")

COLA_MAXIMA = 1000

# Tope de suscripciones vivas a la vez: una interfaz local usa unas pocas.
SUSCRIPTORES_MAXIMOS = 64


class BusLleno(RuntimeError):
    """Ya hay el máximo de suscripciones vivas; la ruta responde 503."""


class Subscription:
    """Una suscripción al bus, con su cola propia."""

    def __init__(self, bus: EventBus, maxsize: int = COLA_MAXIMA) -> None:
        self._bus = bus
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=maxsize)
        self._aviso: tuple[asyncio.AbstractEventLoop, asyncio.Event] | None = None

    def put(self, msg: dict[str, Any]) -> None:
        """Encola un mensaje; descarta si la cola está llena (cliente lento)."""
        try:
            self.queue.put_nowait(msg)
        except queue.Full:
            _log.warning("suscripción llena: se descarta un mensaje del bus")
        aviso = self._aviso
        if aviso is not None:
            try:
                aviso[0].call_soon_threadsafe(aviso[1].set)
            except RuntimeError:  # el bucle ya se cerró: nadie espera
                self._aviso = None

    async def get_async(self, timeout: float) -> dict[str, Any] | None:
        """Espera el siguiente mensaje sin ocupar un hilo; `None` si vence `timeout`."""
        if self._aviso is None:
            self._aviso = (asyncio.get_running_loop(), asyncio.Event())
        evento = self._aviso[1]
        while True:
            evento.clear()
            try:
                return self.queue.get_nowait()
            except queue.Empty:
                pass
            try:
                await asyncio.wait_for(evento.wait(), timeout)
            except TimeoutError:
                return None

    def get(self, timeout: float | None = None) -> dict[str, Any] | None:
        """Devuelve el siguiente mensaje o `None` si vence el tiempo de espera."""
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        """Se da de baja del bus."""
        self._bus.unsubscribe(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class EventBus:
    """Pub/sub en memoria, seguro entre hilos."""

    def __init__(self, max_subscribers: int = SUSCRIPTORES_MAXIMOS) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Subscription] = []
        self._max_subscribers = max_subscribers

    def subscribe(self, maxsize: int = COLA_MAXIMA) -> Subscription:
        """Crea una suscripción nueva y la registra; `BusLleno` si ya hay el máximo."""
        sub = Subscription(self, maxsize=maxsize)
        with self._lock:
            if len(self._subscribers) >= self._max_subscribers:
                raise BusLleno("demasiadas conexiones de seguimiento abiertas")
            self._subscribers.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        """Quita una suscripción del bus. Es idempotente."""
        with self._lock:
            if sub in self._subscribers:
                self._subscribers.remove(sub)

    def publish(self, msg: dict[str, Any]) -> None:
        """Entrega el mensaje a todas las suscripciones vivas."""
        with self._lock:
            destinos = list(self._subscribers)
        for sub in destinos:
            sub.put(msg)

    @property
    def lleno(self) -> bool:
        """Verdadero si ya hay el máximo de suscripciones vivas."""
        with self._lock:
            return len(self._subscribers) >= self._max_subscribers

    @property
    def n_subscribers(self) -> int:
        """Número de suscripciones vivas (para diagnóstico y tests)."""
        with self._lock:
            return len(self._subscribers)
