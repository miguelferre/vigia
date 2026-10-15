"""Disponibilidad, parte D: parámetros de la demo, explicación SHAP y propuesta de umbrales.

Cada test comprueba el control seguro de una huella (ver `HUELLAS`) contra el código actual.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from tests.api.test_explain import _preparar_proyecto_sim_logistic
from vigia.app.main import create_app
from vigia.app.models import Record
from vigia.app.settings import Settings

HUELLAS = {
    "test_lab_rechaza_n_total_enorme": "demo.generator-cardinality-params-unbounded",
    "test_lab_rechaza_frac_young_fuera_de_rango": "demo.generator-cardinality-params-unbounded",
    "test_demo_rechaza_n_clinicians_enorme": "demo.generator-cardinality-params-unbounded",
    "test_shap_global_acota_las_filas_explicadas": "explain.global-shap-all-rows-unbounded",
    "test_propuesta_umbrales_acota_tamano_lote": "monitors/thresholds-proposal-tamano_lote-unbounded-sync-get",
}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=d, host="127.0.0.1", port_start=8973, open_browser=False,
        jobs_inline=True, sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8973
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


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post(
        "/api/projects", json={"name": name, "domain": "reuma"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _crear_run(client: TestClient, **extra) -> dict:
    resp = client.post(
        "/api/demo/runs",
        json={"scenario_key": "timeline_completo", "source": "generate", **extra},
        headers=actor_headers("miguel"),
    )
    return resp


def _lab(client: TestClient, run_id: int, params: dict):
    return client.post(
        f"/api/demo/runs/{run_id}/lab",
        json={"phase_key": "e1_evento", "params": params, "actor": "miguel", "motivo": "prueba", "seed": 1},
    )


def _rechazado_sin_generar(resp, settings: Settings) -> bool:
    """True si la petición se rechazó (4xx o trabajo en error) y no escribió ficheros de laboratorio."""
    ficheros = [p for p in (settings.data_dir / "demo").rglob("*") if p.is_file()] if (
        settings.data_dir / "demo"
    ).exists() else []
    rechazo = 400 <= resp.status_code < 500 or (
        resp.status_code == 200 and resp.json().get("status") == "error"
    )
    return rechazo and not ficheros


def test_lab_rechaza_n_total_enorme(client: TestClient, settings: Settings):
    """Control: el laboratorio rechaza un n_total muy superior a cualquier cota razonable."""
    run = _crear_run(client)
    assert run.status_code == 200, run.text
    ok = _lab(client, run.json()["id"], {"n_total": 450})
    assert ok.status_code == 200 and ok.json()["status"] == "terminado", ok.text  # control positivo
    for f in (settings.data_dir / "demo").rglob("*"):
        if f.is_file():
            f.unlink()
    resp = _lab(client, run.json()["id"], {"n_total": 30_000})
    assert _rechazado_sin_generar(resp, settings), f"n_total=30000 aceptado ({resp.status_code})"


def test_lab_rechaza_frac_young_fuera_de_rango(client: TestClient, settings: Settings):
    """Control: el laboratorio rechaza una fracción fuera de [0, 1] que multiplica las filas."""
    run = _crear_run(client)
    assert run.status_code == 200, run.text
    resp = _lab(client, run.json()["id"], {"n_total": 100, "frac_young": 100.0})
    assert _rechazado_sin_generar(resp, settings), f"frac_young=100 aceptado ({resp.status_code})"


def test_demo_rechaza_n_clinicians_enorme(client: TestClient):
    """Control: la demo rechaza un n_clinicians muy superior a cualquier cota razonable."""

    def _avanzar(n: int):
        run = _crear_run(client, source="canned", with_human=True, params={"human": {"n_clinicians": n}})
        if run.status_code != 200:
            return run
        return client.post(f"/api/demo/runs/{run.json()['id']}/next", headers=actor_headers("miguel"))

    ok = _avanzar(8)
    assert ok.status_code == 200 and ok.json()["status"] == "terminado", ok.text  # control positivo
    resp = _avanzar(50_000)
    assert resp.status_code != 404, resp.text
    rechazo = 400 <= resp.status_code < 500 or (
        resp.status_code == 200 and resp.json()["status"] == "error"
    )
    assert rechazo, "n_clinicians=50000 aceptado"


def test_shap_global_acota_las_filas_explicadas(client: TestClient, session: Session, monkeypatch):
    """Control: SHAP global no explica sin tope todas las filas de un lote grande."""
    import shap

    _, version_id, baseline_id, _ = _preparar_proyecto_sim_logistic(client, "disp-shap")
    originales = list(session.exec(select(Record).where(Record.batch_id == baseline_id)).all())
    assert originales
    seq = max(r.seq for r in originales)
    while len(originales) < 1200:
        for r in list(originales)[: 1200 - len(originales)]:
            seq += 1
            session.add(
                Record(
                    batch_id=r.batch_id, project_id=r.project_id, seq=seq, prediction=r.prediction,
                    prob_favorable=r.prob_favorable, label=r.label, group_code=r.group_code,
                    features_json=r.features_json,
                )
            )
            originales.append(r)
    session.commit()
    vistas: list[int] = []

    def _espia(self, X, *args, **kwargs):
        vistas.append(len(X))
        raise RuntimeError("espía: no se calcula")

    monkeypatch.setattr(shap.KernelExplainer, "shap_values", _espia)
    resp = client.post(
        f"/api/model-versions/{version_id}/explain/global", json={"kind": "shap"}
    )
    assert resp.status_code == 200, resp.text  # muestra fija de 1000 filas, no rechazo
    assert vistas, "la petición no llegó al cálculo de SHAP"
    assert vistas[0] <= 1000, f"SHAP explica {vistas[0]} filas sin submuestrear"


def test_propuesta_umbrales_acota_tamano_lote(client: TestClient):
    """Control: la propuesta de umbrales rechaza (422) un tamano_lote desmesurado."""
    pid = _crear_proyecto(client, "disp-umbrales")["id"]
    url = f"/api/projects/{pid}/thresholds/proposal"
    normal = client.get(url, params={"tamano_lote": 1000})
    assert normal.status_code in (200, 409), normal.text  # control positivo: no es 422
    enorme = client.get(url, params={"tamano_lote": 10**9})
    assert enorme.status_code == 422, f"tamano_lote=10**9 aceptado ({enorme.status_code})"
