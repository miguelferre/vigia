"""La exportación del diario respeta los filtros de la pantalla."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post("/api/projects", json={"name": name, "domain": "libre"}, headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _exportar(client: TestClient, **params) -> list[dict]:
    resp = client.get("/api/events/export", params={"format": "json", **params})
    assert resp.status_code == 200, resp.text
    return json.loads(resp.text)


def test_la_exportacion_filtra_por_carril_y_por_tipo_de_objeto(client: TestClient):
    _crear_proyecto(client, "p-export-carril")
    todos = _exportar(client)
    assert {e["actor_kind"] for e in todos} >= {"humano"}

    solo_humano = _exportar(client, actor_kind="humano")
    assert solo_humano, "el alta deja eventos del carril humano"
    assert {e["actor_kind"] for e in solo_humano} == {"humano"}

    sin_agente = _exportar(client, actor_kind="agente")
    assert all(e["actor_kind"] == "agente" for e in sin_agente)
    assert len(solo_humano) < len(todos) or len(sin_agente) == 0

    un_tipo = _exportar(client, object_type="project")
    assert un_tipo and {e["object_type"] for e in un_tipo} == {"project"}


def test_la_exportacion_filtra_por_correlacion(client: TestClient):
    _crear_proyecto(client, "p-export-correlacion")
    todos = _exportar(client)
    elegida = next(e["correlation_id"] for e in todos if e["correlation_id"])
    acotados = _exportar(client, correlation_id=elegida)
    assert acotados and {e["correlation_id"] for e in acotados} == {elegida}
    assert len(acotados) <= len(todos)
    assert _exportar(client, correlation_id="no-existe-esta-correlacion") == []


def test_el_registro_de_la_exportacion_cuenta_con_los_mismos_filtros(client: TestClient):
    proyecto = _crear_proyecto(client, "p-export-registro")
    esperados = _exportar(client, project_id=proyecto["id"], actor_kind="humano")
    resp = client.post(
        "/api/events/exportaciones",
        json={"format": "json", "project_id": proyecto["id"]},
        params={"actor_kind": "humano"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    despues = resp.json()["after"]
    assert despues["n_eventos"] == len(esperados)
    assert despues["filtros"] == {"carril": "humano"}


def test_sin_filtros_el_registro_de_la_exportacion_no_cambia_de_forma(client: TestClient):
    resp = client.post(
        "/api/events/exportaciones", json={"format": "html"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    assert "filtros" not in resp.json()["after"]
