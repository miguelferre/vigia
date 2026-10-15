"""Mensajes en español con qué hacer.

Un test por mensaje, por la API, con datos sintéticos de `_datos_regresion`. Ninguno da 500.
Los casos de unidad pegada, infinitos y clases de texto en la predicción ya los prueba
`test_regresion_ingesta.py`; aquí se completan con el resto y se comprueba que cada
mensaje dice qué hacer.
"""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from tests.api import _datos_multiclase as d
from tests.api import _datos_regresion as r


def _subir_csv(client: TestClient, proyecto: dict, texto: str):
    return d.subir(client, proyecto["id"], texto.encode("utf-8"))


def test_la_coma_decimal_y_el_punto_y_coma_se_leen_sin_error(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-msg-coma-decimal")
    df = r.filas_regresion(60)
    texto = df.to_csv(index=False, sep=";", decimal=",")
    sub = _subir_csv(client, proyecto, texto)
    resp = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion())
    assert resp.status_code == 200, resp.text
    trabajo = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"], evaluar=False)
    assert trabajo["status"] == "terminado", trabajo


def test_una_prediccion_vacia_o_nan_da_422_con_la_fila_y_que_hacer(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-msg-nan")
    df = r.filas_regresion(60)
    df.loc[10, "prediction"] = np.nan
    df.loc[11, "prediction"] = np.nan
    sub = d.subir(client, proyecto["id"], r.a_csv(df))
    resp = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion())
    assert resp.status_code == 200, resp.text
    trabajo = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"], evaluar=False)
    assert trabajo["status"] == "error", trabajo
    texto = str(trabajo["error"])
    assert "Traceback" not in texto
    assert "la columna de predicción 'prediction' tiene 2 de 60 valores" in texto, texto
    assert "la primera está en la fila 11 de los datos" in texto, texto
    assert "rellena los huecos o quita esas filas y vuelve a subir el fichero" in texto, texto


def test_una_etiqueta_con_texto_en_algunas_filas_se_avisa_y_queda_sin_etiqueta(
    client: TestClient,
):
    proyecto = r.crear_proyecto_regresion(client, "r5-msg-etiqueta-mixta")
    df = r.filas_regresion(80)
    df["label"] = df["label"].astype(object)
    df.loc[[5, 6, 7], "label"] = "pendiente"
    trabajo = r.subir_e_ingerir(client, proyecto, df)
    avisos = " ".join(trabajo["result"].get("avisos") or [])
    assert "etiqueta" in avisos and "sin etiqueta" in avisos, avisos


def test_una_prediccion_constante_avisa_con_que_hacer(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-msg-constante")
    df = r.filas_regresion(80)
    df["prediction"] = 30.0
    trabajo = r.subir_e_ingerir(client, proyecto, df)
    avisos = [a for a in trabajo["result"]["avisos"] if "mismo valor" in a]
    assert avisos, trabajo["result"]["avisos"]
    # El aviso sale de `core/loaders.py`: pregunta si es la columna correcta y dice qué hacer.
    assert "¿es la columna de predicción?" in avisos[0], avisos[0]
    assert "Revisa en el paso Mapeo" in avisos[0], avisos[0]


def test_las_columnas_de_probabilidad_en_regresion_nombran_el_campo_y_dicen_que_hacer(
    client: TestClient,
):
    proyecto = r.crear_proyecto_regresion(client, "r5-msg-probabilidad")
    sub = d.subir(client, proyecto["id"], r.a_csv(r.filas_regresion(40)))
    resp = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion(probability_cols=["x1", "x2"]))
    assert resp.status_code == 422, resp.text
    assert "probability_cols" in resp.text
    assert "regresión" in resp.text
    resp = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion(probability_col="x1"))
    assert resp.status_code == 422, resp.text
    assert "probability_col" in resp.text
