"""Ejemplo multiclase del registro de uso.

`GET /api/content/registro-uso/ejemplo.csv?tipo=multiclass` descarga un ejemplo
con nombres de clase en las tres columnas de decisión, sin `refer`. Sale de
`registro-uso-ayuda.json` (campo `ejemplo_multiclase`), que escribe
`build/gen_content_registro_uso.py` con las clases de la plantilla `multiclase`.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.app.services.plantillas_datos import CLASES_PLANTILLA_MULTICLASE, plantilla_csv

RUTA = "/api/content/registro-uso/ejemplo.csv"
COLUMNAS_DECISION = ("human_decision", "model_output", "ground_truth")

HAY_GENERADOR = (Path(__file__).resolve().parents[2] / "docs" / "ui-4").is_dir()
requiere_generador = pytest.mark.skipif(
    not HAY_GENERADOR,
    reason="falta build/gen_content.py y sus fuentes en docs/, que no viajan en el árbol público",
)


def _filas(texto: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(texto)))


def test_ejemplo_multiclase_lleva_nombres_de_clase_y_no_refer(client: TestClient):
    resp = client.get(RUTA, params={"tipo": "multiclass"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "registro-uso-ejemplo-multiclase.csv" in resp.headers["content-disposition"]
    filas = _filas(resp.text)
    assert len(filas) == 5
    assert tuple(filas[0].keys())[:4] == ("date", *COLUMNAS_DECISION)
    clases = set(CLASES_PLANTILLA_MULTICLASE)
    for fila in filas:
        for col in COLUMNAS_DECISION:
            # la verdad puede ir en blanco (todavía no se sabe); el resto, una clase
            assert fila[col] in clases | {""}, (col, fila)
    assert "refer" not in resp.text and "no-refer" not in resp.text
    # las tres clases salen en el ejemplo, para que se vea el formato entero
    vistas = {fila[col] for fila in filas for col in COLUMNAS_DECISION}
    assert clases <= vistas


def test_ejemplo_por_defecto_sigue_siendo_el_binario(client: TestClient):
    binario = client.get(RUTA)
    explicito = client.get(RUTA, params={"tipo": "binary"})
    assert binario.status_code == explicito.status_code == 200
    assert binario.text == explicito.text
    assert "no-refer" in binario.text
    assert "registro-uso-ejemplo.csv" in binario.headers["content-disposition"]
    assert "multiclase" not in binario.headers["content-disposition"]


def test_tipo_desconocido_da_422(client: TestClient):
    assert client.get(RUTA, params={"tipo": "regresion"}).status_code == 422


def test_ayuda_trae_el_ejemplo_multiclase_igual_que_la_descarga(client: TestClient):
    cuerpo = client.get("/api/content/registro-uso").json()
    ejemplo = cuerpo["ejemplo_multiclase"]
    assert ejemplo["nombre_fichero"] == "registro-uso-ejemplo-multiclase.csv"
    assert ejemplo["n_filas"] == 5 == len(ejemplo["filas"])
    assert ejemplo["columnas"] == cuerpo["ejemplo"]["columnas"]
    assert client.get(RUTA, params={"tipo": "multiclass"}).text == ejemplo["csv"]
    # la nota nombra las clases de la plantilla, sin repetir su texto a mano
    for clase in CLASES_PLANTILLA_MULTICLASE:
        assert clase in ejemplo["nota"]


def test_clases_del_ejemplo_son_las_de_la_plantilla_multiclase():
    """Una sola fuente: las clases de la plantilla `multiclase` y las del ejemplo."""
    _, contenido = plantilla_csv("multiclase")
    clases_plantilla = {fila["prediction"] for fila in _filas(contenido)}
    assert clases_plantilla == set(CLASES_PLANTILLA_MULTICLASE)


def test_ejemplo_multiclase_entra_por_la_subida_real(client: TestClient):
    """Se sube tal cual a un proyecto multiclase con esas clases y da cinco filas."""
    proyecto = client.post(
        "/api/projects",
        json={
            "name": "registro-ejemplo-multiclase",
            "domain": "libre",
            "task_type": "multiclass",
            "classes": list(CLASES_PLANTILLA_MULTICLASE),
            "mapping_template": {"favorable_label": [CLASES_PLANTILLA_MULTICLASE[0]]},
        },
        headers=actor_headers("miguel"),
    )
    assert proyecto.status_code == 200, proyecto.text
    ejemplo = client.get(RUTA, params={"tipo": "multiclass"})
    resp = client.post(
        f"/api/projects/{proyecto.json()['id']}/usage-logs/upload",
        files={"file": ("registro-uso-ejemplo-multiclase.csv", ejemplo.content, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["n_rows"] == 5


def test_el_ejemplo_binario_no_entra_en_un_proyecto_multiclase(client: TestClient):
    """El motivo del arreglo: refer y no-refer dan 422 en multiclase."""
    proyecto = client.post(
        "/api/projects",
        json={
            "name": "registro-binario-en-multiclase",
            "domain": "libre",
            "task_type": "multiclass",
            "classes": list(CLASES_PLANTILLA_MULTICLASE),
            "mapping_template": {"favorable_label": [CLASES_PLANTILLA_MULTICLASE[0]]},
        },
        headers=actor_headers("miguel"),
    ).json()
    binario = client.get(RUTA)
    resp = client.post(
        f"/api/projects/{proyecto['id']}/usage-logs/upload",
        files={"file": ("registro-uso-ejemplo.csv", binario.content, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422


@requiere_generador
def test_registro_uso_ayuda_esta_regenerada_con_el_ejemplo_multiclase():
    """`gen_content --check` cubre el campo nuevo."""
    from build.gen_content import REGISTRO_USO_JSON, _volcar
    from build.gen_content_registro_uso import generar_registro_uso

    generado = generar_registro_uso()
    assert "ejemplo_multiclase" in generado
    assert REGISTRO_USO_JSON.read_text(encoding="utf-8") == _volcar(generado)
    assert "paciente" not in REGISTRO_USO_JSON.read_text(encoding="utf-8").lower()
