"""Endurecimiento de paginación y deduplicación de evaluaciones.

Un test por control de paginación y por la llamada de deduplicación.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.test_alerts import _crear_proyecto
from vigia.app.main import create_app
from vigia.app.settings import Settings


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    datos = tmp_path / "vigia-datos"
    datos.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        data_dir=datos, host="127.0.0.1", port_start=8980, open_browser=False,
        jobs_inline=True, sse_heartbeat_s=0.2,
    )
    application = create_app(settings)
    application.state.port = 8980
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _rutas(pid: int) -> list[str]:
    return [
        f"/api/projects/{pid}/alerts",
        f"/api/projects/{pid}/risks",
        f"/api/projects/{pid}/evaluations",
        f"/api/projects/{pid}/monitors",
        "/api/model-versions/1/explanations",
        "/api/demo/runs",
    ]


@pytest.mark.parametrize("limite", [-1, 0], ids=["negativo", "cero"])
def test_limite_no_positivo_da_422(client: TestClient, limite: int):
    """`limit` menor que 1 se rechaza en todas las listas paginadas."""
    pid = _crear_proyecto(client, name="paginacion")["id"]
    for ruta in _rutas(pid):
        resp = client.get(ruta, params={"limit": limite})
        assert resp.status_code == 422, f"{ruta} con limit={limite}: {resp.status_code}"


def test_limite_valido_sigue_funcionando(client: TestClient):
    """Control positivo, `limit=1` sigue sirviendo la página."""
    pid = _crear_proyecto(client, name="paginacion-ok")["id"]
    for ruta in _rutas(pid):
        if "model-versions" in ruta:
            continue  # la versión de ejemplo no existe: solo importa el rechazo de arriba
        resp = client.get(ruta, params={"limit": 1})
        assert resp.status_code == 200, f"{ruta}: {resp.status_code} {resp.text}"


def test_evaluar_lote_pide_clave_de_deduplicacion(client: TestClient, monkeypatch):
    """Evaluar el mismo lote dos veces seguidas comparte clave de deduplicación (carril 4)."""
    from tests.api.test_alerts import _ingerir, _subir_y_mapear

    pid = _crear_proyecto(client, name="dedup")["id"]
    base = _subir_y_mapear(client, pid, "01_baseline_feedback.json", role="baseline")
    batch_id = _ingerir(client, base["id"])["batch_id"]
    jobs = client.app.state.jobs
    original = jobs.enqueue
    claves: list[str | None] = []

    def _espia(*args, **kwargs):
        claves.append(kwargs.get("clave_dedup"))
        return original(*args, **kwargs)

    monkeypatch.setattr(jobs, "enqueue", _espia)
    resp = client.post(f"/api/batches/{batch_id}/evaluate", json={})
    assert resp.status_code == 200, resp.text
    assert claves == [f"evaluacion:lote:{batch_id}"]
