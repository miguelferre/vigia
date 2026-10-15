"""Las plantillas de datos descargables
(cinco de siempre y la línea base multiclase).

Por tipo: descarga, subida a un proyecto nuevo, mapeo sugerido por
`_suggest_mapping` más las variables, e ingesta sin error ni aviso. Más la
coherencia entre las cinco y el origen único de `registro-uso`.
"""

from __future__ import annotations

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.app.services import plantillas_datos
from vigia.app.services.plantillas_datos import TIPOS_PLANTILLA

VARIABLES = ["crp", "esr", "joint_count"]


def _descargar(client: TestClient, tipo: str) -> tuple[str, bytes]:
    resp = client.get(f"/api/content/plantillas/{tipo}.csv")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    disposicion = resp.headers["content-disposition"]
    nombre = disposicion.split("filename=")[1]
    return nombre, resp.content


def _filas(contenido: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(contenido.decode("utf-8"))))


def _proyecto(client: TestClient, nombre: str) -> dict:
    resp = client.post(
        "/api/projects", json={"name": nombre, "domain": "reuma"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir_dataset(
    client: TestClient, pid: int, nombre: str, contenido: bytes, kind: str, role: str
) -> dict:
    resp = client.post(
        f"/api/projects/{pid}/datasets/upload",
        files={"file": (nombre, contenido, "text/csv")},
        data={"kind": kind, "role": role},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _mapear_e_ingerir(client: TestClient, subida: dict, *, con_variables: bool) -> dict:
    """Mapeo sugerido (más las variables si el tipo las lleva) e ingesta."""
    mapeo = dict(subida["suggested_mapping"])
    if con_variables:
        mapeo["feature_cols"] = VARIABLES
    did = subida["dataset"]["id"]
    resp = client.put(
        f"/api/datasets/{did}/mapping", json={"mapping": mapeo}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    job = client.post(f"/api/datasets/{did}/ingest", json={"evaluate": False})
    assert job.status_code == 200, job.text
    estado = client.get(f"/api/jobs/{job.json()['id']}").json()
    assert estado["status"] == "terminado", estado
    return estado["result"]


# ---------------------------------------------------------------------------
# Descarga y forma
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tipo", TIPOS_PLANTILLA)
def test_plantilla_se_descarga_con_cinco_filas_y_nombre_sintetico(client: TestClient, tipo: str):
    nombre, contenido = _descargar(client, tipo)
    assert nombre == f"plantilla-{tipo}-sintetico.csv"
    assert len(_filas(contenido)) == 5
    assert contenido.decode("utf-8").splitlines()[0].count(",") >= 1


def test_plantilla_desconocida_da_404_en_espanol(client: TestClient):
    resp = client.get("/api/content/plantillas/inventada.csv")
    assert resp.status_code == 404
    assert "inventada" in resp.json()["detail"]


def test_registro_uso_sale_de_la_misma_fuente_que_el_ejemplo(client: TestClient):
    _, contenido = _descargar(client, "registro-uso")
    ejemplo = client.get("/api/content/registro-uso/ejemplo.csv")
    assert contenido == ejemplo.content
    ayuda = json.loads(client.get("/api/content/registro-uso").text)
    assert contenido.decode("utf-8") == ayuda["ejemplo"]["csv"]


def test_plantilla_csv_rechaza_un_tipo_fuera_de_la_lista():
    with pytest.raises(ValueError):
        plantillas_datos.plantilla_csv("otro")


# ---------------------------------------------------------------------------
# Coherencia entre las cinco
# ---------------------------------------------------------------------------


def test_las_plantillas_son_coherentes_entre_si(client: TestClient):
    datos = {tipo: _filas(_descargar(client, tipo)[1]) for tipo in TIPOS_PLANTILLA}
    ids_lote = {f["id"] for f in datos["lote"]}
    ids_base = {f["id"] for f in datos["linea-base"]}
    assert {f["id"] for f in datos["etiquetas"]} == ids_lote
    assert not ids_lote & ids_base, "los ids del lote no repiten los de la línea base"
    fechas_lote = {f["date"] for f in datos["lote"]}
    assert min(fechas_lote) <= min(f["date"] for f in datos["registro-uso"])
    assert max(f["date"] for f in datos["registro-uso"]) <= max(fechas_lote)
    assert all(f["date"] < min(fechas_lote) for f in datos["linea-base"])
    for fila in datos["registro-uso"] + datos["lote"] + datos["linea-base"]:
        assert len(fila["date"]) == 10 and fila["date"][4] == "-" and fila["date"][7] == "-"
    meses_lote = {d[:7] for d in fechas_lote}
    assert meses_lote <= {f["period"] for f in datos["outcomes"]}


# ---------------------------------------------------------------------------
# Subida, mapeo sugerido e ingesta sin error ni aviso
# ---------------------------------------------------------------------------


def test_linea_base_entra_sin_avisos(client: TestClient):
    pid = _proyecto(client, "plantilla-base")["id"]
    nombre, contenido = _descargar(client, "linea-base")
    subida = _subir_dataset(client, pid, nombre, contenido, "combined", "baseline")
    sugerido = subida["suggested_mapping"]
    assert sugerido["prediction_col"] == "prediction"
    assert sugerido["probability_col"] == "probability"
    assert sugerido["label_col"] == "label"
    assert sugerido["id_col"] == "id"
    assert sugerido["timestamp_col"] == "date"
    assert sugerido["protected_attr_col"] is None  # la columna age_years no se toma por grupo
    resultado = _mapear_e_ingerir(client, subida, con_variables=True)
    assert resultado["n_rows"] == 5
    assert resultado["avisos"] == []


def test_lote_etiquetas_y_registro_uso_entran_en_cadena_sin_avisos(client: TestClient):
    pid = _proyecto(client, "plantilla-cadena")["id"]
    base = _subir_dataset(client, pid, *_descargar(client, "linea-base"), "combined", "baseline")
    _mapear_e_ingerir(client, base, con_variables=True)

    lote = _subir_dataset(client, pid, *_descargar(client, "lote"), "payload", "production")
    sugerido = lote["suggested_mapping"]
    assert sugerido["prediction_col"] == "prediction"
    assert sugerido["id_col"] == "id"
    assert sugerido["timestamp_col"] == "date"
    assert sugerido["label_col"] is None
    res_lote = _mapear_e_ingerir(client, lote, con_variables=True)
    assert res_lote["n_rows"] == 5
    assert res_lote["avisos"] == []

    etiquetas = _subir_dataset(client, pid, *_descargar(client, "etiquetas"), "feedback", "production")
    assert etiquetas["suggested_mapping"]["id_col"] == "id"
    assert etiquetas["suggested_mapping"]["label_col"] == "label"
    res_et = _mapear_e_ingerir(client, etiquetas, con_variables=False)
    assert res_et["n_matched"] == 5
    assert res_et["n_unmatched"] == 0
    assert res_et["avisos"] == []

    nombre, contenido = _descargar(client, "registro-uso")
    resp = client.post(
        f"/api/projects/{pid}/usage-logs/upload",
        files={"file": (nombre, contenido, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["n_rows"] == 5
    assert cuerpo.get("avisos", []) == []
    # Con cinco filas la comprobación de codificación no puede decidir: es lo
    # esperado y lo dice la nota del ejemplo; no es un aviso de la plantilla.
    assert cuerpo["comprobacion_codificacion"]["estado"] == "inconcluso"
    assert cuerpo["comprobacion_codificacion"].get("motivo")


def test_outcomes_entra_sin_error(client: TestClient):
    pid = _proyecto(client, "plantilla-outcomes")["id"]
    nombre, contenido = _descargar(client, "outcomes")
    resp = client.post(
        f"/api/projects/{pid}/outcomes",
        files={"file": (nombre, contenido, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["n_rows"] == 5
    assert cuerpo["n_creados"] == 5
    assert cuerpo["n_actualizados"] == 0


# ---------------------------------------------------------------------------
# Línea base multiclase
# ---------------------------------------------------------------------------


def test_plantilla_multiclase_trae_una_probabilidad_por_clase_que_suma_uno(client: TestClient):
    filas = _filas(_descargar(client, "multiclase")[1])
    clases = {f["prediction"] for f in filas} | {f["label"] for f in filas}
    assert clases == {"leve", "moderada", "grave"}
    columnas = [c for c in filas[0] if c.startswith("prob_")]
    assert columnas == ["prob_leve", "prob_moderada", "prob_grave"]
    for fila in filas:
        assert abs(sum(float(fila[c]) for c in columnas) - 1.0) < 1e-9


def test_plantilla_multiclase_entra_sin_avisos_y_el_mapeo_propone_clases(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={
            "name": "plantilla-multiclase",
            "domain": "reuma",
            "task_type": "multiclass",
            "mapping_template": {"favorable_label": ["leve"]},
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    pid = resp.json()["id"]
    nombre, contenido = _descargar(client, "multiclase")
    subida = _subir_dataset(client, pid, nombre, contenido, "combined", "baseline")
    sugerido = subida["suggested_mapping"]
    assert sugerido["prediction_col"] == "prediction"
    assert sugerido["label_col"] == "label"
    assert sugerido["probability_cols"] == ["prob_leve", "prob_moderada", "prob_grave"]
    assert sugerido["classes"] == ["leve", "moderada", "grave"]
    mapeo = dict(sugerido)
    mapeo["feature_cols"] = VARIABLES
    mapeo["favorable_label"] = ["leve"]
    did = subida["dataset"]["id"]
    resp = client.put(
        f"/api/datasets/{did}/mapping", json={"mapping": mapeo}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    job = client.post(f"/api/datasets/{did}/ingest", json={"evaluate": False})
    assert job.status_code == 200, job.text
    estado = client.get(f"/api/jobs/{job.json()['id']}").json()
    assert estado["status"] == "terminado", estado
    assert estado["result"]["n_rows"] == 5
    assert estado["result"]["avisos"] == []


# ---------------------------------------------------------------------------
# Línea base de regresión
# ---------------------------------------------------------------------------


def test_plantilla_regresion_trae_numeros_sin_unidad_ni_probabilidad(client: TestClient):
    filas = _filas(_descargar(client, "regresion")[1])
    assert set(filas[0]) == {"id", "date", "age_years", "crp", "esr", "joint_count", "prediction", "label"}
    for fila in filas:
        float(fila["prediction"])
        float(fila["label"])
        assert fila["prediction"].replace(".", "", 1).isdigit(), "sin unidad pegada al número"


def test_plantilla_regresion_entra_sin_avisos_y_el_mapeo_no_propone_clases(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={
            "name": "plantilla-regresion",
            "domain": "reuma",
            "task_type": "regression",
            "target_unit": plantillas_datos.UNIDAD_PLANTILLA_REGRESION,
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    pid = resp.json()["id"]
    nombre, contenido = _descargar(client, "regresion")
    subida = _subir_dataset(client, pid, nombre, contenido, "combined", "baseline")
    sugerido = subida["suggested_mapping"]
    assert sugerido["prediction_col"] == "prediction"
    assert sugerido["label_col"] == "label"
    assert sugerido["id_col"] == "id"
    assert not sugerido.get("probability_col") and not sugerido.get("probability_cols")
    assert not sugerido.get("favorable_label") and not sugerido.get("classes")
    resultado = _mapear_e_ingerir(client, subida, con_variables=True)
    assert resultado["n_rows"] == 5
    assert resultado["avisos"] == []
