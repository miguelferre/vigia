"""Arreglos del MCP en multiclase: espera de la propuesta y valor favorable."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from vigia.mcp.client import VigiaClient, set_client
from vigia.mcp.server import mcp


@pytest.fixture
def espera_vista():
    """`VigiaClient` sobre un transporte simulado que anota el tiempo de espera que
    recibe cada petición. Sin el arreglo, la propuesta usa el de httpx (5 s)."""
    vistos: dict[str, dict] = {}

    def atender(peticion: httpx.Request) -> httpx.Response:
        if peticion.url.path == "/api/settings":
            return httpx.Response(200, json={"mcp_token": "t"})
        vistos[peticion.url.path] = dict(peticion.extensions["timeout"])
        return httpx.Response(200, json={"monitors": []})

    http = httpx.AsyncClient(transport=httpx.MockTransport(atender), base_url="http://vigia")
    cliente = VigiaClient(url="http://vigia", actor="claude-code-tests", http=http)
    cliente._base_url = "http://vigia"
    set_client(cliente)
    return vistos


async def test_get_threshold_proposal_espera_60_s_y_las_demas_lecturas_no(espera_vista):
    """La propuesta multiclase tarda unos 7 s y el cliente esperaba 5 s (504)."""
    async with create_connected_server_and_client_session(mcp._mcp_server) as sesion:
        propuesta = await sesion.call_tool("get_threshold_proposal", {"project_id": 7})
        assert not propuesta.isError, propuesta
        lectura = await sesion.call_tool("get_alerts", {"project_id": 7})
        assert not lectura.isError, lectura

    espera = espera_vista["/api/projects/7/thresholds/proposal"]
    assert espera["read"] == 60.0
    # El tiempo global no cambia: cualquier otra lectura sigue con el de httpx.
    otras = [t for ruta, t in espera_vista.items() if "proposal" not in ruta]
    assert otras and all(t["read"] == 5.0 for t in otras), espera_vista


# --- upload_usage_log con valor_favorable opcional ---------------------------

USAGE_CSV = Path(__file__).resolve().parents[2] / "data" / "demo" / "usage_logs_demo.csv"
HUMANO = {"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"}


async def _proyecto(cliente_http, nombre: str, **extra) -> dict:
    resp = await cliente_http.post("/api/projects", json={"name": nombre, "domain": "libre", **extra}, headers=HUMANO)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_binario_sin_valor_favorable_da_un_error_que_lo_pide(sesion_mcp, llamar_tool, cliente_http):
    proyecto = await _proyecto(cliente_http, "uso-bin-sin-favorable")
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(
            sesion, "upload_usage_log", {"project_id": proyecto["id"], "file_path": str(USAGE_CSV)}
        )
    assert error
    assert "valor_favorable es obligatorio en un modelo binario" in str(texto)
    assert "refer" in str(texto) and "no-refer" in str(texto)


async def test_multiclase_sin_valor_favorable_sube_el_fichero(sesion_mcp, llamar_tool, cliente_http):
    """Sin el parámetro la tool pasa el fichero a la API (que aquí lo rechaza por sus
    celdas `refer`/`no-refer`, en español), no se queja de que falte `valor_favorable`."""
    proyecto = await _proyecto(
        cliente_http, "uso-multi-sin-favorable", task_type="multiclass", classes=["spam", "phishing", "legitimo"]
    )
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(
            sesion, "upload_usage_log", {"project_id": proyecto["id"], "file_path": str(USAGE_CSV)}
        )
    assert error
    assert "valor_favorable" not in str(texto)
    assert "422" in str(texto) and "clase" in str(texto).lower()


@pytest.mark.parametrize("valor", ["refer", "1", "no-refer", "spam"])
async def test_multiclase_con_valor_favorable_pide_quitarlo(sesion_mcp, llamar_tool, cliente_http, valor):
    proyecto = await _proyecto(
        cliente_http, f"uso-multi-favorable-{valor}", task_type="multiclass", classes=["spam", "phishing", "legitimo"]
    )
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(
            sesion,
            "upload_usage_log",
            {"project_id": proyecto["id"], "file_path": str(USAGE_CSV), "valor_favorable": valor},
        )
    assert error
    assert "no se usa valor_favorable" in str(texto)
    assert "nombres de clase" in str(texto) and "Quita el parámetro" in str(texto)


async def test_siguen_siendo_39_tools_y_el_parametro_es_opcional(sesion_mcp):
    async with sesion_mcp as sesion:
        tools = (await sesion.list_tools()).tools
    assert len(tools) == 39
    esquema = next(t for t in tools if t.name == "upload_usage_log").inputSchema
    assert "valor_favorable" not in esquema.get("required", [])
    assert "NO se usa" in next(t for t in tools if t.name == "upload_usage_log").description
