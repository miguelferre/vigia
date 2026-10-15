"""Explicabilidad, vía API con `TestClient`."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.core import explain as core_explain

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo" / "escenario_1"


def _crear_proyecto(
    client: TestClient,
    name: str,
    *,
    model_kind: str = "sim_logistic",
    store_features: bool = True,
) -> dict:
    resp = client.post(
        "/api/projects",
        json={
            "name": name,
            "domain": "reuma",
            "model_kind": model_kind,
            "store_features": store_features,
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir_mapear_ingerir(client: TestClient, project_id: int, *, filename: str, role: str) -> int:
    contenido = (DEMO_DIR / filename).read_bytes()
    resp = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": (filename, contenido, "application/json")},
        data={"kind": "feedback", "role": role},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    dataset_id = body["dataset"]["id"]

    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={
            "mapping": body["suggested_mapping"],
            "privacy_decisions": {"Patient_Id": "hashear", "Episode_Id": "hashear"},
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(f"/api/datasets/{dataset_id}/ingest", json={"evaluate": False, "mode": "crear"})
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    return job["result"]["batch_id"]


def _preparar_proyecto_sim_logistic(
    client: TestClient, name: str = "explicabilidad-sim"
) -> tuple[dict, int, int, int]:
    """Proyecto `sim_logistic` con baseline E1 congelado y el batch del evento ingerido."""
    proyecto = _crear_proyecto(client, name)
    version_id = proyecto["active_version_id"]
    baseline_batch_id = _subir_mapear_ingerir(
        client, proyecto["id"], filename="01_baseline_feedback.json", role="baseline"
    )
    resp = client.post(
        f"/api/model-versions/{version_id}/baseline",
        json={"batch_id": baseline_batch_id, "actor": "miguel", "motivo": "congelar baseline E1"},
    )
    # La ingesta de la línea base ya la congela: el POST /baseline da 409.
    assert resp.status_code == 409, resp.text
    assert "congelado" in resp.text, resp.text
    evento_batch_id = _subir_mapear_ingerir(
        client, proyecto["id"], filename="02_evento_feedback.json", role="production"
    )
    return proyecto, version_id, baseline_batch_id, evento_batch_id


def test_explain_global_permutation_disponible_y_age_entre_las_tres_primeras(client: TestClient):
    _, version_id, _, _ = _preparar_proyecto_sim_logistic(client)

    resp = client.post(
        f"/api/model-versions/{version_id}/explain/global",
        json={"kind": "permutation"},
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    explanation = job["result"]
    assert explanation["available"] is True
    assert explanation["kind"] == "global_permutation"

    top3 = [f["feature"] for f in explanation["result"]["features"][:3]]
    assert "Age" in top3

    # queda persistida y accesible por los GET de consulta.
    resp = client.get(f"/api/model-versions/{version_id}/explanations")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 1

    resp = client.get(f"/api/explanations/{explanation['id']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["available"] is True


def test_explain_local_fila_0_del_evento_con_age_dominante(client: TestClient):
    _, version_id, _, evento_batch_id = _preparar_proyecto_sim_logistic(client)

    resp = client.post(
        f"/api/model-versions/{version_id}/explain/local",
        json={"batch_id": evento_batch_id, "row_seq": 450},
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    explanation = job["result"]
    assert explanation["available"] is True
    assert explanation["kind"] == "local_lime"
    assert explanation["row_seq"] == 450

    result = explanation["result"]
    assert result["features"][0]["feature"] == "Age"
    assert 0.0 <= result["prob_favorable"] <= 1.0


def test_explain_global_409_en_proyecto_external_files(client: TestClient):
    proyecto = _crear_proyecto(client, "explicabilidad-external", model_kind="external_files")
    version_id = proyecto["active_version_id"]

    resp = client.post(
        f"/api/model-versions/{version_id}/explain/global",
        json={"kind": "permutation"},
    )
    assert resp.status_code == 409, resp.text


def test_explain_shap_no_disponible_simulado_da_available_false_y_job_terminado(
    client: TestClient, monkeypatch
):
    _, version_id, _, _ = _preparar_proyecto_sim_logistic(client)

    monkeypatch.setitem(sys.modules, "shap", None)
    core_explain.shap_available.cache_clear()
    try:
        resp = client.post(
            f"/api/model-versions/{version_id}/explain/global",
            json={"kind": "shap"},
        )
        assert resp.status_code == 200, resp.text
        job = resp.json()
        assert job["status"] == "terminado", job
        explanation = job["result"]
        assert explanation["available"] is False
        assert explanation["motivo"] is not None
        assert explanation["motivo"].startswith("SHAP no disponible en este equipo")
    finally:
        core_explain.shap_available.cache_clear()


def test_explain_global_batch_de_otro_proyecto_da_404(client: TestClient):
    """Un batch_id de OTRO proyecto no debe ser aceptado: fuga de datos entre proyectos."""
    _, version_a, _, _ = _preparar_proyecto_sim_logistic(client, "explicabilidad-sim-a")
    _, _, batch_b, _ = _preparar_proyecto_sim_logistic(client, "explicabilidad-sim-b")

    resp = client.post(
        f"/api/model-versions/{version_a}/explain/global",
        json={"kind": "permutation", "batch_id": batch_b},
    )
    assert resp.status_code == 404, resp.text

    # el batch ajeno tampoco debe colarse en explain/local.
    resp = client.post(
        f"/api/model-versions/{version_a}/explain/local",
        json={"batch_id": batch_b, "row_seq": 0},
    )
    assert resp.status_code == 404, resp.text


def test_explain_global_409_sin_features_guardadas(client: TestClient):
    proyecto = _crear_proyecto(client, "explicabilidad-sin-features", store_features=False)
    version_id = proyecto["active_version_id"]
    baseline_batch_id = _subir_mapear_ingerir(
        client, proyecto["id"], filename="01_baseline_feedback.json", role="baseline"
    )
    resp = client.post(
        f"/api/model-versions/{version_id}/baseline",
        json={"batch_id": baseline_batch_id, "actor": "miguel", "motivo": "congelar baseline E1"},
    )
    # La ingesta de la línea base ya la congela: el POST /baseline da 409.
    assert resp.status_code == 409, resp.text
    assert "congelado" in resp.text, resp.text

    resp = client.post(
        f"/api/model-versions/{version_id}/explain/global",
        json={"kind": "permutation"},
    )
    assert resp.status_code == 409, resp.text


# --- Resumen de explicabilidad para el cuadro de mando -------------------


def test_explanations_summary_sin_explicaciones(client: TestClient):
    proyecto = _crear_proyecto(client, "sin-explicaciones")
    resp = client.get(f"/api/projects/{proyecto['id']}/explanations/summary")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "top_features": [],
        "stability": None,
        # Menos de dos explicaciones -> "sin_datos" siempre, no `None`.
        "stability_state": "sin_datos",
        "ranking_changed_at": None,
        "n_explanations": 0,
        # Sin ninguna explicación no hay nada que comparar.
        "reference_top_features": None,
        "ranking_delta": [],
    }


def test_explanations_summary_una_explicacion_top3_sin_estabilidad(client: TestClient):
    proyecto, version_id, _, _ = _preparar_proyecto_sim_logistic(client)
    resp = client.post(
        f"/api/model-versions/{version_id}/explain/global", json={"kind": "permutation"}
    )
    assert resp.status_code == 200, resp.text

    resp = client.get(f"/api/projects/{proyecto['id']}/explanations/summary")
    assert resp.status_code == 200, resp.text
    resumen = resp.json()
    assert len(resumen["top_features"]) == 3
    assert {"feature", "importance"} == set(resumen["top_features"][0])
    assert "Age" in {f["feature"] for f in resumen["top_features"]}
    # una única explicación (sin referencia anterior): no hay estabilidad todavía.
    assert resumen["stability"] is None
    assert resumen["stability_state"] == "sin_datos"
    assert resumen["ranking_changed_at"] is None
    assert resumen["n_explanations"] == 1
    # Tampoco hay explicación de referencia (es la única que existe).
    assert resumen["reference_top_features"] is None
    assert resumen["ranking_delta"] == []


def test_explanations_summary_con_reproductor_de_demo_trae_estabilidad(client: TestClient, session):
    """`consejeria_regional` marca `explain_global=True` en sus cinco baselines
