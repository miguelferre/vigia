"""Localización de la API (`VigiaClient.discover()`)."""

from __future__ import annotations

import json
import os

import pytest

from vigia.mcp import server as mcp_server
from vigia.mcp.client import MENSAJE_SIN_ARRANQUE, VigiaClient


def test_url_explicita_gana_al_lock(tmp_path):
    (tmp_path / "vigia.lock").write_text(json.dumps({"pid": os.getpid(), "port": 9999}))
    client = VigiaClient(url="http://127.0.0.1:8123", data_dir=tmp_path)
    assert client.discover() == "http://127.0.0.1:8123"


def test_lock_valido(tmp_path):
    (tmp_path / "vigia.lock").write_text(json.dumps({"pid": os.getpid(), "port": 8841}))
    client = VigiaClient(data_dir=tmp_path)
    assert client.discover() == "http://127.0.0.1:8841"


def test_lock_obsoleto_falla_con_mensaje_claro(tmp_path):
    # Un PID casi con toda seguridad muerto.
    (tmp_path / "vigia.lock").write_text(json.dumps({"pid": 999999, "port": 8841}))
    client = VigiaClient(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match=MENSAJE_SIN_ARRANQUE):
        client.discover()


def test_sin_lock_falla_con_mensaje_claro(tmp_path):
    client = VigiaClient(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match=MENSAJE_SIN_ARRANQUE):
        client.discover()


def test_el_arranque_no_abre_conexion_ni_pide_token(tmp_path, monkeypatch):
    """`main()` solo localiza la API; el cliente HTTP y el `mcp_token` esperan a
    la primera petición, dentro del bucle de eventos de `mcp.run()`.

    Pedirlos al arrancar, en un bucle propio (`anyio.run`), dejaba el pool de
    `httpx` atado a un bucle ya cerrado: la primera tool de cada sesión stdio
    fallaba con «Event loop is closed» (verificado contra un `vigia mcp` real).
    """
    (tmp_path / "vigia.lock").write_text(json.dumps({"pid": os.getpid(), "port": 8841}))
    corrido: list[bool] = []
    monkeypatch.setattr(mcp_server.mcp, "run", lambda: corrido.append(True))

    assert mcp_server.main(["--data-dir", str(tmp_path), "--actor", "claude-desktop"]) == 0
    assert corrido == [True]

    from vigia.mcp.client import get_client

    client = get_client()
    assert client.actor == "claude-desktop"
    assert client.http is None
    assert client._token is None


def test_sin_servidor_el_arranque_falla_con_uno_y_sin_run(tmp_path, monkeypatch, capsys):
    corrido: list[bool] = []
    monkeypatch.setattr(mcp_server.mcp, "run", lambda: corrido.append(True))

    assert mcp_server.main(["--data-dir", str(tmp_path)]) == 1
    assert corrido == []
    assert MENSAJE_SIN_ARRANQUE in capsys.readouterr().err
