"""Fixtures de los tests de la API: carpeta de datos temporal, app con lifespan y sesión."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from vigia.app.main import create_app
from vigia.app.settings import Settings


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Carpeta de datos aislada: ningún test escribe fuera de `tmp_path`."""
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    """Ajustes de prueba: colas en línea y latido de SSE corto."""
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
    """App sin arrancar: el lifespan lo corre el fixture `client`."""
    application = create_app(settings)
    application.state.port = 8765
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Cliente de pruebas como contexto, para que corra el lifespan (BD, colas, eventos)."""
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


@pytest.fixture
def session(client: TestClient) -> Iterator[Session]:
    """Sesión de base de datos sobre el mismo motor que usa la app."""
    with Session(client.app.state.engine) as s:
        yield s


def actor_headers(
    actor: str = "miguel",
    *,
    kind: str = "humano",
    role: str | None = None,
    correlation: str | None = None,
    token: str | None = None,
) -> dict[str, str]:
    """Cabeceras `X-Vigia-*` de una petición con actor nominal."""
    cabeceras = {"X-Vigia-Actor": actor, "X-Vigia-Actor-Kind": kind}
    if role:
        cabeceras["X-Vigia-Role"] = role
    if correlation:
        cabeceras["X-Vigia-Correlation"] = correlation
    if token:
        cabeceras["X-Vigia-Token"] = token
    return cabeceras
