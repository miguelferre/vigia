"""Ingesta y evaluación multiclase de punta a punta.

Dependen del motor (`to_canonical` con `task=`, `avisos_clases`,
calidad multiclase, calibración).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api import _datos_multiclase as d
from tests.api.conftest import actor_headers
from vigia.app.models import Event, Monitor, Record


def _records(client: TestClient, proyecto_id: int) -> list[Record]:
    with Session(client.app.state.engine) as s:
        return list(
            s.exec(select(Record).where(Record.project_id == proyecto_id).order_by(Record.seq)).all()
        )


def _eventos(client: TestClient, accion: str, proyecto_id: int | None = None) -> list[Event]:
    with Session(client.app.state.engine) as s:
        consulta = select(Event).where(Event.action == accion)
        if proyecto_id is not None:
            consulta = consulta.where(Event.project_id == proyecto_id)
        return list(s.exec(consulta).all())


# ---------------------------------------------------------------------------
# Lo que se guarda al ingerir
# ---------------------------------------------------------------------------


def test_la_ingesta_guarda_clase_predicha_clase_real_y_probabilidades(client: TestClient):
    proyecto, _subida, _trabajo = d.linea_base_multiclase(client, "r4-guarda", n=300)
    filas = _records(client, proyecto["id"])
    assert len(filas) == 300
    fila = filas[0]
    assert fila.prediction_class in d.CLASES and fila.label_class in d.CLASES
    assert isinstance(fila.probabilities_json, list) and len(fila.probabilities_json) == 5
    assert abs(sum(fila.probabilities_json) - 1.0) < 1e-3
    # Prediction y label son el 0/1 de pertenencia al conjunto favorable ("permitido").
    assert all(f.prediction == int(f.prediction_class == "permitido") for f in filas)
    assert all(f.label == float(f.label_class == "permitido") for f in filas)
    # prob_favorable es la suma de las probabilidades del conjunto favorable.
    assert filas[0].prob_favorable == pytest.approx(fila.probabilities_json[0], abs=1e-6)
    # Las columnas canónicas nuevas no se guardan como variables del modelo.
    assert set(fila.features_json) == {"longitud", "enlaces"}


def test_la_api_de_registros_enseña_la_clase_y_las_probabilidades(client: TestClient):
    _p, _s, trabajo = d.linea_base_multiclase(client, "r4-api-registros", n=60)
    items = client.get(f"/api/batches/{trabajo['result']['batch_id']}/records").json()["items"]
    assert items[0]["prediction_class"] in d.CLASES
    assert len(items[0]["probabilities"]) == 5
    assert items[0]["label_class"] in d.CLASES


def test_un_proyecto_binario_no_guarda_clase_ni_probabilidades(client: TestClient):
    p = client.post(
        "/api/projects", json={"name": "r4-bin-registros"}, headers=actor_headers("miguel")
    ).json()
    sub = d.subir(client, p["id"], b"id,prediction,label\n1,0,0\n2,1,1\n3,1,0\n", rol="production")
    d.mapear(
        client,
        sub["dataset"]["id"],
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": 1},
    )
    d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])
    for fila in _records(client, p["id"]):
        assert fila.prediction_class is None and fila.label_class is None
        assert fila.probabilities_json is None


# ---------------------------------------------------------------------------
# Clases fijadas al congelar la línea base
# ---------------------------------------------------------------------------


def test_la_linea_base_fija_las_clases_y_anota_el_soporte(client: TestClient):
    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-clases-fijadas", n=300)
    leido = client.get(f"/api/projects/{proyecto['id']}").json()
    assert leido["classes"] == d.CLASES
    eventos = _eventos(client, "proyecto.clases_fijadas", proyecto["id"])
    assert eventos
    ultimo = eventos[-1].after_json
    assert ultimo["classes"] == d.CLASES
    assert sum(ultimo["soporte"].values()) == 300
    assert set(ultimo["soporte"]) == set(d.CLASES)


def test_las_clases_salen_del_mapeo_de_la_linea_base_si_el_alta_no_las_traia(
    client: TestClient,
):
    p = client.post(
        "/api/projects",
        json={"name": "r4-clases-de-la-base", "task_type": "multiclass"},
        headers=actor_headers("miguel"),
    ).json()
    assert p["classes"] is None
    sub = d.subir(client, p["id"], d.a_csv(d.filas_multiclase(200)))
    assert d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase()).status_code == 200
    d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])
    assert client.get(f"/api/projects/{p['id']}").json()["classes"] == d.CLASES


def test_una_clase_declarada_sin_filas_se_conserva_con_soporte_cero_y_aviso(
    client: TestClient,
):
    clases = [*d.CLASES, "acoso"]
    filas = d.filas_multiclase(300)
    for f in filas:  # la sexta clase no aparece nunca, pero el modelo da su columna
        f["prob_acoso"] = 0.0
    p = d.crear_proyecto_multiclase(client, "r4-clase-sin-filas", clases=clases)
    sub = d.subir(client, p["id"], d.a_csv(filas))
    assert d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase(clases)).status_code == 200
    trabajo = d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])
    assert trabajo["status"] == "terminado", trabajo
    assert any("acoso" in a for a in trabajo["result"]["avisos"]), trabajo["result"]["avisos"]
    assert client.get(f"/api/projects/{p['id']}").json()["classes"] == clases
    soporte = _eventos(client, "proyecto.clases_fijadas", p["id"])[-1].after_json["soporte"]
    assert soporte["acoso"] == 0 and soporte["permitido"] > 0


def test_un_mapeo_con_otras_clases_que_las_del_proyecto_da_422(client: TestClient):
    p = d.crear_proyecto_multiclase(client, "r4-clases-distintas")
    sub = d.subir(client, p["id"], d.a_csv(d.filas_multiclase(60)))
    resp = d.mapear(
        client,
        sub["dataset"]["id"],
        d.mapeo_multiclase(d.CLASES, classes=["permitido", "spam", "odio", "desnudez", "otra"]),
    )
    assert resp.status_code == 422
    assert "no coinciden" in resp.text


def test_un_lote_posterior_hereda_las_clases_y_no_las_cambia(client: TestClient):
    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-lote-posterior", n=200)
    sub = d.subir(client, proyecto["id"], d.a_csv(d.filas_multiclase(120, seed=99, prefijo_id="q")), rol="production")
    # Un mapeo sin `classes` ni `favorable_label` las hereda del proyecto.
    mapeo = d.mapeo_multiclase()
    del mapeo["classes"], mapeo["favorable_label"]
    resp = d.mapear(client, sub["dataset"]["id"], mapeo)
    assert resp.status_code == 200, resp.text
    assert resp.json()["mapping"]["classes"] == d.CLASES
    assert resp.json()["mapping"]["favorable_label"] == ["permitido"]
    trabajo = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"])
    assert trabajo["status"] == "terminado", trabajo
    assert client.get(f"/api/projects/{proyecto['id']}").json()["classes"] == d.CLASES


# ---------------------------------------------------------------------------
# Clases desconocidas y etiquetas de texto
# ---------------------------------------------------------------------------


def test_una_prediccion_con_clase_nueva_da_422_y_no_gasta_el_fichero(client: TestClient):
    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-prediccion-nueva", n=200)
    filas = d.filas_multiclase(60, seed=3, prefijo_id="n")
    filas[5]["prediction"] = "terrorismo"
    sub = d.subir(client, proyecto["id"], d.a_csv(filas), rol="production")
    mapeo = d.mapeo_multiclase()
    resp = d.mapear(client, sub["dataset"]["id"], mapeo)
    assert resp.status_code == 422, resp.text
    assert "terrorismo" in resp.text
    assert "no está entre las clases del proyecto" in resp.text
    assert "créala" in resp.text
    # El dataset sigue ahí, sin gastar, y se puede corregir el fichero.
    assert client.get(f"/api/datasets/{sub['dataset']['id']}").json()["status"] == "subido"


def test_una_prediccion_con_clase_nueva_tambien_falla_al_ingerir_si_el_mapeo_se_guardo_antes(
    client: TestClient,
):
    """Red de seguridad: `to_canonical` repite la comprobación del `PUT`."""
    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-prediccion-nueva-red", n=200)
    sub = d.subir(client, proyecto["id"], d.a_csv(d.filas_multiclase(40, seed=4, prefijo_id="r")), rol="production")
    assert d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase()).status_code == 200
    # El fichero cambia en disco entre el mapeo y la ingesta.
    from pathlib import Path

    from vigia.app.models import Dataset

    with Session(client.app.state.engine) as s:
        ruta = Path(s.get(Dataset, sub["dataset"]["id"]).file_path)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace(",permitido,", ",inventada,", 1), encoding="utf-8"
    )
    resp = client.post(
        f"/api/datasets/{sub['dataset']['id']}/ingest",
        json={"model_version_id": proyecto["active_version_id"], "evaluate": False},
    )
    cuerpo = resp.json()
    assert resp.status_code != 200 or cuerpo.get("status") == "error", cuerpo
    assert "inventada" in str(cuerpo)


def test_una_etiqueta_con_clase_nueva_no_bloquea_y_se_avisa(client: TestClient):
    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-etiqueta-nueva", n=200)
    filas = d.filas_multiclase(80, seed=5, prefijo_id="e")
    filas[3]["label"] = "terrorismo"
    filas[9]["label"] = "terrorismo"
    sub = d.subir(client, proyecto["id"], d.a_csv(filas), rol="production")
    assert d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase()).status_code == 200
    trabajo = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"])
    assert trabajo["status"] == "terminado", trabajo
    assert any("terrorismo" in a for a in trabajo["result"]["avisos"]), trabajo["result"]["avisos"]
    nuevas = [
        f
        for f in _records(client, proyecto["id"])
        if f.label_class == "terrorismo"
    ]
    assert len(nuevas) == 2
    # Fuera de la calidad: la etiqueta 0/1 queda vacía.
    assert all(f.label is None for f in nuevas)


def test_las_etiquetas_con_mayusculas_o_espacios_se_asignan_a_su_clase(client: TestClient):
    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-etiqueta-mayuscula", n=200)
    filas = d.filas_multiclase(60, seed=6, prefijo_id="x")
    filas[0]["label"] = "Spam"
    filas[1]["label"] = " spam"
    sub = d.subir(client, proyecto["id"], d.a_csv(filas), rol="production")
    assert d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase()).status_code == 200
    trabajo = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"])
    assert trabajo["status"] == "terminado", trabajo
    por_id = {f.external_id: f for f in _records(client, proyecto["id"])}
    assert por_id["x0"].label_class == "spam" and por_id["x1"].label_class == "spam"
    assert por_id["x0"].label == 0.0  # spam no es favorable
    # El aviso nombra la asignación (texto original y clase), no solo la clase.
    assert any(
        "sin distinguir mayúsculas" in a and "«Spam» a spam" in a for a in trabajo["result"]["avisos"]
    )


def test_el_feedback_tardio_asigna_la_clase_sin_mayusculas(client: TestClient):
    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-feedback-clases", n=100)
    sub = d.subir(client, proyecto["id"], d.a_csv(d.filas_multiclase(40, seed=8, prefijo_id="f", etiquetas=False)), rol="production")
    mapeo = d.mapeo_multiclase()
    assert d.mapear(client, sub["dataset"]["id"], mapeo).status_code == 200
    d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"])
    fb = d.subir(
        client,
        proyecto["id"],
        b"id,label\nf0,Spam\nf1,permitido\nf2,inventada\n",
        rol="production",
        kind="feedback",
        nombre="fb.csv",
    )
    assert d.mapear(client, fb["dataset"]["id"], {"label_col": "label", "id_col": "id"}).status_code == 200
    trabajo = d.ingerir(client, fb["dataset"]["id"], proyecto["active_version_id"])
    assert trabajo["status"] == "terminado", trabajo
    assert trabajo["result"]["n_matched"] == 3
    por_id = {f.external_id: f for f in _records(client, proyecto["id"]) if f.external_id.startswith("f")}
    assert por_id["f0"].label_class == "spam" and por_id["f0"].label == 0.0
    assert por_id["f1"].label_class == "permitido" and por_id["f1"].label == 1.0
    assert por_id["f2"].label_class == "inventada" and por_id["f2"].label is None
    assert any("inventada" in a for a in trabajo["result"]["avisos"])
    assert any(
        "sin distinguir mayúsculas" in a and "«Spam» a spam" in a for a in trabajo["result"]["avisos"]
    )


# ---------------------------------------------------------------------------
# Sugerencia de mapeo
# ---------------------------------------------------------------------------


def test_la_sugerencia_propone_probability_cols_y_classes_con_cinco_clases(client: TestClient):
    p = d.crear_proyecto_multiclase(client, "r4-sugerencia", mapping_template=None)
    sub = d.subir(client, p["id"], d.a_csv(d.filas_multiclase(120)))
    sugerido = sub["dataset"]["suggested_mapping"]
    assert sugerido["probability_cols"] == [f"prob_{c}" for c in d.CLASES]
    assert sugerido["classes"] == d.CLASES
    assert sugerido["probability_col"] is None
    assert sugerido["favorable_label"] is None
    assert sugerido["prediction_col"] == "prediction" and sugerido["label_col"] == "label"


def test_sin_columnas_prob_las_clases_salen_de_la_prediccion_y_la_etiqueta(client: TestClient):
    p = d.crear_proyecto_multiclase(client, "r4-sugerencia-sin-prob", mapping_template=None)
    filas = d.filas_multiclase(90)
    for f in filas:
        for c in d.CLASES:
            del f[f"prob_{c}"]
    sub = d.subir(client, p["id"], d.a_csv(filas))
    sugerido = sub["dataset"]["suggested_mapping"]
    assert sugerido["probability_cols"] == []
    assert sugerido["classes"] == sorted(d.CLASES)


def test_una_produccion_no_propone_clases_y_un_binario_no_propone_nada_nuevo(client: TestClient):
    p = d.crear_proyecto_multiclase(client, "r4-sugerencia-prod", mapping_template=None)
    sub = d.subir(client, p["id"], d.a_csv(d.filas_multiclase(60)), rol="production")
    assert sub["dataset"]["suggested_mapping"]["classes"] == []
    b = client.post("/api/projects", json={"name": "r4-sug-bin"}, headers=actor_headers("miguel")).json()
    sub_b = d.subir(client, b["id"], b"id,prediction,probability,label\n1,0,0.2,0\n2,1,0.8,1\n")
    sug_b = sub_b["dataset"]["suggested_mapping"]
    assert sug_b["classes"] == [] and sug_b["probability_cols"] == []
    assert sug_b["favorable_label"] == 1 and sug_b["probability_col"] == "probability"


# ---------------------------------------------------------------------------
# La cardinalidad
# ---------------------------------------------------------------------------


def test_en_multiclase_no_sale_el_aviso_de_cardinalidad(client: TestClient):
    _p, _s, trabajo = d.linea_base_multiclase(client, "r4-sin-cardinalidad", n=120)
    assert not any("modelos binarios" in a for a in trabajo["result"]["avisos"])


def test_en_binario_con_tres_clases_el_aviso_remite_al_tipo_multiclase(client: TestClient):
    p = client.post("/api/projects", json={"name": "r4-bin-3clases"}, headers=actor_headers("miguel")).json()
    filas = "id,prediction,label\n" + "\n".join(f"{i},{i % 3},{i % 3}" for i in range(9))
    sub = d.subir(client, p["id"], filas.encode(), rol="production")
    d.mapear(
        client,
        sub["dataset"]["id"],
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": 1},
    )
    avisos = d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])["result"]["avisos"]
    assert any("modelos binarios" in a and "multiclase" in a for a in avisos), avisos


# ---------------------------------------------------------------------------
# Umbrales de la línea base al congelar
# ---------------------------------------------------------------------------

def _umbrales(client: TestClient, proyecto_id: int, tipo: str) -> dict:
    with Session(client.app.state.engine) as s:
        monitor = s.exec(
            select(Monitor).where(Monitor.project_id == proyecto_id, Monitor.type == tipo)
        ).one()
        return {
            (t["metric_key"], t["kind"]): t for t in (monitor.thresholds_json or {}).get("thresholds", [])
        }


def test_al_congelar_se_aplican_los_umbrales_de_la_linea_base(client: TestClient):
    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-umbrales", n=600)
    calidad = _umbrales(client, proyecto["id"], "quality")
    deriva = _umbrales(client, proyecto["id"], "drift")
    titulares = {k: v for k, v in calidad.items() if k[0] in ("accuracy", "f1_measure", "area_under_roc")}
    assert {k[0] for k in titulares} == {"accuracy", "f1_measure", "area_under_roc"}
    assert all(v.get("origen") == "linea_base" for v in titulares.values())
    # Suelo de 1/k en la exactitud.
    exactitud = next(v for k, v in titulares.items() if k[0] == "accuracy")
    assert exactitud["value"] >= 1 / 5
    assert any(k[0] == "prediction_drift_score" and v.get("origen") == "linea_base" for k, v in deriva.items())
    # Y el evento, con su título.
    eventos = _eventos(client, "proyecto.umbrales_linea_base_aplicados", proyecto["id"])
    assert len(eventos) == 1 and eventos[0].after_json["umbrales"]
    titulos = client.get("/api/events", params={"project_id": proyecto["id"], "limit": 500}).json()["items"]
    assert any(t["titulo"].startswith("Umbrales propuestos desde la línea base aplicados") for t in titulos)
    # El título dice cuántos umbrales, sin las claves crudas.
    titulo = next(t["titulo"] for t in titulos if t["titulo"].startswith("Umbrales propuestos"))
    assert titulo.endswith("umbrales)") and "quality" not in titulo and "accuracy" not in titulo


def test_un_umbral_fijado_por_una_persona_no_se_pisa(client: TestClient):
    p = d.crear_proyecto_multiclase(client, "r4-umbral-persona")
    calidad = next(m for m in p["monitors"] if m["type"] == "quality")
    resp = client.patch(
        f"/api/monitors/{calidad['id']}",
        json={
            "actor": "miguel",
            "motivo": "política",
            "thresholds": {
                "thresholds": [
                    {"metric_key": "accuracy", "kind": "lower_limit", "value": 0.9, "origen": "politica_organizacion"}
                ]
            },
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    sub = d.subir(client, p["id"], d.a_csv(d.filas_multiclase(600)))
    assert d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase()).status_code == 200
    d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])
    exactitud = _umbrales(client, p["id"], "quality")[("accuracy", "lower_limit")]
    assert exactitud["value"] == 0.9 and exactitud["origen"] == "politica_organizacion"
    evento = _eventos(client, "proyecto.umbrales_linea_base_aplicados", p["id"])[0]
    assert any("accuracy" in c for c in evento.after_json["conservados"])


# ---------------------------------------------------------------------------
# Medidas por clase y set_monitor
# ---------------------------------------------------------------------------


def test_set_monitor_rechaza_un_umbral_sobre_una_medida_por_clase(client: TestClient):
    p = d.crear_proyecto_multiclase(client, "r4-umbral-por-clase")
    calidad = next(m for m in p["monitors"] if m["type"] == "quality")
    resp = client.patch(
        f"/api/monitors/{calidad['id']}",
        json={
            "actor": "miguel",
            "motivo": "probar",
            "thresholds": {
                "thresholds": [
                    {
                        "metric_key": "recall",
                        "kind": "lower_limit",
                        "value": 0.5,
                        "group_code": "clase:spam",
                    }
                ]
            },
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422
    assert "medidas por clase no tienen umbral" in resp.text


def test_un_umbral_normal_sigue_funcionando(client: TestClient):
    p = d.crear_proyecto_multiclase(client, "r4-umbral-normal")
    calidad = next(m for m in p["monitors"] if m["type"] == "quality")
    resp = client.patch(
        f"/api/monitors/{calidad['id']}",
        json={
            "actor": "miguel",
            "motivo": "probar",
            "thresholds": {"thresholds": [{"metric_key": "f1_measure", "kind": "lower_limit", "value": 0.6}]},
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text


def test_un_umbral_absoluto_de_area_under_pr_reemplaza_al_relativo(client: TestClient):
    """Fusión de `set_monitor` por `(metric_key, kind)`: el umbral fijado a mano no
    arrastra `relativo_a`."""
    from vigia.mcp.tools_monitores import _fusionar_umbrales

    actual = {
        "thresholds": [
            {"metric_key": "area_under_pr", "kind": "lower_limit", "value": 0.8, "relativo_a": "prevalencia"},
            {"metric_key": "accuracy", "kind": "lower_limit", "value": 0.7},
        ]
    }
    nuevo = {"thresholds": [{"metric_key": "area_under_pr", "kind": "lower_limit", "value": 0.55}]}
    fusion = _fusionar_umbrales(actual, nuevo)
    pr = next(t for t in fusion["thresholds"] if t["metric_key"] == "area_under_pr")
    assert pr == {"metric_key": "area_under_pr", "kind": "lower_limit", "value": 0.55}
    assert any(t["metric_key"] == "accuracy" for t in fusion["thresholds"])
    # Y la API lo guarda sin `relativo_a`.
    p = client.post("/api/projects", json={"name": "r4-pr-absoluto"}, headers=actor_headers("miguel")).json()
    calidad = next(m for m in p["monitors"] if m["type"] == "quality")
    client.patch(
        f"/api/monitors/{calidad['id']}",
        json={"actor": "miguel", "motivo": "relativo", "thresholds": actual},
        headers=actor_headers("miguel"),
    )
    resp = client.patch(
        f"/api/monitors/{calidad['id']}",
        json={"actor": "miguel", "motivo": "absoluto", "thresholds": fusion},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    guardado = next(
        t for t in resp.json()["monitor"]["thresholds"]["thresholds"] if t["metric_key"] == "area_under_pr"
    )
    assert "relativo_a" not in guardado and guardado["value"] == 0.55


# ---------------------------------------------------------------------------
# Evaluación (depende del motor)
# ---------------------------------------------------------------------------


def test_la_evaluacion_multiclase_corre_y_deja_la_matriz_k_por_k(client: TestClient):
    proyecto, _s, trabajo = d.linea_base_multiclase(client, "r4-evalua", n=600, evaluar=True)
    batch_id = trabajo["result"]["batch_id"]
    evaluaciones = client.get(
        f"/api/projects/{proyecto['id']}/evaluations", params={"batch_id": batch_id, "monitor_type": "quality"}
    ).json()["items"]
    calidad = evaluaciones[0]
    detalle = client.get(f"/api/evaluations/{calidad['id']}").json()
    matriz = detalle["result"]["details"]["confusion_matrix"]
    assert matriz["classes"] == d.CLASES
    assert len(matriz["matrix"]) == 5 and all(len(f) == 5 for f in matriz["matrix"])


def test_la_comparacion_de_versiones_lee_las_medidas_por_clase(client: TestClient, session: Session):
    from tests.api.comparacion_util import (
        comparar,
        congelar_base,
        fila,
        lote,
        medida,
        proyecto,
        version_nueva,
    )

    pid, v1 = proyecto(client, session, "r4-compara-clases")
    v2 = version_nueva(session, pid)
    b1, p1 = lote(session, pid, v1, 0), lote(session, pid, v1, 1)
    b2, p2 = lote(session, pid, v2, 2), lote(session, pid, v2, 3)
    congelar_base(session, v1, b1)
    congelar_base(session, v2, b2)
    for v, base, prod, recall_spam, recall_odio in ((v1, b1, p1, 0.60, 0.80), (v2, b2, p2, 0.75, 0.50)):
        for lote_id in (base, prod):
            medida(session, pid, v, lote_id, "quality", "recall", recall_spam, group="clase:spam", n=100)
            medida(session, pid, v, lote_id, "quality", "recall", recall_odio, group="clase:odio", n=100)
            medida(session, pid, v, lote_id, "quality", "n", 100.0, group="clase:spam")
    d = comparar(client, pid, a=v1, b=v2)
    spam = fila(d, "recall", "clase:spam")
    odio = fila(d, "recall", "clase:odio")
    assert spam["direccion"] == "mejora" and odio["direccion"] == "empeora"
    assert spam["threshold_low"] is None and "más alto es mejor" in spam["motivo"]
    # El recuento de la clase no es mejor ni peor: no entra en la tabla.
    assert not [f for f in d["filas"] if f["metric_key"] == "n"]


def test_las_columnas_de_probabilidad_en_otro_orden_se_detectan_con_la_prediccion(
    client: TestClient,
):
    """La clase de mayor probabilidad no coincide con la predicción del fichero."""
    p = d.crear_proyecto_multiclase(client, "r4-orden-probabilidades")
    sub = d.subir(client, p["id"], d.a_csv(d.filas_multiclase(300)))
    columnas = [f"prob_{c}" for c in d.CLASES]
    # Mismas columnas, declaradas en otro orden que `classes`.
    mapeo = d.mapeo_multiclase(probability_cols=[columnas[1], columnas[0], *columnas[2:]])
    assert d.mapear(client, sub["dataset"]["id"], mapeo).status_code == 200
    trabajo = d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])
    assert trabajo["status"] == "terminado", trabajo
    avisos = [a for a in trabajo["result"]["avisos"] if "no cuadran con la predicción" in a]
    assert avisos and "corrige el orden" in avisos[0] and "permitido, spam" in avisos[0]


def test_con_el_orden_bien_declarado_no_hay_aviso(client: TestClient):
    _p, _s, trabajo = d.linea_base_multiclase(client, "r4-orden-bien", n=300)
    assert not any("no cuadran" in a for a in trabajo["result"]["avisos"])


def test_las_medidas_por_clase_no_cuentan_como_comprobaciones_del_resumen(client: TestClient):
    """`checks_by_state` del resumen cuenta comprobaciones con umbral; una clase rara en
    `sin_datos` no es una comprobación fallida."""
    from vigia.app.models import Measurement
    from vigia.core.schema import PREFIJO_GRUPO_CLASE

    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-checks-clases", n=600, evaluar=True)
    resumen = client.get("/api/projects", params={"summary": "true"}).json()["items"][0]["summary"]
    checks = resumen["last_batch"]["checks_by_state"]["quality"]
    with Session(client.app.state.engine) as s:
        medidas = s.exec(
            select(Measurement).where(
                Measurement.project_id == proyecto["id"], Measurement.monitor_type == "quality"
            )
        ).all()
    por_clase = [m for m in medidas if (m.group_code or "").startswith(PREFIJO_GRUPO_CLASE)]
    assert por_clase, "el motor debería publicar medidas por clase"
    # Cada evaluación de calidad del lote suma solo las medidas que no son por clase.
    assert sum(checks.values()) == len([m for m in medidas if m not in por_clase])


# ---------------------------------------------------------------------------
# Formato lista y bordes
# ---------------------------------------------------------------------------


def _ingerir_fichero(client: TestClient, nombre: str, filas: list[dict], mapeo: dict) -> tuple[dict, dict]:
    p = d.crear_proyecto_multiclase(client, nombre)
    sub = d.subir(client, p["id"], d.a_csv(filas))
    assert d.mapear(client, sub["dataset"]["id"], mapeo).status_code == 200
    return p, d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])


def _csv_con_lista(filas: list[dict], acortar: int | None = None) -> bytes:
    import csv
    import io
    import json

    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(["id", "prediction", "label", "probs", "longitud", "enlaces"])
    for i, f in enumerate(filas):
        lista = [f[f"prob_{c}"] for c in d.CLASES]
        if i == acortar:
            lista = lista[:4]
        escritor.writerow(
            [f["id"], f["prediction"], f["label"], json.dumps(lista), f["longitud"], f["enlaces"]]
        )
    return salida.getvalue().encode("utf-8")


def test_probabilidades_que_no_suman_uno_dan_un_aviso_de_suma(client: TestClient):
    filas = d.filas_multiclase(200)
    for f in filas:
        f["prob_spam"] = 0.9  # cada fila suma bastante más que 1
    _p, trabajo = _ingerir_fichero(client, "r4-suma-mala", filas, d.mapeo_multiclase())
    assert trabajo["status"] == "terminado", trabajo
    avisos = [a for a in trabajo["result"]["avisos"] if "no suman 1" in a]
    assert avisos and "suma media" in avisos[0]


def test_probabilidades_normalizadas_no_dan_aviso_de_suma(client: TestClient):
    _p, _s, trabajo = d.linea_base_multiclase(client, "r4-suma-bien", n=200)
    assert not any("no suman 1" in a for a in trabajo["result"]["avisos"])


def test_una_probabilidad_vacia_no_da_500_y_el_mensaje_esta_en_espanol(client: TestClient):
    filas = d.filas_multiclase(120)
    filas[3]["prob_odio"] = ""
    _p, trabajo = _ingerir_fichero(client, "r4-prob-nan", filas, d.mapeo_multiclase())
    assert trabajo["status"] != "terminado", trabajo
    texto = str(trabajo)
    assert "Traceback" not in texto and "KeyError" not in texto


def test_una_lista_de_probabilidades_de_otra_longitud_da_error_en_espanol(client: TestClient):
    p = d.crear_proyecto_multiclase(client, "r4-lista-corta")
    sub = d.subir(client, p["id"], _csv_con_lista(d.filas_multiclase(60), acortar=7))
    mapeo = d.mapeo_multiclase(probability_cols=[], probability_col="probs", probability_format="list")
    assert d.mapear(client, sub["dataset"]["id"], mapeo).status_code == 200
    trabajo = d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])
    assert trabajo["status"] != "terminado", trabajo
    assert "valores" in str(trabajo) and "Traceback" not in str(trabajo)


def test_formato_lista_de_probabilidades_se_ingiere_en_multiclase(client: TestClient):
    p = d.crear_proyecto_multiclase(client, "r4-lista-ok")
    sub = d.subir(client, p["id"], _csv_con_lista(d.filas_multiclase(80)))
    mapeo = d.mapeo_multiclase(probability_cols=[], probability_col="probs", probability_format="list")
    assert d.mapear(client, sub["dataset"]["id"], mapeo).status_code == 200
    trabajo = d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])
    assert trabajo["status"] == "terminado", trabajo
    fila = _records(client, p["id"])[0]
    assert len(fila.probabilities_json) == 5


def test_una_prediccion_con_otras_mayusculas_da_422(client: TestClient):
    """La predicción no se normaliza por mayúsculas (solo la etiqueta)."""
    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-prediccion-mayuscula", n=150)
    filas = d.filas_multiclase(40, seed=5, prefijo_id="q")
    filas[2]["prediction"] = "Spam"
    sub = d.subir(client, proyecto["id"], d.a_csv(filas), rol="production")
    resp = d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase())
    assert resp.status_code == 422, resp.text
    assert "Spam" in resp.text


def test_sin_conjunto_favorable_se_ingiere_y_evalua_sin_500(client: TestClient):
    p = d.crear_proyecto_multiclase(client, "r4-sin-favorable", mapping_template=None)
    sub = d.subir(client, p["id"], d.a_csv(d.filas_multiclase(300)))
    mapeo = d.mapeo_multiclase(favorable_label=[])
    assert d.mapear(client, sub["dataset"]["id"], mapeo).status_code == 200
    trabajo = d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])
    assert trabajo["status"] == "terminado", trabajo
    resp = client.post(
        f"/api/batches/{trabajo['result']['batch_id']}/evaluate", json={}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.json()


def test_una_clase_rara_de_pocas_filas_evalua_sin_error(client: TestClient):
    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-clase-rara", n=400, evaluar=True)
    filas = d.filas_multiclase(150, seed=21, prefijo_id="r", prevalencia=[0.9, 0.04, 0.03, 0.02, 0.01])
    sub = d.subir(client, proyecto["id"], d.a_csv(filas), rol="production")
    assert d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase()).status_code == 200
    trabajo = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"], evaluar=True)
    assert trabajo["status"] == "terminado", trabajo


def test_la_propuesta_de_umbrales_en_multiclase_tiene_la_forma_de_la_binaria(client: TestClient):
    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-propuesta", n=400)
    resp = client.get(f"/api/projects/{proyecto['id']}/thresholds/proposal", params={"tamano_lote": 200})
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert set(cuerpo) >= {"baseline_batch_id", "tamano_lote", "monitors"}
    assert cuerpo["tamano_lote"] == 200
    por_monitor = {m["monitor_type"]: m["propuestas"] for m in cuerpo["monitors"]}
    assert set(por_monitor) == {"quality", "drift", "fairness"}  # La equidad, con sus umbrales de hoy
    claves = {p["metric_key"] for lista in por_monitor.values() for p in lista}
    assert {"accuracy", "f1_measure", "area_under_roc", "prediction_drift_score"} <= claves
    for lista in por_monitor.values():
        for p in lista:
            assert set(p) >= {"metric_key", "kind", "value", "motivo", "umbral_actual", "origen_actual"}
    exactitud = next(p for p in por_monitor["quality"] if p["metric_key"] == "accuracy")
    assert exactitud["value"] >= 1 / 3  # suelo 1/k (k = 3 o más clases del caso)
    # Solo lee: no cambia ningún monitor.
    antes = _umbrales(client, proyecto["id"], "quality")
    assert client.get(f"/api/projects/{proyecto['id']}/thresholds/proposal").status_code == 200
    assert _umbrales(client, proyecto["id"], "quality") == antes


def test_la_propuesta_multiclase_es_la_que_se_aplico_al_congelar(client: TestClient):
    """La propuesta y el congelado usan la misma función: con el mismo tamaño de lote la propuesta
    coincide con los umbrales de `linea_base` que el congelado dejó en el monitor."""
    proyecto, _s, _t = d.linea_base_multiclase(client, "r4-propuesta-igual", n=400)
    aplicados = {
        clave[0]: t["value"]
        for clave, t in _umbrales(client, proyecto["id"], "quality").items()
        if t.get("origen") == "linea_base"
    }
    assert aplicados
    resp = client.get(f"/api/projects/{proyecto['id']}/thresholds/proposal", params={"tamano_lote": 1000})
    assert resp.status_code == 200, resp.text
    calidad = next(m for m in resp.json()["monitors"] if m["monitor_type"] == "quality")
    for p in calidad["propuestas"]:
        if p["metric_key"] in aplicados:
            assert p["value"] == aplicados[p["metric_key"]]
            assert p["origen_actual"] == "linea_base"


def test_la_propuesta_sin_linea_base_da_409(client: TestClient):
    proyecto = d.crear_proyecto_multiclase(client, "r4-propuesta-sin-lb")
    resp = client.get(f"/api/projects/{proyecto['id']}/thresholds/proposal")
    assert resp.status_code == 409, resp.text
    assert "línea base" in resp.text
