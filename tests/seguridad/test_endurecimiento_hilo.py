"""Endurecimiento de la app: cabeceras, documentación de la API y frontera local.

Cabeceras de seguridad en toda respuesta.
Sin /docs ni /redoc, que cargan scripts de un CDN.
Un cuerpo JSON con `Content-Type: text/plain` se rechaza.
La frontera de Host y Origin la prueban `test_nav_a.py` y `test_nav_b.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vigia.app.main import create_app
from vigia.app.seguridad_http import motivo_de_rechazo, nombre_de_host
from vigia.app.settings import Settings

HUELLAS = {
    "test_cabeceras_de_seguridad_en_la_api": "security-headers",
    "test_cabeceras_tambien_en_el_rechazo": "security-headers-on-rejection",
    "test_sin_docs_ni_redoc": "docs-and-redoc-cdn",
    "test_json_con_text_plain_se_rechaza": "json-body-with-text-plain",
    "test_clientes_sin_navegador_pasan": "vigia.api.csrf-multipart-no-origin-check",
    "test_nombre_de_host": "vigia.api.no-host-validation-dns-rebinding",
}


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=d, port_start=8765, open_browser=False, jobs_inline=True)
    application = create_app(settings)
    application.state.port = 8765
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def test_cabeceras_de_seguridad_en_la_api(client: TestClient):
    """Toda respuesta lleva nosniff, marco solo del mismo origen y sin referer."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "SAMEORIGIN"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'self'" in resp.headers["content-security-policy"]


def test_cabeceras_tambien_en_el_rechazo(client: TestClient):
    """El 403 de la frontera también lleva las cabeceras."""
    resp = client.get("/api/health", headers={"Host": "evil.example"})
    assert resp.status_code == 403
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_sin_docs_ni_redoc(client: TestClient):
    """/docs y /redoc no sirven la página de Swagger; /openapi.json sigue."""
    for ruta in ("/docs", "/redoc"):
        resp = client.get(ruta)
        assert "swagger" not in resp.text.lower() and "redoc" not in resp.text.lower()
    assert client.get("/openapi.json").status_code == 200


def test_json_con_text_plain_se_rechaza(client: TestClient):
    """Un POST JSON con Content-Type text/plain no crea nada."""
    resp = client.post(
        "/api/projects",
        content=b'{"name": "texto-plano", "domain": "libre"}',
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status_code in {415, 422}
    nombres = [p["name"] for p in client.get("/api/projects").json()["items"]]
    assert "texto-plano" not in nombres


def test_clientes_sin_navegador_pasan():
    """Sin Origin ni Sec-Fetch-Site (CLI, MCP), una petición que escribe pasa."""
    scope = {"type": "http", "method": "POST", "headers": [(b"host", b"127.0.0.1:8765")]}
    assert motivo_de_rechazo(scope) is None
    scope["headers"].append((b"sec-fetch-site", b"cross-site"))
    assert motivo_de_rechazo(scope) is not None
    scope["headers"][-1] = (b"origin", b"null")
    assert motivo_de_rechazo(scope) is not None


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("127.0.0.1:8765", "127.0.0.1"),
        ("LOCALHOST", "localhost"),
        ("http://localhost:5173", "localhost"),
        ("evil.example:8765", "evil.example"),
        ("127.0.0.1.evil.example", "127.0.0.1.evil.example"),
        ("[::1]:8765", "::1"),
    ],
)
def test_nombre_de_host(valor: str, esperado: str):
    """El nombre del host se compara sin puerto y en minúsculas."""
    assert nombre_de_host(valor) == esperado
