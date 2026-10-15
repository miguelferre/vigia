"""Matriz de riesgos por proyecto."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.human.risk_levels import IMPACTO_LABELS, NIVELES, PROBABILIDAD_LABELS, nivel


def test_nivel_25_celdas() -> None:
    for (impacto, probabilidad), esperado in NIVELES.items():
        assert nivel(impacto, probabilidad) == esperado, (impacto, probabilidad)
    assert len(NIVELES) == 25


@pytest.mark.parametrize("fuera", [0, 6])
def test_nivel_fuera_de_rango(fuera: int) -> None:
    with pytest.raises(ValueError):
        nivel(fuera, 3)
    with pytest.raises(ValueError):
        nivel(3, fuera)


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post(
        "/api/projects", json={"name": name, "domain": "reuma"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _reproducir_demo(client: TestClient) -> dict:
    cab = actor_headers("miguel")
    creada = client.post(
        "/api/demo/runs", json={"scenario_key": "timeline_completo", "with_human": True}, headers=cab
    )
    assert creada.status_code == 200, creada.text
    run = creada.json()
    reproducida = client.post(f"/api/demo/runs/{run['id']}/play", headers=cab)
    assert reproducida.status_code == 200, reproducida.text
    return run


def _primera_alerta(client: TestClient, project_id: int) -> dict:
    alertas = client.get(f"/api/projects/{project_id}/alerts", params={"limit": 500}).json()["items"]
    assert alertas, "la demo no ha abierto ninguna alerta"
    return alertas[0]


def test_alta_desde_alerta_y_movimientos(client: TestClient) -> None:
    run = _reproducir_demo(client)
    project_id = run["project_id"]
    alerta = _primera_alerta(client, project_id)

    resp = client.post(
        f"/api/projects/{project_id}/risks",
        json={
            "origin_alert_id": alerta["id"],
            "title": "Falsos negativos por encima del umbral",
            **actor_headers_body(),
        },
        headers=actor_headers("miguel", role="auditor"),
    )
    assert resp.status_code == 200, resp.text
    riesgo = resp.json()
    assert riesgo["monitor_type"] == alerta["monitor_type"]
    assert riesgo["code"] == "R-001"
    assert riesgo["level"] == nivel(riesgo["impact_level"], riesgo["probability_level"])
    assert riesgo["impact_label"] == IMPACTO_LABELS[riesgo["impact_level"]]
    assert riesgo["probability_label"] == PROBABILIDAD_LABELS[riesgo["probability_level"]]

    eventos = client.get("/api/events", params={"limit": 500}).json()["items"]
    assert any(e["action"] == "riesgo.creado" for e in eventos)

    movimientos = client.get(f"/api/risks/{riesgo['id']}/movements").json()["items"]
    assert len(movimientos) == 1
    assert movimientos[0]["texto"].startswith("R-001 nuevo · Creado desde la alerta de")


def actor_headers_body() -> dict:
    return {"actor": "miguel", "role": "auditor", "motivo": "riesgo abierto tras revisión"}


def test_codigo_correlativo_por_proyecto(client: TestClient) -> None:
    run = _reproducir_demo(client)
    project_id = run["project_id"]
    otro = _crear_proyecto(client, "reuma-riesgos-2")

    for pid in (project_id, otro["id"]):
        resp = client.post(
            f"/api/projects/{pid}/risks",
            json={
                "impact_level": 3,
                "probability_level": 3,
                "title": "Riesgo manual",
                **actor_headers_body(),
            },
            headers=actor_headers("miguel"),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == "R-001"

    riesgo_1 = client.get(f"/api/projects/{project_id}/risks").json()["items"][-1]
    cierre = client.post(
        f"/api/risks/{riesgo_1['id']}/close", json=actor_headers_body(), headers=actor_headers("miguel")
    )
    assert cierre.status_code == 200, cierre.text

    segundo = client.post(
        f"/api/projects/{project_id}/risks",
        json={
            "impact_level": 2,
            "probability_level": 2,
            "title": "Otro riesgo manual",
            **actor_headers_body(),
        },
        headers=actor_headers("miguel"),
    )
    assert segundo.status_code == 200, segundo.text
    assert segundo.json()["code"] == "R-002"


def test_alta_manual_sin_niveles_422_y_alerta_inexistente_404(client: TestClient) -> None:
    proyecto = _crear_proyecto(client, "reuma-riesgos-3")
    resp = client.post(
        f"/api/projects/{proyecto['id']}/risks",
        json={"title": "Riesgo sin niveles", **actor_headers_body()},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422, resp.text

    resp2 = client.post(
        f"/api/projects/{proyecto['id']}/risks",
        json={"origin_alert_id": 999999, "title": "Riesgo alerta inexistente", **actor_headers_body()},
        headers=actor_headers("miguel"),
    )
    assert resp2.status_code == 404, resp2.text


def test_move_status_close(client: TestClient) -> None:
    proyecto = _crear_proyecto(client, "reuma-riesgos-4")
    riesgo = client.post(
        f"/api/projects/{proyecto['id']}/risks",
        json={
            "impact_level": 3,
            "probability_level": 3,
            "title": "Riesgo para mover",
            **actor_headers_body(),
        },
        headers=actor_headers("miguel"),
    ).json()
    risk_id = riesgo["id"]

    sin_motivo = client.patch(
        f"/api/risks/{risk_id}/move",
        json={"impact_level": 4, "probability_level": 4, "actor": "miguel"},
        headers=actor_headers("miguel"),
    )
    assert sin_motivo.status_code == 422, sin_motivo.text

    misma_celda = client.patch(
        f"/api/risks/{risk_id}/move",
        json={"impact_level": 3, "probability_level": 3, **actor_headers_body()},
        headers=actor_headers("miguel"),
    )
    assert misma_celda.status_code == 422, misma_celda.text

    subida = client.patch(
        f"/api/risks/{risk_id}/move",
        json={"impact_level": 4, "probability_level": 4, **actor_headers_body()},
        headers=actor_headers("miguel"),
    )
    assert subida.status_code == 200, subida.text
    assert subida.json()["level"] == nivel(4, 4)

    movimientos = client.get(
        f"/api/projects/{proyecto['id']}/risks/movements", params={"days": 7}
    ).json()["items"]
    texto_celda = next(m for m in movimientos if m["kind"] == "celda")
    assert "subió" in texto_celda["texto"] or "bajó" in texto_celda["texto"]

    a_seguimiento = client.patch(
        f"/api/risks/{risk_id}/status",
        json={"status": "en_seguimiento", **actor_headers_body()},
        headers=actor_headers("miguel"),
    )
    assert a_seguimiento.status_code == 200, a_seguimiento.text

    cierre = client.post(
        f"/api/risks/{risk_id}/close", json=actor_headers_body(), headers=actor_headers("miguel")
    )
    assert cierre.status_code == 200, cierre.text
    cierre_2 = client.post(
        f"/api/risks/{risk_id}/close", json=actor_headers_body(), headers=actor_headers("miguel")
    )
    assert cierre_2.status_code == 409, cierre_2.text

    move_cerrado = client.patch(
        f"/api/risks/{risk_id}/move",
        json={"impact_level": 5, "probability_level": 5, **actor_headers_body()},
        headers=actor_headers("miguel"),
    )
    assert move_cerrado.status_code == 409, move_cerrado.text

    status_otra_vez = client.patch(
        f"/api/risks/{risk_id}/status",
        json={"status": "en_seguimiento", **actor_headers_body()},
        headers=actor_headers("miguel"),
    )
    assert status_otra_vez.status_code == 409, status_otra_vez.text


def test_filtros_de_listado(client: TestClient) -> None:
    proyecto = _crear_proyecto(client, "reuma-riesgos-5")
    riesgo = client.post(
        f"/api/projects/{proyecto['id']}/risks",
        json={
            "impact_level": 5,
            "probability_level": 5,
            "title": "Riesgo crítico",
            **actor_headers_body(),
        },
        headers=actor_headers("miguel"),
    ).json()
    client.post(
        f"/api/risks/{riesgo['id']}/close", json=actor_headers_body(), headers=actor_headers("miguel")
    )

    cerrados = client.get(f"/api/projects/{proyecto['id']}/risks", params={"status": "cerrado"})
    assert cerrados.status_code == 200
    assert len(cerrados.json()["items"]) == 1

    por_impacto = client.get(f"/api/projects/{proyecto['id']}/risks", params={"impact": 5})
    assert por_impacto.status_code == 200
    assert len(por_impacto.json()["items"]) == 1

    fuera_de_rango = client.get(f"/api/projects/{proyecto['id']}/risks", params={"probability": 9})
    assert fuera_de_rango.status_code == 422

    estado_raro = client.get(f"/api/projects/{proyecto['id']}/risks", params={"status": "raro"})
    assert estado_raro.status_code == 422
