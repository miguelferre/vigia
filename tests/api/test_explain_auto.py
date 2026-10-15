"""Explicación global automática tras evaluar un lote."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo" / "escenario_1"


def _crear_proyecto(
    client: TestClient,
    name: str,
    *,
    model_kind: str = "sim_logistic",
    explain_auto: bool | None = None,
) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "reuma", "model_kind": model_kind},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    proyecto = resp.json()
    if explain_auto is not None:
        resp = client.patch(
            f"/api/projects/{proyecto['id']}",
            json={"explain_auto": explain_auto, "actor": "miguel", "motivo": "ajuste de prueba"},
        )
        assert resp.status_code == 200, resp.text
        proyecto = resp.json()
    return proyecto


def _subir_mapear_ingerir_evaluar(client: TestClient, project_id: int, *, filename: str) -> dict:
    contenido = (DEMO_DIR / filename).read_bytes()
    resp = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": (filename, contenido, "application/json")},
        data={"kind": "feedback", "role": "baseline" if filename.startswith("01_") else "production"},
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

    resp = client.post(f"/api/datasets/{dataset_id}/ingest", json={"evaluate": True, "mode": "crear"})
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    if not job["result"]["evaluated"]:
        # La línea base no se evalúa al ingerir (se evalúa al confirmar
        # los umbrales); aquí se hace con el botón «Evaluar» de siempre.
        resp = client.post(f"/api/batches/{job['result']['batch_id']}/evaluate", json={"trigger": "manual"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "terminado", resp.json()
    return job["result"]


def test_explain_auto_activado_por_defecto_crea_una_explicacion_global(client: TestClient):
    proyecto = _crear_proyecto(client, "explain-auto-on")
    _subir_mapear_ingerir_evaluar(client, proyecto["id"], filename="01_baseline_feedback.json")

    version_id = proyecto["active_version_id"]
    resp = client.get(f"/api/model-versions/{version_id}/explanations")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 1
    explicacion = resp.json()["items"][0]
    assert explicacion["kind"] == "global_permutation"

    resp = client.get(f"/api/projects/{proyecto['id']}/explanations/summary")
    assert resp.status_code == 200, resp.text
    resumen = resp.json()
    assert resumen["n_explanations"] == 1
    # Con una sola explicación, no hay comparación posible.
    assert resumen["stability"] is None
    assert resumen["stability_state"] == "sin_datos"


def test_explain_auto_desactivado_no_crea_ninguna(client: TestClient):
    proyecto = _crear_proyecto(client, "explain-auto-off", explain_auto=False)
    _subir_mapear_ingerir_evaluar(client, proyecto["id"], filename="01_baseline_feedback.json")

    version_id = proyecto["active_version_id"]
    resp = client.get(f"/api/model-versions/{version_id}/explanations")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0


def test_explain_auto_dos_lotes_da_dos_explicaciones_y_estabilidad(client: TestClient):
    """El segundo lote debe llegar a `evaluate_batch` con `explanation=`
    (services/explain.py, orden con el router): solo así el motor calcula la
    medida `explain_stability_ndcg` del monitor `explain`."""
    proyecto = _crear_proyecto(client, "explain-auto-dos-lotes")
    _subir_mapear_ingerir_evaluar(client, proyecto["id"], filename="01_baseline_feedback.json")
    _subir_mapear_ingerir_evaluar(client, proyecto["id"], filename="02_evento_feedback.json")

    resp = client.get(f"/api/projects/{proyecto['id']}/explanations/summary")
    assert resp.status_code == 200, resp.text
    resumen = resp.json()
    assert resumen["n_explanations"] == 2
    # con dos explicaciones globales, la vía automática ha producido
    # comparación: no puede quedarse en "sin_datos".
    assert resumen["stability"] is not None
    assert resumen["stability_state"] != "sin_datos"


def test_explain_auto_tambien_al_evaluar_por_separado(client: TestClient):
    """La explicabilidad automática cubre los dos sitios donde se evalúa un lote: la ingesta
    (`routers/datasets.py`) y `POST /batches/{id}/evaluate`
    (`routers/evaluations.py`)."""
    proyecto = _crear_proyecto(client, "explain-auto-evaluate-endpoint")
    contenido = (DEMO_DIR / "01_baseline_feedback.json").read_bytes()
    resp = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("01_baseline_feedback.json", contenido, "application/json")},
        data={"kind": "feedback", "role": "baseline"},
        headers=actor_headers("miguel"),
    )
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
    batch_id = resp.json()["result"]["batch_id"]

    version_id = proyecto["active_version_id"]
    resp = client.get(f"/api/model-versions/{version_id}/explanations")
    assert resp.json()["total"] == 0  # sin evaluar, sin explicación

    resp = client.post(f"/api/batches/{batch_id}/evaluate", json={"trigger": "manual"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.json()

    resp = client.get(f"/api/model-versions/{version_id}/explanations")
    assert resp.json()["total"] == 1


def test_explain_auto_en_proyecto_no_explicable_no_registra_fallo(client: TestClient):
    """Una versión sin modelo ejecutable no es un fallo: `maybe_auto_explain`
    devuelve `None` en silencio (check_explainable, explain.py:42-48), sin
    evento `explicacion.fallida` (ese evento queda para fallos reales)."""
    proyecto = _crear_proyecto(client, "explain-auto-no-explicable", model_kind="external_files")
    _subir_mapear_ingerir_evaluar(client, proyecto["id"], filename="01_baseline_feedback.json")

    version_id = proyecto["active_version_id"]
    resp = client.get(f"/api/model-versions/{version_id}/explanations")
    assert resp.json()["total"] == 0

    resp = client.get("/api/events", params={"project_id": proyecto["id"], "limit": 100})
    assert resp.status_code == 200, resp.text
    acciones = [e["action"] for e in resp.json()["items"]]
    assert "explicacion.fallida" not in acciones
