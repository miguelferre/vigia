"""Endurecimiento de la frontera del proceso, la CLI y el cliente del MCP.

Un test por arreglo, incluidas las comprobaciones de `::1`. Puertos de este grupo: 8960 a 8964.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vigia import cli
from vigia.app import events as events_mod
from vigia.app.main import create_app
from vigia.app.preflight import LockFile, calcular_prueba, nuevo_reto
from vigia.app.routers import health as health_mod
from vigia.app.settings import Settings
from vigia.mcp import client as client_mod
from vigia.mcp import server as server_mod
from vigia.mcp.client import VigiaClient, VigiaError, validar_url_local

PUERTO = 8960
BASE = "http://127.0.0.1:8765"


@pytest.fixture
def cliente(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "datos", host="127.0.0.1", open_browser=False, jobs_inline=True)
    app = create_app(settings)
    app.state.shutdown_token = "tok-ficticio"
    app.state.shutdown_event = threading.Event()
    with TestClient(app, base_url=BASE) as c:
        yield c


def _espia(monkeypatch: pytest.MonkeyPatch, modulo) -> list[tuple]:
    llamadas: list[tuple] = []
    original = modulo.hmac.compare_digest

    def espia(a, b):
        llamadas.append((a, b))
        return original(a, b)

    monkeypatch.setattr(modulo.hmac, "compare_digest", espia)
    return llamadas


def test_token_de_apagado_en_tiempo_constante(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas = _espia(monkeypatch, health_mod)
    assert cliente.post("/api/shutdown", headers={"X-Vigia-Token": "otro"}).status_code == 403
    assert llamadas, "la comparación del token debe pasar por compare_digest"
    assert cliente.post("/api/shutdown", headers={"X-Vigia-Token": "tok-ficticio"}).status_code == 200


def test_apagado_con_prueba_firmada_vale_una_vez(cliente: TestClient) -> None:
    reto = nuevo_reto()
    cabeceras = {"X-Vigia-Reto": reto, "X-Vigia-Prueba": calcular_prueba("tok-ficticio", reto, "apagado")}
    assert cliente.post("/api/shutdown", headers=cabeceras).status_code == 200
    assert cliente.post("/api/shutdown", headers=cabeceras).status_code == 403, "el reto no se reutiliza"
    reto2 = nuevo_reto()
    mala = {"X-Vigia-Reto": reto2, "X-Vigia-Prueba": calcular_prueba("tok-ficticio", reto2, "identidad")}
    assert cliente.post("/api/shutdown", headers=mala).status_code == 403, "la prueba de identidad no apaga"


def test_identidad_responde_solo_con_reto_reciente(cliente: TestClient) -> None:
    reto = nuevo_reto()
    resp = cliente.get("/api/identidad", headers={"X-Vigia-Reto": reto})
    assert resp.status_code == 200
    assert resp.json()["prueba"] == calcular_prueba("tok-ficticio", reto, "identidad")
    assert cliente.get("/api/identidad").status_code == 404
    assert cliente.get("/api/identidad", headers={"X-Vigia-Reto": "1.abc"}).status_code == 404


def test_token_del_mcp_en_tiempo_constante(cliente: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    llamadas = _espia(monkeypatch, events_mod)
    cuerpo = {"name": "Proyecto ficticio"}
    resp = cliente.post(
        "/api/projects", json=cuerpo, headers={"X-Vigia-Actor-Kind": "agente", "X-Vigia-Token": "no-es-el-token"}
    )
    assert resp.status_code == 401
    assert llamadas, "la comparación del token del MCP debe pasar por compare_digest"
    token = cliente.get("/api/settings", params={"reveal": "true"}).json()["mcp_token"]
    ok = cliente.post("/api/projects", json=cuerpo, headers={"X-Vigia-Actor-Kind": "agente", "X-Vigia-Token": token})
    assert ok.status_code != 401


def test_lock_atomico_con_dos_arranques_a_la_vez(tmp_path: Path) -> None:
    resultados: list[str] = []
    barrera = threading.Barrier(8)

    def intentar() -> None:
        barrera.wait()
        try:
            LockFile(tmp_path).acquire(PUERTO, token="t")
            resultados.append("ok")
        except RuntimeError:
            resultados.append("ocupado")

    hilos = [threading.Thread(target=intentar) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert resultados.count("ok") == 1, resultados


def test_fallo_de_lock_sale_con_mensaje_y_respeta_el_lock_ajeno(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    datos = tmp_path / "datos"
    datos.mkdir(parents=True)
    # Un lock vivo de otro proceso (el padre de este).
    (datos / "vigia.lock").write_text(
        json.dumps({"pid": os.getppid(), "port": PUERTO + 1, "token": "de-otro"}), encoding="utf-8"
    )
    monkeypatch.setattr(cli, "find_free_port", lambda *a, **k: PUERTO)
    monkeypatch.setattr(cli, "import_with_retry", lambda *a, **k: None)
    monkeypatch.setattr(cli, "prepare_cache_env", lambda *a, **k: None)
    args = argparse.Namespace(host="127.0.0.1", port=None, data_dir=str(datos), no_browser=True)
    assert cli.cmd_serve(args) == 1
    assert "ya está en marcha" in capsys.readouterr().err
    assert LockFile(datos).read()["token"] == "de-otro", "el lock ajeno no se borra"


@pytest.mark.parametrize("host", ["::1", "0.0.0.0", "evil.example"])
def test_host_distinto_de_127_y_localhost_da_error(
    host: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.LOOPBACK_HOSTS == {"127.0.0.1", "localhost"}
    assert cli.main(["serve", "--host", host, "--no-browser"]) == 2
    err = capsys.readouterr().err
    assert "127.0.0.1" in err and "localhost" in err


def test_upload_no_lee_un_fichero_mayor_de_200_mb(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gigante = str(tmp_path / "no-existe.csv")  # si se intentara leer, daría FileNotFoundError
    monkeypatch.setattr(client_mod.os.path, "getsize", lambda _p: 201 * 1024 * 1024)

    async def _go() -> None:
        c = VigiaClient(url=BASE)
        await c.upload("/projects/1/datasets", file_path=gigante, fields={})

    with pytest.raises(VigiaError) as exc:
        asyncio.run(_go())
    assert exc.value.status_code == 413
    assert "200 MB" in str(exc.value)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8765", "http://localhost:8123", "http://127.0.0.1"])
def test_url_local_se_admite(url: str) -> None:
    assert validar_url_local(url) == url


@pytest.mark.parametrize(
    "url",
    ["https://127.0.0.1:8765", "http://evil.example:8765", "http://127.0.0.1.evil.example", "ftp://localhost", "http://[::1]:8765", "127.0.0.1:8765", "http://127.0.0.1:abc"],
)
def test_url_no_local_da_error(url: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(RuntimeError, match="solo se admite http://"):
        validar_url_local(url)
    with pytest.raises(RuntimeError):
        server_mod._preparar(["--url", url])
    assert server_mod.main(["--url", url]) == 1
    assert "--url" in capsys.readouterr().err


def test_serve_escribe_la_direccion_al_arrancar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manejadores: list = []
    monkeypatch.setattr(cli, "find_free_port", lambda *a, **k: PUERTO + 2)
    monkeypatch.setattr(cli, "import_with_retry", lambda *a, **k: None)
    monkeypatch.setattr(cli, "prepare_cache_env", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_install_windows_ctrl_handler", manejadores.append)
    monkeypatch.setattr(cli.signal, "signal", lambda _s, h: manejadores.append(h))
    args = argparse.Namespace(host="127.0.0.1", port=None, data_dir=str(tmp_path / "datos"), no_browser=True)
    resultado: dict = {}
    hilo = threading.Thread(target=lambda: resultado.setdefault("rc", cli.cmd_serve(args)), daemon=True)
    hilo.start()
    for _ in range(100):
        if len(manejadores) >= 2 or not hilo.is_alive():
            break
        threading.Event().wait(0.1)
    try:
        assert f"Vigía está en marcha en http://127.0.0.1:{PUERTO + 2}" in capsys.readouterr().out
    finally:
        for m in manejadores:
            m(signal.SIGINT, None) if m.__code__.co_argcount else m()
        hilo.join(15)
    assert resultado.get("rc") == 0


def test_cliente_con_lock_verifica_la_identidad_del_servidor_real(tmp_path: Path) -> None:
    """Contra un servidor real: con el token del lock el cliente trabaja; con otro, se niega."""
    import time

    import uvicorn

    puerto = PUERTO + 3
    settings = Settings(data_dir=tmp_path / "datos", host="127.0.0.1", open_browser=False, jobs_inline=True)
    app = create_app(settings)
    app.state.port = puerto
    app.state.shutdown_token = "tok-real"
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="error", use_colors=False))
    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()
    try:
        for _ in range(100):
            if servidor.started:
                break
            time.sleep(0.1)
        assert servidor.started

        async def _con(token: str) -> object:
            LockFile(tmp_path / "bloqueo").path.unlink(missing_ok=True)
            LockFile(tmp_path / "bloqueo").acquire(puerto, token=token)
            c = VigiaClient(data_dir=tmp_path / "bloqueo")
            try:
                return await c.get("/health")
            finally:
                await c.aclose()

        assert asyncio.run(_con("tok-real"))["status"] == "ok"
        with pytest.raises(VigiaError, match="no es este Vigía"):
            asyncio.run(_con("otro-token"))
    finally:
        servidor.should_exit = True
        hilo.join(10)
