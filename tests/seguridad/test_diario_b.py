"""Area diario (b): estado de monitores y alertas, config numerica y umbrales de los monitores.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.test_alerts import (
    _alertas,
    _crear_proyecto,
    _evaluar,
    _ingerir,
    _subir_y_mapear,
)
from vigia.app.main import create_app
from vigia.app.models import Evaluation, Monitor
from vigia.app.settings import Settings


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        data_dir=data_dir,
        host="127.0.0.1",
        port_start=8976,
        open_browser=False,
        jobs_inline=True,
        sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8976
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


def _preparar(client: TestClient) -> tuple[dict, int, int]:
    """Proyecto con linea base ingerida y lote de evento (con sesgo) evaluado."""
    proyecto = _crear_proyecto(client, name="diario-b")
    base = _subir_y_mapear(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    id_base = _ingerir(client, base["id"])["batch_id"]
    evento = _subir_y_mapear(client, proyecto["id"], "02_evento_feedback.json", role="production")
    id_evento = _ingerir(client, evento["id"])["batch_id"]
    _evaluar(client, id_evento)
    return proyecto, id_base, id_evento


def _monitor(client: TestClient, project_id: int, tipo: str) -> dict:
    items = client.get(f"/api/projects/{project_id}/monitors").json()["items"]
    return next(m for m in items if m["type"] == tipo)


def _patch(client: TestClient, monitor_id: int, *, config=None, thresholds=None, crudo=None):
    if crudo is not None:
        return client.patch(
            f"/api/monitors/{monitor_id}",
            content=crudo,
            headers={"Content-Type": "application/json"},
        )
    cuerpo: dict = {"actor": "t", "motivo": "t"}
    if config is not None:
        cuerpo["config"] = config
    if thresholds is not None:
        cuerpo["thresholds"] = thresholds
    return client.patch(f"/api/monitors/{monitor_id}", json=cuerpo)


def test_reevaluar_lote_antiguo_no_cambia_alerta_ni_estado(client: TestClient):
    """Reevaluar un lote anterior no cambia el estado vivo de la alerta de equidad."""
    proyecto, id_base, _ = _preparar(client)
    pid = proyecto["id"]
    antes = [a for a in _alertas(client, pid, status="abierta") if a["monitor_type"] == "fairness"]
    assert antes, "control positivo: el lote con sesgo abre alertas de equidad"
    ids = {a["id"] for a in antes}
    resp = client.post(f"/api/batches/{id_base}/evaluate", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.json()
    despues = {a["id"]: a for a in _alertas(client, pid) if a["id"] in ids}
    assert set(despues) == ids
    assert {a["status"] for a in despues.values()} == {"abierta"}, {
        i: a["status"] for i, a in despues.items()
    }


def test_reevaluar_lote_antiguo_no_baja_el_estado_del_monitor(client: TestClient):
    """Reevaluar un lote anterior no deja el monitor de equidad en un estado mejor."""
    proyecto, id_base, _ = _preparar(client)
    pid = proyecto["id"]

    def _estado() -> str:
        estado = client.get(f"/api/projects/{pid}/state").json()
        return next(m for m in estado["monitors"] if m["type"] == "fairness")["worst_state"]

    assert _estado() == "alerta", "control positivo: el lote con sesgo deja el monitor en alerta"
    resp = client.post(f"/api/batches/{id_base}/evaluate", json={})
    assert resp.status_code == 200 and resp.json()["status"] == "terminado", resp.text
    assert _estado() == "alerta"


RANGOS_FUERA = [
    pytest.param("drift", {"psi_bins": -3}, id="psi_bins-3"),
    pytest.param("drift", {"psi_bins": 0}, id="psi_bins0"),
    pytest.param("drift", {"confidence_bins": 1}, id="confidence_bins1"),
    pytest.param("drift", {"psi_bins": 10**9}, id="psi_bins-enorme"),
    pytest.param("fairness", {"window_step": 0}, id="window_step0"),
    pytest.param("fairness", {"window_step": -1}, id="window_step-1"),
    pytest.param("fairness", {"interval_windows_max": 10**9}, id="windows_max-enorme"),
    pytest.param("fairness", {"min_group": 0}, id="min_group0"),
    pytest.param("fairness", {"min_positives": -1}, id="min_positives-1"),
    pytest.param("cross", {"z_alert": 0}, id="z_alert0"),
    pytest.param("cross", {"z_alert": -2.5}, id="z_alert-neg"),
]


@pytest.mark.parametrize(("tipo", "config"), RANGOS_FUERA)
def test_config_numerica_fuera_de_rango_se_rechaza(client: TestClient, tipo: str, config: dict):
    """Un valor fuera de rango recibe 422 y no se guarda."""
    proyecto = _crear_proyecto(client, name="diario-rangos")
    monitor = _monitor(client, proyecto["id"], tipo)
    valido = {k: type(v)(10) if isinstance(v, int) else 3.0 for k, v in config.items()}
    resp = _patch(client, monitor["id"], config=valido)
    assert resp.status_code == 200, f"control positivo: {resp.text}"
    resp = _patch(client, monitor["id"], config=config)
    assert resp.status_code == 422, resp.text
    guardado = client.get(f"/api/monitors/{monitor['id']}").json()["config"]
    assert all(guardado.get(k) == valido[k] for k in config), guardado


@pytest.mark.parametrize(
    ("campo", "literal"),
    [("z_alert", "NaN"), ("z_alert", "Infinity")],
    ids=["z_alert-nan", "z_alert-inf"],
)
def test_config_no_finita_se_rechaza_y_no_se_guarda(client: TestClient, campo: str, literal: str):
    """NaN e infinito no se aceptan como valor de configuracion."""
    proyecto = _crear_proyecto(client, name="diario-nan")
    monitor = _monitor(client, proyecto["id"], "cross")
    resp = _patch(client, monitor["id"], config={campo: 3.0})
    assert resp.status_code == 200, f"control positivo: {resp.text}"
    crudo = f'{{"actor":"t","motivo":"t","config":{{"{campo}":{literal}}}}}'
    resp = _patch(client, monitor["id"], crudo=crudo)
    assert resp.status_code in (400, 422), resp.text
    guardado = client.get(f"/api/monitors/{monitor['id']}").json()["config"]
    assert guardado[campo] == 3.0, guardado


def test_drift_mal_configurado_no_impide_evaluar_equidad(client: TestClient, session: Session):
    """Un fallo de un monitor no deja sin evaluar a los demas."""
    proyecto, _, id_evento = _preparar(client)
    drift = session.exec(
        select(Monitor).where(Monitor.project_id == proyecto["id"], Monitor.type == "drift")
    ).one()
    drift.config_json = {**(drift.config_json or {}), "psi_bins": -3}
    session.add(drift)
    session.commit()
    fairness = _monitor(client, proyecto["id"], "fairness")["id"]

    def _cuenta() -> int:
        session.expire_all()
        filtro = (Evaluation.monitor_id == fairness, Evaluation.batch_id == id_evento)
        return len(session.exec(select(Evaluation).where(*filtro)).all())

    previas = _cuenta()
    assert previas >= 1, "control positivo: la evaluacion previa del lote existe"
    resp = client.post(f"/api/batches/{id_evento}/evaluate", json={})
    assert resp.status_code == 200, resp.text
    assert _cuenta() > previas, "la equidad debe evaluarse aunque deriva este mal configurada"


def _umbral(valor: str) -> str:
    return (
        '{"actor":"t","motivo":"t","thresholds":{"thresholds":'
        f'[{{"metric_key":"accuracy","kind":"lower_limit","value":{valor}}}]}}}}'
    )


@pytest.mark.parametrize("valor", ["1e999", "NaN", "-Infinity"], ids=["inf-1e999", "nan", "menos-inf"])
def test_umbral_no_finito_se_rechaza_y_no_se_guarda(client: TestClient, valor: str):
    """Un umbral no finito recibe 4xx y el monitor conserva el anterior."""
    proyecto = _crear_proyecto(client, name="diario-umbral")
    monitor = _monitor(client, proyecto["id"], "quality")
    resp = _patch(client, monitor["id"], crudo=_umbral("0.7"))
    assert resp.status_code == 200, f"control positivo: {resp.text}"
    antes = client.get(f"/api/monitors/{monitor['id']}").json()["thresholds"]
    resp = _patch(client, monitor["id"], crudo=_umbral(valor))
    assert resp.status_code in (400, 422), resp.text
    despues = client.get(f"/api/monitors/{monitor['id']}").json()["thresholds"]
    assert despues == antes


@pytest.mark.parametrize("valor", ["1e999", "NaN"], ids=["inf-1e999", "nan"])
def test_tras_umbral_no_finito_las_lecturas_siguen_validas(client: TestClient, valor: str):
    """Tras intentar un umbral no finito, evaluar, proponer y exportar siguen bien."""
    proyecto, _, id_evento = _preparar(client)
    pid = proyecto["id"]
    monitor = _monitor(client, pid, "quality")
    _patch(client, monitor["id"], crudo=_umbral(valor))
    resp = client.post(f"/api/batches/{id_evento}/evaluate", json={})
    assert resp.status_code == 200 and resp.json()["status"] == "terminado", resp.text
    resp = client.get(f"/api/projects/{pid}/thresholds/proposal")
    assert resp.status_code == 200, resp.text
    resp = client.get("/api/events/export", params={"format": "json"})
    assert resp.status_code == 200, resp.text

    def _rechaza(constante: str):
        raise ValueError(constante)

    json.loads(resp.text, parse_constant=_rechaza)
