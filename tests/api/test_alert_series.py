"""`GET /projects/{id}/alerts/series`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import Alert, Batch, Dataset, Evaluation, Monitor


def _reproducir_timeline_completo(client: TestClient) -> dict:
    resp = client.post(
        "/api/demo/runs",
        json={"scenario_key": "timeline_completo", "with_human": False},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    resp = client.post(f"/api/demo/runs/{run['id']}/play", headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.text
    return run


def _series(client: TestClient, project_id: int, **params) -> dict:
    resp = client.get(f"/api/projects/{project_id}/alerts/series", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_series_por_lote_reproduce_las_cifras_de_la_demo(client: TestClient):
    """Cifras esperadas: #6 y #7 con 2 de equidad, #8 y #9
    con 6 de calidad y deriva 3, 3, 1, 1 en #6 a #9. Si la demo real da otros
    números, se anotan tal cual (no se fuerza aquí)."""
    run = _reproducir_timeline_completo(client)
    project_id = run["project_id"]

    body = _series(client, project_id, granularity="batch")
    assert body["granularity"] == "batch"
    assert body["tz"] == "Europe/Paris"
    por_label = {item["label"]: item for item in body["items"]}
    assert set(por_label) == {f"#{i}" for i in range(9)}

    assert por_label["#5"]["by_monitor"]["fairness"] == 2
    assert por_label["#6"]["by_monitor"]["fairness"] == 2
    assert por_label["#7"]["by_monitor"]["quality"] == 6
    assert por_label["#8"]["by_monitor"]["quality"] == 6
    assert [por_label[f"#{i}"]["by_monitor"]["drift"] for i in (5, 6, 7, 8)] == [3, 3, 1, 1]

    for item in body["items"]:
        assert item["total"] == sum(item["by_severity"].values())
        assert item["total"] == sum(item["by_monitor"].values())
        assert item["by_monitor"]["cross"] == 0  # las cruzadas van a `cross_unbatched`


def test_series_n_checks_y_total_coherentes(client: TestClient):
    run = _reproducir_timeline_completo(client)
    project_id = run["project_id"]
    body = _series(client, project_id, granularity="batch")
    for item in body["items"]:
        assert item["n_checks"] >= 0
        assert item["n_batches"] == 1
        assert len(item["batches"]) == 1


def test_since_until_recortan_por_lote(client: TestClient):
    run = _reproducir_timeline_completo(client)
    project_id = run["project_id"]
    completa = _series(client, project_id, granularity="batch")
    assert len(completa["items"]) == 9

    # Un rango que solo cubre el futuro no deja ningún lote.
    futuro = (datetime.now(UTC) + timedelta(days=365)).date().isoformat()
    recortada = _series(client, project_id, granularity="batch", since=futuro)
    assert recortada["items"] == []
    assert recortada["since"] == futuro


def test_since_until_recortan_por_lote_en_el_limite_exacto(client: TestClient, session: Session):
    """El filtro ahora vive en el `HAVING`/`WHERE` de la consulta,
    no en Python; el límite sigue siendo inclusivo en los dos extremos, tal
    como hacía `en_rango` antes de moverse a SQL."""
    proyecto = _proyecto_dos_lotes_en_dias_distintos(session, client)
    project_id = proyecto["id"]

    # `until` = justo la marca del primer lote: lo incluye, el segundo (un día
    # después) queda fuera.
    recortada = _series(
        client, project_id, granularity="batch", until="2026-09-10T10:00:00+00:00", tz="UTC"
    )
    assert {item["label"] for item in recortada["items"]} == {"#0"}

    # `since` = justo la marca del segundo lote: lo incluye, el primero queda
    # fuera.
    recortada = _series(
        client, project_id, granularity="batch", since="2026-09-11T09:00:00+00:00", tz="UTC"
    )
    assert {item["label"] for item in recortada["items"]} == {"#1"}


def test_granularidad_desconocida_422(client: TestClient):
    run = _reproducir_timeline_completo(client)
    resp = client.get(
        f"/api/projects/{run['project_id']}/alerts/series", params={"granularity": "semana"}
    )
    assert resp.status_code == 422, resp.text
    assert "semana" in resp.json()["detail"]


def test_zona_horaria_desconocida_422(client: TestClient):
    run = _reproducir_timeline_completo(client)
    resp = client.get(
        f"/api/projects/{run['project_id']}/alerts/series", params={"tz": "Marte/Cráter"}
    )
    assert resp.status_code == 422, resp.text


def _proyecto_dos_lotes_en_dias_distintos(session: Session, client: TestClient) -> dict:
    """Proyecto con dos lotes, cada uno con una evaluación de equidad en alerta
    en un día distinto (marca la fecha manipulando `Evaluation.created_at`)."""
    resp = client.post(
        "/api/projects",
        json={"name": "serie-dos-dias", "domain": "libre"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    proyecto = resp.json()
    project_id = proyecto["id"]
    version_id = proyecto["active_version_id"]
    monitor_equidad = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == "fairness")
    ).first()

    dia_1 = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)
    dia_2 = datetime(2026, 9, 11, 9, 0, tzinfo=UTC)
    for i, marca in enumerate((dia_1, dia_2)):
        batch = Batch(project_id=project_id, model_version_id=version_id, seq=i, n_rows=10)
        session.add(batch)
        session.flush()
        evaluacion = Evaluation(
            monitor_id=monitor_equidad.id,
            project_id=project_id,
            model_version_id=version_id,
            batch_id=batch.id,
            trigger="manual",
            worst_state="alerta",
            created_at=marca.isoformat(timespec="microseconds"),
        )
        session.add(evaluacion)
        session.flush()
        session.add(
            Alert(
                project_id=project_id,
                monitor_type="fairness",
                metric_key="fairness_value",
                severity="alta",
                status="abierta",
                title=f"alerta lote {i}",
                opened_at=marca.isoformat(timespec="microseconds"),
                history_json=[
                    {
                        "ts": marca.isoformat(timespec="microseconds"),
                        "from": None,
                        "to": "abierta",
                        "evaluation_id": evaluacion.id,
                        "value": 1.5,
                        "actor": "vigia.core 0.1.0",
                        "motivo": None,
                    }
                ],
            )
        )
    session.commit()
    return proyecto


def test_series_por_dia_agrupa_dos_lotes_en_dos_tramos(client: TestClient, session: Session):
    proyecto = _proyecto_dos_lotes_en_dias_distintos(session, client)
    body = _series(client, proyecto["id"], granularity="day", tz="UTC")
    assert body["granularity"] == "day"
    assert {item["key"] for item in body["items"]} == {"2026-09-10", "2026-09-11"}
    for item in body["items"]:
        assert item["n_batches"] == 1
        assert item["by_monitor"]["fairness"] == 1
        assert item["by_severity"]["alta"] == 1
        assert item["total"] == 1
    assert body["cross_unbatched"] == {"alta": 0, "media": 0, "baja": 0}


def test_series_por_hora_agrupa_en_el_tramo_de_una_hora(client: TestClient, session: Session):
    proyecto = _proyecto_dos_lotes_en_dias_distintos(session, client)
    body = _series(client, proyecto["id"], granularity="hour", tz="UTC")
    assert body["granularity"] == "hour"
    assert {item["key"] for item in body["items"]} == {"2026-09-10T10", "2026-09-11T09"}


def test_series_trae_el_nombre_del_lote_en_cada_referencia(client: TestClient, session: Session):
    """`batches[].name` es el nombre del dataset de origen, con
    cualquier granularidad; `null` si el lote no tiene dataset."""
    proyecto = _proyecto_dos_lotes_en_dias_distintos(session, client)
    primero = session.exec(
        select(Batch).where(Batch.project_id == proyecto["id"]).order_by(Batch.seq)
    ).first()
    dataset = Dataset(project_id=proyecto["id"], name="lote-01.csv")
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    primero.dataset_id = dataset.id
    session.add(primero)
    session.commit()

    por_lote = _series(client, proyecto["id"], granularity="batch", tz="UTC")["items"]
    assert [item["batches"][0]["name"] for item in por_lote] == ["lote-01.csv", None]
    por_dia = _series(client, proyecto["id"], granularity="day", tz="UTC")["items"]
    assert [item["batches"][0]["name"] for item in por_dia] == ["lote-01.csv", None]
