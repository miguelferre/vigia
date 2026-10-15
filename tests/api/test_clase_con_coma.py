"""El alta por la API rechaza con 422 una clase con coma y
nombra la clase en el mensaje."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers


def test_una_clase_con_coma_da_422_en_el_alta_y_nombra_la_clase(client: TestClient):
    cuerpo = {
        "name": "r8-clase-coma",
        "domain": "libre",
        "task_type": "multiclass",
        "classes": ["alto,medio", "spam", "odio"],
        "mapping_template": {"favorable_label": ["spam"]},
    }
    resp = client.post("/api/projects", json=cuerpo, headers=actor_headers("miguel"))
    assert resp.status_code == 422, resp.text
    assert "alto,medio" in resp.text
    assert "coma" in resp.text
