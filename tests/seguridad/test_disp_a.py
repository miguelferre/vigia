"""Disponibilidad, parte A: cola de trabajos, CSV exportado, suscripciones SSE y artefacto del modelo.

Cada test comprueba el control seguro de una huella (ver `HUELLAS`) contra el código actual.
"""

from __future__ import annotations

import csv
import io
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api.conftest import actor_headers
from tests.api.test_explain import _preparar_proyecto_sim_logistic
from tests.api.test_model_artifacts import (
    _entrenar_pipeline,
    _onnx_bytes,
    _preparar_proyecto_con_baseline,
    _subir_artefacto,
)
from vigia.app.main import create_app
from vigia.app.models import ModelVersion
from vigia.app.services import evaluate as evaluate_service
from vigia.app.services import human_layer
from vigia.app.settings import Settings

HUELLAS = {
    "test_cross_evaluate_no_apila_trabajos": "cross-evaluate-unbounded-rapida-queue",
    "test_evaluate_lote_no_apila_trabajos": "cross-evaluate-unbounded-rapida-queue",
    "test_export_csv_neutraliza_celdas_de_formula": "csv-formula-injection:usage-log-export",
    "test_stream_job_inexistente_no_deja_suscripcion": "job-stream-subscription-leak-bus",
    "test_stream_job_terminado_no_deja_suscripcion": "job-stream-subscription-leak-bus",
    "test_artefacto_fallido_no_destruye_el_vigente": "model-artifact-overwrite-before-validation",
}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=d, host="127.0.0.1", port_start=8970, open_browser=False,
        jobs_inline=True, sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8970
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


@pytest.fixture
def session(client: TestClient) -> Iterator[Session]:
    with Session(client.app.state.engine) as s:
        yield s


@pytest.fixture
def liberador(client: TestClient) -> Iterator[threading.Event]:
    """Evento que libera los trabajos bloqueados al cerrar (antes de parar el cliente)."""
    evento = threading.Event()
    yield evento
    evento.set()


