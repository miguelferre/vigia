"""`GET /projects/{id}/thresholds/proposal` sobre una
línea base mapeada sin `probability_col`. La propuesta de calidad no incluye
AUC ni calibración (valor `None` con motivo), y el resto de métricas sí se
proponen. El aviso del paso de mapeo del alta lo pinta la interfaz."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from tests.api.test_ciclo_de_vida_proyecto import _crear_proyecto, _ingerir, _subir

CLAVES_CON_PROBABILIDAD = {
    "area_under_roc",
    "area_under_pr",
    "log_loss",
    "gini_coefficient",
    "brier_score",
}


def _linea_base(client: TestClient, name: str, *, con_probabilidad: bool) -> dict:
    proyecto = _crear_proyecto(client, name)
    subida = _subir(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    mapeo = dict(subida["suggested_mapping"])
    if not con_probabilidad:
        mapeo["probability_col"] = None
    resp = client.put(
        f"/api/datasets/{subida['dataset']['id']}/mapping",
        json={"mapping": mapeo},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    _ingerir(client, subida["dataset"]["id"])
    return proyecto


def _calidad(client: TestClient, project_id: int) -> dict[str, dict]:
    resp = client.get(f"/api/projects/{project_id}/thresholds/proposal")
    assert resp.status_code == 200, resp.text
    monitor = next(m for m in resp.json()["monitors"] if m["monitor_type"] == "quality")
    return {p["metric_key"]: p for p in monitor["propuestas"]}


def test_propuesta_de_calidad_sin_probability_col_no_incluye_auc_ni_calibracion(client: TestClient):
    proyecto = _linea_base(client, "propuesta-sin-prob", con_probabilidad=False)
    por_clave = _calidad(client, proyecto["id"])

    presentes = CLAVES_CON_PROBABILIDAD & por_clave.keys()
    assert presentes, "la propuesta de fábrica debe nombrar alguna métrica con probabilidad"
    for clave in presentes:
        assert por_clave[clave]["value"] is None, clave
        assert por_clave[clave]["motivo"], clave

    # Las métricas que salen de predicción y etiqueta sí se proponen.
    con_valor = [c for c, p in por_clave.items() if c not in CLAVES_CON_PROBABILIDAD and p["value"] is not None]
    assert con_valor, por_clave


def test_propuesta_de_calidad_con_probability_col_si_incluye_auc(client: TestClient):
    proyecto = _linea_base(client, "propuesta-con-prob", con_probabilidad=True)
    por_clave = _calidad(client, proyecto["id"])
    assert por_clave["area_under_roc"]["value"] is not None
