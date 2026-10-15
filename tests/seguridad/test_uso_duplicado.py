"""Un registro de uso ya ingerido no entra dos veces.

Una subida cuya huella sha256 coincide con la de un registro de uso ya ingerido en el
mismo proyecto da 409 con el nombre y la fecha de la primera subida, y no suma filas.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from tests.api import conftest as _api
from tests.api.conftest import actor_headers
from vigia.app.models import Dataset, UsageLog

# Fixtures de tests/api/conftest.py: app, client, data_dir y settings.
app, client, data_dir, settings = _api.app, _api.client, _api.data_dir, _api.settings

HUELLAS = {
    "test_misma_subida_dos_veces_da_409_y_no_suma_filas": "usage-log-duplicate-upload",
    "test_fichero_distinto_entra": "usage-log-duplicate-upload",
    "test_tras_reiniciar_el_proyecto_el_mismo_fichero_entra": "usage-log-duplicate-upload",
    "test_el_mismo_fichero_en_otro_proyecto_entra": "usage-log-duplicate-upload",
}

CABECERA = "date,human_decision,model_output,ground_truth\n"
CUERPO_A = CABECERA + "2026-01-05,refer,refer,refer\n2026-01-06,no-refer,refer,refer\n"
CUERPO_B = CABECERA + "2026-01-07,refer,refer,refer\n2026-01-08,no-refer,no-refer,refer\n"


def _proyecto(client: TestClient, nombre: str) -> dict:
    resp = client.post(
        "/api/projects", json={"name": nombre, "domain": "reuma"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir(client: TestClient, proyecto_id: int, cuerpo: str, nombre: str = "semana-10.csv"):
    return client.post(
        f"/api/projects/{proyecto_id}/usage-logs/upload",
        files={"file": (nombre, cuerpo.encode("utf-8"), "text/csv")},
        headers=actor_headers("miguel"),
    )


def _n_filas(client: TestClient, proyecto_id: int) -> int:
    with Session(client.app.state.engine) as s:
        return s.exec(
            select(func.count()).select_from(UsageLog).where(UsageLog.project_id == proyecto_id)
        ).one()


def _n_datasets_uso(client: TestClient, proyecto_id: int) -> int:
    with Session(client.app.state.engine) as s:
        return s.exec(
            select(func.count())
            .select_from(Dataset)
            .where(Dataset.project_id == proyecto_id, Dataset.kind == "usage_log")
        ).one()


def test_misma_subida_dos_veces_da_409_y_no_suma_filas(client: TestClient):
    proyecto = _proyecto(client, "a2d-duplicado")
    assert _subir(client, proyecto["id"], CUERPO_A).status_code == 200
    assert _n_filas(client, proyecto["id"]) == 2
    resp = _subir(client, proyecto["id"], CUERPO_A, nombre="otro-nombre.csv")
    assert resp.status_code == 409, resp.text
    detalle = resp.json()["detail"]
    assert "semana-10.csv" in detalle
    assert "ya se subió" in detalle
    assert "20" in detalle  # año de la fecha de la primera subida
    assert _n_filas(client, proyecto["id"]) == 2
    assert _n_datasets_uso(client, proyecto["id"]) == 1


def test_fichero_distinto_entra(client: TestClient):
    proyecto = _proyecto(client, "a2d-distinto")
    assert _subir(client, proyecto["id"], CUERPO_A).status_code == 200
    assert _subir(client, proyecto["id"], CUERPO_B).status_code == 200
    assert _n_filas(client, proyecto["id"]) == 4


def test_tras_reiniciar_el_proyecto_el_mismo_fichero_entra(client: TestClient):
    proyecto = _proyecto(client, "a2d-reinicio")
    assert _subir(client, proyecto["id"], CUERPO_A).status_code == 200
    reinicio = client.post(
        f"/api/projects/{proyecto['id']}/reset",
        json={"confirm": True, "actor": "miguel", "motivo": "prueba de registro duplicado"},
        headers=actor_headers("miguel"),
    )
    assert reinicio.status_code == 200, reinicio.text
    assert _n_filas(client, proyecto["id"]) == 0
    assert _subir(client, proyecto["id"], CUERPO_A).status_code == 200
    assert _n_filas(client, proyecto["id"]) == 2


def test_el_mismo_fichero_en_otro_proyecto_entra(client: TestClient):
    uno = _proyecto(client, "a2d-uno")
    dos = _proyecto(client, "a2d-dos")
    assert _subir(client, uno["id"], CUERPO_A).status_code == 200
    assert _subir(client, dos["id"], CUERPO_A).status_code == 200
