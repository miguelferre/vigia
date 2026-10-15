"""Ejemplo del registro de uso de un modelo de regresión.

`GET /api/content/registro-uso/ejemplo.csv?tipo=regression` descarga un ejemplo
con cifras en las tres columnas de decisión, sin `refer`. Sale de
`registro-uso-ayuda.json` (campo `ejemplo_regresion`), que escribe
`build/gen_content_registro_uso.py`.
"""

from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient

from tests.api import _datos_regresion as r
from tests.api.conftest import actor_headers

RUTA = "/api/content/registro-uso/ejemplo.csv"
COLUMNAS_DECISION = ("human_decision", "model_output", "ground_truth")


def _filas(texto: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(texto)))


def _subir(client: TestClient, proyecto_id: int, contenido: bytes):
    return client.post(
        f"/api/projects/{proyecto_id}/usage-logs/upload",
        files={"file": ("registro.csv", contenido, "text/csv")},
        headers=actor_headers("miguel"),
    )


def test_el_ejemplo_de_regresion_lleva_cifras_y_no_refer(client: TestClient):
    resp = client.get(RUTA, params={"tipo": "regression"})
    assert resp.status_code == 200
    assert "registro-uso-ejemplo-regresion.csv" in resp.headers["content-disposition"]
    filas = _filas(resp.text)
    assert len(filas) == 5
    for fila in filas:
        for col in COLUMNAS_DECISION:
            if fila[col]:
                float(fila[col])
            assert fila[col] not in ("refer", "no-refer")


def test_la_ayuda_trae_el_ejemplo_de_regresion_igual_que_la_descarga(client: TestClient):
    ejemplo = client.get("/api/content/registro-uso").json()["ejemplo_regresion"]
    assert ejemplo["csv"] == client.get(RUTA, params={"tipo": "regression"}).text
    assert "no cuenta como override" in ejemplo["nota"]


def test_el_ejemplo_de_regresion_entra_por_la_subida_real(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "registro-ejemplo-regresion", rangos=[[40.0, None]])
    resp = _subir(client, proyecto["id"], client.get(RUTA, params={"tipo": "regression"}).content)
    assert resp.status_code == 200, resp.text
    assert resp.json()["n_rows"] == 5


def test_el_ejemplo_binario_no_entra_en_un_proyecto_de_regresion(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "registro-binario-en-regresion", rangos=[[40.0, None]])
    resp = _subir(client, proyecto["id"], client.get(RUTA).content)
    assert resp.status_code == 422
    assert "en regresión el registro trae las cifras" in resp.text
