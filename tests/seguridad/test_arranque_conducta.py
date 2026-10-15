"""Comprobaciones de conducta de arranque, registro y cupo.

Estas pruebas ejercitan el comportamiento por el camino público (`cmd_serve`, `print` sin
consola, `POST /api/demo/runs`), no por los símbolos nuevos; ver `HUELLAS`.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia import cli
from vigia.app.main import create_app
from vigia.app.settings import Settings

HUELLAS = {
    "test_vigia_log_no_pasa_de_5_mb_ni_de_3_copias": "log-rotation-and-flush",
    "test_vigia_serve_arranca_en_el_puerto_guardado": "saved-port",
    "test_cmd_serve_deja_el_registro_cerrado_al_salir": "log-rotation-and-flush",
    "test_el_cupo_de_demos_de_fabrica_da_409_en_el_51": "demo-quota",
    "test_la_salida_sin_consola_no_pierde_lineas_con_hilos": "log-rotation-and-flush",
}

BASE = "http://127.0.0.1:8765"
ACTOR = actor_headers("miguel")
MB = 1024 * 1024


class _CerrojoQueParaElArranque:
    """Sustituto de `LockFile`: anota el puerto con el que `cmd_serve` intenta arrancar y para."""

    puertos: ClassVar[list[int]] = []

    def __init__(self, *_a: object, **_k: object) -> None:
        pass

    def acquire(self, port: int, **_k: object) -> None:
        self.puertos.append(port)
        raise RuntimeError("parada de la prueba")

    def release(self) -> None:
        pass


def _cerrar_todo() -> None:
    """Quita los manejadores del paquete, con o sin `cerrar_registro` (rojo previo al arreglo)."""
    log = logging.getLogger("vigia")
    for manejador in list(log.handlers):
        if isinstance(manejador, RotatingFileHandler | logging.FileHandler):
            log.removeHandler(manejador)
            manejador.close()


@pytest.fixture
def sin_registro():
    yield
    _cerrar_todo()


def _args(datos: Path, puerto: int | None) -> argparse.Namespace:
    return argparse.Namespace(host="127.0.0.1", port=puerto, data_dir=str(datos), no_browser=True)


def _preparar_serve(monkeypatch: pytest.MonkeyPatch, pedidos: list[int]) -> None:
    def libre(start: int = 8765, **_k: object) -> int:
        pedidos.append(start)
        return start

    _CerrojoQueParaElArranque.puertos = []
    monkeypatch.setattr(cli, "find_free_port", libre)
    monkeypatch.setattr(cli, "port_is_free", lambda *_a, **_k: True)
    monkeypatch.setattr(cli, "import_with_retry", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "prepare_cache_env", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "LockFile", _CerrojoQueParaElArranque)


def _guardar_puerto(datos: Path, puerto: int) -> None:
    ajustes = Settings(data_dir=datos, port_start=8904, open_browser=False, jobs_inline=True)
    with TestClient(create_app(ajustes), base_url=BASE) as c:
        resp = c.patch(
            "/api/settings",
            json={"actor": "miguel", "motivo": "puerto", "values": {"puerto": puerto}},
            headers=ACTOR,
        )
        assert resp.status_code == 200, resp.text


def test_vigia_log_no_pasa_de_5_mb_ni_de_3_copias(tmp_path, monkeypatch, sin_registro):
    """Sin consola, escribir 7 MB de salida deja `vigia.log` en 5 MB como máximo y 3 copias."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    cli.redirect_streams_if_headless(tmp_path)
    for i in range(700):
        print(f"línea {i} " + "z" * 10_000)
    sys.stdout.flush()
    archivos = {p.name: p.stat().st_size for p in tmp_path.iterdir() if p.name.startswith("vigia.log")}
    assert set(archivos) <= {"vigia.log", "vigia.log.1", "vigia.log.2", "vigia.log.3"}, archivos
    assert max(archivos.values()) <= 5 * MB + 20_000, archivos
    assert len(archivos) > 1, "el registro no rotó"


def test_vigia_serve_arranca_en_el_puerto_guardado(tmp_path, monkeypatch, sin_registro):
    """Sin `--port`, `vigia serve` busca el puerto desde el ajuste guardado; con `--port`, manda este."""
    datos = tmp_path / "datos"
    datos.mkdir()
    _guardar_puerto(datos, 40123)
    pedidos: list[int] = []
    _preparar_serve(monkeypatch, pedidos)
    assert cli.cmd_serve(_args(datos, None)) == 1
    assert pedidos == [40123]
    assert _CerrojoQueParaElArranque.puertos == [40123]
    pedidos.clear()
    assert cli.cmd_serve(_args(datos, 8999)) == 1
    assert _CerrojoQueParaElArranque.puertos[-1] == 8999
    assert pedidos == []


def test_cmd_serve_deja_el_registro_cerrado_al_salir(tmp_path, monkeypatch, sin_registro):
    """Tras salir `cmd_serve` con consola, el paquete no conserva `vigia.log` abierto."""
    datos = tmp_path / "datos"
    datos.mkdir()
    _preparar_serve(monkeypatch, [])
    assert cli.cmd_serve(_args(datos, None)) == 1
    abiertos = [h for h in logging.getLogger("vigia").handlers if isinstance(h, RotatingFileHandler)]
    assert abiertos == []
    (datos / "vigia.log").unlink()  # en Windows falla si algún manejador lo tiene abierto


def test_el_cupo_de_demos_de_fabrica_da_409_en_el_51(tmp_path):
    """Con el cupo de fábrica, la demo número 51 sin proyecto da 409 en español."""
    datos = tmp_path / "datos-cupo"
    datos.mkdir()
    ajustes = Settings(data_dir=datos, port_start=8904, open_browser=False, jobs_inline=True)
    with TestClient(create_app(ajustes), base_url=BASE) as c:
        cuerpo = {"scenario_key": "timeline_completo"}
        for _ in range(50):
            assert c.post("/api/demo/runs", json=cuerpo, headers=ACTOR).status_code == 200
        resp = c.post("/api/demo/runs", json=cuerpo, headers=ACTOR)
        assert resp.status_code == 409, resp.status_code
        assert "50" in resp.json()["detail"]


def test_la_salida_sin_consola_no_pierde_lineas_con_hilos(tmp_path, sin_registro):
    """Varios hilos escribiendo a la vez en la salida sin consola dejan todas sus líneas enteras."""
    cli.configurar_registro(tmp_path)
    salida = cli._SalidaALog(logging.INFO)
    n_hilos, n_lineas = 8, 400

    def escribir(h: int) -> None:
        for i in range(n_lineas):
            salida.write(f"h{h}-l{i}-fin\n")

    hilos = [threading.Thread(target=escribir, args=(h,)) for h in range(n_hilos)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    salida.flush()
    for manejador in logging.getLogger("vigia").handlers:
        manejador.flush()
    lineas = (tmp_path / "vigia.log").read_text(encoding="utf-8").splitlines()
    lineas = [linea.split(": ", 1)[1] for linea in lineas]  # sin la fecha ni el nivel
    assert sorted(lineas) == sorted(f"h{h}-l{i}-fin" for h in range(n_hilos) for i in range(n_lineas))
