"""Area nav (parte b): peticiones multipart de otro origen y puerta del pickle.

Huellas:
- vigia.api.csrf-multipart-no-origin-check
- model-artifact-pickle-confirmation-client-asserted

Control esperado: una peticion de otro origen (Origin ajeno, Sec-Fetch-Site
cross-site) que cambia estado se rechaza sin tocar datos ni abrir el pickle;
la misma peticion sin esas cabeceras funciona. La confirmacion del pickle no
la puede fijar solo el llamador de un carril no humano.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import joblib
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.test_model_artifacts import (
    PICKLE_FEATURE_COLS,
    _csv_baseline_pickle,
    _entrenar_pipeline_pickle,
    _preparar_proyecto_con_baseline,
)
from vigia.app.main import create_app
from vigia.app.services import model_registry
from vigia.app.settings import Settings

HUELLAS = {
    "test_outcomes_de_otro_origen_se_rechazan_csrf_multipart": "vigia.api.csrf-multipart-no-origin-check",
    "test_dataset_de_otro_origen_se_rechaza_csrf_multipart": "vigia.api.csrf-multipart-no-origin-check",
    "test_json_con_text_plain_sigue_rechazado_csrf_multipart": "vigia.api.csrf-multipart-no-origin-check",
    "test_pickle_de_otro_origen_no_se_abre_csrf_multipart": "vigia.api.csrf-multipart-no-origin-check",
    "test_pickle_misma_origen_llega_a_la_carga_control_positivo": "vigia.api.csrf-multipart-no-origin-check",
    "test_pickle_con_host_ajeno_no_se_abre_pickle_client_asserted": "model-artifact-pickle-confirmation-client-asserted",
    "test_pickle_confirmado_solo_por_un_agente_no_se_abre_pickle_client_asserted": "model-artifact-pickle-confirmation-client-asserted",
}

BASE = "http://127.0.0.1:8961"
CROSS = {"Origin": "https://atacante.example", "Sec-Fetch-Site": "cross-site"}
RECHAZOS = {400, 403, 421}
CSV_OUTCOMES = "period,metric_key,value,source\n2026-01,tasa_derivacion_correcta,0.81,manual\n"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=d,
        host="127.0.0.1",
        port_start=8961,
        open_browser=False,
        jobs_inline=True,
        sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8961
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url=BASE) as c:
        yield c


def _proyecto(client: TestClient, nombre: str) -> int:
    resp = client.post("/api/projects", json={"name": nombre, "domain": "libre"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _outcomes(client: TestClient, pid: int):
    resp = client.get(f"/api/projects/{pid}/outcomes")
    assert resp.status_code == 200, resp.text
    return resp.json()["rows"]


def _artefactos_en_disco(settings: Settings) -> list[Path]:
    raiz = Path(settings.data_dir) / "artifacts"
    return [p for p in raiz.rglob("*") if p.is_file()] if raiz.is_dir() else []


def _pickle_listo(client: TestClient, nombre: str) -> tuple[int, bytes]:
    _, version_id, _ = _preparar_proyecto_con_baseline(
        client, nombre, csv_bytes=_csv_baseline_pickle(), feature_cols=PICKLE_FEATURE_COLS
    )
    buf = io.BytesIO()
    joblib.dump(_entrenar_pipeline_pickle(), buf)
    return version_id, buf.getvalue()


def _subir_pickle(client: TestClient, version_id: int, contenido: bytes, headers: dict):
    return client.post(
        f"/api/model-versions/{version_id}/artifact",
        files={"file": ("m.joblib", contenido, "application/octet-stream")},
        data={"artifact_kind": "pickle", "confirmacion_pickle": "true"},
        headers=headers,
    )


def test_outcomes_de_otro_origen_se_rechazan_csrf_multipart(client: TestClient):
    """Un multipart con Origin ajeno a /outcomes se rechaza y no escribe filas."""
    pid = _proyecto(client, "nav-outcomes")
    fichero = {"file": ("o.csv", CSV_OUTCOMES.encode(), "text/csv")}
    resp = client.post(f"/api/projects/{pid}/outcomes", files=fichero, headers=CROSS)
    assert resp.status_code in RECHAZOS, (resp.status_code, resp.text[:200])
    assert _outcomes(client, pid) == []

    ok = client.post(f"/api/projects/{pid}/outcomes", files=fichero)
    assert ok.status_code == 200, ok.text
    assert len(_outcomes(client, pid)) == 1


def test_dataset_de_otro_origen_se_rechaza_csrf_multipart(client: TestClient):
    """Un multipart con Origin ajeno a /datasets/upload se rechaza."""
    pid = _proyecto(client, "nav-dataset")
    campos = {"kind": "combined", "role": "baseline"}
    csv = _csv_baseline_pickle()
    resp = client.post(
        f"/api/projects/{pid}/datasets/upload",
        files={"file": ("b.csv", csv, "text/csv")},
        data=campos,
        headers=CROSS,
    )
    assert resp.status_code in RECHAZOS, (resp.status_code, resp.text[:200])

    ok = client.post(
        f"/api/projects/{pid}/datasets/upload",
        files={"file": ("b.csv", csv, "text/csv")},
        data=campos,
    )
    assert ok.status_code == 200, ok.text


def test_json_con_text_plain_sigue_rechazado_csrf_multipart(client: TestClient):
    """Control negativo: PATCH /api/settings con text/plain da 422 (no es JSON valido)."""
    resp = client.patch(
        "/api/settings",
        content='{"actor": "x", "motivo": "y", "values": {}}',
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status_code in {415, 422}, (resp.status_code, resp.text[:200])


def test_pickle_de_otro_origen_no_se_abre_csrf_multipart(client: TestClient, settings: Settings):
    """Un pickle subido con Origin ajeno se rechaza antes de abrirlo y sin dejar fichero."""
    version_id, contenido = _pickle_listo(client, "nav-pickle-cross")
    with mock.patch.object(model_registry.joblib, "load") as m_load:
        resp = _subir_pickle(client, version_id, contenido, CROSS)
        assert resp.status_code in RECHAZOS, (resp.status_code, resp.text[:200])
        m_load.assert_not_called()
    assert _artefactos_en_disco(settings) == []


def test_pickle_misma_origen_llega_a_la_carga_control_positivo(client: TestClient):
    """Control positivo: sin cabeceras de otro origen la peticion llega a la carga."""
    version_id, contenido = _pickle_listo(client, "nav-pickle-mismo")
    with mock.patch.object(model_registry.joblib, "load") as m_load:
        resp = _subir_pickle(client, version_id, contenido, {})
        assert resp.status_code not in {404, 405}, resp.status_code
        m_load.assert_called_once()


def test_pickle_con_host_ajeno_no_se_abre_pickle_client_asserted(client: TestClient):
    """Con Host y Origin ajenos (mismo origen aparente) el pickle no se abre."""
    version_id, contenido = _pickle_listo(client, "nav-pickle-host")
    ajeno = {"Host": "rebind.example:8961", "Origin": "http://rebind.example:8961"}
    with mock.patch.object(model_registry.joblib, "load") as m_load:
        resp = _subir_pickle(client, version_id, contenido, ajeno)
        assert resp.status_code in RECHAZOS, (resp.status_code, resp.text[:200])
        m_load.assert_not_called()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Límite conocido (decisión de diseño): con el MCP, un agente "
        "puede cargar un pickle si fija la confirmación; SEGURIDAD.md lo declara"
    ),
)
def test_pickle_confirmado_solo_por_un_agente_no_se_abre_pickle_client_asserted(
    client: TestClient,
):
    """Un agente con token valido que fija el booleano por su cuenta no abre el pickle."""
    version_id, contenido = _pickle_listo(client, "nav-pickle-agente")
    token = client.get("/api/settings", params={"reveal": "true"}).json()["mcp_token"]
    cab = {"X-Vigia-Actor": "agente-prueba", "X-Vigia-Actor-Kind": "agente", "X-Vigia-Token": token}
    with mock.patch.object(model_registry.joblib, "load") as m_load:
        resp = _subir_pickle(client, version_id, contenido, cab)
        assert resp.status_code not in {401, 404, 405}, (resp.status_code, resp.text[:200])
        assert resp.status_code in {400, 403, 409, 422}, (resp.status_code, resp.text[:200])
        m_load.assert_not_called()
