"""Robustez del arranque de `vigia serve`.

Huella: src/vigia/cli.py:serve-port-probe-then-rebind-fail-open.
Control esperado: si el servidor propio no llega a escuchar, `cmd_serve` termina con
codigo distinto de 0, no abre el navegador contra un par ajeno y libera el lock.
"""

from __future__ import annotations

import argparse
import json
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import uvicorn

from vigia import cli

HUELLA_ARRANQUE = "src/vigia/cli.py:serve-port-probe-then-rebind-fail-open"
HUELLAS = {
    "test_serve_no_abre_navegador_ni_queda_vivo_con_par_ajeno": HUELLA_ARRANQUE,
    "test_serve_termina_si_el_servidor_propio_no_arranca": HUELLA_ARRANQUE,
    "test_serve_termina_si_el_lifespan_falla": HUELLA_ARRANQUE,
}

PUERTO = 8985  # area ident: 8985 a 8989


class _ParAjeno(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        cuerpo = json.dumps({"status": "ok", "data_dir": "otra-carpeta", "port": 1}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *_args: object) -> None:
        return


def _lanzar_serve(monkeypatch: pytest.MonkeyPatch, datos: Path, *, espera_s: float = 7.0) -> dict:
    """Ejecuta `cmd_serve` en un hilo y mide su estado tras `espera_s`; luego lo apaga."""
    manejadores: list = []
    abiertos: list[str] = []
    monkeypatch.setattr(cli, "find_free_port", lambda *a, **k: PUERTO)
    monkeypatch.setattr(cli, "import_with_retry", lambda *a, **k: None)
    monkeypatch.setattr(cli, "prepare_cache_env", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_install_windows_ctrl_handler", manejadores.append)
    monkeypatch.setattr(cli.signal, "signal", lambda _s, h: manejadores.append(h))
    monkeypatch.setattr(cli.webbrowser, "open", abiertos.append)
    monkeypatch.setattr(cli, "HEALTH_TIMEOUT_S", 2.0)
    args = argparse.Namespace(host="127.0.0.1", port=None, data_dir=str(datos), no_browser=False)

    resultado: dict = {}
    hilo = threading.Thread(target=lambda: resultado.setdefault("rc", cli.cmd_serve(args)), daemon=True)
    hilo.start()
    hilo.join(espera_s)
    estado = {
        "vivo": hilo.is_alive(),
        "abiertos": list(abiertos),
        "lock": (datos / "vigia.lock").exists(),
    }
    if hilo.is_alive():
        for _ in range(50):  # el manejador se instala tras el sondeo de salud
            if manejadores:
                break
            threading.Event().wait(0.1)
        for manejador in manejadores:
            manejador(signal.SIGINT, None) if manejador.__code__.co_argcount else manejador()
        hilo.join(15)
    estado["rc"] = resultado.get("rc")
    return estado


def _servidor_ajeno() -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", PUERTO), _ParAjeno)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _servidor_propio_no_arranca(self: uvicorn.Server) -> None:
    raise SystemExit(1)


def test_control_positivo_serve_arranca_y_apaga(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Control del montaje: sin fallos inyectados, `cmd_serve` abre el navegador y sale con 0."""
    estado = _lanzar_serve(monkeypatch, tmp_path / "datos", espera_s=6.0)
    assert estado["vivo"], "el servidor sano debe seguir en marcha hasta que se le apague"
    assert estado["abiertos"] == [f"http://127.0.0.1:{PUERTO}"]
    assert estado["rc"] == 0


def test_serve_no_abre_navegador_ni_queda_vivo_con_par_ajeno(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Con el bind propio fallido y otro proceso respondiendo 200, no se abre el navegador."""
    monkeypatch.setattr(uvicorn.Server, "run", _servidor_propio_no_arranca)
    ajeno = _servidor_ajeno()
    try:
        estado = _lanzar_serve(monkeypatch, tmp_path / "datos")
    finally:
        ajeno.shutdown()
        ajeno.server_close()
    assert estado["abiertos"] == [], "no debe abrirse el navegador contra un par ajeno"
    assert not estado["vivo"], "cmd_serve debe terminar si el servidor propio murio"
    assert estado["rc"] not in (None, 0)
    assert not estado["lock"], "el lock debe liberarse"


def test_serve_termina_si_el_servidor_propio_no_arranca(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Con el bind propio fallido y nadie escuchando, cmd_serve sale con codigo distinto de 0."""
    monkeypatch.setattr(uvicorn.Server, "run", _servidor_propio_no_arranca)
    estado = _lanzar_serve(monkeypatch, tmp_path / "datos")
    assert not estado["vivo"], "cmd_serve debe terminar si el servidor propio murio"
    assert estado["rc"] not in (None, 0)
    assert not estado["lock"], "el lock debe liberarse"


def test_serve_termina_si_el_lifespan_falla(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Con la migracion del lifespan fallida, cmd_serve sale con codigo distinto de 0."""
    import vigia.app.main as app_main

    def _migrar_falla(*_a: object, **_k: object) -> int:
        raise RuntimeError("migracion de prueba fallida")

    monkeypatch.setattr(app_main, "migrate", _migrar_falla)
    estado = _lanzar_serve(monkeypatch, tmp_path / "datos")
    assert not estado["vivo"], "cmd_serve debe terminar si el lifespan fallo"
    assert estado["rc"] not in (None, 0)
    assert not estado["lock"], "el lock debe liberarse"
