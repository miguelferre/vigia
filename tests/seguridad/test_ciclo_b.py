"""Ciclo de vida: minimización con `store_features` desmarcado.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.app.main import create_app
from vigia.app.settings import Settings

VALOR_EXTRA = "valor-de-prueba-ciclo"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=d,
        host="127.0.0.1",
        port_start=8981,
        open_browser=False,
        jobs_inline=True,
        sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8981
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _ingerir_csv(client: TestClient, nombre: str, *, store_features: bool) -> tuple[dict, int]:
    """Alta de proyecto, subida de un CSV con una columna extra sin mapear, mapeo e ingesta."""
    resp = client.post(
        "/api/projects",
        json={"name": nombre, "domain": "reuma", "store_features": store_features},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    proyecto = resp.json()
    csv = (
        "id,prediction,label,Age,nombre_ficticio\n"
        f"1,1,1,30,{VALOR_EXTRA}\n"
        f"2,0,0,45,{VALOR_EXTRA}\n"
    ).encode()
    resp = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("datos.csv", csv, "text/csv")},
        data={"kind": "combined", "role": "production"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    dataset_id = resp.json()["dataset"]["id"]
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "feature_cols": ["Age"],
        "favorable_label": 1,
    }
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": mapping, "privacy_decisions": {}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"model_version_id": proyecto["active_version_id"], "evaluate": False},
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    return proyecto, job["result"]["batch_id"]


def test_privado_csv_no_guarda_columnas_no_mapeadas_sin_store_features(
    client: TestClient, settings: Settings
):
    """Con la casilla desmarcada, ningún
    fichero de subidas conserva el contenido de una columna que el mapeo no usa."""
    _ingerir_csv(client, "ciclo-privado-sin-features", store_features=False)
    ficheros = [p for p in (settings.data_dir / "uploads").rglob("*") if p.is_file()]
    contenidos = b"".join(p.read_bytes() for p in ficheros)
    assert VALOR_EXTRA.encode() not in contenidos


def test_desmarcar_store_features_retira_las_variables_ya_guardadas(client: TestClient):
    """El cambio posterior de la casilla
    no deja disponibles las variables de entrada que ya se guardaron."""
    proyecto, batch_id = _ingerir_csv(client, "ciclo-retroactivo", store_features=True)
    antes = client.get(f"/api/batches/{batch_id}/records", params={"with_features": "true"})
    assert antes.status_code == 200, antes.text
    assert antes.json()["items"][0]["features"] is not None
    resp = client.patch(
        f"/api/projects/{proyecto['id']}",
        json={"actor": "miguel", "motivo": "minimizar datos", "store_features": False},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["store_features"] is False
    despues = client.get(f"/api/batches/{batch_id}/records", params={"with_features": "true"})
    assert despues.status_code == 200, despues.text
    items = despues.json()["items"]
    assert items
    assert all(it["features"] is None for it in items)
