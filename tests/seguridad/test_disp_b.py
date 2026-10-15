"""Disponibilidad, parte B: pruebas con servidor real (puertos 8970 a 8974).

Cada test comprueba el control seguro de una huella (ver `HUELLAS`) contra el código actual.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import uvicorn

from vigia.app.main import create_app
from vigia.app.services import human_layer
from vigia.app.services import outcomes as outcomes_service
from vigia.app.settings import Settings

HUELLAS = {
    "test_flujos_sse_no_saturan_la_api": "sse-streams-saturate-default-thread-limiter",
    "test_subida_diario_no_bloquea_el_bucle": "usage-log-upload-sync-work-in-async-handler",
    "test_subida_outcomes_no_bloquea_el_bucle": "usage-log-upload-sync-work-in-async-handler",
}

CABECERAS = {"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"}


@contextmanager
def _servidor(tmp_path: Path, puerto: int, heartbeat: float) -> Iterator[str]:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        data_dir=d, host="127.0.0.1", port_start=puerto, open_browser=False,
        jobs_inline=False, sse_heartbeat_s=heartbeat,
    )
    app = create_app(settings)
    app.state.port = puerto
    app.state.shutdown_token = "test-token"
    config = uvicorn.Config(
        app, host="127.0.0.1", port=puerto, log_level="error", timeout_graceful_shutdown=1
    )
    server = uvicorn.Server(config)
    hilo = threading.Thread(target=server.run, daemon=True)
    hilo.start()
    base = f"http://127.0.0.1:{puerto}"
    limite = time.monotonic() + 20
    while time.monotonic() < limite:
        try:
            if httpx.get(f"{base}/api/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        raise AssertionError("el servidor de prueba no arrancó")
    try:
        yield base
    finally:
        server.force_exit = True
        server.should_exit = True
        hilo.join(timeout=5)


def test_flujos_sse_no_saturan_la_api(tmp_path: Path):
    """Control: con decenas de flujos SSE abiertos, GET /api/health sigue respondiendo en pocos segundos."""
    with _servidor(tmp_path, 8970, heartbeat=15.0) as base:
        assert httpx.get(f"{base}/api/health", timeout=5).status_code == 200  # control positivo
        socks = []
        try:
            for _ in range(60):
                s = socket.create_connection(("127.0.0.1", 8970), timeout=5)
                s.sendall(b"GET /api/events/stream HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
                socks.append(s)
            time.sleep(1.0)
            t0 = time.monotonic()
            try:
                r = httpx.get(f"{base}/api/health", timeout=5)
                estado = r.status_code
            except httpx.HTTPError:
                estado = None
            espera = time.monotonic() - t0
        finally:
            for s in socks:
                s.close()
        assert estado == 200, f"la API no respondió en 5 s con 60 flujos SSE abiertos ({estado})"
        assert espera < 3.0, f"GET /api/health tardó {espera:.1f} s con 60 flujos SSE abiertos"


def _latencia_durante(base: str, ruta: str, archivo: tuple[str, bytes, str]) -> float:
    """Lanza una subida y mide la latencia de GET /api/health mientras se procesa."""
    hilo = threading.Thread(
        target=lambda: httpx.post(
            f"{base}{ruta}", files={"file": archivo}, headers=CABECERAS, timeout=30
        ),
        daemon=True,
    )
    hilo.start()
    time.sleep(0.5)
    t0 = time.monotonic()
    r = httpx.get(f"{base}/api/health", timeout=10)
    latencia = time.monotonic() - t0
    assert r.status_code == 200
    hilo.join(timeout=15)
    return latencia


def _crear_proyecto(base: str) -> int:
    r = httpx.post(
        f"{base}/api/projects", json={"name": "disp-bucle", "domain": "reuma"},
        headers=CABECERAS, timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_subida_diario_no_bloquea_el_bucle(tmp_path: Path, monkeypatch):
    """Control: procesar la subida del diario de uso no bloquea el bucle de eventos de la API."""

    llamadas: list[int] = []

    def _lento(*args, **kwargs):
        llamadas.append(1)
        time.sleep(2.0)
        return SimpleNamespace(id=1), 0, None, []

    monkeypatch.setattr(human_layer, "ingest_usage_log", _lento)
    with _servidor(tmp_path, 8971, heartbeat=0.5) as base:
        pid = _crear_proyecto(base)
        csv = b"date,human_decision,model_output,ground_truth\n2026-01-05,refer,refer,refer\n"
        latencia = _latencia_durante(
            base, f"/api/projects/{pid}/usage-logs/upload", ("uso.csv", csv, "text/csv")
        )
    assert llamadas == [1], "la petición no llegó al servicio de ingesta"
    assert latencia < 1.0, f"GET /api/health tardó {latencia:.1f} s durante la subida"


def test_subida_outcomes_no_bloquea_el_bucle(tmp_path: Path, monkeypatch):
    """Control: procesar la subida de outcomes no bloquea el bucle de eventos de la API."""

    llamadas: list[int] = []

    def _lento(*args, **kwargs):
        llamadas.append(1)
        time.sleep(2.0)
        return 0, 0, 0

    monkeypatch.setattr(outcomes_service, "ingest_outcomes", _lento)
    with _servidor(tmp_path, 8972, heartbeat=0.5) as base:
        pid = _crear_proyecto(base)
        csv = b"period,metric_key,value,source\n2026-01,tasa,0.8,manual\n"
        latencia = _latencia_durante(
            base, f"/api/projects/{pid}/outcomes", ("outcomes.csv", csv, "text/csv")
        )
    assert llamadas == [1], "la petición no llegó al servicio de ingesta"
    assert latencia < 1.0, f"GET /api/health tardó {latencia:.1f} s durante la subida"
