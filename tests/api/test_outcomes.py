"""Outcomes: ingesta por CSV con upsert, tabla y serie sin baseline/target."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import Alert, Outcome

CSV_5_FILAS = (
    "period,metric_key,value,source\n"
    "2026-01,tasa_derivacion_correcta,0.81,manual\n"
    "2026-01,tiempo_medio_dias,3.2,manual\n"
    "2026-02,tasa_derivacion_correcta,0.79,manual\n"
    "2026-02,tiempo_medio_dias,3.4,manual\n"
    "2026-03,tasa_derivacion_correcta,0.83,manual\n"
)


def _crear_proyecto(client: TestClient, name: str = "reuma-outcomes") -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "reuma"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir_csv(client: TestClient, project_id: int, contenido: str):
    return client.post(
        f"/api/projects/{project_id}/outcomes",
        files={"file": ("outcomes.csv", io.BytesIO(contenido.encode()), "text/csv")},
        headers=actor_headers("miguel"),
    )


def test_csv_valido_de_cinco_filas_crea_cinco_outcomes(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client)
    resp = _subir_csv(client, proyecto["id"], CSV_5_FILAS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["n_rows"] == 5
    assert body["n_creados"] == 5
    assert body["n_actualizados"] == 0
    assert body["dataset_id"] is None

    filas = session.exec(
        select(Outcome).where(Outcome.project_id == proyecto["id"])
    ).all()
    assert len(filas) == 5
    assert all(f.baseline is None and f.target is None for f in filas)


def test_reingesta_con_un_valor_cambiado_actualiza_las_cinco_filas(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="reuma-outcomes-reingesta")
    _subir_csv(client, proyecto["id"], CSV_5_FILAS)

    csv_modificado = CSV_5_FILAS.replace("0.83", "0.90")
    resp = _subir_csv(client, proyecto["id"], csv_modificado)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["n_creados"] == 0
    assert body["n_actualizados"] == 5

    resp = client.get(f"/api/projects/{proyecto['id']}/outcomes")
    assert resp.status_code == 200, resp.text
    filas = resp.json()["rows"]
    fila_cambiada = next(f for f in filas if f["period"] == "2026-03")
    assert fila_cambiada["value"] == 0.90


def test_fichero_con_fila_repetida_devuelve_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="reuma-outcomes-repetida")
    csv_repetido = (
        "period,metric_key,value,source\n"
        "2026-01,tasa_derivacion_correcta,0.81,manual\n"
        "2026-01,tasa_derivacion_correcta,0.85,manual\n"
    )
    resp = _subir_csv(client, proyecto["id"], csv_repetido)
    assert resp.status_code == 422, resp.text
    assert "fila repetida" in resp.text


def test_csv_sin_columna_value_devuelve_422_con_el_nombre(client: TestClient):
    proyecto = _crear_proyecto(client, name="reuma-outcomes-sin-value")
    csv_sin_value = "period,metric_key,source\n2026-01,tasa_derivacion_correcta,manual\n"
    resp = _subir_csv(client, proyecto["id"], csv_sin_value)
    assert resp.status_code == 422, resp.text
    assert "value" in resp.text


def test_outcomes_sin_filas_devuelve_listas_vacias(client: TestClient):
    proyecto = _crear_proyecto(client, name="reuma-outcomes-vacio")
    resp = client.get(f"/api/projects/{proyecto['id']}/outcomes")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"rows": [], "series": {}}


def test_ingesta_de_outcomes_no_crea_alertas(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, name="reuma-outcomes-sin-alertas")
    antes = len(session.exec(select(Alert)).all())
    resp = _subir_csv(client, proyecto["id"], CSV_5_FILAS)
    assert resp.status_code == 200, resp.text
    despues = len(session.exec(select(Alert)).all())
    assert despues == antes


def test_valor_con_coma_decimal_se_acepta(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, name="reuma-outcomes-coma")
    csv = 'period,metric_key,value,source\n2026-01,tasa_derivacion_correcta,"0,8",manual\n'
    resp = _subir_csv(client, proyecto["id"], csv)
    assert resp.status_code == 200, resp.text
    fila = session.exec(select(Outcome).where(Outcome.project_id == proyecto["id"])).one()
    assert fila.value == 0.8
