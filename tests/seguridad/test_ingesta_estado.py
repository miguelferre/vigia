"""Ingesta y mapeo: estado del dataset y evaluación encadenada.

Cada test comprueba el control seguro de una huella; ver `HUELLAS`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.main import create_app
from vigia.app.models import Batch, Dataset, Evaluation
from vigia.app.services import alerting
from vigia.app.settings import Settings
from vigia.core.schema import DatosNoValidos

HUELLAS = {
    "test_un_dataset_ingerido_no_se_remapea": "ingest/completed-dataset-can-be-remapped-and-reingested",
    "test_un_dataset_ingerido_no_se_reingiere": "ingest/completed-dataset-can-be-remapped-and-reingested",
    "test_un_dataset_mapeado_o_en_error_conserva_su_camino": "ingest/completed-dataset-can-be-remapped-and-reingested",
    "test_si_la_evaluacion_encadenada_falla_no_queda_estado_parcial": "ingest/evaluation-failure-swallowed-with-partial-state-committed",
}

MAPEO = {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": 1}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        data_dir=d, host="127.0.0.1", port_start=8901, open_browser=False, jobs_inline=True,
        sse_heartbeat_s=0.2,
    )
    app: FastAPI = create_app(settings)
    app.state.port = 8901
    app.state.shutdown_token = "test-token"
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _csv(n: int = 60) -> bytes:
    filas = ["id,prediction,label"] + [f"E{i},{i % 2},{1 if i % 3 == 0 else 0}" for i in range(n)]
    return ("\n".join(filas) + "\n").encode()


def _proyecto_y_dataset(client: TestClient, nombre: str) -> tuple[dict, int]:
    r = client.post("/api/projects", json={"name": nombre, "domain": "reuma"},
                    headers=actor_headers("miguel"))
    assert r.status_code == 200, r.text
    proyecto = r.json()
    r = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("lote.csv", _csv(), "text/csv")},
        data={"kind": "combined", "role": "production"},
        headers=actor_headers("miguel"),
    )
    assert r.status_code == 200, r.text
    return proyecto, r.json()["dataset"]["id"]


def _mapear(client: TestClient, dataset_id: int):
    return client.put(f"/api/datasets/{dataset_id}/mapping", json={"mapping": MAPEO},
                      headers=actor_headers("miguel"))


def _ingerir(client: TestClient, dataset_id: int, version_id: int, evaluate: bool = False):
    return client.post(f"/api/datasets/{dataset_id}/ingest",
                       json={"model_version_id": version_id, "evaluate": evaluate})


def _lotes(client: TestClient, proyecto_id: int) -> list:
    with Session(client.app.state.engine) as s:
        return list(s.exec(select(Batch).where(Batch.project_id == proyecto_id)).all())


def test_un_dataset_ingerido_no_se_remapea(client: TestClient):
    """El mapeo de un dataset ya ingerido se rechaza con 409 en español."""
    proyecto, ds = _proyecto_y_dataset(client, "s1a-remapeo")
    assert _mapear(client, ds).status_code == 200
    assert _ingerir(client, ds, proyecto["active_version_id"]).json()["status"] == "terminado"
    resp = _mapear(client, ds)
    assert resp.status_code == 409, resp.text
    assert "ya está ingerido" in resp.json()["detail"]


def test_un_dataset_ingerido_no_se_reingiere(client: TestClient):
    """Pedir otra ingesta de un dataset ingerido da 409 y no crea un lote nuevo."""
    proyecto, ds = _proyecto_y_dataset(client, "s1a-reingesta")
    assert _mapear(client, ds).status_code == 200
    assert _ingerir(client, ds, proyecto["active_version_id"]).json()["status"] == "terminado"
    assert len(_lotes(client, proyecto["id"])) == 1
    resp = _ingerir(client, ds, proyecto["active_version_id"])
    assert resp.status_code == 409, resp.text
    assert "ya está ingerido" in resp.json()["detail"]
    assert len(_lotes(client, proyecto["id"])) == 1


def test_un_dataset_mapeado_o_en_error_conserva_su_camino(client: TestClient):
    """Un dataset `mapeado` se remapea y se ingiere; uno en `error` se remapea
    pero sigue sin ingerirse (hay que volver a subir el fichero)."""
    proyecto, ds = _proyecto_y_dataset(client, "s1a-camino")
    assert _mapear(client, ds).status_code == 200
    assert _mapear(client, ds).status_code == 200
    with Session(client.app.state.engine) as s:
        fila = s.get(Dataset, ds)
        fila.status = "error"
        s.add(fila)
        s.commit()
    resp = _ingerir(client, ds, proyecto["active_version_id"])
    assert resp.status_code == 409, resp.text
    assert "vuelve a subir" in resp.json()["detail"]
    assert _mapear(client, ds).status_code == 200


@pytest.mark.parametrize("fallo", [RuntimeError("fallo de prueba"), DatosNoValidos("datos de prueba")])
def test_si_la_evaluacion_encadenada_falla_no_queda_estado_parcial(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fallo: Exception
):
    """Si la evaluación encadenada falla, la ingesta se conserva, no queda ninguna
    evaluación a medias y la respuesta dice que no se evaluó."""
    proyecto, ds = _proyecto_y_dataset(client, "s1a-evaluacion")
    assert _mapear(client, ds).status_code == 200

    def _falla(*args, **kwargs):
        raise fallo

    monkeypatch.setattr(alerting, "sync_alerts", _falla)
    resp = _ingerir(client, ds, proyecto["active_version_id"], evaluate=True)
    assert resp.status_code == 200, resp.text
    resultado = resp.json()["result"]
    assert resultado["evaluated"] is False
    assert resultado["evaluate_revertida"] is True
    assert resultado["evaluate_motivo"]
    assert len(_lotes(client, proyecto["id"])) == 1
    with Session(client.app.state.engine) as s:
        assert s.exec(select(Evaluation).where(Evaluation.project_id == proyecto["id"])).all() == []
