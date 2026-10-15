"""Comparación de versiones de una regresión.

Para las claves en la unidad de la salida, «igual» es una diferencia menor que el 1 % de la
desviación del valor real en la línea base de la versión A; `r2` y `prediction_drift_score`
siguen con 0,01; `mean_error` y sus diferencias son de dos lados (mejor es más cerca del
centro); sin umbrales la respuesta lleva un `motivo` (en los tres tipos).
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api import _datos_multiclase as d
from tests.api import _datos_regresion as r
from tests.api import comparacion_util as cu
from tests.api.conftest import actor_headers
from vigia.app.models import Record

# Valor real de la línea base de v1: desviación típica (ddof=1) conocida.
REALES = np.array([0.0, 10.0] * 25)
DESVIACION = float(np.std(REALES, ddof=1))
UN_PORCIENTO = 0.01 * DESVIACION  # ~0,0503


def _escenario(client: TestClient, session: Session) -> dict:
    p = r.crear_proyecto_regresion(client, "r5-cmp-regresion")
    pid, v1 = p["id"], p["active_version_id"]
    v2 = cu.version_nueva(session, pid)
    b1_base, b1_prod = cu.lote(session, pid, v1, 0), cu.lote(session, pid, v1, 1)
    b2_base, b2_prod = cu.lote(session, pid, v2, 2), cu.lote(session, pid, v2, 3)
    cu.congelar_base(session, v1, b1_base)
    cu.congelar_base(session, v2, b2_base)
    for i, valor in enumerate(REALES):
        session.add(Record(batch_id=b1_base, project_id=pid, seq=i, label_value=float(valor)))
    session.commit()
    return {"pid": pid, "v1": v1, "v2": v2, "b1": (b1_base, b1_prod), "b2": (b2_base, b2_prod)}


def _medir(session: Session, e: dict, clave: str, a: float, b: float, **umbral) -> None:
    cu.medida(session, e["pid"], e["v1"], e["b1"][1], "quality", clave, a, **umbral)
    cu.medida(session, e["pid"], e["v2"], e["b2"][1], "quality", clave, b, **umbral)


def _comparar(client: TestClient, e: dict) -> dict:
    resp = client.get(
        f"/api/projects/{e['pid']}/versions/compare", params={"a": e["v1"], "b": e["v2"]}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_una_diferencia_menor_que_el_uno_por_ciento_de_la_desviacion_es_igual(
    client: TestClient, session: Session
):
    e = _escenario(client, session)
    _medir(session, e, "mean_absolute_error", 2.0, 2.0 + 0.4 * UN_PORCIENTO, high=3.0)
    _medir(session, e, "root_mean_squared_error", 2.0, 2.0 + 3 * UN_PORCIENTO, high=3.0)
    datos = _comparar(client, e)
    mae = cu.fila(datos, "mean_absolute_error")
    assert mae["direccion"] == "igual" and "diferencia menor que" in mae["motivo"]
    rmse = cu.fila(datos, "root_mean_squared_error")
    assert rmse["direccion"] == "empeora"  # más error: peor, y supera el 1 % de la desviación
    assert datos["motivo"] is None


def test_en_miligramos_o_en_euros_la_regla_sigue_a_la_escala(client: TestClient, session: Session):
    """Con 0,01 absoluto, un error en unidades pequeñas saldría siempre «igual»."""
    e = _escenario(client, session)
    # 0,3 es 6 veces el 1 % de la desviación y 30 veces 0,01: cuenta como cambio.
    _medir(session, e, "mean_absolute_error", 2.0, 2.3, high=3.0)
    assert cu.fila(_comparar(client, e), "mean_absolute_error")["direccion"] == "empeora"


def test_r2_y_la_deriva_de_la_prediccion_siguen_con_0_01(client: TestClient, session: Session):
    e = _escenario(client, session)
    _medir(session, e, "r2", 0.90, 0.903, low=0.8)  # 0,003 < 0,01, aunque > 1 % de la desviación
    cu.medida(session, e["pid"], e["v1"], e["b1"][1], "drift", "prediction_drift_score", 0.05, high=0.2)
    cu.medida(session, e["pid"], e["v2"], e["b2"][1], "drift", "prediction_drift_score", 0.07, high=0.2)
    datos = _comparar(client, e)
    assert cu.fila(datos, "r2")["direccion"] == "igual"
    assert cu.fila(datos, "prediction_drift_score")["direccion"] == "empeora"  # 0,02 > 0,01


def test_el_sesgo_medio_es_de_dos_lados_mejor_es_estar_mas_cerca_del_centro(
    client: TestClient, session: Session
):
    e = _escenario(client, session)
    _medir(session, e, "mean_error", 0.8, 0.1, low=-1.0, high=1.0)
    _medir(session, e, "mean_error_difference", -0.1, -0.9, low=-1.0, high=1.0)
    datos = _comparar(client, e)
    assert cu.fila(datos, "mean_error")["direccion"] == "mejora"
    assert "centro" in cu.fila(datos, "mean_error")["motivo"]
    assert cu.fila(datos, "mean_error_difference")["direccion"] == "empeora"


def test_sin_desviacion_no_se_decide_igual_por_diferencia_y_el_motivo_lo_dice(
    client: TestClient, session: Session
):
    """Sin línea base con valor real que varíe no hay escala: un error en miligramos no sale
    «igual» por caer bajo 0,01. La fila lo dice; un valor idéntico sí es «igual»."""
    p = r.crear_proyecto_regresion(client, "r5-cmp-sin-desviacion")
    pid, v1 = p["id"], p["active_version_id"]
    v2 = cu.version_nueva(session, pid)
    b1_prod, b2_prod = cu.lote(session, pid, v1, 0), cu.lote(session, pid, v2, 1)
    e = {"pid": pid, "v1": v1, "v2": v2, "b1": (None, b1_prod), "b2": (None, b2_prod)}
    _medir(session, e, "mean_absolute_error", 2.0, 2.005, high=3.0)
    _medir(session, e, "root_mean_squared_error", 2.0, 2.0, high=3.0)
    _medir(session, e, "r2", 0.5, 0.505, low=0.2)
    datos = _comparar(client, e)
    mae = cu.fila(datos, "mean_absolute_error")
    assert mae["direccion"] == "empeora" and "sin escala" in mae["motivo"]
    assert cu.fila(datos, "root_mean_squared_error")["direccion"] == "igual"
    # `r2` no lleva unidad: sigue con el 0,01 y sin el aviso de escala.
    r2 = cu.fila(datos, "r2")
    assert r2["direccion"] == "igual" and "sin escala" not in r2["motivo"]


@pytest.mark.parametrize("tipo", ["binary", "multiclass", "regression"])
def test_sin_umbrales_que_comparar_la_respuesta_lleva_un_motivo(
    client: TestClient, session: Session, tipo: str
):
    if tipo == "regression":
        p = r.crear_proyecto_regresion(client, "r5-cmp-motivo-regresion")
    elif tipo == "multiclass":
        p = d.crear_proyecto_multiclase(client, "r5-cmp-motivo-multi")
    else:
        p = client.post("/api/projects", json={"name": "r5-cmp-motivo-bin"}, headers=actor_headers()).json()
    cu.version_nueva(session, p["id"])
    datos = client.get(f"/api/projects/{p['id']}/versions/compare").json()
    assert datos["filas"] == []
    # Sin ningún lote evaluado, el motivo pide los lotes (no los umbrales).
    assert datos["motivo"] and "lote" in datos["motivo"] and "umbral" not in datos["motivo"]


@pytest.mark.parametrize("tipo", ["binary", "multiclass", "regression"])
def test_con_lotes_pero_sin_umbrales_el_motivo_pide_los_umbrales(
    client: TestClient, session: Session, tipo: str
):
    if tipo == "regression":
        p = r.crear_proyecto_regresion(client, "r5-cmp-motivo-umbral-regresion")
    elif tipo == "multiclass":
        p = d.crear_proyecto_multiclase(client, "r5-cmp-motivo-umbral-multi")
    else:
        p = client.post("/api/projects", json={"name": "r5-cmp-motivo-umbral-bin"}, headers=actor_headers()).json()
    pid, v1 = p["id"], p["active_version_id"]
    v2 = cu.version_nueva(session, pid)
    e = {"pid": pid, "v1": v1, "v2": v2, "b1": (None, cu.lote(session, pid, v1, 0)),
         "b2": (None, cu.lote(session, pid, v2, 1))}
    _medir(session, e, "mean_absolute_error", 2.0, 2.5)  # medidas sin umbral
    datos = _comparar(client, e)
    assert datos["filas"] == []
    assert "Ninguna medida" in datos["motivo"] and "umbral" in datos["motivo"]
    # En binario los umbrales de fábrica ya existen: no se promete que Vigía los proponga.
    assert ("propone" in datos["motivo"]) == (tipo != "binary")


def test_con_filas_el_motivo_es_nulo_en_clasificacion(client: TestClient, session: Session):
    datos_cu = cu.escenario_dos_versiones(client, session)
    resp = client.get(f"/api/projects/{datos_cu['pid']}/versions/compare")
    assert resp.status_code == 200 and resp.json()["filas"] and resp.json()["motivo"] is None
