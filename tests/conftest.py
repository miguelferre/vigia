"""Fixtures comunes: data_dir temporal y app FastAPI de pruebas."""

from __future__ import annotations

from pathlib import Path

import pytest

from vigia.app.main import create_app
from vigia.app.settings import Settings


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def app(data_dir: Path):
    settings = Settings(data_dir=data_dir, host="127.0.0.1", port_start=8765)
    application = create_app(settings)
    application.state.port = 8765
    application.state.shutdown_token = "test-token"
    return application
