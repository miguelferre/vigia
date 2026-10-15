"""Frontera HTTP de la API local: Host y Origin locales y cabeceras de seguridad.

Vigía escucha solo en 127.0.0.1 y no tiene cuentas. Una página web abierta en el
mismo equipo no debe poder hablar con la API: el `Host` tiene que ser local (DNS
rebinding) y una petición que escribe no puede venir de otro origen (CSRF). Los
clientes que no son un navegador (CLI, MCP) no mandan `Origin` ni
`Sec-Fetch-Site` y pasan. Huellas `vigia.api.no-host-validation-dns-rebinding` y
`vigia.api.csrf-multipart-no-origin-check`.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any
from urllib.parse import urlsplit

HOSTS_LOCALES = frozenset({"127.0.0.1", "localhost"})
METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})

# Cabeceras de toda respuesta. El informe de la revisión se incrusta en un
# iframe de la propia app, así que el marco se permite solo al mismo origen.
CABECERAS_SEGURIDAD: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", b"frame-ancestors 'self'"),
)

TEXTO_HOST = (
    "Vigía solo acepta peticiones dirigidas a 127.0.0.1 o localhost. "
    "Abre Vigía con la dirección que muestra al arrancar."
)
TEXTO_ORIGEN = (
    "Vigía rechaza cambios que llegan desde otra página web. "
    "Usa la propia ventana de Vigía."
)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def nombre_de_host(valor: str) -> str:
    """Nombre del host de una cabecera `Host` u `Origin`, sin puerto y en minúsculas."""
    if "://" in valor:
        return (urlsplit(valor).hostname or "").lower()
    return (urlsplit(f"//{valor}").hostname or "").lower()


def _cabecera(scope: Scope, nombre: bytes) -> str | None:
    for clave, valor in scope.get("headers", []):
        if clave == nombre:
            return valor.decode("latin-1")
    return None


def motivo_de_rechazo(scope: Scope) -> str | None:
    """`None` si la petición pasa la frontera; si no, el texto del 403."""
    host = _cabecera(scope, b"host")
    if host is None or nombre_de_host(host) not in HOSTS_LOCALES:
        return TEXTO_HOST
    if scope.get("method", "GET").upper() in METODOS_SEGUROS:
        return None
    origen = _cabecera(scope, b"origin")
    if origen is not None:
        if nombre_de_host(origen) not in HOSTS_LOCALES:
            return TEXTO_ORIGEN
        return None
    sitio = _cabecera(scope, b"sec-fetch-site")
    if sitio is not None and sitio.lower() not in {"same-origin", "none"}:
        return TEXTO_ORIGEN
    return None


class FronteraLocal:
    """Middleware ASGI puro: no envuelve el cuerpo, así que no rompe los flujos SSE."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        motivo = motivo_de_rechazo(scope)
        if motivo is not None:
            cuerpo = json.dumps({"detail": motivo}, ensure_ascii=False).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"content-length", str(len(cuerpo)).encode("ascii")),
                        *CABECERAS_SEGURIDAD,
                    ],
                }
            )
            await send({"type": "http.response.body", "body": cuerpo})
            return

        async def enviar(mensaje: Message) -> None:
            if mensaje["type"] == "http.response.start":
                presentes = {clave.lower() for clave, _ in mensaje.get("headers", [])}
                extra = [par for par in CABECERAS_SEGURIDAD if par[0] not in presentes]
                mensaje["headers"] = [*mensaje.get("headers", []), *extra]
            await send(mensaje)

        await self.app(scope, receive, enviar)
