"""Importancias no finitas de la explicabilidad.

Cada test comprueba el control seguro de un apunte; ver `HUELLAS`.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api import conftest as _api
from tests.api.test_explain import _preparar_proyecto_sim_logistic
from vigia.app.models import Batch, Explanation, ModelVersion
from vigia.app.services import evaluate as evaluate_service
from vigia.core import explain as core_explain

# Fixtures de tests/api/conftest.py: app, client, data_dir y settings.
app, client, data_dir, settings = _api.app, _api.client, _api.data_dir, _api.settings

HUELLAS = {
    "test_importancia_no_finita_no_se_guarda_como_numero": (
        "explain/importancia-no-finita-guardada-y-releida-sin-validar"
    ),
    "test_modelo_que_devuelve_nan_da_explicacion_no_disponible": (
        "explain/importancia-no-finita-guardada-y-releida-sin-validar"
    ),
    "test_listado_con_importancia_nan_guardada_responde_200": (
        "explain/importancia-no-finita-guardada-y-releida-sin-validar"
    ),
    "test_evaluar_con_explicacion_ilegible_evalua_el_resto": (
        "explain/importancia-no-finita-guardada-y-releida-sin-validar"
    ),
    "test_referencia_ilegible_se_salta": (
        "explain/importancia-no-finita-guardada-y-releida-sin-validar"
    ),
}


def _marco() -> pd.DataFrame:
    return pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [0.5, 0.1, 0.9, 0.3]})


def _modelo_nan(X: pd.DataFrame) -> np.ndarray:
    return np.full((len(X), 2), np.nan)


def test_modelo_que_devuelve_nan_da_explicacion_no_disponible():
    """La importancia por permutacion con una salida no numerica no se declara
    disponible: queda `available=False` con motivo y sin variables."""
    r = core_explain.global_permutation(_modelo_nan, _marco(), y=None)
    assert r.available is False
    assert r.motivo
    assert r.features == []


def test_importancia_no_finita_no_se_guarda_como_numero():
    """Ninguna importancia que llega al JSON es NaN o infinita."""
    r = core_explain.global_permutation(_modelo_nan, _marco(), y=None)
    datos = r.to_dict()
    texto = json.dumps(datos, allow_nan=False)
    assert "NaN" not in texto
    assert all(f["importance"] is not None for f in datos["features"])
    ok = core_explain.global_permutation(
        lambda X: np.column_stack([1 - X["b"], X["b"]]), _marco(), y=None
    )
    assert ok.available is True
    assert all(math.isfinite(f.importance) for f in ok.features)


def _guardar_global(session: Session, version_id: int, batch_id: int, importancia) -> Explanation:
    batch = session.get(Batch, batch_id)
    fila = Explanation(
        project_id=batch.project_id,
        model_version_id=version_id,
        batch_id=batch_id,
        kind="global_permutation",
        params_json={},
        available=True,
        result_json={
            "kind": "global_permutation",
            "available": True,
            "features": [{"feature": "Age", "importance": importancia}],
            "params": {},
        },
    )
    session.add(fila)
    session.commit()
    session.refresh(fila)
    return fila


def test_listado_con_importancia_nan_guardada_responde_200(client: TestClient):
    """Una explicacion ya guardada con una importancia no finita se sirve con
    `null` en lugar de romper el listado."""
    proyecto, version_id, base_id, _ = _preparar_proyecto_sim_logistic(client)
    with Session(client.app.state.engine) as s:
        fila = _guardar_global(s, version_id, base_id, float("nan"))
        fila_id = fila.id
    lista = client.get(f"/api/model-versions/{version_id}/explanations")
    assert lista.status_code == 200, lista.text
    una = client.get(f"/api/explanations/{fila_id}")
    assert una.status_code == 200, una.text
    assert una.json()["result"]["features"][0]["importance"] is None
    resumen = client.get(f"/api/projects/{proyecto['id']}/explanations/summary")
    assert resumen.status_code == 200, resumen.text


def test_evaluar_con_explicacion_ilegible_evalua_el_resto(client: TestClient):
    """Si la explicacion del lote no se puede releer, la evaluacion calcula
    igualmente calidad, deriva y equidad."""
    _, version_id, base_id, evento_id = _preparar_proyecto_sim_logistic(client)
    with Session(client.app.state.engine) as s:
        fila = _guardar_global(s, version_id, base_id, None)
        lote = s.get(Batch, evento_id)
        resultado = evaluate_service.evaluate_batch(s, lote, trigger="manual", explanation=fila)
        s.commit()
    assert {"fairness", "quality", "drift"} & set(resultado)
    assert "explain" not in resultado


def test_referencia_ilegible_se_salta(client: TestClient):
    """La referencia del monitor de explicabilidad ignora una explicacion global
    que no se puede releer."""
    _, version_id, base_id, _ = _preparar_proyecto_sim_logistic(client)
    with Session(client.app.state.engine) as s:
        _guardar_global(s, version_id, base_id, None)
        version = s.get(ModelVersion, version_id)
        assert evaluate_service._explain_reference_for_version(s, version, excluir_explanation_id=None) is None
