"""Evaluación, vía API con `TestClient`.

Los números de referencia (`fairness_value` 19,50, FNRD 0,631, `accuracy`
0,860, `confidence_drift_score` 0,370, `feature_drift_score` 0,189) son el
contrato: ya salen del motor sobre el mismo fichero de feedback
(`tests/core/test_engine.py::test_e1_evento_fairness_alerta_inestable_y_valores`,
misma reconstrucción que hace `vigia eval` en `cli.py::cmd_eval`, solo con la
feedback: `load_harness_pair` no usa el payload más que para verificar el
orden). Aquí se reproducen subiendo, mapeando e ingiriendo `01_baseline_feedback.json`
y `02_evento_feedback.json` como datasets `kind=combined` por la API.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo" / "escenario_1"


def _crear_proyecto(client: TestClient, name: str = "reuma-eval") -> dict:
    resp = client.post(
        "/api/projects",
        # Números de referencia: método de ventanas, no por lote.
        json={"name": name, "domain": "reuma", "fairness_interval_method": "ventanas"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir_y_mapear(client: TestClient, project_id: int, filename: str, *, role: str) -> dict:
    contenido = (DEMO_DIR / filename).read_bytes()
    resp = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": (filename, contenido, "application/json")},
        data={"kind": "combined", "role": role},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    dataset = body["dataset"]
    mapping = body["suggested_mapping"]
    resp = client.put(
        f"/api/datasets/{dataset['id']}/mapping",
        json={"mapping": mapping},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ingerir(client: TestClient, dataset_id: int, **body) -> dict:
    body.setdefault("evaluate", False)
    resp = client.post(f"/api/datasets/{dataset_id}/ingest", json=body)
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    return job["result"]


def _evaluar(client: TestClient, batch_id: int, trigger: str = "manual") -> dict:
    resp = client.post(f"/api/batches/{batch_id}/evaluate", json={"trigger": trigger})
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    return job["result"]


def _medida(client: TestClient, evaluation_id: int, metric_key: str) -> dict:
    resp = client.get(f"/api/evaluations/{evaluation_id}")
    assert resp.status_code == 200, resp.text
    for m in resp.json()["measurements"]:
        if m["metric_key"] == metric_key:
            return m
    raise KeyError(metric_key)


def _preparar_baseline_y_evento(client: TestClient) -> tuple[dict, dict, dict]:
    """Crea el proyecto, ingiere el baseline (congelado) y el evento E1. Devuelve
    (proyecto, resultado_ingesta_baseline, resultado_ingesta_evento)."""
    proyecto = _crear_proyecto(client)
    baseline_ds = _subir_y_mapear(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    resultado_baseline = _ingerir(client, baseline_ds["id"])

    # Ingerir la línea base ya la congela; no hay POST /baseline que hacer.

    evento_ds = _subir_y_mapear(client, proyecto["id"], "02_evento_feedback.json", role="production")
    resultado_evento = _ingerir(client, evento_ds["id"])
    return proyecto, resultado_baseline, resultado_evento


# --- números de referencia -----------------------------------------------------


def test_evaluar_evento_e1_reproduce_los_numeros_del_plan(client: TestClient):
    _proyecto, _, resultado_evento = _preparar_baseline_y_evento(client)
    resultado = _evaluar(client, resultado_evento["batch_id"])

    fairness_id = resultado["evaluations"]["fairness"]
    fairness_value = _medida(client, fairness_id, "fairness_value")
    assert fairness_value["value"] == pytest.approx(19.50, abs=0.05)
    assert fairness_value["interval_low"] <= 20.0 <= fairness_value["interval_high"]
    assert fairness_value["state"] == "inestable"

    fnrd = _medida(client, fairness_id, "false_negative_rate_difference")
    assert fnrd["value"] == pytest.approx(0.631, abs=0.005)
    assert fnrd["state"] == "alerta"

    quality_id = resultado["evaluations"]["quality"]
    accuracy = _medida(client, quality_id, "accuracy")
    assert accuracy["value"] == pytest.approx(0.860, abs=0.005)

    drift_id = resultado["evaluations"]["drift"]
    confianza = _medida(client, drift_id, "confidence_drift_score")
    assert confianza["value"] == pytest.approx(0.370, abs=0.01)
    feature_drift = _medida(client, drift_id, "feature_drift_score")
    assert feature_drift["value"] == pytest.approx(0.189, abs=0.01)

    resp = client.get(f"/api/evaluations/{fairness_id}")
    evaluacion = resp.json()
    assert evaluacion["config_snapshot"]["fairness"]["min_records"] == 200
    assert evaluacion["window"]["kind"] == "ultimos_n"
    assert evaluacion["window"]["n"] == 200


def test_cambiar_umbral_fnrd_y_reevaluar_cambia_estado_y_snapshot(client: TestClient, session):
    from sqlmodel import select

    from vigia.app.models import Monitor

    proyecto, _, resultado_evento = _preparar_baseline_y_evento(client)
    resultado = _evaluar(client, resultado_evento["batch_id"])
    fairness_id_1 = resultado["evaluations"]["fairness"]
    fnrd_1 = _medida(client, fairness_id_1, "false_negative_rate_difference")
    assert fnrd_1["state"] == "alerta"

    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == proyecto["id"], Monitor.type == "fairness")
    ).first()
    thresholds = dict(monitor.thresholds_json)
    nuevos = []
    for t in thresholds["thresholds"]:
        if t["metric_key"] == "false_negative_rate_difference":
            nuevos.append({**t, "value": 0.70})
        else:
            nuevos.append(t)
    thresholds["thresholds"] = nuevos
    monitor.thresholds_json = thresholds
    session.add(monitor)
    session.commit()

    resultado_2 = _evaluar(client, resultado_evento["batch_id"])
    fairness_id_2 = resultado_2["evaluations"]["fairness"]
    assert fairness_id_2 != fairness_id_1
    fnrd_2 = _medida(client, fairness_id_2, "false_negative_rate_difference")
    assert fnrd_2["state"] != "alerta"

    resp = client.get(f"/api/evaluations/{fairness_id_2}")
    snapshot = resp.json()["config_snapshot"]
    umbral_nuevo = next(
        t["value"]
        for t in snapshot["thresholds"]["fairness"]["thresholds"]
        if t["metric_key"] == "false_negative_rate_difference"
    )
    assert umbral_nuevo == pytest.approx(0.70)


def test_timeline_devuelve_las_dos_evaluaciones_en_orden(client: TestClient):
    proyecto, resultado_baseline, resultado_evento = _preparar_baseline_y_evento(client)
    _evaluar(client, resultado_baseline["batch_id"])
    _evaluar(client, resultado_evento["batch_id"])

    resp = client.get(
        f"/api/projects/{proyecto['id']}/timeline",
        params={"monitor_type": "fairness", "metric_key": "fairness_value"},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 2
    assert items[0]["ts"] <= items[1]["ts"]
    assert items[1]["state"] == "inestable"


# --- `order` en `GET /projects/{id}/evaluations` -------


def test_evaluations_order_desc_con_limit_2_devuelve_las_dos_ultimas(client: TestClient):
    proyecto, resultado_baseline, resultado_evento = _preparar_baseline_y_evento(client)
    _evaluar(client, resultado_baseline["batch_id"])
    resultado_2 = _evaluar(client, resultado_evento["batch_id"])

    resp_asc = client.get(f"/api/projects/{proyecto['id']}/evaluations", params={"limit": 500})
    assert resp_asc.status_code == 200, resp_asc.text
    ids_asc = [e["id"] for e in resp_asc.json()["items"]]
    assert ids_asc == sorted(ids_asc)  # por defecto, ascendente como hasta ahora
    assert len(ids_asc) == 6  # tres monitores por lote, dos lotes evaluados

    resp_desc = client.get(
        f"/api/projects/{proyecto['id']}/evaluations",
        params={"order": "desc", "limit": 2},
    )
    assert resp_desc.status_code == 200, resp_desc.text
    items_desc = resp_desc.json()["items"]
    assert len(items_desc) == 2
    # las dos últimas por `created_at`, la más reciente primero: exactamente
    # el reverso de las dos últimas del orden ascendente.
    assert [e["id"] for e in items_desc] == list(reversed(ids_asc[-2:]))
    # y son evaluaciones del segundo lote (el evento), no del baseline.
    ids_evento = set(resultado_2["evaluations"].values())
    assert {e["id"] for e in items_desc} <= ids_evento


def test_evaluations_order_invalido_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="reuma-eval-order-422")
    resp = client.get(f"/api/projects/{proyecto['id']}/evaluations", params={"order": "invertido"})
    assert resp.status_code == 422, resp.text


# --- Lista de métricas y rango de fechas ----------------


def test_timeline_con_varias_metric_key_las_devuelve_todas_con_su_clave(client: TestClient):
    proyecto, _, resultado_evento = _preparar_baseline_y_evento(client)
    _evaluar(client, resultado_evento["batch_id"])

    resp = client.get(
        f"/api/projects/{proyecto['id']}/timeline",
        params={
            "monitor_type": "fairness",
            "metric_key": "fairness_value,false_negative_rate_difference",
        },
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert {i["metric_key"] for i in items} == {"fairness_value", "false_negative_rate_difference"}
    for item in items:
        assert item["metric_key"]  # nunca vacío: cada punto sabe de qué métrica es


def test_timeline_since_until_recorta_la_serie_y_until_antes_de_since_es_422(client: TestClient):
    proyecto, resultado_baseline, resultado_evento = _preparar_baseline_y_evento(client)
    _evaluar(client, resultado_baseline["batch_id"])
    corte = datetime.now(UTC).isoformat(timespec="microseconds")
    _evaluar(client, resultado_evento["batch_id"])

    resp = client.get(
        f"/api/projects/{proyecto['id']}/timeline",
        params={"monitor_type": "fairness", "metric_key": "fairness_value", "since": corte},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["state"] == "inestable"

    resp = client.get(
        f"/api/projects/{proyecto['id']}/timeline",
        params={
            "monitor_type": "fairness",
            "metric_key": "fairness_value",
            "since": "2026-09-10",
            "until": "2026-09-01",
        },
    )
    assert resp.status_code == 422, resp.text


def test_timeline_until_con_fecha_sola_incluye_ese_dia_entero(client: TestClient):
    """`until=aaaa-mm-dd` nombra el día completo, no su medianoche.

    El servicio compara `Evaluation.created_at` como texto, así que sin
    extender la fecha al final del día el periodo "hoy" del selector no
    devolvería ni un punto de los de hoy.
    """
    proyecto, resultado_baseline, resultado_evento = _preparar_baseline_y_evento(client)
    _evaluar(client, resultado_baseline["batch_id"])
    _evaluar(client, resultado_evento["batch_id"])
    hoy = datetime.now(UTC).date().isoformat()

    resp = client.get(
        f"/api/projects/{proyecto['id']}/timeline",
        params={
            "monitor_type": "fairness",
            "metric_key": "fairness_value",
            "since": hoy,
            "until": hoy,
        },
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 2


def test_timeline_metric_key_vacio_o_con_mas_de_20_da_422(client: TestClient):
    proyecto, _resultado_baseline, _resultado_evento = _preparar_baseline_y_evento(client)

    resp = client.get(
        f"/api/projects/{proyecto['id']}/timeline",
        params={"monitor_type": "fairness", "metric_key": " , ,"},
    )
    assert resp.status_code == 422, resp.text

    demasiadas = ",".join(f"m{i}" for i in range(21))
    resp = client.get(
        f"/api/projects/{proyecto['id']}/timeline",
        params={"monitor_type": "fairness", "metric_key": demasiadas},
    )
    assert resp.status_code == 422, resp.text


def test_evaluate_batch_de_otro_proyecto_409(client: TestClient, session):
    """§9.6: `POST /batches/{id}/evaluate` valida que la versión del lote sea del mismo
    proyecto que el lote; si no (integridad rota), 409 en lugar de evaluar a ciegas."""
    from vigia.app.models import Batch

    _proyecto, resultado_baseline, _resultado_evento = _preparar_baseline_y_evento(client)
    otro_proyecto = _crear_proyecto(client, name="reuma-eval-otro")

    batch = session.get(Batch, resultado_baseline["batch_id"])
    assert batch is not None
    batch.project_id = otro_proyecto["id"]
    session.add(batch)
    session.commit()

    resp = client.post(f"/api/batches/{resultado_baseline['batch_id']}/evaluate", json={})
    assert resp.status_code == 409


# --- casos añadidos ------------------------------------------------------------


def test_evento_de_evaluacion_trae_monitor_type_y_los_estados(client: TestClient):
    """Hueco 9a: el `after` de `evaluacion.completada` dice de qué monitor es la
    evaluación sin perder el estado por métrica, y llega igual por `GET /api/events`."""
    _proyecto, _, resultado_evento = _preparar_baseline_y_evento(client)
    resultado = _evaluar(client, resultado_evento["batch_id"])
    assert set(resultado["evaluations"]) == {"fairness", "quality", "drift"}

    for tipo, evaluation_id in resultado["evaluations"].items():
        resp = client.get(
            "/api/events", params={"object_type": "evaluation", "object_id": evaluation_id}
        )
        assert resp.status_code == 200, resp.text
        evento = next(e for e in resp.json()["items"] if e["action"] == "evaluacion.completada")
        assert evento["after"]["monitor_type"] == tipo

        medidas = client.get(f"/api/evaluations/{evaluation_id}").json()["measurements"]
        assert medidas
        for m in medidas:
            assert evento["after"][m["metric_key"]] == m["state"]


def test_get_evaluation_poda_lo_que_ya_va_fuera_de_result(client: TestClient, session):
    """Hueco 3: `result` no repite `measurements`, `window` ni `config_snapshot`
    (que la respuesta ya sirve en la raíz) y conserva el resto del motor."""
    _proyecto, _, resultado_evento = _preparar_baseline_y_evento(client)
    resultado = _evaluar(client, resultado_evento["batch_id"])
    fairness_id = resultado["evaluations"]["fairness"]

    cuerpo = client.get(f"/api/evaluations/{fairness_id}").json()
    result = cuerpo["result"]
    for clave in ("measurements", "window", "config_snapshot"):
        assert clave not in result
    assert result["monitor"] == "fairness"
    assert result["core_version"]
    assert "details" in result

    # lo podado sigue en la raíz de la respuesta y en la BD sin tocar
    assert cuerpo["window"]["kind"] == "ultimos_n"
    assert cuerpo["config_snapshot"]["fairness"]["min_records"] == 200
    assert cuerpo["measurements"]

    from vigia.app.models import Evaluation

    guardada = session.get(Evaluation, fairness_id)
    assert guardada is not None
    assert "measurements" in guardada.result_json
    assert "window" in guardada.result_json
    assert "config_snapshot" in guardada.result_json


def test_lista_de_evaluaciones_sigue_sin_result(client: TestClient):
    """La forma `light=True` no cambia con la poda: sin `result` ni medidas."""
    proyecto, _, resultado_evento = _preparar_baseline_y_evento(client)
    _evaluar(client, resultado_evento["batch_id"])
    items = client.get(f"/api/projects/{proyecto['id']}/evaluations").json()["items"]
    assert items
    for item in items:
        assert "result" not in item
        assert "measurements" not in item
        assert "config_snapshot" not in item


# --- El monitor explain se evalúa cuando se le -
# --- pasa explanation=, comparado contra la primera explicación global -----


def _crear_proyecto_sim_logistic(client: TestClient, name: str = "reuma-explain") -> dict:
    resp = client.post(
        "/api/projects",
        json={
            "name": name,
            "domain": "reuma",
            "model_kind": "sim_logistic",
            "store_features": True,
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_monitor_explain_por_defecto_trae_el_umbral_0_50(client: TestClient):
    """services/projects.py: la config por defecto de explain deja de ser
    `{"thresholds": []}` y trae `DEFAULT_EXPLAIN_THRESHOLDS`, como fairness,
    quality y drift."""
    proyecto = _crear_proyecto_sim_logistic(client, "reuma-explain-defaults")
    resp = client.get(f"/api/projects/{proyecto['id']}/monitors")
    assert resp.status_code == 200, resp.text
    monitor_explain = next(m for m in resp.json()["items"] if m["type"] == "explain")
    umbrales = monitor_explain["thresholds"]["thresholds"]
    assert len(umbrales) == 1
    assert umbrales[0]["metric_key"] == "explain_stability_ndcg"
    assert umbrales[0]["kind"] == "lower_limit"
    assert umbrales[0]["value"] == pytest.approx(0.50)


def test_evaluate_batch_con_explanation_evalua_el_monitor_explain(client: TestClient, session):
    """services/evaluate.py: si se pasa `explanation=` a `evaluate_batch`, se añade el
    monitor `explain` con `explain_stability_ndcg`. La primera explicación global de la
    versión no tiene referencia (`sin_datos` con motivo); la segunda se compara contra
    ella ("primera explicación global de la versión")."""
    from vigia.app.models import Batch, ModelVersion
    from vigia.app.services import evaluate as evaluate_service
    from vigia.app.services import explain as explain_service

    proyecto = _crear_proyecto_sim_logistic(client)
    baseline_ds = _subir_y_mapear(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    resultado_baseline = _ingerir(client, baseline_ds["id"])
    version_id = proyecto["active_version_id"]
    # Ingerir la línea base ya la congela; no hay POST /baseline que hacer.
    evento_ds = _subir_y_mapear(client, proyecto["id"], "02_evento_feedback.json", role="production")
    resultado_evento = _ingerir(client, evento_ds["id"])

    version = session.get(ModelVersion, version_id)
    batch_baseline = session.get(Batch, resultado_baseline["batch_id"])
    batch_evento = session.get(Batch, resultado_evento["batch_id"])

    explicacion_1 = explain_service.explain_global(
        session, version, kind="permutation", batch=batch_baseline
    )
    assert explicacion_1.available is True
    evaluaciones_1 = evaluate_service.evaluate_batch(
        session, batch_baseline, trigger="manual", explanation=explicacion_1
    )
    assert "explain" in evaluaciones_1
    medida_1 = _medida(client, evaluaciones_1["explain"].id, "explain_stability_ndcg")
    assert medida_1["state"] == "sin_datos"
    assert medida_1["value"] is None
    # sin referencia todavía, core/explain.py no publica umbral (no hay nada
    # que clasificar contra él): el umbral 0,50 se comprueba abajo, con la
    # segunda explicación, que sí tiene referencia.
    assert medida_1["threshold_low"] is None
    assert "referencia" in (medida_1["motivo"] or "")

    explicacion_2 = explain_service.explain_global(
        session, version, kind="permutation", batch=batch_evento
    )
    assert explicacion_2.available is True
    evaluaciones_2 = evaluate_service.evaluate_batch(
        session, batch_evento, trigger="manual", explanation=explicacion_2
    )
    assert "explain" in evaluaciones_2
    medida_2 = _medida(client, evaluaciones_2["explain"].id, "explain_stability_ndcg")
    assert medida_2["state"] != "sin_datos"
    assert medida_2["value"] is not None
    assert 0.0 <= medida_2["value"] <= 1.0
    assert medida_2["threshold_low"] == pytest.approx(0.50)

    detalle_2 = client.get(f"/api/evaluations/{evaluaciones_2['explain'].id}").json()
    top_referencia = detalle_2["result"]["details"]["referencia_top"]
    top_explicacion_1 = [f["feature"] for f in explicacion_1.result_json["features"][:10]]
    assert top_referencia == top_explicacion_1
