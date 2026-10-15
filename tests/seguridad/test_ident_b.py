"""Proxy del entorno e identidad del servidor local.

Huellas:
- src/vigia/mcp/client.py:httpx-trust-env-loopback-via-proxy
  Control esperado: las peticiones a loopback no pasan por el proxy del entorno.
- src/vigia/mcp/client.py:local-server-identity-unverified
  Control esperado: ni el cliente MCP ni `vigia shutdown` envian datos ni el token
  del lock a un par que no demuestra ser el servidor de esa carpeta de datos.
Solo datos ficticios; los servidores de prueba escuchan en el puerto 0 de loopback.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from vigia import cli
from vigia.app.preflight import LockFile
from vigia.mcp.client import VigiaClient

HUELLA_PROXY = "src/vigia/mcp/client.py:httpx-trust-env-loopback-via-proxy"
HUELLA_IDENTIDAD = "src/vigia/mcp/client.py:local-server-identity-unverified"
HUELLAS = {
    "test_bootstrap_mcp_no_usa_proxy_del_entorno": HUELLA_PROXY,
    "test_sondeo_de_salud_no_usa_proxy_del_entorno": HUELLA_PROXY,
    "test_shutdown_no_usa_proxy_del_entorno": HUELLA_PROXY,
    "test_cliente_mcp_no_envia_json_a_par_sin_identidad": HUELLA_IDENTIDAD,
    "test_cliente_mcp_no_sube_ficheros_a_par_sin_identidad": HUELLA_IDENTIDAD,
    "test_shutdown_no_envia_token_a_par_sin_identidad": HUELLA_IDENTIDAD,
}

VARIABLES_PROXY = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
MARCADOR = b"MARCADOR-FICTICIO-0001"


class _Servidor:
    """Servidor HTTP de prueba en loopback que registra cada peticion y responde con `respuesta`."""

    def __init__(self, respuesta) -> None:
        self.registros: list[dict] = []
        registros = self.registros

        class Manejador(BaseHTTPRequestHandler):
            def _atender(self) -> None:
                largo = int(self.headers.get("Content-Length") or 0)
                cuerpo = self.rfile.read(largo) if largo else b""
                registros.append(
                    {
                        "metodo": self.command,
                        "ruta": self.path,
                        "cabeceras": {k.lower(): v for k, v in self.headers.items()},
                        "cuerpo": cuerpo,
                    }
                )
                estado, datos = respuesta(self.command, self.path)
                salida = json.dumps(datos).encode()
                self.send_response(estado)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(salida)))
                self.end_headers()
                self.wfile.write(salida)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _atender

            def log_message(self, *_args: object) -> None:
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.puerto = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.puerto}"

    def cerrar(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _api_falsa(_metodo: str, ruta: str) -> tuple[int, dict]:
    if ruta.startswith("/api/settings"):
        return 200, {"mcp_token": "t"}
    return 200, {"status": "ok"}


@pytest.fixture
def api():
    s = _Servidor(_api_falsa)
    yield s
    s.cerrar()


@pytest.fixture
def proxy():
    s = _Servidor(lambda *_a: (502, {"detail": "proxy de prueba"}))
    yield s
    s.cerrar()


@pytest.fixture
def sin_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    for nombre in VARIABLES_PROXY:
        monkeypatch.delenv(nombre, raising=False)
        monkeypatch.delenv(nombre.lower(), raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost,::1")


def _con_proxy(monkeypatch: pytest.MonkeyPatch, proxy: _Servidor) -> None:
    for nombre in VARIABLES_PROXY:
        monkeypatch.delenv(nombre, raising=False)
        monkeypatch.delenv(nombre.lower(), raising=False)
    monkeypatch.setenv("HTTP_PROXY", proxy.url)


def _bootstrap(url: str) -> None:
    async def _go() -> None:
        cliente = VigiaClient(url=url)
        try:
            with contextlib.suppress(Exception):  # el resultado se mide en los servidores de prueba
                await cliente.bootstrap()
        finally:
            await cliente.aclose()

    asyncio.run(_go())


def _lock(datos: Path, puerto: int, token: str = "ficticio") -> None:
    datos.mkdir(parents=True, exist_ok=True)
    LockFile(datos).acquire(puerto, token=token)


def test_bootstrap_mcp_no_usa_proxy_del_entorno(
    monkeypatch: pytest.MonkeyPatch, api: _Servidor, proxy: _Servidor, sin_proxy: None
) -> None:
    """El bootstrap del cliente MCP a loopback no pasa por HTTP_PROXY."""
    _bootstrap(api.url)  # control positivo: sin proxy llega a la API
    assert [r["ruta"] for r in api.registros] == ["/api/settings?reveal=true"]
    api.registros.clear()

    _con_proxy(monkeypatch, proxy)
    _bootstrap(api.url)
    assert proxy.registros == [], "la peticion a loopback no debe llegar al proxy"
    assert [r["ruta"] for r in api.registros] == ["/api/settings?reveal=true"]


def test_sondeo_de_salud_no_usa_proxy_del_entorno(
    monkeypatch: pytest.MonkeyPatch, api: _Servidor, proxy: _Servidor, sin_proxy: None
) -> None:
    """El sondeo /api/health de `vigia serve` a loopback no pasa por HTTP_PROXY."""
    assert cli._wait_for_health(api.url, 2.0) is True  # control positivo
    api.registros.clear()

    _con_proxy(monkeypatch, proxy)
    sano = cli._wait_for_health(api.url, 2.0)
    assert proxy.registros == [], "la peticion a loopback no debe llegar al proxy"
    assert sano is True
    assert api.registros, "la API de prueba debe recibir el sondeo"


def test_shutdown_no_usa_proxy_del_entorno(
    monkeypatch: pytest.MonkeyPatch, api: _Servidor, proxy: _Servidor, sin_proxy: None, tmp_path: Path
) -> None:
    """Huella: `vigia shutdown` a loopback no pasa por HTTP_PROXY."""
    _lock(tmp_path / "datos", api.puerto)
    argv = ["shutdown", "--data-dir", str(tmp_path / "datos")]
    assert cli.main(argv) == 0  # control positivo
    assert [r["ruta"] for r in api.registros] == ["/api/shutdown"]
    api.registros.clear()

    _con_proxy(monkeypatch, proxy)
    cli.main(argv)
    assert proxy.registros == [], "ni la peticion ni el token de apagado deben llegar al proxy"
    assert [r["ruta"] for r in api.registros] == ["/api/shutdown"]


def _lock_hacia(datos: Path, par: _Servidor) -> VigiaClient:
    _lock(datos, par.puerto)
    cliente = VigiaClient(data_dir=datos)
    assert cliente.discover() == par.url  # el cliente toma el puerto del lock
    assert httpx.get(f"{par.url}/api/settings", trust_env=False).status_code == 200
    par.registros.clear()
    return cliente


def _no_llega_carga(par: _Servidor, *marcas: bytes) -> bool:
    return not any(m in r["cuerpo"] for r in par.registros for m in marcas)


def test_cliente_mcp_no_envia_json_a_par_sin_identidad(
    api: _Servidor, sin_proxy: None, tmp_path: Path
) -> None:
    """El cliente MCP no envia un cuerpo JSON a un par que no prueba ser el servidor del lock."""
    cliente = _lock_hacia(tmp_path / "datos", api)

    async def _go() -> None:
        try:
            with contextlib.suppress(Exception):  # un rechazo del cliente es lo esperado tras el arreglo
                await cliente.post("/projects", json={"name": MARCADOR.decode()})
        finally:
            await cliente.aclose()

    asyncio.run(_go())
    assert _no_llega_carga(api, MARCADOR), "el par sin identidad no debe recibir el cuerpo"
    assert not any(r["cabeceras"].get("x-vigia-token") == "t" for r in api.registros)


def test_cliente_mcp_no_sube_ficheros_a_par_sin_identidad(
    api: _Servidor, sin_proxy: None, tmp_path: Path
) -> None:
    """El cliente MCP no sube un fichero a un par que no prueba ser el servidor del lock."""
    cliente = _lock_hacia(tmp_path / "datos", api)
    fichero = tmp_path / "ficticio.csv"
    fichero.write_bytes(b"col\n" + MARCADOR + b"\n")

    async def _go() -> None:
        try:
            with contextlib.suppress(Exception):
                await cliente.upload("/projects/1/datasets", file_path=str(fichero), fields={"a": "b"})
        finally:
            await cliente.aclose()

    asyncio.run(_go())
    assert _no_llega_carga(api, MARCADOR), "el par sin identidad no debe recibir el fichero"


def test_shutdown_no_envia_token_a_par_sin_identidad(
    api: _Servidor, sin_proxy: None, tmp_path: Path
) -> None:
    """Huella: `vigia shutdown` no envia el token del lock a un par que no prueba ser el servidor."""
    datos = tmp_path / "datos"
    _lock(datos, api.puerto, token="ficticio")
    assert LockFile(datos).is_stale() is False and os.getpid() == LockFile(datos).read()["pid"]
    cli.main(["shutdown", "--data-dir", str(datos)])
    assert not any(r["cabeceras"].get("x-vigia-token") == "ficticio" for r in api.registros)
