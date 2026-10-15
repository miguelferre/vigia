"""Fixtures compartidas por los `test_r8_s1c_*.py`.

No contiene tests: la app de prueba con carpeta de datos temporal y el cliente
con `base_url` local.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from vigia.app.main import create_app
from vigia.app.settings import Settings

HUELLAS: dict[str, str] = {}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=d,
        host="127.0.0.1",
        port_start=8903,
        open_browser=False,
        jobs_inline=True,
        sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8903
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


@pytest.fixture
def session(client: TestClient) -> Iterator[Session]:
    with Session(client.app.state.engine) as s:
        yield s
