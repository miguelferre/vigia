"""La columna de fecha no es una variable del modelo.

Un CSV con `fecha` semanal (un valor por fichero) sale de las variables en la
sugerencia, en el mapeo guardado y en la plantilla del proyecto, y la
plantilla guarda y propaga `timestamp_col` a las subidas siguientes.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api.conftest import actor_headers
from vigia.app.models import Batch, Dataset, Project

CSV_SEMANAL = (
    b"id,fecha,prediction,label,importe,canal\n"
    b"1,2026-01-05,0,0,10.5,app\n"
    b"2,2026-01-05,1,1,22.0,online\n"
    b"3,2026-01-05,0,1,8.0,presencial\n"
)


def _crear_proyecto(client: TestClient, name: str, **extra) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "libre", **extra},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir(client: TestClient, project_id: int, content: bytes, filename: str = "lote.csv") -> int:
    resp = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": (filename, content, "text/csv")},
        data={"kind": "combined", "role": "production"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["dataset"]["id"]


def _sugerido(client: TestClient, dataset_id: int) -> dict:
    resp = client.get(f"/api/datasets/{dataset_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()["suggested_mapping"]


def test_sugerencia_da_la_fecha_semanal_como_timestamp_y_no_como_variable(client: TestClient):
    proyecto = _crear_proyecto(client, "fecha-sugerencia")
    sugerido = _sugerido(client, _subir(client, proyecto["id"], CSV_SEMANAL))
    assert sugerido["timestamp_col"] == "fecha"
    assert "fecha" not in sugerido["feature_cols"]


def test_plantilla_con_fecha_entre_las_variables_no_la_sugiere_como_variable(
    client: TestClient, session: Session
):
    """Plantilla de antes del arreglo (sin `timestamp_col`, `fecha` en
    `feature_cols`): el cruce con la sugerencia la saca de las variables."""
    proyecto = _crear_proyecto(client, "fecha-plantilla-antigua")
    fila = session.get(Project, proyecto["id"])
    fila.mapping_template_json = {"feature_cols": ["fecha", "importe", "canal"], "id_col": "id"}
    session.add(fila)
    session.commit()

    sugerido = _sugerido(client, _subir(client, proyecto["id"], CSV_SEMANAL))
    assert sugerido["timestamp_col"] == "fecha"
    assert sugerido["feature_cols"] == ["importe", "canal"]


def test_plantilla_guarda_timestamp_col_y_las_subidas_lo_heredan(client: TestClient):
    proyecto = _crear_proyecto(
        client,
        "fecha-plantilla",
        mapping_template={
            "timestamp_col": "fecha",
            "feature_cols": ["importe", "canal"],
            "id_col": "id",
        },
    )
    assert proyecto["mapping_template_json"]["timestamp_col"] == "fecha"
    assert proyecto["mapping_template_json"]["feature_cols"] == ["importe", "canal"]

    sugerido = _sugerido(client, _subir(client, proyecto["id"], CSV_SEMANAL))
    assert sugerido["timestamp_col"] == "fecha"
    assert sugerido["feature_cols"] == ["importe", "canal"]

    # Un lote que llama distinto a la columna no hereda una que no existe.
    sin_fecha = CSV_SEMANAL.replace(b"fecha", b"semana")
    sugerido = _sugerido(client, _subir(client, proyecto["id"], sin_fecha, "otro.csv"))
    assert sugerido["timestamp_col"] is None
    assert sugerido["feature_cols"] == ["importe", "canal"]


def test_plantilla_con_fecha_entre_las_variables_da_422_legible(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={
            "name": "fecha-doble",
            "domain": "libre",
            "mapping_template": {"timestamp_col": "fecha", "feature_cols": ["fecha", "importe"]},
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422, resp.text
    assert "columna de fecha" in resp.text
    assert "feature_cols" in resp.text


def test_mapeo_con_la_fecha_entre_las_variables_la_guarda_fuera_de_ellas(client: TestClient):
    proyecto = _crear_proyecto(client, "fecha-mapeo")
    dataset_id = _subir(client, proyecto["id"], CSV_SEMANAL)
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={
            "mapping": {
                "prediction_col": "prediction",
                "label_col": "label",
                "id_col": "id",
                "timestamp_col": "fecha",
                "feature_cols": ["fecha", "importe", "canal"],
                "favorable_label": 1,
            }
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    guardado = resp.json()["mapping"]
    assert guardado["timestamp_col"] == "fecha"
    assert guardado["feature_cols"] == ["importe", "canal"]


def test_linea_base_sin_plantilla_propaga_la_fecha_a_la_plantilla(
    client: TestClient, session: Session
):
    """«Crear sin plantilla»: al congelar la línea base, `timestamp_col` pasa
    a la plantilla para que el lote siguiente lo herede."""
    proyecto = _crear_proyecto(client, "fecha-sincronia")
    project_id, v1_id = proyecto["id"], proyecto["active_version_id"]
    dataset = Dataset(
        project_id=project_id,
        name="linea-base.csv",
        mapping_json={
            "favorable_label": 1,
            "timestamp_col": "fecha",
            "feature_cols": ["importe", "canal"],
        },
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    batch = Batch(
        project_id=project_id, model_version_id=v1_id, seq=0, n_rows=5, dataset_id=dataset.id
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)

    resp = client.post(
        f"/api/model-versions/{v1_id}/baseline",
        json={"batch_id": batch.id, "actor": "miguel", "motivo": "línea base"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    plantilla = client.get(f"/api/projects/{project_id}").json()["mapping_template_json"]
    assert plantilla["timestamp_col"] == "fecha"
