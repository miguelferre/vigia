"""Tests de `vigia mcp`: reenvío de flags a
`vigia.mcp.server.main`, sin arrancar stdio de verdad."""

from __future__ import annotations

import sys
import types

from vigia.cli import main


def _instalar_mcp_falso(monkeypatch, devuelve: int = 0):
    capturado: dict[str, list[str]] = {}

    def falso_main(argv: list[str]) -> int:
        capturado["argv"] = argv
        return devuelve

    modulo = types.SimpleNamespace(main=falso_main)
    monkeypatch.setitem(sys.modules, "vigia.mcp.server", modulo)
    return capturado


def test_mcp_reenvia_data_dir_y_actor_sin_url(monkeypatch):
    capturado = _instalar_mcp_falso(monkeypatch)

    codigo = main(["mcp", "--data-dir", "x", "--actor", "claude-desktop"])

    assert codigo == 0
    assert capturado["argv"] == ["--data-dir", "x", "--actor", "claude-desktop"]


def test_mcp_reenvia_url_y_actor_por_defecto(monkeypatch):
    capturado = _instalar_mcp_falso(monkeypatch)

    codigo = main(["mcp", "--url", "http://127.0.0.1:1"])

    assert codigo == 0
    assert capturado["argv"] == ["--url", "http://127.0.0.1:1", "--actor", "claude-code"]


def test_mcp_devuelve_el_codigo_de_mcp_main(monkeypatch):
    _instalar_mcp_falso(monkeypatch, devuelve=7)

    codigo = main(["mcp"])

    assert codigo == 7


def test_mcp_sin_paquete_instalado_falla_claro(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "vigia.mcp", None)
    monkeypatch.setitem(sys.modules, "vigia.mcp.server", None)

    codigo = main(["mcp"])

    assert codigo == 2
    assert "no está instalado" in capsys.readouterr().err
