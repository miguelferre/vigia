"""Seguridad, área mcp_llm (parte c): prompts del MCP con texto durable de terceros."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest_asyncio
from mcp.shared.memory import create_connected_server_and_client_session

import vigia.mcp.client as cliente_mod
from vigia.app.main import create_app
from vigia.app.settings import Settings
from vigia.mcp.client import VigiaClient, set_client
from vigia.mcp.server import mcp

HUELLAS = {
    "test_informe_semanal_delimita_texto_de_terceros": "mcp.prompts.durable-text-in-user-message",
    "test_informe_semanal_tamano_acotado": "mcp.prompts.durable-text-in-user-message",
    "test_diagnostico_delimita_texto_de_terceros": "mcp.prompts.durable-text-in-user-message",
    "test_diagnostico_tamano_acotado": "mcp.prompts.durable-text-in-user-message",
}

MARCA = "PRUEBA_DELIMITACION texto de prueba"
LIMITE_PROMPT = 120_000
ACTOR = {"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"}
# Línea que delimita un bloque: valla, separador largo, marca BEGIN/END o etiqueta de datos.
VALLA = re.compile(
    r"^\s*(?:`{3,}|~{3,}|<{3,}|>{3,}|-{3,}|={3,}|\*{3,}|\[{2}.*\]{2}"
    r"|<\/?(?:datos|data|untrusted|no_fiable|contenido|diario|evento)[^>]*>"
    r"|.*\b(?:BEGIN|END|INICIO|FIN)\b[ _:-].*)\s*$",
    re.IGNORECASE,
)

def _texto(resultado) -> str:
    return "\n".join(m.content.text for m in resultado.messages if hasattr(m.content, "text"))


def _delimitado(texto: str, marca: str) -> bool:
    """La marca está entre una línea de valla anterior y otra posterior."""
    lineas = texto.splitlines()
    sitios = [i for i, linea in enumerate(lineas) if marca in linea]
    if not sitios:
        return True  # el texto ya no llega al prompt: tampoco hay nada que delimitar
    i = sitios[0]
    return any(VALLA.match(x) for x in lineas[:i]) and any(VALLA.match(x) for x in lineas[i + 1 :])


@pytest_asyncio.fixture
async def cliente_http(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    datos = tmp_path / "vigia-datos"
    datos.mkdir()
    ajustes = Settings(
        data_dir=datos, host="127.0.0.1", port_start=8765, open_browser=False,
        jobs_inline=True, sse_heartbeat_s=0.2,
    )
    app = create_app(ajustes)
    app.state.port = 8765
    app.state.shutdown_token = "test-token"
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
    ) as http:
        yield http


async def _sesion_real(cliente_http: httpx.AsyncClient):
    cliente = VigiaClient(url="http://vigia", actor="claude-code-tests", http=cliente_http)
    cliente._base_url = "http://vigia"
    await cliente.bootstrap()
    set_client(cliente)
    return create_connected_server_and_client_session(mcp._mcp_server)


async def _proyecto_con_nota(cliente_http: httpx.AsyncClient, motivo: str) -> tuple[int, int]:
    creado = await cliente_http.post(
        "/api/projects", json={"name": "seg-prompts", "deployment_stage": "validacion"}, headers=ACTOR,
    )
    assert creado.status_code in (200, 201), creado.text
    pid = creado.json()["id"]
    nota = await cliente_http.post(
        "/api/events", json={"actor": "miguel", "motivo": motivo, "project_id": pid}, headers=ACTOR
    )
    return pid, nota.status_code


async def _informe(cliente_http, pid: int) -> str:
    sesion_cm = await _sesion_real(cliente_http)
    async with sesion_cm as sesion:
        resultado = await sesion.get_prompt(
            "informe_semanal", {"project_id": str(pid), "since": "2020-01-01", "until": "2099-01-01"}
        )
    return _texto(resultado)


async def test_informe_semanal_delimita_texto_de_terceros(cliente_http):
    """mcp.prompts.durable-text-in-user-message: el texto del diario va dentro de un bloque delimitado."""
    pid, estado = await _proyecto_con_nota(cliente_http, MARCA)
    assert estado == 200
    prompt = await _informe(cliente_http, pid)
    assert "## 1." in prompt  # el prompt se generó
    assert MARCA in prompt  # control: la nota llega al prompt
    assert _delimitado(prompt, MARCA), "la nota del diario aparece sin delimitar"


async def test_informe_semanal_tamano_acotado(cliente_http):
    """mcp.prompts.durable-text-in-user-message: el tamaño del prompt tiene tope (o la API rechaza el motivo enorme)."""
    pid, _ = await _proyecto_con_nota(cliente_http, "nota inicial")
    enorme = await cliente_http.post(
        "/api/events", json={"actor": "miguel", "motivo": "x" * 300_000, "project_id": pid}, headers=ACTOR
    )
    assert enorme.status_code not in (404, 405), enorme.text
    if enorme.status_code == 200:
        prompt = await _informe(cliente_http, pid)
        assert len(prompt) < LIMITE_PROMPT, f"prompt de {len(prompt)} caracteres sin tope"
    else:
        assert enorme.status_code in (413, 422)


class _ClienteFalso:
    """Devuelve una alerta con un título de paso del protocolo elegido por la prueba."""

    def __init__(self, titulo: str):
        self.titulo = titulo

    async def get(self, path: str, params=None):
        if path.startswith("/alerts/"):
            return {"metric_key": "m", "stage": "triaje",
                    "protocol_steps": [{"key": "p1", "titulo": self.titulo, "status": "pending"}]}
        return {}


async def _diagnostico(monkeypatch, titulo: str) -> str:
    monkeypatch.setattr(cliente_mod, "_client", _ClienteFalso(titulo))
    async with create_connected_server_and_client_session(mcp._mcp_server) as sesion:
        resultado = await sesion.get_prompt("diagnostico_de_alerta", {"alert_id": "1"})
    return _texto(resultado)


async def test_diagnostico_delimita_texto_de_terceros(monkeypatch):
    """mcp.prompts.durable-text-in-user-message: el título de un paso del protocolo va dentro de un bloque delimitado."""
    prompt = await _diagnostico(monkeypatch, MARCA)
    assert "Alerta #1" in prompt  # el prompt se generó
    assert MARCA in prompt
    assert _delimitado(prompt, MARCA), "el título del protocolo aparece sin delimitar"


async def test_diagnostico_tamano_acotado(monkeypatch):
    """mcp.prompts.durable-text-in-user-message: el texto de terceros en el prompt de diagnóstico tiene tope de tamaño."""
    prompt = await _diagnostico(monkeypatch, "y" * 300_000)
    assert "Alerta #1" in prompt
    assert len(prompt) < LIMITE_PROMPT, f"prompt de {len(prompt)} caracteres sin tope"
