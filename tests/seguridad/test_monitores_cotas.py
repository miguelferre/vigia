"""Cotas de la configuracion de los monitores.

Cada test comprueba el control seguro de un apunte; ver `HUELLAS`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api import conftest as _api
from tests.api.test_alerts import _crear_proyecto
from tests.seguridad.test_diario_b import _monitor, _patch

# Fixtures de tests/api/conftest.py: app, client, data_dir y settings.
app, client, data_dir, settings = _api.app, _api.client, _api.data_dir, _api.settings

HUELLAS = {
    "test_config_de_minimos_de_filas_fuera_de_rango_se_rechaza": (
        "monitors/patch-config-numeric-fields-unbounded"
    ),
    "test_config_de_minimos_de_filas_en_rango_se_acepta": (
        "monitors/patch-config-numeric-fields-unbounded"
    ),
}

FUERA = [
    pytest.param("quality", {"min_feedback": 10**9}, id="min_feedback-enorme"),
    pytest.param("quality", {"min_feedback": 0}, id="min_feedback0"),
    pytest.param("fairness", {"label_min_records": 10**9}, id="label_min_records-enorme"),
    pytest.param("fairness", {"label_min_records": 0}, id="label_min_records0"),
    pytest.param("fairness", {"label_min_records": -5}, id="label_min_records-neg"),
    pytest.param("fairness", {"min_group": 10**9}, id="min_group-enorme"),
    pytest.param("fairness", {"min_positives": 10**9}, id="min_positives-enorme"),
]


@pytest.mark.parametrize(("tipo", "config"), FUERA)
def test_config_de_minimos_de_filas_fuera_de_rango_se_rechaza(
    client: TestClient, tipo: str, config: dict
):
    """El PATCH rechaza con 422 un minimo de filas fuera de rango y no cambia lo guardado."""
    proyecto = _crear_proyecto(client, "r8-n11-fuera")
    monitor = _monitor(client, proyecto["id"], tipo)
    antes = client.get(f"/api/monitors/{monitor['id']}").json()["config"]
    resp = _patch(client, monitor["id"], config=config)
    assert resp.status_code == 422, resp.text
    despues = client.get(f"/api/monitors/{monitor['id']}").json()["config"]
    assert despues == antes


@pytest.mark.parametrize(
    ("tipo", "config"),
    [
        ("quality", {"min_feedback": 100_000}),
        ("fairness", {"label_min_records": 1, "min_group": 100_000, "min_positives": 100_000}),
    ],
)
def test_config_de_minimos_de_filas_en_rango_se_acepta(client: TestClient, tipo: str, config: dict):
    """Control positivo: los extremos del rango se aceptan y se guardan."""
    proyecto = _crear_proyecto(client, "r8-n11-dentro")
    monitor = _monitor(client, proyecto["id"], tipo)
    resp = _patch(client, monitor["id"], config=config)
    assert resp.status_code == 200, resp.text
    guardado = client.get(f"/api/monitors/{monitor['id']}").json()["config"]
    assert all(guardado[k] == v for k, v in config.items())