def _modo_real(client: TestClient) -> None:
    """Pasa la cola a modo real (hilos worker) una vez preparados los datos en línea."""
    jobs = client.app.state.jobs
    jobs.settings.jobs_inline = False
    jobs._start_workers()


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post(
        "/api/projects", json={"name": name, "domain": "reuma"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_cross_evaluate_no_apila_trabajos(client: TestClient, monkeypatch, liberador):
    """Control: la API no encola sin tope trabajos de cruzadas iguales del mismo proyecto."""
    proyecto = _crear_proyecto(client, "disp-cross")

    def _bloqueo(ctx, session, **kwargs):
        liberador.wait(30)
        return {}

    monkeypatch.setattr(human_layer, "run_cross_evaluation_job", _bloqueo)
    _modo_real(client)
    url = f"/api/projects/{proyecto['id']}/cross/evaluate"
    primera = client.post(url, headers=actor_headers("miguel"))
    assert primera.status_code == 200, primera.text  # control positivo
    respuestas = [client.post(url, headers=actor_headers("miguel")) for _ in range(5)]
    for r in respuestas:
        assert r.status_code in (200, 409, 429), r.text
    ids = {primera.json()["id"]} | {r.json()["id"] for r in respuestas if r.status_code == 200}
    assert len(ids) <= 2, f"{len(ids)} trabajos distintos de cruzadas encolados para un proyecto"


def test_evaluate_lote_no_apila_trabajos(client: TestClient, monkeypatch, liberador):
    """Control: evaluar el mismo lote varias veces no apila trabajos iguales sin tope (variante)."""
    _, _, _, batch_id = _preparar_proyecto_sim_logistic(client, "disp-eval")

    def _bloqueo(*args, **kwargs):
        liberador.wait(30)
        return {}

    monkeypatch.setattr(evaluate_service, "evaluate_batch", _bloqueo)
    _modo_real(client)
    url = f"/api/batches/{batch_id}/evaluate"
    primera = client.post(url, json={"trigger": "manual"}, headers=actor_headers("miguel"))
    assert primera.status_code == 200, primera.text
    respuestas = [
        client.post(url, json={"trigger": "manual"}, headers=actor_headers("miguel"))
        for _ in range(5)
    ]
    for r in respuestas:
        assert r.status_code in (200, 409, 429), r.text
    ids = {primera.json()["id"]} | {r.json()["id"] for r in respuestas if r.status_code == 200}
    assert len(ids) <= 2, f"{len(ids)} evaluaciones iguales encoladas para un lote"


def test_export_csv_neutraliza_celdas_de_formula(client: TestClient):
    """Control: el CSV exportado no trae celdas de texto que empiecen por = + - @."""
    proyecto = _crear_proyecto(client, "disp-csv")
    contenido = (
        "date,human_decision,model_output,ground_truth,clinician_pseudonym,subgroup\n"
        "2026-01-05,refer,refer,refer,=1+1,@SUM(1+1)\n"
        "2026-01-06,no-refer,refer,refer,+1+1,-1+1\n"
    )
    resp = client.post(
        f"/api/projects/{proyecto['id']}/usage-logs/upload",
        files={"file": ("uso.csv", contenido.encode(), "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text  # control positivo: la subida legítima funciona
    resp = client.get(f"/api/projects/{proyecto['id']}/usage-logs/export.csv")
    assert resp.status_code == 200, resp.text
    filas = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(filas) == 2
    celdas = [f[c] for f in filas for c in ("clinician_pseudonym", "subgroup")]
    assert all(celdas), celdas  # los valores siguen presentes (no se descartan)
    peligrosas = [c for c in celdas if c[0] in "=+-@\t\r"]
    assert peligrosas == [], f"celdas sin neutralizar: {peligrosas}"


def test_stream_job_inexistente_no_deja_suscripcion(client: TestClient):
    """Control: pedir el flujo de un trabajo inexistente no deja suscripciones vivas en el bus."""
    bus = client.app.state.bus
    base = bus.n_subscribers
    for _ in range(5):
        r = client.get("/api/jobs/999999/stream")
        assert r.status_code == 404, r.text  # el handler se ejerce y rechaza
    assert bus.n_subscribers == base


def test_stream_job_terminado_no_deja_suscripcion(client: TestClient):
    """Control: el flujo de un trabajo ya terminado no deja suscripciones vivas en el bus."""
    proyecto = _crear_proyecto(client, "disp-stream")
    job = client.post(
        f"/api/projects/{proyecto['id']}/cross/evaluate", headers=actor_headers("miguel")
    ).json()
    assert job["status"] == "terminado", job  # control positivo
    bus = client.app.state.bus
    base = bus.n_subscribers
    for _ in range(5):
        r = client.get(f"/api/jobs/{job['id']}/stream")
        assert r.status_code == 200, r.text
        assert "event: job" in r.text
    assert bus.n_subscribers == base


def test_artefacto_fallido_no_destruye_el_vigente(client: TestClient, session: Session):
    """Control: una subida inválida con el mismo nombre no borra el artefacto ya activo."""
    _, version_id, _ = _preparar_proyecto_con_baseline(client, "disp-artefacto")
    resp = _subir_artefacto(
        client, version_id, contenido=_onnx_bytes(_entrenar_pipeline()), filename="modelo.onnx"
    )
    assert resp.status_code == 200, resp.text  # control positivo
    version = session.get(ModelVersion, version_id)
    ruta = Path(version.artifact_path)
    sha = version.artifact_sha256
    assert ruta.exists()

    malo = _subir_artefacto(client, version_id, contenido=b"no es un modelo", filename="modelo.onnx")
    assert malo.status_code == 422, malo.text  # la validación rechaza
    session.expire_all()
    version = session.get(ModelVersion, version_id)
    assert version.model_kind == "executable"
    assert version.artifact_sha256 == sha
    assert ruta.exists(), "el fichero del artefacto vigente ya no está en disco"
    assert Path(version.artifact_path).exists()
