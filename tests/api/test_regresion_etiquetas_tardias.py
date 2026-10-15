"""Etiquetas tardías, `sin_datos` que no es recuperación, fila en el rechazo del mapeo
y ONNX con entradas `double`."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api import _datos_multiclase as d
from tests.api import _datos_regresion as r
from vigia.app.models import Evaluation, Event

MONITORES = ("quality", "fairness", "drift")


def _subir_etiquetas(client: TestClient, proyecto: dict, df: pd.DataFrame, *, evaluar: bool) -> dict:
    sub = d.subir(client, proyecto["id"], r.a_csv(df), rol="production", kind="feedback")
    resp = d.mapear(client, sub["dataset"]["id"], {"id_col": "id", "label_col": "label"})
    assert resp.status_code == 200, resp.text
    ing = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"], evaluar=evaluar)
    assert ing["status"] == "terminado", ing
    return ing["result"]


def _lotes_sin_verdad(client: TestClient, proyecto: dict) -> tuple[int, int]:
    """Línea base de 200 filas y dos lotes de producción sin etiquetas (prefijos `a` y `b`)."""
    a = r.subir_e_ingerir(
        client, proyecto, r.filas_regresion(60, semilla=11, prefijo="a", con_etiqueta=False),
        rol="production", evaluar=True,
    )
    b = r.subir_e_ingerir(
        client, proyecto, r.filas_regresion(60, semilla=12, prefijo="b", con_etiqueta=False),
        rol="production", evaluar=True,
    )
    return a["result"]["batch_id"], b["result"]["batch_id"]


def _evaluaciones(client: TestClient, batch_id: int) -> list[Evaluation]:
    with Session(client.app.state.engine) as s:
        return list(s.exec(select(Evaluation).where(Evaluation.batch_id == batch_id)).all())


def _etiquetas_de_dos_lotes() -> pd.DataFrame:
    parte_a = r.filas_regresion(60, semilla=11, prefijo="a")[["id", "label"]]
    parte_b = r.filas_regresion(60, semilla=12, prefijo="b")[["id", "label"]]
    return pd.concat([parte_a, parte_b], ignore_index=True)


# ---------------------------------------------------------------------------
# Etiquetas tardías
# ---------------------------------------------------------------------------


def test_con_evaluate_true_las_etiquetas_tardias_reevaluan_cada_lote(client: TestClient):
    proyecto, _t = r.linea_base_regresion(client, "r5-arr-tardias-si", n=200)
    lote_a, lote_b = _lotes_sin_verdad(client, proyecto)
    antes = {lote: len(_evaluaciones(client, lote)) for lote in (lote_a, lote_b)}
    resultado = _subir_etiquetas(client, proyecto, _etiquetas_de_dos_lotes(), evaluar=True)
    assert resultado["lotes_con_verdad"] == sorted([lote_a, lote_b])
    assert resultado["evaluated"] is True
    assert resultado["lotes_reevaluados"] == sorted([lote_a, lote_b])
    assert resultado["lotes_a_reevaluar"] == []
    assert "evaluate_motivo" not in resultado
    for lote in (lote_a, lote_b):
        nuevas = _evaluaciones(client, lote)[antes[lote]:]
        assert nuevas, f"el lote {lote} no se reevaluó"
        assert {e.trigger for e in nuevas} == {"feedback_tardio"}


def test_con_evaluate_false_avisa_de_los_lotes_a_reevaluar(client: TestClient):
    proyecto, _t = r.linea_base_regresion(client, "r5-arr-tardias-no", n=200)
    lote_a, lote_b = _lotes_sin_verdad(client, proyecto)
    antes = {lote: len(_evaluaciones(client, lote)) for lote in (lote_a, lote_b)}
    resultado = _subir_etiquetas(client, proyecto, _etiquetas_de_dos_lotes(), evaluar=False)
    lotes = sorted([lote_a, lote_b])
    assert resultado["lotes_con_verdad"] == lotes
    assert resultado["evaluated"] is False
    assert resultado["lotes_a_reevaluar"] == lotes
    assert resultado["lotes_reevaluados"] == []
    assert resultado["evaluate_motivo"] == (
        f"Las etiquetas llegaron a 2 lotes (#{lotes[0]}, #{lotes[1]}). "
        "Evalúa esos lotes para que la calidad use su verdad."
    )
    for lote in (lote_a, lote_b):
        assert len(_evaluaciones(client, lote)) == antes[lote]


def test_un_fichero_que_no_empareja_nada_deja_las_listas_vacias(client: TestClient):
    proyecto, _t = r.linea_base_regresion(client, "r5-arr-tardias-vacio", n=200)
    _lotes_sin_verdad(client, proyecto)
    ajenas = _etiquetas_de_dos_lotes()
    ajenas["id"] = [f"zz{i}" for i in range(len(ajenas))]
    for evaluar in (True, False):
        resultado = _subir_etiquetas(client, proyecto, ajenas, evaluar=evaluar)
        assert resultado["lotes_con_verdad"] == []
        assert resultado["lotes_reevaluados"] == []
        assert resultado["lotes_a_reevaluar"] == []
        assert resultado["evaluated"] is False
        assert "evaluate_motivo" not in resultado


# ---------------------------------------------------------------------------
# `sin_datos` no es recuperación
# ---------------------------------------------------------------------------


def _estados_del_lote(client: TestClient, proyecto_id: int, batch_id: int) -> dict[tuple[str, str | None], str]:
    estados: dict[tuple[str, str | None], str] = {}
    for monitor in MONITORES:
        try:
            medidas = r.medidas(client, proyecto_id, batch_id, monitor)
        except AssertionError:
            continue
        for clave, lista in medidas.items():
            for m in lista:
                estados[(clave, m.get("group_code"))] = m["state"]
    return estados


def _alertas(client: TestClient, proyecto_id: int) -> list[dict]:
    resp = client.get(f"/api/projects/{proyecto_id}/alerts", params={"limit": 200})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def test_sin_datos_deja_la_alerta_abierta_y_ok_la_pasa_a_observacion(client: TestClient):
    proyecto, _t = r.linea_base_regresion(client, "r5-arr-sin-datos", n=500)
    # Un lote con recorte al grupo B abre alertas de calidad y de equidad.
    lote_malo = r.subir_e_ingerir(
        client, proyecto, r.filas_regresion(400, semilla=21, desplazar_grupo_b=3.0, prefijo="m"),
        rol="production", evaluar=True,
    )["result"]["batch_id"]
    abiertas = {(a["metric_key"], a["group_code"]): a for a in _alertas(client, proyecto["id"]) if a["status"] == "abierta"}
    assert abiertas, "el lote malo no abrió ninguna alerta"
    # Un lote sin etiquetas: las medidas que necesitan la verdad salen `sin_datos`.
    lote_sin = r.subir_e_ingerir(
        client, proyecto, r.filas_regresion(400, semilla=22, prefijo="s", con_etiqueta=False),
        rol="production", evaluar=True,
    )["result"]["batch_id"]
    estados = _estados_del_lote(client, proyecto["id"], lote_sin)
    sin_datos = [k for k in abiertas if estados.get(k) == "sin_datos"]
    assert sin_datos, ("ninguna alerta abierta tiene su medida en sin_datos", estados)
    ahora = {(a["metric_key"], a["group_code"]): a for a in _alertas(client, proyecto["id"])}
    for clave in sin_datos:
        assert ahora[clave]["status"] == "abierta", (clave, ahora[clave]["status"])
        assert ahora[clave]["observation_count"] == abiertas[clave]["observation_count"] == 0
        assert ahora[clave]["last_evaluation_id"] == abiertas[clave]["last_evaluation_id"]
    with Session(client.app.state.engine) as s:
        eventos = s.exec(select(Event).where(Event.action == "alerta.en_observacion")).all()
        for ev in eventos:
            assert (ev.after_json or {}).get("state") != "sin_datos"
    # Un lote bueno con etiquetas: las medidas que cumplen (`ok`) pasan la alerta a observación.
    lote_bueno = r.subir_e_ingerir(
        client, proyecto, r.filas_regresion(400, semilla=23, prefijo="g"), rol="production", evaluar=True,
    )["result"]["batch_id"]
    estados_ok = _estados_del_lote(client, proyecto["id"], lote_bueno)
    recuperables = [k for k in sin_datos if estados_ok.get(k) in ("ok", "aviso")]
    assert recuperables, ("ninguna alerta recupera con el lote bueno", estados_ok)
    final = {(a["metric_key"], a["group_code"]): a for a in _alertas(client, proyecto["id"])}
    for clave in recuperables:
        assert final[clave]["status"] == "en_observacion", (clave, final[clave]["status"])
        assert final[clave]["observation_count"] == 1
    assert lote_malo and lote_sin


# ---------------------------------------------------------------------------
# Fila en el rechazo del mapeo
# ---------------------------------------------------------------------------


def _mapear_con_celda_mala(client: TestClient, nombre: str, fila: int, valor: str) -> str:
    proyecto = r.crear_proyecto_regresion(client, nombre)
    df = r.filas_regresion(30, semilla=4).astype({"prediction": object})
    df.loc[fila - 1, "prediction"] = valor
    sub = d.subir(client, proyecto["id"], r.a_csv(df), rol="baseline")
    resp = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion())
    assert resp.status_code == 422, resp.text
    return resp.json().get("detail", resp.text)


def test_el_rechazo_de_un_valor_con_unidad_dice_la_columna_el_valor_y_la_fila(client: TestClient):
    texto = _mapear_con_celda_mala(client, "r5-arr-fila-unidad", 7, "12 h")
    assert "«prediction»" in texto and "'12 h'" in texto and "fila 7 de los datos" in texto, texto


def test_el_rechazo_de_un_infinito_dice_la_fila(client: TestClient):
    texto = _mapear_con_celda_mala(client, "r5-arr-fila-inf", 12, "-inf")
    assert "«prediction»" in texto and "'-inf'" in texto and "fila 12 de los datos" in texto, texto


def test_la_fila_cuenta_las_celdas_vacias_anteriores(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-arr-fila-vacias")
    df = r.filas_regresion(30, semilla=4).astype({"prediction": object})
    df.loc[0, "prediction"] = np.nan
    df.loc[1, "prediction"] = np.nan
    df.loc[4, "prediction"] = "alta"
    sub = d.subir(client, proyecto["id"], r.a_csv(df), rol="baseline")
    resp = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion())
    assert resp.status_code == 422, resp.text
    assert "fila 5 de los datos" in resp.text, resp.text


# ---------------------------------------------------------------------------
# ONNX con entradas `double`
# ---------------------------------------------------------------------------


def _onnx_regresor(tipo: str) -> bytes:
    pytest.importorskip("skl2onnx", reason="skl2onnx no está instalado")
    from skl2onnx import to_onnx
    from skl2onnx.common.data_types import DoubleTensorType, FloatTensorType
    from sklearn.ensemble import RandomForestRegressor

    rng = np.random.default_rng(3)
    x = rng.normal(0, 1, (200, 2))
    y = 12 + 3 * x[:, 0] + 2 * x[:, 1]
    modelo = RandomForestRegressor(n_estimators=5, random_state=1).fit(x, y)
    tipos = {"double": DoubleTensorType([None, 2]), "float": FloatTensorType([None, 2])}
    return to_onnx(modelo, initial_types=[("X", tipos[tipo])], target_opset=15).SerializeToString()


def test_un_regresor_onnx_con_entradas_double_da_422_con_que_hacer(client: TestClient):
    proyecto, _t = r.linea_base_regresion(client, "r5-arr-onnx-double", n=200)
    resp = d.subir_modelo(client, proyecto["active_version_id"], _onnx_regresor("double"))
    assert resp.status_code == 422, resp.text
    texto = resp.text
    assert "float32" in texto and "FloatTensorType" in texto and "double" in texto, texto
    assert "no es un modelo ONNX válido" not in texto


def test_un_regresor_onnx_con_entradas_float32_sigue_cargando(client: TestClient):
    proyecto, _t = r.linea_base_regresion(client, "r5-arr-onnx-float", n=200)
    resp = d.subir_modelo(client, proyecto["active_version_id"], _onnx_regresor("float"))
    # Las columnas x1 y x2 de la línea base no son las del modelo fabricado: aquí solo cuenta que
    # el rechazo, si lo hay, no es el de las entradas double.
    assert "entradas de tipo double" not in resp.text, resp.text
