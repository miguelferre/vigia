"""Fixtures de los tests del servidor MCP: app con lifespan, `VigiaClient`
inyectado sobre `ASGITransport` (sin socket) y una sesión MCP en memoria."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from mcp.shared.memory import create_connected_server_and_client_session

from vigia.app.main import create_app
from vigia.app.settings import Settings
from vigia.mcp.client import VigiaClient, set_client
from vigia.mcp.server import mcp


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        data_dir=data_dir,
        host="127.0.0.1",
        port_start=8765,
        open_browser=False,
        jobs_inline=True,
        sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8765
    application.state.shutdown_token = "test-token"
    return application


@pytest_asyncio.fixture
async def cliente_http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP real sin socket: el lifespan de la app corre dentro de este contexto."""
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def cliente_vigia(cliente_http: httpx.AsyncClient) -> AsyncIterator[VigiaClient]:
    """`VigiaClient` con el `http` ya inyectado y `bootstrap()` hecho; se fija
    como cliente activo de las tools con `set_client`."""
    client = VigiaClient(url="http://vigia", actor="claude-code-tests", http=cliente_http)
    client._base_url = "http://vigia"
    await client.bootstrap()
    set_client(client)
    yield client


@pytest.fixture
def sesion_mcp(cliente_vigia: VigiaClient):
    """El gestor de contexto de la sesión MCP en memoria (`FastMCP` real, sin
    proceso ni stdio), SIN entrar: cada test hace `async with sesion_mcp as cs:`
    él mismo, para que apertura y cierre corran en la misma tarea de asyncio
    (un `TaskGroup` de anyio no admite que su `__aenter__`/`__aexit__` los
    ejecuten corrutinas distintas, y `pytest-asyncio` ejecuta el `setup` y el
    `teardown` de un fixture generador como dos tareas separadas)."""
    return create_connected_server_and_client_session(mcp._mcp_server)


async def _llamar_tool(sesion, nombre: str, args: dict) -> tuple[bool, object]:
    """Llama una tool de la sesión MCP y devuelve `(is_error, resultado)`.

    `resultado` es `structuredContent` si la sesión lo trae, si no el JSON
    (o texto) del primer bloque de contenido.
    """
    resultado = await sesion.call_tool(nombre, args)
    if getattr(resultado, "structuredContent", None) is not None:
        return resultado.isError, resultado.structuredContent
    if not resultado.content:
        return resultado.isError, None
    texto = resultado.content[0].text
    try:
        return resultado.isError, json.loads(texto)
    except (ValueError, TypeError):
        return resultado.isError, texto


@pytest.fixture
def llamar_tool():
    """Fixture-función: `await llamar_tool(sesion, nombre, args)` (sin import
    entre ficheros de test, `tests/mcp` no es un paquete, D-... ver `test_client.py`)."""
    return _llamar_tool


async def _post(http: httpx.AsyncClient, path: str, **kw) -> httpx.Response:
    headers = {"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"}
    return await http.post(f"/api{path}", headers=headers, **kw)


@pytest_asyncio.fixture
async def proyecto_demo(cliente_http: httpx.AsyncClient) -> dict:
    """Reproduce `timeline_completo` con capa humana por HTTP; devuelve ids reales."""
    creada = await _post(
        cliente_http, "/demo/runs", json={"scenario_key": "timeline_completo", "with_human": True}
    )
    assert creada.status_code == 200, creada.text
    run = creada.json()
    reproducida = await _post(cliente_http, f"/demo/runs/{run['id']}/play", json={})
    assert reproducida.status_code == 200, reproducida.text

    project_id = run["project_id"]
    proyecto = await cliente_http.get(f"/api/projects/{project_id}")
    version_id = proyecto.json()["active_version_id"]
    batches = await cliente_http.get(f"/api/projects/{project_id}/batches")
    alertas = await cliente_http.get(f"/api/projects/{project_id}/alerts")
    alerta = alertas.json()["items"][0] if alertas.json()["items"] else None

    return {
        "run_id": run["id"],
        "project_id": project_id,
        "version_id": version_id,
        "batches": batches.json().get("items", []) if batches.status_code == 200 else [],
        "alert_id": alerta["id"] if alerta else None,
    }
