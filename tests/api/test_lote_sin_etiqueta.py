"""Un lote de producción sin columna de etiqueta se mapea con la plantilla.

La etiqueta puede llegar después con las etiquetas tardías, así que un `combined`
de producción sin `label_col` ya no da 422 al mapear. La línea base sigue
exigiéndola, y un `feedback` también (su único contenido es la etiqueta).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers

PLANTILLA = {
    "id_col": "id",
    "prediction_col": "pred",
    "probability_col": "prob",
    "label_col": "outcome",
    "feature_cols": ["edad"],
    "protected_attr_col": "grupo",
    "protected_kind": "categorical",
    "unpriv_groups": ["a"],
    "priv_groups": ["b"],
    "favorable_label": 1,
}


def _csv(n: int, con_etiqueta: bool, desde: int = 0) -> bytes:
    filas = ["id,edad,grupo,prob,pred" + (",outcome" if con_etiqueta else "")]
    for i in range(n):
        p = ((i * 37) % 100) / 100
        fila = f"{desde + i},{30 + i % 40},{'ab'[i % 2]},{p},{1 if p > 0.5 else 0}"
        if con_etiqueta:
            fila += f",{1 if (i % 3) == 0 else 0}"
        filas.append(fila)
    return ("\n".join(filas) + "\n").encode()


def _proyecto(client: TestClient, nombre: str) -> int:
    resp = client.post(
        "/api/projects",
        json={"name": nombre, "domain": "reuma", "mapping_template": PLANTILLA},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _subir(client: TestClient, pid: int, fichero: bytes, *, kind: str, role: str) -> dict:
    resp = client.post(
        f"/api/projects/{pid}/datasets/upload",
        files={"file": (f"{role}.csv", fichero, "text/csv")},
        data={"kind": kind, "role": role},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["dataset"]


def _mapear(client: TestClient, dataset: dict):
    return client.put(
        f"/api/datasets/{dataset['id']}/mapping",
        json={"mapping": dataset["suggested_mapping"]},
        headers=actor_headers("miguel"),
    )


def _con_linea_base(client: TestClient, nombre: str) -> int:
    pid = _proyecto(client, nombre)
    base = _subir(client, pid, _csv(60, True), kind="combined", role="baseline")
    resp = _mapear(client, base)
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/api/datasets/{base['id']}/ingest", json={"evaluate": False})
    assert resp.status_code == 200, resp.text
    return pid


def test_lote_de_produccion_combined_sin_etiqueta_se_mapea_con_la_plantilla(client: TestClient):
    pid = _con_linea_base(client, "u6-16-lote")
    lote = _subir(client, pid, _csv(40, False, 1000), kind="combined", role="production")
    # La plantilla se aplica sin la etiqueta: la columna no está en el fichero.
    assert lote["suggested_mapping"]["label_col"] is None
    assert lote["suggested_mapping"]["prediction_col"] == "pred"
    resp = _mapear(client, lote)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "mapeado"


def test_lote_sin_etiqueta_sigue_su_curso_y_queda_sin_etiquetar(client: TestClient):
    pid = _con_linea_base(client, "u6-16-curso")
    lote = _subir(client, pid, _csv(40, False, 1000), kind="combined", role="production")
    assert _mapear(client, lote).status_code == 200
    resp = client.post(f"/api/datasets/{lote['id']}/ingest", json={"evaluate": False})
    assert resp.status_code == 200, resp.text
    final = client.get(f"/api/datasets/{lote['id']}").json()
    assert final["status"] == "ingerido"
    lotes = client.get(f"/api/projects/{pid}/batches").json()["items"]
    sin_etiqueta = [b for b in lotes if b["dataset_id"] == lote["id"]]
    assert len(sin_etiqueta) == 1
    assert sin_etiqueta[0]["n_rows"] == 40
    assert sin_etiqueta[0]["n_labeled"] == 0


def test_la_linea_base_sigue_exigiendo_la_etiqueta(client: TestClient):
    pid = _proyecto(client, "u6-16-base")
    base = _subir(client, pid, _csv(60, False), kind="combined", role="baseline")
    resp = _mapear(client, base)
    assert resp.status_code == 422
    assert "etiquetas" in resp.json()["detail"]
    assert "línea base" in resp.json()["detail"]


def test_un_feedback_sin_etiqueta_sigue_dando_422(client: TestClient):
    pid = _con_linea_base(client, "u6-16-feedback")
    fichero = b"id,otra\n1,2\n2,3\n"
    feedback = _subir(client, pid, fichero, kind="feedback", role="production")
    resp = client.put(
        f"/api/datasets/{feedback['id']}/mapping",
        json={"mapping": {"id_col": "id"}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422
    assert "etiquetas" in resp.json()["detail"]
