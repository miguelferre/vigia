"""`group_context` del monitor `fairness` desde el mapping
del último lote de la versión activa."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers

_CSV = (
    b"id,prediction,label,sexo,Age\n"
    b"1,1,1,mujer,30\n"
    b"2,0,0,hombre,45\n"
    b"3,1,0,mujer,50\n"
    b"4,0,1,hombre,60\n"
)


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post(
        "/api/projects", json={"name": name, "domain": "reuma"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _monitor_fairness(client: TestClient, project_id: int) -> dict:
    resp = client.get(f"/api/projects/{project_id}/monitors")
    assert resp.status_code == 200, resp.text
    return next(m for m in resp.json()["items"] if m["type"] == "fairness")


def test_group_context_null_sin_lotes(client: TestClient):
    proyecto = _crear_proyecto(client, "sin-lotes-fairness")
    monitor = _monitor_fairness(client, proyecto["id"])
    assert monitor["group_context"] is None


def test_group_context_con_mapping_de_atributo_protegido(client: TestClient):
    proyecto = _crear_proyecto(client, "con-mapping-fairness")
    version_id = proyecto["active_version_id"]

    resp = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("pacientes.csv", _CSV, "text/csv")},
        data={"kind": "combined", "role": "production"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    dataset_id = resp.json()["dataset"]["id"]

    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        # `id_col` obligatorio en lotes si el modelo acepta feedback.
        "id_col": "id",
        # Sin plantilla ni línea base, la clase favorable se declara.
        "favorable_label": 1,
        "feature_cols": ["Age"],
        "protected_attr_col": "sexo",
        "protected_kind": "categorical",
        "unpriv_groups": ["mujer"],
        "priv_groups": ["hombre"],
    }
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": mapping, "privacy_decisions": {}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"evaluate": False, "model_version_id": version_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado"

    monitor = _monitor_fairness(client, proyecto["id"])
    assert monitor["group_context"] == {
        "protected_attr": "sexo",
        "supervised": ["mujer"],
        "reference": ["hombre"],
    }

    # también por `GET /monitors/{id}`.
    resp = client.get(f"/api/monitors/{monitor['id']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["group_context"]["protected_attr"] == "sexo"
