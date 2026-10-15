"""Referencia y resumen de la explicabilidad.

Cada test comprueba el control seguro de un apunte; ver `HUELLAS`.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api import conftest as _api
from tests.api.conftest import actor_headers
from tests.api.test_multiclase_modelo import _con_modelo_subido
from vigia.app.models import ModelVersion
from vigia.app.services import explain as explain_service

# Fixtures de tests/api/conftest.py: app, client, data_dir y settings.
app, client, data_dir, settings = _api.app, _api.client, _api.data_dir, _api.settings

HUELLAS = {
    "test_resumen_no_toma_como_referencia_un_ranking_de_otra_clase": (
        "explain/referencia-y-resumen-sin-clase-lote-ni-version"
    ),
    "test_resumen_compara_rankings_de_la_misma_clase": (
        "explain/referencia-y-resumen-sin-clase-lote-ni-version"
    ),
    "test_lote_de_otra_version_no_se_explica_con_esta": (
        "explain/referencia-y-resumen-sin-clase-lote-ni-version"
    ),
    "test_evaluar_un_lote_no_usa_como_referencia_la_explicacion_de_otra_clase": (
        "explain/referencia-y-resumen-sin-clase-lote-ni-version"
    ),
}


def _explicar(client: TestClient, version_id: int, clase: str) -> None:
    resp = client.post(
        f"/api/model-versions/{version_id}/explain/global",
        json={"kind": "permutation", "clase": clase},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.json()


def _resumen(client: TestClient, project_id: int) -> dict:
    resp = client.get(f"/api/projects/{project_id}/explanations/summary")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_resumen_no_toma_como_referencia_un_ranking_de_otra_clase(client: TestClient):
    """El resumen de explicabilidad no compara el ranking de una clase con el de
    otra: sin otra explicacion de la misma clase, no hay referencia."""
    p = _con_modelo_subido(client, "r8-n03-otra-clase")
    v = p["active_version_id"]
    _explicar(client, v, "spam")
    _explicar(client, v, "odio")
    resumen = _resumen(client, p["id"])
    assert resumen["n_explanations"] == 1
    assert resumen["reference_top_features"] is None
    assert resumen["ranking_delta"] == []


def test_resumen_compara_rankings_de_la_misma_clase(client: TestClient):
    """Control positivo: con dos explicaciones de la misma clase el resumen sigue
    dando referencia."""
    p = _con_modelo_subido(client, "r8-n03-misma-clase")
    v = p["active_version_id"]
    _explicar(client, v, "spam")
    _explicar(client, v, "odio")
    _explicar(client, v, "odio")
    resumen = _resumen(client, p["id"])
    assert resumen["n_explanations"] == 2
    assert resumen["reference_top_features"]


def test_lote_de_otra_version_no_se_explica_con_esta(client: TestClient):
    """El lote que se explica pertenece a la version de la peticion; el de otra
    version del mismo proyecto se rechaza con 422."""
    p = _con_modelo_subido(client, "r8-n03-otra-version")
    resp = client.post(
        f"/api/projects/{p['id']}/versions",
        json={"label": "v2", "model_kind": "external_files", "actor": "clara", "motivo": "prueba"},
    )
    assert resp.status_code in (200, 201), resp.text
    v2 = resp.json()["id"]
    with Session(client.app.state.engine) as s:
        version2 = s.get(ModelVersion, v2)
        lote_v1 = s.get(ModelVersion, p["active_version_id"]).baseline_batch_id
        assert lote_v1 is not None
        with pytest.raises(HTTPException) as exc:
            explain_service.resolve_batch(s, version2, lote_v1)
    assert exc.value.status_code == 422


def test_evaluar_un_lote_no_usa_como_referencia_la_explicacion_de_otra_clase(client: TestClient):
    """Al evaluar un lote con la explicacion de una clase, la referencia de la
    estabilidad es la primera explicacion de la misma clase: la de otra clase se
    salta y la medida queda sin datos por falta de referencia."""
    from vigia.app.models import Batch
    from vigia.app.services import evaluate as evaluate_service

    p = _con_modelo_subido(client, "r8-n03-evaluar")
    with Session(client.app.state.engine) as s:
        version = s.get(ModelVersion, p["active_version_id"])
        lote = s.get(Batch, version.baseline_batch_id)
        otra = explain_service.explain_global(s, version, kind="permutation", batch=lote, clase="spam")
        actual = explain_service.explain_global(s, version, kind="permutation", batch=lote, clase="odio")
        assert otra.available and actual.available
        evaluaciones = evaluate_service.evaluate_batch(s, lote, trigger="manual", explanation=actual)
        evaluacion_id = evaluaciones["explain"].id
    resp = client.get(f"/api/evaluations/{evaluacion_id}")
    assert resp.status_code == 200, resp.text
    medida = next(m for m in resp.json()["measurements"] if m["metric_key"] == "explain_stability_ndcg")
    assert medida["state"] == "sin_datos"
    assert medida["value"] is None
