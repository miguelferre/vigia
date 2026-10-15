"""`primary_metric` configurable del monitor de calidad."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post(
        "/api/projects", json={"name": name, "domain": "reuma"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _monitor_calidad(client: TestClient, project_id: int) -> dict:
    resp = client.get(f"/api/projects/{project_id}/monitors")
    assert resp.status_code == 200, resp.text
    return next(m for m in resp.json()["items"] if m["type"] == "quality")


def test_state_expone_accuracy_por_defecto(client: TestClient):
    proyecto = _crear_proyecto(client, "calidad-default")
    resp = client.get(f"/api/projects/{proyecto['id']}/state")
    assert resp.status_code == 200, resp.text
    assert resp.json()["quality_primary_metric"] == "accuracy"


def test_patch_primary_metric_valido_cambia_el_estado(client: TestClient):
    proyecto = _crear_proyecto(client, "calidad-auc")
    monitor = _monitor_calidad(client, proyecto["id"])

    resp = client.patch(
        f"/api/monitors/{monitor['id']}",
        json={
            "config": {"primary_metric": "area_under_roc"},
            "actor": "miguel",
            "motivo": "métrica principal para el cuadro",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["monitor"]["config"]["primary_metric"] == "area_under_roc"

    resp = client.get(f"/api/projects/{proyecto['id']}/state")
    assert resp.json()["quality_primary_metric"] == "area_under_roc"


def test_patch_primary_metric_invalido_422(client: TestClient):
    proyecto = _crear_proyecto(client, "calidad-invalida")
    monitor = _monitor_calidad(client, proyecto["id"])

    resp = client.patch(
        f"/api/monitors/{monitor['id']}",
        json={
            "config": {"primary_metric": "no_existe"},
            "actor": "miguel",
            "motivo": "prueba",
        },
    )
    assert resp.status_code == 422


def test_patch_parcial_sin_tocar_primary_metric_lo_conserva(client: TestClient):
    proyecto = _crear_proyecto(client, "calidad-preserva")
    monitor = _monitor_calidad(client, proyecto["id"])
    client.patch(
        f"/api/monitors/{monitor['id']}",
        json={
            "config": {"primary_metric": "f1_measure"},
            "actor": "miguel",
            "motivo": "fijar métrica",
        },
    )
    resp = client.patch(
        f"/api/monitors/{monitor['id']}",
        json={
            "config": {"min_feedback": 50},
            "actor": "miguel",
            "motivo": "otro cambio que no toca la métrica",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["monitor"]["config"]["primary_metric"] == "f1_measure"
    assert resp.json()["monitor"]["config"]["min_feedback"] == 50
