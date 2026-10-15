"""Tabla Lotes y Datasets: el lote lleva el nombre de su fichero y el dataset cuenta sus lotes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.test_datasets import _crear_proyecto, _ingerir, _mapear, _subir

CSV = b"id,prediction,label,Age\n1,1,1,30\n2,0,0,45\n"
MAPEO = {
    "prediction_col": "prediction",
    "label_col": "label",
    "id_col": "id",
    "feature_cols": ["Age"],
    "favorable_label": 1,
}


def _subir_e_ingerir(client: TestClient, proyecto: dict, nombre: str, role: str) -> dict:
    body = _subir(
        client,
        proyecto["id"],
        filename=nombre,
        content=CSV,
        kind="combined",
        role=role,
        content_type="text/csv",
    )
    dataset_id = body["dataset"]["id"]
    _mapear(client, dataset_id, MAPEO, {})
    resultado = _ingerir(
        client, dataset_id, model_version_id=proyecto["active_version_id"], mode="crear"
    )
    return {"dataset_id": dataset_id, "batch_id": resultado["batch_id"]}


def test_lote_lleva_el_nombre_del_fichero_en_lista_y_detalle(client: TestClient):
    proyecto = _crear_proyecto(client, "lotes-con-fichero")
    base = _subir_e_ingerir(client, proyecto, "linea-base.csv", "baseline")
    nuevo = _subir_e_ingerir(client, proyecto, "lote-02.csv", "production")

    lista = client.get(f"/api/projects/{proyecto['id']}/batches").json()
    nombres = {b["id"]: b["dataset_name"] for b in lista["items"]}
    assert nombres == {base["batch_id"]: "linea-base.csv", nuevo["batch_id"]: "lote-02.csv"}

    detalle = client.get(f"/api/batches/{nuevo['batch_id']}").json()
    assert detalle["dataset_name"] == "lote-02.csv"


def test_dataset_cuenta_sus_lotes_y_sin_lotes_es_cero(client: TestClient):
    proyecto = _crear_proyecto(client, "datasets-con-lotes")
    ingerido = _subir_e_ingerir(client, proyecto, "a.csv", "baseline")
    suelto = _subir(
        client,
        proyecto["id"],
        filename="suelto.csv",
        content=CSV,
        kind="combined",
        role="production",
        content_type="text/csv",
    )["dataset"]
    assert suelto["n_batches"] == 0

    lista = client.get(f"/api/projects/{proyecto['id']}/datasets").json()
    cuentas = {d["id"]: d["n_batches"] for d in lista["items"]}
    assert cuentas == {ingerido["dataset_id"]: 1, suelto["id"]: 0}

    assert client.get(f"/api/datasets/{ingerido['dataset_id']}").json()["n_batches"] == 1
    assert client.get(f"/api/datasets/{suelto['id']}").json()["n_batches"] == 0
