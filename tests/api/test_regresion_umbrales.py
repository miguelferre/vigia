"""Umbrales desde la línea base.

Al congelar la línea base de una regresión se aplican `umbrales_linea_base_regresion` (y, con
rango, la equidad sobre la pertenencia). La propuesta (`GET /thresholds/proposal`) usa
la misma función.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api import _datos_multiclase as d
from tests.api import _datos_regresion as r
from tests.api.conftest import actor_headers
from vigia.app.models import Event, Project

HUMANO = actor_headers("miguel")

CLAVES_CALIDAD = {"mean_absolute_error", "root_mean_squared_error", "r2", "mean_error"}
CLAVES_ERROR_GRUPO = {"mean_error_difference", "mean_absolute_error_difference", "mean_absolute_error_ratio"}


def _umbrales(client: TestClient, proyecto_id: int, tipo: str) -> list[dict]:
    detalle = client.get(f"/api/projects/{proyecto_id}").json()
    return next(m for m in detalle["monitors"] if m["type"] == tipo)["thresholds"]["thresholds"]


def _eventos(client: TestClient, proyecto_id: int, accion: str) -> list[Event]:
    with Session(client.app.state.engine) as s:
        return list(
            s.exec(select(Event).where(Event.project_id == proyecto_id, Event.action == accion)).all()
        )


def test_al_congelar_se_aplican_los_umbrales_de_la_linea_base_con_su_origen(client: TestClient):
    p, _t = r.linea_base_regresion(client, "r5-umb-congelar", n=500)
    calidad = _umbrales(client, p["id"], "quality")
    assert CLAVES_CALIDAD <= {t["metric_key"] for t in calidad}
    assert {t["origen"] for t in calidad} == {"linea_base"}
    mae = next(t for t in calidad if t["metric_key"] == "mean_absolute_error")
    assert mae["kind"] == "upper_limit" and 0 < mae["value"] < 3  # sale de una línea base con MAE ~0,6
    sesgo = [t for t in calidad if t["metric_key"] == "mean_error"]
    assert {t["kind"] for t in sesgo} == {"lower_limit", "upper_limit"}  # de dos lados
    deriva = {t["metric_key"]: t for t in _umbrales(client, p["id"], "drift")}
    assert deriva["prediction_drift_score"]["origen"] == "linea_base"
    assert deriva["feature_drift_score"]["origen"] == "fabrica"  # el de fábrica no se toca
    equidad = {t["metric_key"] for t in _umbrales(client, p["id"], "fairness")}
    assert CLAVES_ERROR_GRUPO <= equidad
    # Con rango, también la equidad sobre la pertenencia.
    assert "fairness_value" in equidad
    aplicado = _eventos(client, p["id"], "proyecto.umbrales_linea_base_aplicados")
    assert len(aplicado) == 1
    assert any("mean_absolute_error" in u for u in aplicado[0].after_json["umbrales"])


def test_sin_rango_la_equidad_solo_lleva_las_medidas_de_error_por_grupo(client: TestClient):
    p, _t = r.linea_base_regresion(client, "r5-umb-sin-rango", rangos=None, n=400)
    equidad = {t["metric_key"] for t in _umbrales(client, p["id"], "fairness")}
    assert equidad == CLAVES_ERROR_GRUPO
    assert CLAVES_CALIDAD <= {t["metric_key"] for t in _umbrales(client, p["id"], "quality")}


def test_no_corre_la_sincronizacion_de_la_clase_favorable(client: TestClient):
    p, _t = r.linea_base_regresion(client, "r5-umb-sin-sync", n=300)
    assert _eventos(client, p["id"], "proyecto.favorable_sincronizado") == []
    leido = client.get(f"/api/projects/{p['id']}").json()
    assert leido["favorable_label"] is None
    assert "favorable_label" not in {k for k, v in leido["mapping_template_json"].items() if v}
    # Sí copia las columnas estables para que el segundo lote no las repita.
    assert leido["mapping_template_json"]["prediction_col"] == "prediction"
    assert leido["mapping_template_json"]["label_col"] == "label"


def test_un_umbral_fijado_por_una_persona_no_se_pisa(client: TestClient):
    p = r.crear_proyecto_regresion(client, "r5-umb-persona")
    calidad = next(m for m in p["monitors"] if m["type"] == "quality")
    resp = client.patch(
        f"/api/monitors/{calidad['id']}",
        json={
            "actor": "miguel",
            "motivo": "criterio clínico",
            "thresholds": {
                "thresholds": [
                    {
                        "metric_key": "mean_absolute_error",
                        "kind": "upper_limit",
                        "value": 5.0,
                        "origen": "criterio_clinico",
                    }
                ]
            },
        },
        headers=HUMANO,
    )
    assert resp.status_code == 200, resp.text
    r.subir_e_ingerir(client, p, r.filas_regresion(400))
    mae = [t for t in _umbrales(client, p["id"], "quality") if t["metric_key"] == "mean_absolute_error"]
    assert len(mae) == 1 and mae[0]["value"] == 5.0 and mae[0]["origen"] == "criterio_clinico"
    aplicado = _eventos(client, p["id"], "proyecto.umbrales_linea_base_aplicados")[0].after_json
    assert any("mean_absolute_error" in c for c in aplicado["conservados"])
    assert "root_mean_squared_error" in " ".join(aplicado["umbrales"])


def test_un_fallo_del_calculo_no_impide_congelar(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from vigia.core import calibration

    def falla(*a, **k):
        raise ValueError("línea base sin variación")

    monkeypatch.setattr(calibration, "umbrales_linea_base_regresion", falla)
    p, _t = r.linea_base_regresion(client, "r5-umb-fallo", n=300)
    version = client.get(f"/api/projects/{p['id']}").json()["versions"][0]
    assert version["frozen_at"] is not None
    fallido = _eventos(client, p["id"], "proyecto.umbrales_linea_base_fallidos")
    assert len(fallido) == 1 and "sin variación" in fallido[0].after_json["error"]
    assert _umbrales(client, p["id"], "quality") == []  # nace vacío y se queda así


def test_con_la_calidad_vacia_un_lote_de_produccion_da_sin_datos_y_ninguna_alerta(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """Sin umbrales en la unidad de la salida (la calidad nace vacía y el cálculo cayó),
    los titulares y la deriva de la predicción salen `sin_datos` con «umbral pendiente» y no
    alertan: nada se clasifica contra un umbral binario de fábrica."""
    from vigia.core import calibration

    def falla(*a, **k):
        raise ValueError("línea base sin variación")

    monkeypatch.setattr(calibration, "umbrales_linea_base_regresion", falla)
    p, _t = r.linea_base_regresion(client, "r5-umb-sin-umbrales-evalua", n=300)
    lote = r.subir_e_ingerir(
        client, p, r.filas_regresion(300, semilla=9, desplazar_todo=5.0, prefijo="q"),
        rol="production", evaluar=True,
    )
    batch_id = lote["result"]["batch_id"]
    calidad = r.medidas(client, p["id"], batch_id, "quality")
    for clave in CLAVES_CALIDAD:
        assert {m["state"] for m in calidad[clave]} == {"sin_datos"}, (clave, calidad[clave])
        assert all("umbral pendiente" in (m["motivo"] or "") for m in calidad[clave]), clave
    deriva = r.medidas(client, p["id"], batch_id, "drift")["prediction_drift_score"]
    assert {m["state"] for m in deriva} == {"sin_datos"}
    assert all("umbral pendiente" in (m["motivo"] or "") for m in deriva)
    alertas = client.get(f"/api/projects/{p['id']}/alerts").json()["items"]
    assert not [a for a in alertas if a["metric_key"] in CLAVES_CALIDAD | {"prediction_drift_score"}]


def test_unidad_y_rango_quedan_fijados_en_el_proyecto_al_congelar(client: TestClient):
    p, _t = r.linea_base_regresion(client, "r5-umb-fijados", n=300)
    with Session(client.app.state.engine) as s:
        fila = s.get(Project, p["id"])
        assert fila.target_unit == r.UNIDAD and fila.favorable_ranges_json == [[12.0, None]]
    assert len(_eventos(client, p["id"], "proyecto.rango_favorable_fijado")) == 1  # el del alta; no se repite


def test_la_propuesta_de_una_regresion_con_rango_lleva_error_y_pertenencia(client: TestClient):
    p, _t = r.linea_base_regresion(client, "r5-umb-propuesta", n=500)
    resp = client.get(f"/api/projects/{p['id']}/thresholds/proposal", params={"tamano_lote": 300})
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["tamano_lote"] == 300 and cuerpo["baseline_batch_id"]
    por_monitor = {m["monitor_type"]: {f["metric_key"] for f in m["propuestas"]} for m in cuerpo["monitors"]}
    assert CLAVES_CALIDAD <= por_monitor["quality"]
    assert "prediction_drift_score" in por_monitor["drift"]
    assert CLAVES_ERROR_GRUPO <= por_monitor["fairness"]
    assert "fairness_value" in por_monitor["fairness"]  # La propuesta binaria sobre la pertenencia
    for m in cuerpo["monitors"]:
        for f in m["propuestas"]:
            assert set(f) >= {"metric_key", "kind", "value", "motivo", "umbral_actual", "origen_actual"}
    # Con el tamaño de lote de siempre es la misma que se aplicó al congelar (semilla fija).
    igual = client.get(f"/api/projects/{p['id']}/thresholds/proposal").json()
    calidad = next(m for m in igual["monitors"] if m["monitor_type"] == "quality")["propuestas"]
    mae = next(f for f in calidad if f["metric_key"] == "mean_absolute_error")
    aplicado = next(
        t["value"] for t in _umbrales(client, p["id"], "quality") if t["metric_key"] == "mean_absolute_error"
    )
    assert mae["value"] == pytest.approx(aplicado, rel=1e-6)
    assert mae["umbral_actual"] == pytest.approx(aplicado) and mae["origen_actual"] == "linea_base"
    # Solo lee.
    antes = _umbrales(client, p["id"], "quality")
    client.get(f"/api/projects/{p['id']}/thresholds/proposal")
    assert _umbrales(client, p["id"], "quality") == antes


def test_sin_rango_la_propuesta_no_lista_las_medidas_de_pertenencia(client: TestClient):
    p, _t = r.linea_base_regresion(client, "r5-umb-propuesta-sin-rango", rangos=None, n=400)
    cuerpo = client.get(f"/api/projects/{p['id']}/thresholds/proposal").json()
    por_monitor = {m["monitor_type"]: {f["metric_key"] for f in m["propuestas"]} for m in cuerpo["monitors"]}
    assert por_monitor["fairness"] == CLAVES_ERROR_GRUPO


def test_multiclase_sin_conjunto_favorable_no_lista_la_equidad(client: TestClient):
    p = d.crear_proyecto_multiclase(client, "r5-umb-multi-sin-conjunto", mapping_template={})
    sub = d.subir(client, p["id"], d.a_csv(d.filas_multiclase(500)))
    assert d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase(favorable_label=[])).status_code == 200
    assert d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])["status"] == "terminado"
    cuerpo = client.get(f"/api/projects/{p['id']}/thresholds/proposal").json()
    assert {m["monitor_type"] for m in cuerpo["monitors"]} == {"quality", "drift"}


def test_multiclase_con_conjunto_sin_atributo_protegido_conserva_la_equidad_de_fabrica(
    client: TestClient,
):
    """Sin atributo protegido no hay grupos con los que proponer: la equidad conserva el origen
    `fabrica` y no hay evento de fallo (la propuesta lista las filas sin valor)."""
    p, _s, _t = d.linea_base_multiclase(client, "r5-umb-multi-conjunto", n=500)
    equidad = _umbrales(client, p["id"], "fairness")
    assert equidad and {t["origen"] for t in equidad} == {"fabrica"}
    assert not _eventos(client, p["id"], "proyecto.umbrales_linea_base_fallidos")
    cuerpo = client.get(f"/api/projects/{p['id']}/thresholds/proposal").json()
    assert "fairness" in {m["monitor_type"] for m in cuerpo["monitors"]}


def test_la_regresion_sin_linea_base_no_tiene_propuesta_y_dice_por_que(client: TestClient):
    p = r.crear_proyecto_regresion(client, "r5-umb-sin-linea")
    resp = client.get(f"/api/projects/{p['id']}/thresholds/proposal")
    assert resp.status_code == 409
    assert "línea base" in resp.text


def _multiclase_con_atributo_protegido(client: TestClient, nombre: str) -> dict:
    p = d.crear_proyecto_multiclase(client, nombre)
    sub = d.subir(client, p["id"], d.a_csv(d.filas_multiclase(900)))
    mapeo = d.mapeo_multiclase(
        protected_attr_col="idioma",
        protected_kind="categorical",
        unpriv_groups=["en"],
        priv_groups=["es"],
    )
    assert d.mapear(client, sub["dataset"]["id"], mapeo).status_code == 200
    assert d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])["status"] == "terminado"
    return p


def test_multiclase_con_conjunto_y_atributo_protegido_fija_la_equidad_desde_la_linea_base(
    client: TestClient,
):
    p = _multiclase_con_atributo_protegido(client, "r5-umb-multi-protegido")
    equidad = _umbrales(client, p["id"], "fairness")
    de_linea_base = {t["metric_key"] for t in equidad if t.get("origen") == "linea_base"}
    assert de_linea_base, equidad  # la propuesta binaria sobre la pertenencia
    # La calidad y la deriva de multiclase siguen igual.
    assert {t["metric_key"] for t in _umbrales(client, p["id"], "quality")} >= {"accuracy", "f1_measure"}
    assert "prediction_drift_score" in {t["metric_key"] for t in _umbrales(client, p["id"], "drift")}
    cuerpo = client.get(f"/api/projects/{p['id']}/thresholds/proposal").json()
    filas = next(m for m in cuerpo["monitors"] if m["monitor_type"] == "fairness")["propuestas"]
    assert any(f["value"] is not None for f in filas)


def test_un_fallo_de_la_equidad_no_quita_los_umbrales_de_calidad_ni_de_deriva(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from vigia.core import calibration

    def falla(*a, **k):
        raise ValueError("equidad sin datos")

    monkeypatch.setattr(calibration, "proponer_umbrales", falla)
    p = _multiclase_con_atributo_protegido(client, "r5-umb-multi-fallo-equidad")
    assert {t["metric_key"] for t in _umbrales(client, p["id"], "quality")} >= {"accuracy", "f1_measure"}
    fallido = _eventos(client, p["id"], "proyecto.umbrales_linea_base_fallidos")
    assert len(fallido) == 1 and "equidad sin datos" in fallido[0].after_json["error"]
    assert not [t for t in _umbrales(client, p["id"], "fairness") if t.get("origen") == "linea_base"]
