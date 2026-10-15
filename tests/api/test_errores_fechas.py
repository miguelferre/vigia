"""Avisos de fecha en la ingesta y en el
registro de uso. Un aviso nunca rechaza."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers

CABECERA_USO = "date,human_decision,model_output,ground_truth\n"


def _proyecto(client: TestClient, nombre: str) -> dict:
    resp = client.post(
        "/api/projects", json={"name": nombre, "domain": "reuma"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ingerir_lote(client: TestClient, proyecto: dict, filas: list[str], *, con_fecha: bool) -> dict:
    cuerpo = "id,fecha,edad,pred,label\n" + "\n".join(filas) + "\n"
    resp = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("lote.csv", cuerpo.encode("utf-8"), "text/csv")},
        data={"kind": "combined", "role": "production"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    dataset_id = resp.json()["dataset"]["id"]
    mapeo = {
        "prediction_col": "pred",
        "label_col": "label",
        "id_col": "id",
        "feature_cols": ["edad"],
        "favorable_label": 1,
    }
    if con_fecha:
        mapeo["timestamp_col"] = "fecha"
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": mapeo},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"model_version_id": proyecto["active_version_id"], "evaluate": False},
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    return job["result"]


def _subir_uso(client: TestClient, proyecto: dict, fechas: list[str]) -> dict:
    cuerpo = CABECERA_USO + "".join(f"{f},refer,refer,refer\n" for f in fechas)
    resp = client.post(
        f"/api/projects/{proyecto['id']}/usage-logs/upload",
        files={"file": ("uso.csv", cuerpo.encode("utf-8"), "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_fechas_mezcladas_dan_aviso_con_filas_ejemplo_y_formatos(client: TestClient):
    proyecto = _proyecto(client, "fechas-mezcladas")
    resultado = _ingerir_lote(
        client,
        proyecto,
        [
            "1,2026-01-05,30,1,1",
            "2,05/01/2026,40,0,0",
            "3,12 enero 2026,50,1,1",
            "4,ayer,60,0,0",
            "5,2026-02-30,70,1,0",
            "6,06-01-2026,35,1,1",
        ],
        con_fecha=True,
    )
    avisos = [a for a in resultado["avisos"] if "fecha ilegible" in a]
    assert len(avisos) == 1, resultado["avisos"]
    texto = avisos[0]
    assert "3 filas tienen una fecha ilegible" in texto
    assert "«fecha»" in texto and "«12 enero 2026»" in texto
    assert "aaaa-mm-dd, dd/mm/aaaa o dd-mm-aaaa" in texto
    # se ingiere igual y la columna se guarda como llega
    registros = client.get(f"/api/batches/{resultado['batch_id']}/records").json()["items"]
    assert len(registros) == 6
    assert {r["timestamp"] for r in registros} >= {"12 enero 2026", "ayer"}


def test_fechas_iso_y_espanolas_entran_sin_aviso(client: TestClient):
    proyecto = _proyecto(client, "fechas-limpias")
    resultado = _ingerir_lote(
        client,
        proyecto,
        [
            "1,2026-01-05,30,1,1",
            "2,2026-01-06T10:30:00,40,0,0",
            "3,07/01/2026,50,1,1",
            "4,08-01-2026,60,0,0",
        ],
        con_fecha=True,
    )
    assert not [a for a in resultado["avisos"] if "fecha" in a]


def test_sin_columna_de_fecha_mapeada_no_hay_aviso(client: TestClient):
    proyecto = _proyecto(client, "sin-timestamp")
    resultado = _ingerir_lote(
        client, proyecto, ["1,ayer,30,1,1", "2,antes de ayer,40,0,0"], con_fecha=False
    )
    assert not [a for a in resultado["avisos"] if "fecha" in a]


def test_registro_de_uso_con_fechas_sin_lote_avisa_en_respuesta_y_evento(client: TestClient):
    proyecto = _proyecto(client, "uso-adelantado")
    _ingerir_lote(
        client,
        proyecto,
        ["1,2026-01-05,30,1,1", "2,2026-01-12,40,0,0", "3,2026-01-09,50,1,1"],
        con_fecha=True,
    )
    cuerpo = _subir_uso(client, proyecto, ["2026-01-10", "2026-01-12", "2026-01-20", "2026-01-26"])
    assert cuerpo["n_rows"] == 4  # la subida entra completa
    assert len(cuerpo["avisos"]) == 1
    aviso = cuerpo["avisos"][0]
    assert aviso.startswith(
        "2 filas son de fechas sin lote del modelo: las reglas cruzadas las usan igual;"
    )
    assert "sube antes los lotes de esas semanas" in aviso
    assert "2026-01-12" in aviso and "columna de fecha del lote" in aviso
    eventos = client.get(
        "/api/events", params={"object_type": "dataset", "object_id": cuerpo["dataset_id"]}
    ).json()["items"]
    evento = next(e for e in eventos if e["action"] == "usage_log.ingerido")
    assert evento["after"]["avisos"] == cuerpo["avisos"]


def test_registro_de_uso_sin_columna_de_fecha_en_el_lote_usa_la_fecha_de_ingesta(
    client: TestClient,
):
    proyecto = _proyecto(client, "uso-sin-fecha-de-lote")
    _ingerir_lote(client, proyecto, ["1,x,30,1,1", "2,y,40,0,0"], con_fecha=False)
    cuerpo = _subir_uso(client, proyecto, ["2026-01-10", "2030-01-01"])
    assert len(cuerpo["avisos"]) == 1
    assert cuerpo["avisos"][0].startswith("1 fila es de una fecha sin lote del modelo")
    assert "fecha de ingesta del lote" in cuerpo["avisos"][0]


def test_registro_de_uso_dentro_del_rango_de_los_lotes_no_avisa(client: TestClient):
    proyecto = _proyecto(client, "uso-en-rango")
    _ingerir_lote(client, proyecto, ["1,2026-01-05,30,1,1", "2,2026-01-12,40,0,0"], con_fecha=True)
    assert _subir_uso(client, proyecto, ["2026-01-05", "2026-01-12"])["avisos"] == []


def test_registro_de_uso_sin_lotes_de_produccion_no_avisa(client: TestClient):
    proyecto = _proyecto(client, "uso-sin-lotes")
    assert _subir_uso(client, proyecto, ["2026-01-05", "2026-03-12"])["avisos"] == []


def test_registro_de_uso_con_fecha_ilegible_da_422_con_la_fila_y_los_formatos(client: TestClient):
    proyecto = _proyecto(client, "uso-fecha-ilegible")
    cuerpo = CABECERA_USO + "2026-01-05,refer,refer,refer\n12 enero 2026,refer,refer,refer\n"
    resp = client.post(
        f"/api/projects/{proyecto['id']}/usage-logs/upload",
        files={"file": ("uso.csv", cuerpo.encode("utf-8"), "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422, resp.text
    detalle = resp.json()["detail"]
    assert "fila 2" in detalle and "no se lee" in detalle
    assert "aaaa-mm-dd, dd/mm/aaaa o dd-mm-aaaa" in detalle
