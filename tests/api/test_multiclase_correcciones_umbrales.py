"""Arreglos del backend: umbrales multiclase."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api import _datos_multiclase as d

HUMANO = {"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"}


# ---------------------------------------------------------------------------
# La equidad multiclase sale en la propuesta de umbrales
# ---------------------------------------------------------------------------


def test_la_propuesta_multiclase_lista_la_equidad_y_ahora_es_la_propuesta_de_la_linea_base(client: TestClient):
    """Con conjunto favorable, la equidad sobre el 0/1 de
    pertenencia es `proponer_umbrales(fairness)`, la binaria; ya no es la lista de los
    umbrales de hoy con el motivo «no tiene propuesta»."""
    proyecto, _s, _t = d.linea_base_multiclase(client, "a-229", n=600)
    resp = client.get(f"/api/projects/{proyecto['id']}/thresholds/proposal")
    assert resp.status_code == 200, resp.text
    por_monitor = {m["monitor_type"]: m["propuestas"] for m in resp.json()["monitors"]}
    assert set(por_monitor) == {"quality", "drift", "fairness"}
    detalle = client.get(f"/api/projects/{proyecto['id']}").json()
    equidad = next(m for m in detalle["monitors"] if m["type"] == "fairness")
    hoy = {(t["metric_key"], t["kind"]): t for t in equidad["thresholds"]["thresholds"]}
    filas = por_monitor["fairness"]
    assert {(f["metric_key"], f["kind"]) for f in filas} == set(hoy)
    for f in filas:
        actual = hoy[(f["metric_key"], f["kind"])]
        assert f["umbral_actual"] == actual["value"]
        assert f["origen_actual"] == (actual.get("origen") or "fabrica")
        assert "la equidad no tiene propuesta desde la línea base" not in (f["motivo"] or "")
        assert "En multiclase la equidad no tiene propuesta" not in (f["motivo"] or "")
    # La calidad y la deriva siguen igual que antes.
    assert {p["metric_key"] for p in por_monitor["drift"]} == {"prediction_drift_score"}
    assert {"accuracy", "f1_measure", "area_under_roc"} <= {p["metric_key"] for p in por_monitor["quality"]}


def test_la_propuesta_binaria_no_cambia(client: TestClient):
    creada = client.post(
        "/api/demo/runs", json={"scenario_key": "timeline_completo", "with_human": False}, headers=HUMANO
    )
    assert creada.status_code == 200, creada.text
    client.post(f"/api/demo/runs/{creada.json()['id']}/play", json={}, headers=HUMANO)
    prop = client.get(f"/api/projects/{creada.json()['project_id']}/thresholds/proposal")
    assert prop.status_code == 200, prop.text
    assert [m["monitor_type"] for m in prop.json()["monitors"]] == ["fairness", "quality"]
    assert all(
        "la equidad no tiene propuesta" not in (p["motivo"] or "")
        for m in prop.json()["monitors"]
        for p in m["propuestas"]
    )


# ---------------------------------------------------------------------------
# El monitor de calidad multiclase nace sin umbrales de fábrica
# ---------------------------------------------------------------------------


def _umbrales_de(proyecto: dict, tipo: str) -> list[dict]:
    monitor = next(m for m in proyecto["monitors"] if m["type"] == tipo)
    return monitor["thresholds"]["thresholds"]


def test_el_alta_multiclase_no_guarda_umbrales_de_calidad_y_el_binario_si(client: TestClient):
    multi = d.crear_proyecto_multiclase(client, "a-215-multi")
    assert _umbrales_de(multi, "quality") == []
    # Los demás monitores conservan sus umbrales (la deriva no cambia).
    assert any(t["metric_key"] == "prediction_drift_score" for t in _umbrales_de(multi, "drift"))
    assert any(t["metric_key"] == "fairness_value" for t in _umbrales_de(multi, "fairness"))
    binario = client.post("/api/projects", json={"name": "a-215-bin"}, headers=HUMANO).json()
    claves = {t["metric_key"] for t in _umbrales_de(binario, "quality")}
    assert {"accuracy", "area_under_roc", "area_under_pr", "recall", "log_loss"} <= claves
    pr = next(t for t in _umbrales_de(binario, "quality") if t["metric_key"] == "area_under_pr")
    assert pr["relativo_a"] == "prevalencia"


def test_la_linea_base_anade_los_tres_titulares_con_origen_linea_base(client: TestClient):
    proyecto, _s, _t = d.linea_base_multiclase(client, "a-215-base", n=600)
    umbrales = _umbrales_de(client.get(f"/api/projects/{proyecto['id']}").json(), "quality")
    assert {t["metric_key"] for t in umbrales} == {"accuracy", "f1_measure", "area_under_roc"}
    assert {t["origen"] for t in umbrales} == {"linea_base"}


def test_los_titulares_siguen_en_sin_datos_antes_de_la_linea_base():
    """Con el monitor de calidad recién creado (sin umbrales), el motor da lo mismo que
    daba con los de fábrica: los tres titulares en `sin_datos` con su motivo."""
    from tests.core._datos_multiclase import canonico, historia, tarea
    from vigia.core.quality import evaluate_quality
    from vigia.core.schema import MonitorThresholds, QualityConfig, State

    sin_umbrales = MonitorThresholds(thresholds=[])
    res = evaluate_quality(
        historia(canonico(300, seed=1)),
        batch_seq=0,
        config=QualityConfig(),
        thresholds=sin_umbrales,
        task=tarea(),
    )
    por_clave = {m.metric_key: m for m in res.measurements if m.group_code is None}
    for clave in ("accuracy", "f1_measure", "area_under_roc"):
        assert por_clave[clave].state == State.sin_datos
        assert por_clave[clave].motivo == "umbral pendiente de la línea base"
    assert por_clave["area_under_pr"].state == State.ok  # sin umbral, se publica
    assert por_clave["area_under_pr"].threshold_low is None
