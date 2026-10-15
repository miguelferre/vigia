"""Alertas abiertas: un `aviso` cuyo valor cruza su umbral (lote
pequeño) no baja una alerta abierta a observación; un `aviso` normal sí."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import Alert, Evaluation, Monitor, Project
from vigia.app.services import alerting

METRICA = "disparate_impact"
UMBRAL = 0.8


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "reuma", "fairness_interval_method": "ventanas"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _preparar(client: TestClient, session: Session, name: str) -> tuple[Project, Monitor]:
    proyecto = _crear_proyecto(client, name)
    project = session.get(Project, proyecto["id"])
    assert project is not None
    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == project.id, Monitor.type == "fairness")
    ).first()
    assert monitor is not None
    return project, monitor


def _sync(session: Session, project: Project, monitor: Monitor, estado: str, valor: float):
    evaluacion = Evaluation(
        monitor_id=monitor.id,
        project_id=project.id,
        model_version_id=project.active_version_id,
        trigger="manual",
    )
    session.add(evaluacion)
    session.flush()
    afectadas = alerting.sync_candidates(
        session,
        project,
        monitor,
        evaluacion,
        [
            {
                "metric_key": METRICA,
                "group_code": None,
                "state": estado,
                "value": valor,
                "threshold_low": UMBRAL,
                "threshold_high": None,
                "motivo": "lote pequeño (150 filas, menos de 200): valor",
            }
        ],
    )
    session.commit()
    return afectadas


def _alerta(session: Session, project: Project) -> Alert | None:
    session.expire_all()
    return session.exec(
        select(Alert).where(Alert.project_id == project.id, Alert.metric_key == METRICA)
    ).first()


def test_aviso_que_cruza_el_umbral_no_baja_una_alerta_abierta(client: TestClient, session: Session):
    project, monitor = _preparar(client, session, "a2-aviso-cruza")
    _sync(session, project, monitor, "alerta", 0.5)
    alerta = _alerta(session, project)
    assert alerta is not None and alerta.status == "abierta"

    afectadas = _sync(session, project, monitor, "aviso", 0.7)

    alerta = _alerta(session, project)
    assert alerta is not None
    assert alerta.status == "abierta"
    assert alerta.observation_count == 0
    assert alerta.last_value == 0.7
    assert afectadas and afectadas[0].id == alerta.id
    ultima = alerta.history_json[-1]
    assert ultima["to"] == "abierta"
    assert not any(h["to"] == "en_observacion" for h in alerta.history_json)


def test_aviso_que_cruza_el_umbral_no_abre_una_alerta_nueva(client: TestClient, session: Session):
    project, monitor = _preparar(client, session, "a2-aviso-sin-alerta")
    afectadas = _sync(session, project, monitor, "aviso", 0.7)
    assert afectadas == []
    assert _alerta(session, project) is None


def test_aviso_normal_con_el_valor_dentro_de_los_umbrales_pasa_a_observacion(
    client: TestClient, session: Session
):
    project, monitor = _preparar(client, session, "a2-aviso-normal")
    _sync(session, project, monitor, "alerta", 0.5)

    _sync(session, project, monitor, "aviso", 0.82)

    alerta = _alerta(session, project)
    assert alerta is not None
    assert alerta.status == "en_observacion"
    assert alerta.observation_count == 1
    assert alerta.history_json[-1]["to"] == "en_observacion"
