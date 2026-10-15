"""El cliente MCP repite la prueba de identidad del servidor.

Los servidores de prueba escuchan en el puerto 0 de loopback; solo datos ficticios.
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from vigia.app.preflight import CABECERA_RETO, DOMINIO_IDENTIDAD, LockFile, calcular_prueba
from vigia.mcp.client import VigiaClient
from vigia.mcp.errores import VigiaError

HUELLAS = {
    "test_el_cliente_mcp_repite_la_prueba_de_identidad_en_cada_peticion": (
        "mcp/client.py:identity-verified-once-then-cached"
    ),
    "test_el_cliente_mcp_redescubre_el_servidor_tras_un_fallo_de_conexion": (
        "mcp/client.py:identity-verified-once-then-cached"
    ),
}
MARCADOR = b"MARCADOR-FICTICIO-0002"


class Par:
    """Servidor de prueba. En modo `real` contesta la prueba de identidad con el
    token del lock; en modo `otro` es un programa que no conoce ese token."""

    def __init__(self, token: str, modo: str = "real") -> None:
        self.token, self.modo = token, modo
        self.registros: list[dict] = []
        par = self

        class Manejador(BaseHTTPRequestHandler):
            def _atender(self) -> None:
                largo = int(self.headers.get("Content-Length") or 0)
                cuerpo = self.rfile.read(largo) if largo else b""
                cab = {k.lower(): v for k, v in self.headers.items()}
                par.registros.append({"ruta": self.path, "cabeceras": cab, "cuerpo": cuerpo})
                estado, datos = 200, {"items": [], "mcp_token": "t-mcp"}
                if self.path.startswith("/api/identidad"):
                    if par.modo == "real":
                        reto = cab[CABECERA_RETO.lower()]
                        datos = {"prueba": calcular_prueba(par.token, reto, DOMINIO_IDENTIDAD)}
                    else:
                        estado, datos = 404, {"detail": "no existe"}
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

    def cerrar(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def con_carga(self) -> list[dict]:
        """Peticiones que no son la prueba de identidad."""
        return [r for r in self.registros if not r["ruta"].startswith("/api/identidad")]


def _lock(datos: Path, puerto: int, token: str) -> None:
    (datos / "vigia.lock").unlink(missing_ok=True)
    LockFile(datos).acquire(puerto, token=token)


def test_el_cliente_mcp_repite_la_prueba_de_identidad_en_cada_peticion(tmp_path: Path):
    """Aunque otro programa pase a contestar en el puerto del lock después de la
    primera comprobación, el cliente no le envía ni el token, ni el JSON ni el fichero."""
    datos = tmp_path / "datos"
    par = Par("token-del-lock")
    _lock(datos, par.puerto, "token-del-lock")
    fichero = tmp_path / "ficticio.csv"
    fichero.write_bytes(b"col\n" + MARCADOR + b"\n")
    cliente = VigiaClient(data_dir=datos)
    cliente.discover()

    async def _go() -> list[object]:
        resultados: list[object] = []
        try:
            await cliente.get("/projects")  # el servidor de verdad: pasa la prueba
            assert par.con_carga(), "el control positivo no llegó al servidor"
            par.modo = "otro"
            par.registros.clear()
            for llamada in (
                lambda: cliente.get("/projects"),
                lambda: cliente.post("/projects", json={"name": MARCADOR.decode()}),
                lambda: cliente.upload("/projects/1/datasets", file_path=str(fichero), fields={}),
            ):
                try:
                    await llamada()
                except VigiaError as exc:
                    resultados.append(exc)
        finally:
            await cliente.aclose()
        return resultados

    try:
        errores = asyncio.run(_go())
    finally:
        par.cerrar()
    assert [e.status_code for e in errores] == [502, 502, 502]
    assert par.con_carga() == [], "el programa sin identidad no debe recibir nada más que el reto"
    assert not any("x-vigia-token" in r["cabeceras"] for r in par.registros)


def test_el_cliente_mcp_redescubre_el_servidor_tras_un_fallo_de_conexion(tmp_path: Path):
    """Si el servidor se para y arranca otro en otro puerto con otro token, el cliente
    olvida lo anterior tras el fallo, lee el lock otra vez y vuelve a probar la identidad."""
    datos = tmp_path / "datos"
    primero = Par("token-uno")
    _lock(datos, primero.puerto, "token-uno")
    cliente = VigiaClient(data_dir=datos)
    cliente.discover()
    segundo = Par("token-dos")

    async def _go() -> None:
        try:
            await cliente.get("/projects")
            primero.cerrar()
            with pytest.raises(VigiaError) as caido:
                await cliente.get("/projects")
            assert caido.value.status_code == 503
            _lock(datos, segundo.puerto, "token-dos")
            await cliente.get("/projects")
        finally:
            await cliente.aclose()

    try:
        asyncio.run(_go())
    finally:
        segundo.cerrar()
    rutas = [r["ruta"] for r in segundo.registros]
    assert rutas[0].startswith("/api/identidad") and any(r.startswith("/api/projects") for r in rutas)
