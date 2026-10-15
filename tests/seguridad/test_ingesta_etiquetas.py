"""Ingesta y mapeo: emparejamiento de etiquetas tardías.

Cada test comprueba el control seguro de una huella; ver `HUELLAS`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.app.main import create_app
from vigia.app.settings import Settings

HUELLAS = {
    "test_las_etiquetas_tardias_no_pisan_la_linea_base_congelada": "ingest/late-labels-overwrite-recorded-ground-truth-without-guard",
    "test_una_etiqueta_ya_registrada_no_se_sobrescribe": "ingest/late-labels-overwrite-recorded-ground-truth-without-guard",
    "test_la_linea_base_sin_etiquetas_las_recibe_del_fichero_tardio": "ingest/late-labels-overwrite-recorded-ground-truth-without-guard",
    "test_una_etiqueta_que_falta_si_se_rellena": "ingest/late-labels-overwrite-recorded-ground-truth-without-guard",
}

N = 30


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


def _cargar(client, pid, vid, contenido: str, *, kind: str, role: str, mapeo: dict) -> dict:
    r = client.post(
        f"/api/projects/{pid}/datasets/upload",
        files={"file": ("f.csv", contenido.encode(), "text/csv")},
        data={"kind": kind, "role": role},
        headers=actor_headers("miguel"),
    )
    assert r.status_code == 200, r.text
    ds = r.json()["dataset"]["id"]
    r = client.put(f"/api/datasets/{ds}/mapping", json={"mapping": mapeo},
                   headers=actor_headers("miguel"))
    assert r.status_code == 200, r.text
    r = client.post(f"/api/datasets/{ds}/ingest", json={"model_version_id": vid, "evaluate": False})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "terminado", r.json()
    return r.json()["result"]


def _proyecto(client: TestClient, nombre: str) -> tuple[int, int]:
    r = client.post("/api/projects", json={"name": nombre, "domain": "reuma"},
                    headers=actor_headers("miguel"))
    assert r.status_code == 200, r.text
    return r.json()["id"], r.json()["active_version_id"]


def _etiquetas(client: TestClient, lote: int) -> list:
    r = client.get(f"/api/batches/{lote}/records")
    assert r.status_code == 200, r.text
    return [x["label"] for x in sorted(r.json()["items"], key=lambda x: x["external_id"])]


def _feedback(client, pid, vid, prefijo: str, etiqueta: int) -> dict:
    filas = "\n".join(f"{prefijo}{i:02d},{etiqueta}" for i in range(N))
    return _cargar(client, pid, vid, "id,label\n" + filas + "\n", kind="feedback",
                   role="production", mapeo={"id_col": "id", "label_col": "label", "favorable_label": 1})


def _lote(client, pid, vid, prefijo: str, *, role: str, con_etiqueta: bool) -> int:
    filas = [f"{prefijo}{i:02d},{i % 2}" + (f",{i % 2}" if con_etiqueta else "") for i in range(N)]
    cabecera = "id,prediction" + (",label" if con_etiqueta else "")
    mapeo = {"prediction_col": "prediction", "id_col": "id", "favorable_label": 1}
    if con_etiqueta:
        mapeo["label_col"] = "label"
    res = _cargar(client, pid, vid, cabecera + "\n" + "\n".join(filas) + "\n",
                  kind="combined" if con_etiqueta else "payload", role=role, mapeo=mapeo)
    return res["batch_id"]


def test_las_etiquetas_tardias_no_pisan_la_linea_base_congelada(client: TestClient):
    """Un fichero de etiquetas no cambia las que ya tiene la línea base congelada: las
    omite y da su recuento."""
    pid, vid = _proyecto(client, "s1a-base")
    base = _lote(client, pid, vid, "B", role="baseline", con_etiqueta=True)
    antes = _etiquetas(client, base)
    res = _feedback(client, pid, vid, "B", 1)
    assert _etiquetas(client, base) == antes
    assert res["etiquetas_omitidas"] == N
    assert res["n_matched"] == 0
    assert any("línea base congelada" in a for a in res["avisos"]), res["avisos"]


def test_una_etiqueta_ya_registrada_no_se_sobrescribe(client: TestClient):
    """Una etiqueta ya registrada en un lote de producción no se sobrescribe."""
    pid, vid = _proyecto(client, "s1a-registrada")
    _lote(client, pid, vid, "B", role="baseline", con_etiqueta=True)
    lote = _lote(client, pid, vid, "P", role="production", con_etiqueta=False)
    primera = _feedback(client, pid, vid, "P", 1)
    assert primera["n_matched"] == N
    assert primera["etiquetas_omitidas"] == 0
    assert _etiquetas(client, lote) == [1.0] * N
    segunda = _feedback(client, pid, vid, "P", 0)
    assert segunda["etiquetas_omitidas"] == N
    assert not any("línea base congelada" in a for a in segunda["avisos"]), segunda["avisos"]
    assert any("ya tenían etiqueta" in a for a in segunda["avisos"]), segunda["avisos"]
    assert _etiquetas(client, lote) == [1.0] * N


def test_la_linea_base_sin_etiquetas_las_recibe_del_fichero_tardio(client: TestClient):
    """El camino del harness sigue: la línea base ingerida sin etiquetas (payload)
    recibe las suyas del fichero de etiquetas; solo una etiqueta ya puesta se protege."""
    pid, vid = _proyecto(client, "s1a-base-sin-etiquetas")
    base = _lote(client, pid, vid, "B", role="baseline", con_etiqueta=False)
    res = _feedback(client, pid, vid, "B", 1)
    assert res["n_matched"] == N
    assert res["etiquetas_omitidas"] == 0
    assert _etiquetas(client, base) == [1.0] * N
    assert _feedback(client, pid, vid, "B", 0)["etiquetas_omitidas"] == N
    assert _etiquetas(client, base) == [1.0] * N


def test_una_etiqueta_que_falta_si_se_rellena(client: TestClient):
    """El camino legítimo sigue: el lote sin etiquetas las recibe con el fichero tardío."""
    pid, vid = _proyecto(client, "s1a-falta")
    _lote(client, pid, vid, "B", role="baseline", con_etiqueta=True)
    lote = _lote(client, pid, vid, "P", role="production", con_etiqueta=False)
    assert all(e is None for e in _etiquetas(client, lote))
    res = _feedback(client, pid, vid, "P", 0)
    assert res["n_matched"] == N
    assert _etiquetas(client, lote) == [0.0] * N
