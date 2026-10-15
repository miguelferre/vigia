"""Registro rotatorio, puerto guardado y textos de la interfaz.

Cada test comprueba el control seguro de un apunte; ver `HUELLAS`.
"""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia import cli
from vigia.app.main import create_app
from vigia.app.preflight import find_free_port
from vigia.app.settings import Settings

HUELLAS = {
    "test_vigia_log_rota_a_5_mb_con_3_copias": "log-rotation-and-flush",
    "test_el_registro_rota_de_verdad": "log-rotation-and-flush",
    "test_sin_consola_la_salida_va_al_registro_rotatorio": "log-rotation-and-flush",
    "test_vigia_serve_usa_el_puerto_guardado": "saved-port",
    "test_el_puerto_guardado_no_rompe_el_arranque": "saved-port",
    "test_la_ruta_de_la_demo_codifica_guion_y_fase": "demo-route-encoding",
    "test_la_confirmacion_no_local_habla_de_todo_el_dossier": "non-local-confirmation-text",
}

RAIZ = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8765"


@pytest.fixture
def registro():
    yield
    cli.cerrar_registro()


def _rotatorio() -> RotatingFileHandler:
    return next(h for h in logging.getLogger("vigia").handlers if isinstance(h, RotatingFileHandler))


def test_vigia_log_rota_a_5_mb_con_3_copias(tmp_path, registro):
    """`vigia.log` es un archivo rotatorio de 5 MB con 3 copias, configurado en un solo sitio."""
    ruta = cli.configurar_registro(tmp_path)
    manejador = _rotatorio()
    assert ruta == tmp_path / "vigia.log"
    assert Path(manejador.baseFilename) == ruta
    assert manejador.maxBytes == 5 * 1024 * 1024
    assert manejador.backupCount == 3
    cli.configurar_registro(tmp_path)  # idempotente: no apila manejadores
    assert sum(isinstance(h, RotatingFileHandler) for h in logging.getLogger("vigia").handlers) == 1


def test_el_registro_rota_de_verdad(tmp_path, registro, monkeypatch):
    """Al pasar el tope, el registro se parte en copias y nunca hay más de tres."""
    monkeypatch.setattr(cli, "REGISTRO_MAX_BYTES", 2000)
    cli.configurar_registro(tmp_path)
    log = logging.getLogger("vigia.app.jobs")
    for i in range(300):
        log.warning("aviso de prueba número %d %s", i, "x" * 60)
    nombres = sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("vigia.log"))
    assert nombres == ["vigia.log", "vigia.log.1", "vigia.log.2", "vigia.log.3"]


def test_sin_consola_la_salida_va_al_registro_rotatorio(tmp_path, monkeypatch, registro):
    """Sin consola (pythonw), `print` y los errores caen en el mismo archivo rotatorio."""
    monkeypatch.setattr(cli, "REGISTRO_MAX_BYTES", 2000)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    ruta = cli.redirect_streams_if_headless(tmp_path / "datos")
    assert ruta == tmp_path / "datos" / "vigia.log"
    print("hola desde pythonw")
    assert "hola desde pythonw" in ruta.read_text(encoding="utf-8")
    for i in range(200):
        print(f"línea {i} " + "y" * 60)
    sys.stderr.write("fallo de uvicorn\n")
    assert (tmp_path / "datos" / "vigia.log.1").exists()
    assert not (tmp_path / "datos" / "vigia.log.4").exists()


def _guardar_puerto(datos: Path, puerto: int) -> None:
    ajustes = Settings(data_dir=datos, port_start=8904, open_browser=False, jobs_inline=True)
    app = create_app(ajustes)
    app.state.port = 8904
    with TestClient(app, base_url=BASE) as c:
        resp = c.patch(
            "/api/settings",
            json={"actor": "miguel", "motivo": "puerto", "values": {"puerto": puerto}},
            headers=actor_headers("miguel"),
        )
        assert resp.status_code == 200, resp.text


def test_vigia_serve_usa_el_puerto_guardado(tmp_path):
    """Sin `--port`, el arranque usa el ajuste `puerto` guardado; con `--port`, manda el argumento."""
    datos = tmp_path / "datos"
    datos.mkdir()
    ajustes = Settings(data_dir=datos, port_start=8765)
    assert cli.puerto_de_arranque(None, ajustes) == find_free_port(start=8765, host=ajustes.host)
    _guardar_puerto(datos, 40123)
    assert cli.puerto_de_arranque(None, ajustes) == find_free_port(start=40123, host=ajustes.host)
    assert cli.puerto_de_arranque(8999, ajustes) == 8999


def test_el_puerto_guardado_no_rompe_el_arranque(tmp_path):
    """Una base ilegible o un valor guardado raro no impiden arrancar: vale el puerto de fábrica."""
    datos = tmp_path / "datos"
    datos.mkdir()
    (datos / "vigia.db").write_bytes(b"esto no es una base de datos")
    ajustes = Settings(data_dir=datos, port_start=8765)
    assert cli.puerto_de_arranque(None, ajustes) == find_free_port(start=8765, host=ajustes.host)


def test_la_ruta_de_la_demo_codifica_guion_y_fase():
    """El asistente de subida codifica guion y fase antes de ponerlos en la ruta del fetch."""
    fuente = (RAIZ / "frontend/src/pages/modelos/subida-dataset-demo.ts").read_text(encoding="utf-8")
    ruta = re.search(r"`\$\{API_BASE\}/demo/scenarios/([^`]*)`", fuente)
    assert ruta, "no se encontró la ruta del fetch"
    assert "encodeURIComponent(precargaDemo.guion)" in ruta.group(1)
    assert "encodeURIComponent(precargaDemo.fase)" in ruta.group(1)


def test_la_confirmacion_no_local_habla_de_todo_el_dossier():
    """El texto que confirma un backend no local nombra el dossier entero, no solo los formularios."""
    fuente = (RAIZ / "frontend/src/pages/ajustes/ajustes-datos.ts").read_text(encoding="utf-8")
    texto = re.search(r"CONFIRMACION_NO_LOCAL\s*=\s*([^;]*);", fuente, re.DOTALL).group(1)
    assert "dossier" in texto
    assert "deskilling" in texto
