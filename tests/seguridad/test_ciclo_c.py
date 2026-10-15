"""Ciclo de vida: ficheros que sobreviven al borrado y al reinicio de un proyecto.
"""

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
from vigia.app.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=d,
        host="127.0.0.1",
        port_start=8982,
        open_browser=False,
        jobs_inline=True,
        sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8982
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _ficheros(carpeta: Path) -> list[Path]:
    return [p for p in carpeta.rglob("*") if p.is_file()] if carpeta.exists() else []


def _borrar(client: TestClient, project_id: int) -> None:
    resp = client.delete(
        f"/api/projects/{project_id}", params={"confirm": "true"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 204, resp.text


def _reiniciar(client: TestClient, project_id: int) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/reset",
        json={"actor": "miguel", "motivo": "limpieza de pruebas", "confirm": True},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text


def _proyecto_con_demo(client: TestClient, settings: Settings) -> tuple[int, Path]:
    resp = client.post(
        "/api/demo/runs",
        json={"scenario_key": "timeline_completo", "source": "canned", "with_human": False},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    resp = client.post(f"/api/demo/runs/{run['id']}/next", headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.json()
    carpeta = settings.data_dir / "demo" / str(run["id"])
    assert _ficheros(carpeta), "la fase de demo debía dejar sus JSON en disco"
    return run["project_id"], carpeta


def test_borrar_proyecto_retira_sus_artefactos_de_modelo(client: TestClient, settings: Settings):
    """Borrar el proyecto retira el fichero del
    modelo subido a una de sus versiones."""
    proyecto, version_id, _ = _preparar_proyecto_con_baseline(client, "ciclo-artefacto-borrado")
    resp = _subir_artefacto(client, version_id, contenido=_onnx_bytes(_entrenar_pipeline()))
    assert resp.status_code == 200, resp.text
    carpeta = settings.data_dir / "artifacts"
    assert _ficheros(carpeta), "la subida debía dejar el modelo en disco"
    _borrar(client, proyecto["id"])
    assert _ficheros(carpeta) == []


def test_sustituir_el_artefacto_retira_el_anterior(client: TestClient, settings: Settings):
    """Al subir otro modelo con distinto nombre a
    la misma versión, el fichero anterior no queda sin referencia."""
    _, version_id, _ = _preparar_proyecto_con_baseline(client, "ciclo-artefacto-sustituido")
    onnx = _onnx_bytes(_entrenar_pipeline())
    primero = _subir_artefacto(client, version_id, contenido=onnx, filename="primero.onnx")
    assert primero.status_code == 200, primero.text
    segundo = _subir_artefacto(client, version_id, contenido=onnx, filename="segundo.onnx")
    assert segundo.status_code == 200, segundo.text
    assert len(_ficheros(settings.data_dir / "artifacts")) == 1


def test_subida_rechazada_no_deja_fichero(client: TestClient, settings: Settings):
    """Una subida de datos que la validación
    rechaza no deja su fichero en la carpeta de subidas."""
    resp = client.post(
        "/api/projects",
        json={"name": "ciclo-subida-rechazada", "domain": "reuma"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    pid = resp.json()["id"]
    ok = client.post(
        f"/api/projects/{pid}/datasets/upload",
        files={"file": ("ok.csv", b"id,prediction,label\n1,1,1\n2,0,0\n", "text/csv")},
        data={"kind": "combined", "role": "production"},
        headers=actor_headers("miguel"),
    )
    assert ok.status_code == 200, ok.text
    antes = len(_ficheros(settings.data_dir / "uploads"))
    assert antes == 1
    malo = client.post(
        f"/api/projects/{pid}/datasets/upload",
        files={"file": ("roto.csv", b"\x00\x01\x02 no es un csv \xff\xfe\n", "text/csv")},
        data={"kind": "combined", "role": "production"},
        headers=actor_headers("miguel"),
    )
    assert malo.status_code not in (404, 405), malo.text
    assert 400 <= malo.status_code < 500, malo.text
    assert len(_ficheros(settings.data_dir / "uploads")) == antes


def test_borrar_proyecto_retira_la_carpeta_de_demo(client: TestClient, settings: Settings):
    """Borrar el proyecto retira los JSON de su demo."""
    pid, carpeta = _proyecto_con_demo(client, settings)
    _borrar(client, pid)
    assert _ficheros(carpeta) == []


def test_reiniciar_proyecto_retira_la_carpeta_de_demo(client: TestClient, settings: Settings):
    """Reiniciar el proyecto retira los JSON de su demo."""
    pid, carpeta = _proyecto_con_demo(client, settings)
    _reiniciar(client, pid)
    assert _ficheros(carpeta) == []
