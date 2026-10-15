"""Exportar el diario deja un evento `diario.exportado`."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.app.events_titulos import titulo_evento
from vigia.app.models import Event


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post("/api/projects", json={"name": name, "domain": "libre"}, headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_registrar_exportacion_deja_evento_con_formato_periodo_y_recuento(client: TestClient):
    _crear_proyecto(client, "p-exporta")
    n_antes = client.get("/api/events").json()["total"]

    resp = client.post(
        "/api/events/exportaciones",
        json={"format": "json", "since": "2020-01-01T00:00:00"},
        headers=actor_headers("ana", role="gestor"),
    )
    assert resp.status_code == 200, resp.text
    evento = resp.json()
    assert evento["action"] == "diario.exportado"
    assert evento["actor_id"] == "ana"
    assert evento["actor_kind"] == "humano"
    after = evento["after"]
    assert after["formato"] == "json"
    assert after["desde"] == "2020-01-01T00:00:00"
    assert after["n_eventos"] == n_antes

    # Queda en el diario, a la vista de la lista.
    assert client.get("/api/events", params={"object_type": "sistema"}).json()["items"][0]["action"] == (
        "diario.exportado"
    )


def test_registrar_exportacion_rechaza_formato_y_proyecto_inexistentes(client: TestClient):
    # El 422 de formato llega en español (manejador global), nunca un JSON de pydantic en crudo.
    r = client.post("/api/events/exportaciones", json={"format": "pdf"}, headers=actor_headers("ana"))
    assert r.status_code == 422
    r = client.post(
        "/api/events/exportaciones", json={"format": "html", "project_id": 999999}, headers=actor_headers("ana")
    )
    assert r.status_code == 404


def test_titulo_del_evento_de_exportacion(client: TestClient, session):
    resp = client.post("/api/events/exportaciones", json={"format": "html"}, headers=actor_headers("ana"))
    assert resp.status_code == 200
    evento = session.get(Event, resp.json()["id"])
    titulo = titulo_evento(evento)
    assert "HTML" in titulo and "completo" in titulo and "eventos" in titulo
