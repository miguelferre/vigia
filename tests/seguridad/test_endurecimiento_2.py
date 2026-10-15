"""Endurecimiento del MCP y de la revisión con modelo."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session

from vigia.app.main import create_app
from vigia.app.settings import Settings
from vigia.human import llm_env
from vigia.mcp.server import mcp

ACTOR = {"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    datos = tmp_path / "vigia-datos"
    datos.mkdir()
    ajustes = Settings(
        data_dir=datos, host="127.0.0.1", port_start=8765, open_browser=False,
        jobs_inline=True, sse_heartbeat_s=0.2,
    )
    app = create_app(ajustes)
    app.state.port = 8765
    app.state.shutdown_token = "test-token"
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _patch_llm(client: TestClient, llm: dict):
    cuerpo = {"actor": "miguel", "motivo": "prueba", "values": {"llm": llm}}
    return client.patch("/api/settings", json=cuerpo, headers=ACTOR)


def test_entorno_del_sdk_limpio_dentro_y_restaurado_fuera(monkeypatch):
    """La URL base y el token del SDK heredados no existen dentro del trabajo."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://otro.example")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "T-heredado")
    with llm_env.llm_environment(backend="anthropic", model="m", base_url="", api_key="K"):
        assert "ANTHROPIC_BASE_URL" not in os.environ
        assert "ANTHROPIC_AUTH_TOKEN" not in os.environ
    assert os.environ["ANTHROPIC_BASE_URL"] == "http://otro.example"
    assert os.environ["ANTHROPIC_AUTH_TOKEN"] == "T-heredado"


def test_campo_url_base_solo_con_ollama():
    """El campo «URL base» solo se dibuja con ollama y no nombra Anthropic."""
    raiz = Path(__file__).resolve().parents[2]
    fuente = (raiz / "frontend/src/pages/ajustes/ajustes-llm.tsx").read_text(encoding="utf-8")
    assert "https://api.anthropic.com" not in fuente
    antes, _, resto = fuente.partition('htmlFor="llm-base-url"')
    assert resto, "falta el campo URL base"
    assert 'borrador.backend === "ollama" ? (' in antes[-200:]


def test_base_url_no_se_arrastra_al_cambiar_de_backend(client: TestClient):
    """Al cambiar de backend, la URL base previa se borra."""
    ok = _patch_llm(client, {"backend": "ollama", "base_url": "http://localhost:11434"})
    assert ok.status_code == 200, ok.text
    cambio = _patch_llm(
        client,
        {"backend": "anthropic", "api_key": "sk-prueba", "confirmacion_no_local": "sin datos de personas"},
    )
    assert cambio.status_code == 200, cambio.text
    assert client.get("/api/settings").json()["llm"]["base_url"] == ""


def test_docstring_de_get_settings_no_promete_la_clave_llm():
    """La docstring no dice que `reveal=true` entregue la clave LLM."""
    herramienta = mcp._tool_manager.get_tool("get_settings")
    doc = " ".join(herramienta.description.split())
    assert "clave LLM va siempre oculta" in doc
    assert "token y clave LLM ocultos salvo" not in doc


@pytest.mark.parametrize("malo", ["abc", "-1", "1.5", "1%2f..", "1e3"])
async def test_state_project_valida_el_id(malo: str):
    """Un id de proyecto que no es un entero se rechaza antes de llamar a la API."""
    async with create_connected_server_and_client_session(mcp._mcp_server) as sesion:
        with pytest.raises(Exception) as exc:
            await sesion.read_resource(f"state://project/{malo}")
    assert "no válido" in str(exc.value)


def test_ollama_remoto_confirmado_se_acepta_y_deja_evento(client: TestClient):
    """Con `confirmar_remoto` una URL de otro equipo se guarda y queda un evento."""
    remota = "http://ollama.interna.example:11434"
    sin = _patch_llm(client, {"backend": "ollama", "base_url": remota})
    assert sin.status_code == 422
    con = _patch_llm(client, {"backend": "ollama", "base_url": remota, "confirmar_remoto": True})
    assert con.status_code == 200, con.text
    assert client.get("/api/settings").json()["llm"]["base_url"] == remota
    for url in ("http://127.0.0.1.example:11434", "http://localhost@evil.example", "ftp://127.0.0.1"):
        assert _patch_llm(client, {"backend": "ollama", "base_url": url}).status_code == 422, url


def test_comprobar_ruta_de_subida():
    """Una ruta de red o de dispositivo se rechaza antes de abrir."""
    from vigia.mcp.rutas import comprobar_ruta_de_subida

    for ruta in (r"\\servidor\r\f.csv", "//servidor/r/f.csv", r"\\?\C:\f.csv", r"\\.\PhysicalDrive0"):
        with pytest.raises(ValueError, match="red o de dispositivo"):
            comprobar_ruta_de_subida(ruta)
    comprobar_ruta_de_subida("no-existe.csv")  # lo informa la tool al abrir