: tras reproducirla hay referencia y, por tanto,
    estabilidad medida. La sexta fase no declara `explain_global`, pero
    con `explain_auto` activado por defecto obtiene su propia explicación
    automática."""
    from sqlmodel import select as _select

    from vigia.app.models import Explanation as _Explanation

    resp = client.post(
        "/api/demo/runs",
        json={"scenario_key": "consejeria_regional"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    resp = client.post(f"/api/demo/runs/{run['id']}/play", headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.text

    project_id = run["project_id"]
    resp = client.get(f"/api/projects/{project_id}/explanations/summary")
    assert resp.status_code == 200, resp.text
    resumen = resp.json()
    assert len(resumen["top_features"]) == 3
    assert resumen["stability"] is not None
    assert resumen["stability_state"] in ("ok", "aviso", "alerta", "inestable", "sin_datos")

    explicaciones = session.exec(
        _select(_Explanation)
        .where(_Explanation.project_id == project_id, _Explanation.available == True)  # ruff: E712 ok
        .order_by(_Explanation.created_at)
    ).all()
    assert len(explicaciones) == 6
    if resumen["ranking_changed_at"] is not None:
        assert resumen["ranking_changed_at"] in {e.created_at for e in explicaciones[1:]}


def test_explanations_summary_referencia_y_ranking_delta_en_caso_digestivo(client: TestClient):
    """`reference_top_features` reutiliza la
    MISMA explicación de referencia que ya sostiene `stability`
    (`_explain_reference_for_version`: la primera explicación global
    disponible de la versión) y `ranking_delta` es coherente con los dos
    rankings de top 10, leídos de forma independiente vía `GET
    /model-versions/{id}/explanations`."""
    resp = client.post(
        "/api/demo/runs", json={"scenario_key": "caso_digestivo"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    resp = client.post(f"/api/demo/runs/{run['id']}/play", headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.text

    project_id = run["project_id"]
    resp = client.get(f"/api/projects/{project_id}")
    assert resp.status_code == 200, resp.text
    version_id = resp.json()["active_version_id"]

    resp = client.get(f"/api/model-versions/{version_id}/explanations", params={"limit": 500})
    assert resp.status_code == 200, resp.text
    globales = [
        e
        for e in resp.json()["items"]
        if e["kind"] in ("global_permutation", "global_shap") and e["available"]
    ]
    globales.sort(key=lambda e: e["id"])
    assert len(globales) >= 2, "caso_digestivo declara explain_global en varias fases"

    referencia_esperada = [
        {"feature": f["feature"], "importance": f["importance"]}
        for f in globales[0]["result"]["features"][:10]
    ]
    actual_esperado = [
        {"feature": f["feature"], "importance": f["importance"]}
        for f in globales[-1]["result"]["features"][:10]
    ]
    assert len(referencia_esperada) == 10

    resp = client.get(f"/api/projects/{project_id}/explanations/summary")
    assert resp.status_code == 200, resp.text
    resumen = resp.json()

    assert resumen["reference_top_features"] == referencia_esperada

    puesto_ref = {f["feature"]: i + 1 for i, f in enumerate(referencia_esperada)}
    puesto_actual = {f["feature"]: i + 1 for i, f in enumerate(actual_esperado)}
    variables = set(puesto_ref) | set(puesto_actual)
    delta_esperado = {
        v: (puesto_ref.get(v), puesto_actual.get(v))
        for v in variables
        if puesto_ref.get(v) != puesto_actual.get(v)
    }
    delta_recibido = {c["feature"]: (c["from"], c["to"]) for c in resumen["ranking_delta"]}
    assert delta_recibido == delta_esperado
