"""Ciclo de vida del proyecto: ficheros que se retiran al borrar y reiniciar."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from tests.api.test_model_artifacts import (
    _entrenar_pipeline,
    _onnx_bytes,
    _preparar_proyecto_con_baseline,
    _subir_artefacto,
)
from vigia.app.main import create_app
from vigia.app.services.projects import _carpeta_de
from vigia.app.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=d,
        host="127.0.0.1",
        port_start=8985,
        open_browser=False,
        jobs_inline=True,
        sse_heartbeat_s=0.2,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app: FastAPI = create_app(settings)
    app.state.port = 8985
    app.state.shutdown_token = "test-token"
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _ficheros(carpeta: Path) -> list[Path]:
    return [p for p in carpeta.rglob("*") if p.is_file()] if carpeta.exists() else []


def test_borrar_proyecto_deja_intactos_los_ficheros_de_otro(client: TestClient, settings: Settings):
    """Borrar un proyecto solo retira sus carpetas, no las de otro proyecto."""
    uno, version_uno, _ = _preparar_proyecto_con_baseline(client, "fin-6-uno")
    dos, version_dos, _ = _preparar_proyecto_con_baseline(client, "fin-6-dos")
    onnx = _onnx_bytes(_entrenar_pipeline())
    assert _subir_artefacto(client, version_uno, contenido=onnx).status_code == 200
    assert _subir_artefacto(client, version_dos, contenido=onnx).status_code == 200
    resp = client.delete(
        f"/api/projects/{uno['id']}", params={"confirm": "true"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 204, resp.text
    assert _ficheros(settings.data_dir / "artifacts" / str(uno["id"])) == []
    assert _ficheros(settings.data_dir / "artifacts" / str(dos["id"]))


def test_reiniciar_proyecto_conserva_los_artefactos_de_sus_versiones(
    client: TestClient, settings: Settings
):
    """Reiniciar conserva las versiones y, con ellas, el modelo subido."""
    proyecto, version_id, _ = _preparar_proyecto_con_baseline(client, "fin-6-reinicio")
    onnx = _onnx_bytes(_entrenar_pipeline())
    assert _subir_artefacto(client, version_id, contenido=onnx).status_code == 200
    resp = client.post(
        f"/api/projects/{proyecto['id']}/reset",
        json={"actor": "miguel", "motivo": "limpieza de pruebas", "confirm": True},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert _ficheros(settings.data_dir / "artifacts" / str(proyecto["id"]))
    assert _ficheros(settings.data_dir / "uploads" / str(proyecto["id"])) == []


def test_las_carpetas_de_limpieza_no_salen_de_la_carpeta_de_datos(tmp_path: Path):
    """El resolvedor de carpetas rechaza lo que se salga de `data_dir`."""
    assert _carpeta_de(tmp_path, "uploads", 3).parent.parent == tmp_path.resolve()
    with pytest.raises(ValueError):
        _carpeta_de(tmp_path, "..", "fuera")
