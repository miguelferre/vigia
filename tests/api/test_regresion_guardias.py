"""Guardias de la capa humana y despacho.

Una regresión sin rango favorable no pasa por el camino binario de la capa humana: el registro de
uso da 422 con el motivo y las cruzadas, el deskilling y los overrides dan `sin_datos` con el
mismo motivo. Con rango la capa humana está abierta (`test_regresion_capa_humana.py`).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api import _datos_regresion as r
from tests.api.conftest import actor_headers
from vigia.app.services import tarea
from vigia.core.schema import (
    CLAVES_SOLO_CLASIFICACION,
    MOTIVO_CAPA_HUMANA_SIN_RANGO,
)

HUMANO = actor_headers("miguel")
CSV_USO = (
    "date,human_decision,model_output,ground_truth\n"
    "2026-01-05,40,38.5,41\n2026-01-06,12,11,12.5\n"
)


def _subir_uso(client: TestClient, proyecto_id: int, contenido: str = CSV_USO, **datos):
    return client.post(
        f"/api/projects/{proyecto_id}/usage-logs/upload",
        files={"file": ("uso.csv", contenido.encode(), "text/csv")},
        data=datos,
        headers=HUMANO,
    )


def test_el_registro_de_uso_de_una_regresion_sin_rango_da_422_con_el_motivo(client: TestClient):
    texto = MOTIVO_CAPA_HUMANA_SIN_RANGO
    p = r.crear_proyecto_regresion(client, "r5-guardia-uso-sin-rango", rangos=None)
    resp = _subir_uso(client, p["id"])
    assert resp.status_code == 422, resp.text
    assert texto in resp.text
    # El 422 dice también qué hacer, y el MCP dice lo mismo (`tarea.texto_guardia_capa_humana`).
    assert tarea.texto_guardia_capa_humana(sin_rango=True) in resp.json()["detail"]
    assert "Crea un proyecto de regresión con rango favorable" in resp.text
    # Ni con la declaración binaria ni con `refer` se cae al camino binario.
    for extra in ({"valor_favorable": "no-refer"}, {"valor_favorable": "1"}):
        resp = _subir_uso(client, p["id"], "date,human_decision,model_output,ground_truth\n2026-01-05,refer,refer,no-refer\n", **extra)
        assert resp.status_code == 422, resp.text
        assert texto in resp.text
    assert client.get(f"/api/projects/{p['id']}/usage-logs/export.csv").text.count("\n") <= 1


@pytest.mark.parametrize(("rangos", "texto"), [(None, MOTIVO_CAPA_HUMANA_SIN_RANGO)])
def test_las_cruzadas_de_una_regresion_dan_sin_datos_con_el_motivo(client: TestClient, rangos, texto):
    p, _t = r.linea_base_regresion(client, f"r5-guardia-cruzadas-{bool(rangos)}", rangos=rangos, n=200)
    resp = client.post(f"/api/projects/{p['id']}/cross/evaluate", headers=HUMANO)
    assert resp.status_code == 200, resp.text
    trabajo = client.get(f"/api/jobs/{resp.json()['id']}").json()
    assert trabajo["status"] == "terminado"
    assert trabajo["result"]["evaluation_id"] is None and trabajo["result"]["motivo"] == texto
    ultimo = client.get(f"/api/projects/{p['id']}/cross/latest").json()
    assert ultimo["estado"] == "sin_datos" and ultimo["rules"] == [] and ultimo["motivo"] == texto


@pytest.mark.parametrize(("rangos", "texto"), [(None, MOTIVO_CAPA_HUMANA_SIN_RANGO)])
def test_el_deskilling_de_una_regresion_da_sin_datos_con_el_motivo(client: TestClient, rangos, texto):
    p, _t = r.linea_base_regresion(client, f"r5-guardia-deskilling-{bool(rangos)}", rangos=rangos, n=200)
    resp = client.get(f"/api/projects/{p['id']}/deskilling")
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["sin_datos"] is True and cuerpo["motivo"] == texto
    assert cuerpo["windows"] == [] and cuerpo["trends"] is None and cuerpo["signal"] is None


@pytest.mark.parametrize("por", ["subgroup", "phase", "clinician"])
@pytest.mark.parametrize(("rangos", "texto"), [(None, MOTIVO_CAPA_HUMANA_SIN_RANGO)])
def test_los_overrides_de_una_regresion_dan_sin_datos_con_el_motivo(
    client: TestClient, por: str, rangos, texto
):
    p, _t = r.linea_base_regresion(client, f"r5-guardia-overrides-{por}-{bool(rangos)}", rangos=rangos, n=200)
    resp = client.get(f"/api/projects/{p['id']}/overrides", params={"by": por})
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["motivo"] == texto and cuerpo["n_total"] == 0
    # El selector de profesional y la vista propia dicen lo mismo, no una lista vacía muda.
    assert client.get(f"/api/projects/{p['id']}/overrides/clinicians").json() == {
        "clinicians": [], "motivo": texto,
    }
    yo = client.get(f"/api/projects/{p['id']}/overrides/me", params={"clinician": "enf-1"})
    assert yo.status_code == 200 and yo.json()["windows"] == [] and yo.json()["motivo"] == texto


def test_una_clasificacion_no_cambia(client: TestClient):
    """El binario sigue con su camino de siempre: `cross/latest` sin motivo, y el deskilling
    sin datos por falta de diario, no por tipo."""
    binario = client.post("/api/projects", json={"name": "r5-guardia-binario"}, headers=HUMANO).json()
    assert client.get(f"/api/projects/{binario['id']}/cross/latest").json()["motivo"] is None
    cuerpo = client.get(f"/api/projects/{binario['id']}/deskilling").json()
    assert cuerpo["motivo"] != MOTIVO_CAPA_HUMANA_SIN_RANGO
    assert client.get(f"/api/projects/{binario['id']}/overrides").json().get("motivo") is None


def test_una_evaluacion_de_regresion_no_publica_ninguna_clave_de_clasificacion(client: TestClient):
    p, _t = r.linea_base_regresion(client, "r5-despacho-claves", n=400)
    lote = r.subir_e_ingerir(client, p, r.filas_regresion(300, semilla=31, prefijo="n"), rol="production", evaluar=True)
    batch_id = lote["result"]["batch_id"]
    vistas: set[str] = set()
    for monitor in ("quality", "drift", "fairness"):
        vistas |= set(r.medidas(client, p["id"], batch_id, monitor))
    assert not vistas & set(CLAVES_SOLO_CLASIFICACION), vistas & set(CLAVES_SOLO_CLASIFICACION)
    # Y sí las de regresión: los cuatro titulares y las medidas por grupo.
    calidad = set(r.medidas(client, p["id"], batch_id, "quality"))
    assert {"mean_absolute_error", "root_mean_squared_error", "r2", "mean_error"} <= calidad
    assert "prediction_drift_score" in r.medidas(client, p["id"], batch_id, "drift")
    equidad = r.medidas(client, p["id"], batch_id, "fairness")
    assert {"mean_absolute_error_difference", "mean_error_difference"} <= set(equidad)


def test_la_linea_base_de_una_regresion_no_tiene_matriz_ni_probabilidades(client: TestClient):
    p, t = r.linea_base_regresion(client, "r5-despacho-linea-base", n=300)
    r.evaluar_lote(client, t["result"]["batch_id"])
    calidad = r.evaluacion(client, p["id"], t["result"]["batch_id"], "quality")
    detalle = calidad["result"]["details"]
    assert detalle["task_type"] == "regression" and detalle["unidad"] == r.UNIDAD
    assert not {"confusion_matrix", "tp", "fp", "fn", "tn", "por_clase"} & set(detalle)


def test_unidad_en_el_titulo_de_las_alertas_de_las_medidas_en_la_unidad(client: TestClient):
    """Las medidas en la unidad de la salida llevan la unidad en el valor del título de
    su alerta, no en el umbral («El MAE sube a 7,4 horas por semana (umbral 5,9)»); `r2` y la
    razón de errores, no."""
    p, _t = r.linea_base_regresion(client, "r5-titulo-unidad", n=500)
    lote = r.subir_e_ingerir(
        client, p, r.filas_regresion(400, semilla=21, desplazar_grupo_b=3.0, prefijo="b"),
        rol="production", evaluar=True,
    )
    assert lote["result"]["batch_id"]
    titulos = [a["title"] for a in client.get(f"/api/projects/{p['id']}/alerts").json()["items"]]
    en_unidad = [t for t in titulos if "mean_error_difference" in t or "mean_absolute_error:" in t or "Error absoluto" in t]
    assert en_unidad and all(t.count(r.UNIDAD) == 1 for t in en_unidad), titulos
    for t in en_unidad:
        valor, _, umbral = t.partition("(umbral")
        assert r.UNIDAD in valor and r.UNIDAD not in umbral, t
    for t in titulos:
        if t.startswith("r2:") or "mean_absolute_error_ratio" in t:
            assert r.UNIDAD not in t, t
