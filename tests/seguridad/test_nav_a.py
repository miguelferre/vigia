"""Area nav (parte a): la API local rechaza un Host que no es local.

Huella: vigia.api.no-host-validation-dns-rebinding.
Control esperado: una peticion con Host ajeno recibe un 4xx de rechazo y no
llega al handler; con Host local la misma peticion funciona.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vigia.app.main import create_app
from vigia.app.settings import Settings

HUELLAS = {
    "test_host_ajeno_no_revela_el_token_no_host_validation": "vigia.api.no-host-validation-dns-rebinding",
    "test_host_ajeno_no_crea_estado_no_host_validation": "vigia.api.no-host-validation-dns-rebinding",
    "test_host_local_sigue_aceptado_no_host_validation": "vigia.api.no-host-validation-dns-rebinding",
}

HOST_AJENO = "evil.example:8765"
RECHAZOS = {400, 403, 421}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=d,
        host="127.0.0.1",
        port_start=8960,
        open_browser=False,
        jobs_inline=True,
        sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8960
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8960") as c:
        yield c


def test_host_ajeno_no_revela_el_token_no_host_validation(client: TestClient):
    """Host ajeno: GET /api/settings?reveal=true se rechaza y no devuelve el token."""
    ok = client.get("/api/settings", params={"reveal": "true"})
    assert ok.status_code == 200, ok.text
    token = ok.json()["mcp_token"]
    assert token

    resp = client.get(
        "/api/settings",
        params={"reveal": "true"},
        headers={"Host": HOST_AJENO, "Origin": f"http://{HOST_AJENO}"},
    )
    assert resp.status_code in RECHAZOS, (resp.status_code, resp.text[:200])
    assert token not in resp.text


def test_host_ajeno_no_crea_estado_no_host_validation(client: TestClient):
    """Host ajeno: un POST JSON a /api/projects se rechaza y no crea el proyecto."""
    cuerpo = {"name": "proyecto-host-ajeno", "domain": "libre"}
    resp = client.post(
        "/api/projects",
        json=cuerpo,
        headers={"Host": HOST_AJENO, "Origin": f"http://{HOST_AJENO}"},
    )
    assert resp.status_code in RECHAZOS, (resp.status_code, resp.text[:200])

    listado = client.get("/api/projects")
    assert listado.status_code == 200, listado.text
    assert "proyecto-host-ajeno" not in listado.text


@pytest.mark.parametrize("host", ["127.0.0.1:8960", "localhost:8960"])
def test_host_local_sigue_aceptado_no_host_validation(client: TestClient, host: str):
    """Control positivo: con Host local el POST JSON funciona."""
    resp = client.post(
        "/api/projects",
        json={"name": f"proyecto-{host[:3]}", "domain": "libre"},
        headers={"Host": host},
    )
    assert resp.status_code == 200, (resp.status_code, resp.text[:200])
