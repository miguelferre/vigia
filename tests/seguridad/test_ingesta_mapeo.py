"""Ingesta y mapeo: validación del mapeo y del formato de subida.

Cada test comprueba el control seguro de una huella; ver `HUELLAS`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.app.main import create_app
from vigia.app.services.ingest import detect_format
from vigia.app.settings import Settings
from vigia.core.loaders import to_canonical
from vigia.core.schema import ColumnMapping, DatosNoValidos

HUELLAS = {
    "test_el_mapeo_rechaza_una_columna_sin_mapear_con_nombre_canonico": "ingest/feature-cols-overwrite-canonical-columns",
    "test_un_registro_de_uso_sin_mapear_remite_a_su_sitio": "ingest/feature-cols-overwrite-canonical-columns",
    "test_el_mapeo_rechaza_una_variable_con_nombre_canonico": "ingest/feature-cols-overwrite-canonical-columns",
    "test_las_columnas_canonicas_del_fichero_no_pisan_el_lote": "ingest/feature-cols-overwrite-canonical-columns",
    "test_el_mapeo_con_grupos_invalidos_da_422_y_no_se_guarda": "mapping/protected-groups-shape-finiteness-overlap-unvalidated",
    "test_la_plantilla_con_grupos_invalidos_da_422": "mapping/protected-groups-shape-finiteness-overlap-unvalidated",
    "test_un_json_demasiado_profundo_o_con_entero_enorme_da_422": "ingest/detect-format-json-loads-depth",
}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        data_dir=d, host="127.0.0.1", port_start=8901, open_browser=False, jobs_inline=True,
        sse_heartbeat_s=0.2,
    )
    app: FastAPI = create_app(settings)
    app.state.port = 8901
    app.state.shutdown_token = "test-token"
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _subir(client: TestClient, contenido: bytes, nombre: str = "lote.csv"):
    r = client.post("/api/projects", json={"name": f"s1a-{nombre}", "domain": "reuma"},
                    headers=actor_headers("miguel"))
    assert r.status_code == 200, r.text
    proyecto = r.json()
    return proyecto, client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": (nombre, contenido, "application/octet-stream")},
        data={"kind": "combined", "role": "production"},
        headers=actor_headers("miguel"),
    )


def _csv(extra: str = "age") -> bytes:
    filas = [f"id,prediction,label,{extra}"] + [f"E{i},{i % 2},{i % 3 == 0:d},{20 + i}" for i in range(30)]
    return ("\n".join(filas) + "\n").encode()


def _mapear(client: TestClient, dataset_id: int, **extra):
    mapeo = {"prediction_col": "prediction", "label_col": "label", "id_col": "id",
             "favorable_label": 1, **extra}
    return client.put(f"/api/datasets/{dataset_id}/mapping", json={"mapping": mapeo},
                      headers=actor_headers("miguel"))


def test_el_mapeo_rechaza_una_columna_sin_mapear_con_nombre_canonico(client: TestClient):
    """Una columna del fichero sin mapear que se llama como una columna canónica
    se rechaza con 422 y el nombre de la columna."""
    _, resp = _subir(client, _csv("group_code"))
    assert resp.status_code == 200, resp.text
    r = _mapear(client, resp.json()["dataset"]["id"])
    assert r.status_code == 422, r.text
    assert "group_code" in r.text


def test_un_registro_de_uso_sin_mapear_remite_a_su_sitio(client: TestClient):
    """Un registro de uso subido como datos del modelo se rechaza en el mapeo y el
    mensaje dice dónde se sube."""
    contenido = (
        b"date,human_decision,model_output,ground_truth,clinician_pseudonym,subgroup\n"
        b"2026-01-01,refer,refer,refer,c1,a\n"
    )
    _, resp = _subir(client, contenido)
    r = _mapear(client, resp.json()["dataset"]["id"], prediction_col="model_output",
                label_col="ground_truth", id_col="date", favorable_label="refer")
    assert r.status_code == 422, r.text
    assert "Registro de uso" in r.text


def test_el_mapeo_rechaza_una_variable_con_nombre_canonico(client: TestClient):
    """Una variable declarada en `feature_cols` con nombre canónico se rechaza con 422."""
    _, resp = _subir(client, _csv("seq"))
    r = _mapear(client, resp.json()["dataset"]["id"], feature_cols=["seq"])
    assert r.status_code == 422, r.text
    assert "seq" in r.text


def test_las_columnas_canonicas_del_fichero_no_pisan_el_lote():
    """`to_canonical` no deja que una columna extra con nombre canónico sustituya
    la columna que el mapeo ya calculó, ni la acepta como variable explícita."""
    df = pd.DataFrame({"id": ["a", "b", "c"], "pred": [1, 0, 1], "y": [1, 1, 0],
                       "label": [9, 9, 9], "seq": [7, 7, 7], "edad": [3, 4, 5]})
    mapeo = ColumnMapping(prediction_col="pred", label_col="y", id_col="id", favorable_label=1)
    canon = to_canonical(df, mapeo)
    assert canon["label"].tolist() == [1.0, 1.0, 0.0]
    assert canon["seq"].tolist() == [0, 1, 2]
    assert "edad" in canon.columns
    explicito = mapeo.model_copy(update={"feature_cols": ["label"]})
    with pytest.raises(DatosNoValidos, match="label"):
        to_canonical(df, explicito)


@pytest.mark.parametrize("grupos", [[[1]], [[18, 35]]], ids=["forma", "solape"])
def test_el_mapeo_con_grupos_invalidos_da_422_y_no_se_guarda(client: TestClient, grupos):
    """Un mapeo con grupos mal formados o solapados da 422 antes de guardar nada."""
    _, resp = _subir(client, _csv())
    ds = resp.json()["dataset"]["id"]
    r = _mapear(client, ds, protected_attr_col="age", unpriv_groups=grupos, priv_groups=[[30, 75]])
    assert r.status_code == 422, r.text
    guardado = client.get(f"/api/datasets/{ds}").json()
    assert guardado["status"] == "subido"
    assert guardado["mapping"] is None


def test_la_plantilla_con_grupos_invalidos_da_422(client: TestClient):
    """El PATCH de la plantilla del proyecto rechaza grupos solapados."""
    r = client.post("/api/projects", json={"name": "s1a-plantilla", "domain": "reuma"},
                    headers=actor_headers("miguel"))
    pid = r.json()["id"]
    plantilla = {"protected_attr_col": "age", "unpriv_groups": [[18, 35]], "priv_groups": [[30, 75]]}
    r = client.patch(f"/api/projects/{pid}", headers=actor_headers("miguel"),
                     json={"actor": "miguel", "motivo": "plantilla de prueba", "mapping_template": plantilla})
    assert r.status_code == 422, r.text


@pytest.mark.parametrize(
    "contenido",
    [b"[" * 200_000 + b"]" * 200_000, b"[" + b"9" * 6000 + b"]"],
    ids=["anidado", "entero"],
)
def test_un_json_demasiado_profundo_o_con_entero_enorme_da_422(client: TestClient, contenido):
    """Un JSON demasiado anidado o con un entero enorme da 422 en español, no 500."""
    with pytest.raises(HTTPException) as exc:
        detect_format("datos.json", contenido)
    assert exc.value.status_code == 422
    _, resp = _subir(client, contenido, "datos.json")
    assert resp.status_code == 422, resp.text
