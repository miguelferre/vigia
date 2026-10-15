"""Arreglos del backend multiclase.

Cada test falla antes de su arreglo y pasa después. Los de MCP están
en `tests/mcp/test_multiclase_correcciones.py`.
"""

from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from tests.api import _datos_multiclase as d
from vigia.app.services import alerting
from vigia.core.drift import prediction_drift_multiclase

# ---------------------------------------------------------------------------
# Mensajes de multiclase con «qué hacer»
# ---------------------------------------------------------------------------


def test_t2m2_etiqueta_con_clase_nueva_dice_que_hacer(client: TestClient):
    """El aviso dice qué filas quedan fuera de la calidad y qué hacer."""
    proyecto, _s, _t = d.linea_base_multiclase(client, "a-t2m2", n=200)
    filas = d.filas_multiclase(80, seed=5, prefijo_id="e")
    filas[3]["label"] = "acoso"
    sub = d.subir(client, proyecto["id"], d.a_csv(filas), rol="production")
    assert d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase()).status_code == 200
    trabajo = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"])
    assert trabajo["status"] == "terminado", trabajo
    aviso = next(a for a in trabajo["result"]["avisos"] if "acoso" in a)
    assert "quedan fuera de la calidad" in aviso
    assert "corrígela en el fichero" in aviso
    assert "crea un modelo o una versión con esa clase" in aviso


def test_t2m4_clase_sin_filas_en_la_linea_base_dice_que_hacer(client: TestClient):
    """El aviso de soporte 0 dice qué hacer."""
    clases = [*d.CLASES, "acoso"]
    filas = d.filas_multiclase(300)
    for f in filas:
        f["prob_acoso"] = 0.0
    p = d.crear_proyecto_multiclase(client, "a-t2m4", clases=clases)
    sub = d.subir(client, p["id"], d.a_csv(filas))
    assert d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase(clases)).status_code == 200
    trabajo = d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])
    aviso = next(a for a in trabajo["result"]["avisos"] if "La clase acoso" in a)
    assert "soporte 0" in aviso
    assert "Las clases de un modelo no cambian después de subir la línea base" in aviso
    assert "crea el modelo de nuevo sin ella" in aviso
    assert "con una línea base que tenga casos de esa clase" in aviso
    # Lo que dice el aviso es verdad: las clases no se cambian después de fijarlas.
    cambio = client.patch(
        f"/api/projects/{p['id']}",
        json={"actor": "miguel", "motivo": "probar", "mapping_template": {"classes": d.CLASES}},
        headers={"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"},
    )
    assert cambio.status_code in (200, 422), cambio.text
    assert client.get(f"/api/projects/{p['id']}").json()["classes"] == clases


def test_t2m4_el_titulo_de_la_alerta_de_deriva_nombra_la_clase_nueva():
    """La línea base no tenía `violencia` y el lote sí. El motor deja
    `permitido` como clase de mayor cambio, pero la causa es `violencia`."""
    clases = tuple(d.CLASES)
    base = pd.Series(["permitido"] * 70 + ["spam"] * 20 + ["odio"] * 10)
    lote = pd.Series(["permitido"] * 50 + ["spam"] * 26 + ["odio"] * 10 + ["violencia"] * 14)
    pred = prediction_drift_multiclase(base, lote, clases, ("permitido",))
    assert pred["clase_mayor_cambio"] == "permitido"  # clase de mayor cambio
    detalle = alerting._detalle_deriva("prediction_drift_score", {"details": {"prediction": pred}})
    assert detalle == "clase violencia nueva: 0 % en la línea base y 14,0 % en el lote"


def test_deriva_sin_clase_nueva_nombra_la_de_mayor_cambio_y_binario_no_cambia():
    clases = ("a", "b", "c")
    base = pd.Series(["a"] * 60 + ["b"] * 30 + ["c"] * 10)
    lote = pd.Series(["a"] * 40 + ["b"] * 40 + ["c"] * 20)
    pred = prediction_drift_multiclase(base, lote, clases, ("a",))
    detalle = alerting._detalle_deriva("prediction_drift_score", {"details": {"prediction": pred}})
    assert detalle == "mayor cambio en la clase a (-20,0 puntos)"
    # Binario: la deriva de predicción no trae `por_clase` y el título queda como estaba.
    binario = {"details": {"prediction": {"rate_base": 0.4, "rate_cur": 0.5}}}
    assert alerting._detalle_deriva("prediction_drift_score", binario) is None


def test_cuatro_columnas_para_cinco_clases_da_un_422_en_espanol(client: TestClient):
    """Sin nombres de campo en inglés ni «Value error»."""
    p = d.crear_proyecto_multiclase(client, "a-t2m5b")
    sub = d.subir(client, p["id"], d.a_csv(d.filas_multiclase(60)))
    mapeo = d.mapeo_multiclase(probability_cols=[f"prob_{c}" for c in d.CLASES[:-1]])
    resp = d.mapear(client, sub["dataset"]["id"], mapeo)
    assert resp.status_code == 422, resp.text
    # Misma forma que el resto de 422 de cuerpo: lista con `loc`, `type` y `msg` en español.
    errores = resp.json()["detail"]
    assert isinstance(errores, list) and len(errores) == 1
    assert errores[0]["msg"] == (
        "Hay 5 clases y 4 columnas de probabilidad: pon una columna por clase, en el orden de las clases"
    )
    assert "probability_cols" not in resp.text and "Value error" not in resp.text


def test_t2m8_probabilidad_vacia_concuerda_y_dice_que_hacer(client: TestClient):
    """«las columnas de probabilidad tiene» pasa a una frase que concuerda."""
    filas = d.filas_multiclase(120)
    for i in (3, 7):
        filas[i]["prob_odio"] = ""
    p = d.crear_proyecto_multiclase(client, "a-t2m8")
    sub = d.subir(client, p["id"], d.a_csv(filas))
    assert d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase()).status_code == 200
    trabajo = d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])
    assert trabajo["status"] == "error", trabajo
    texto = trabajo["error"]
    assert "Hay 2 de 120 filas con alguna probabilidad vacía en las columnas de probabilidad" in texto
    assert "tiene" not in texto
    assert "rellena los huecos o quita esas filas del fichero" in texto
