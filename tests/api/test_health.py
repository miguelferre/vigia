"""Tests de /api/health, catch-all del SPA, 404 de /api/* y /api/shutdown."""

from __future__ import annotations

import vigia.app.main as main_module
from vigia import __version__
from vigia.app.errores import TEXTO_404_RUTA


def test_health_devuelve_200_y_campos(app, client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body.get("python")
    assert body["data_dir"] == str(app.state.settings.data_dir)
    assert body["port"] == 8765


def test_catch_all_sin_index_sirve_html_no_store(client, monkeypatch, tmp_path):
    faltante = tmp_path / "no-existe" / "index.html"
    monkeypatch.setattr(main_module, "INDEX_FILE", faltante)
    resp = client.get("/alguna/ruta/spa")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert resp.headers["cache-control"] == "no-store"
    assert "frontend no compilado" in resp.text.lower()
    assert "/api/health" in resp.text


def test_catch_all_con_index_sirve_index_no_store(client, monkeypatch, tmp_path):
    index = tmp_path / "index.html"
    index.write_text("<html><body>spa</body></html>", encoding="utf-8")
    monkeypatch.setattr(main_module, "INDEX_FILE", index)
    resp = client.get("/alguna/ruta/spa")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    assert "spa" in resp.text


def test_api_inexistente_devuelve_404_json(client):
    resp = client.get("/api/inexistente")
    assert resp.status_code == 404
    assert resp.json() == {"detail": TEXTO_404_RUTA}  # Un solo texto para el 404 de ruta


def test_shutdown_sin_token_403(client):
    resp = client.post("/api/shutdown")
    assert resp.status_code == 403

    resp2 = client.post("/api/shutdown", headers={"X-Vigia-Token": "incorrecto"})
    assert resp2.status_code == 403


def test_shutdown_con_token_200(client):
    resp = client.post("/api/shutdown", headers={"X-Vigia-Token": "test-token"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "shutting_down"
