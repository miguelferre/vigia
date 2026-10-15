"""Exclusión en cascada en el servicio `human_layer`.

- Una alerta CX-1 viva (abierta, reconocida o en observacion) de la version
  activa suprime CX-6 en su grupo en la evaluacion siguiente.
- Una alerta de fairness en observacion cuenta para la exclusion en cascada
  aunque la ultima evaluacion de fairness ya este en `ok`.
"""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import Alert, Evaluation, Measurement, ModelVersion, Monitor, Project
from vigia.app.services import alerting
from vigia.app.services.human_layer import (
    ESTADOS_ALERTA_VIVOS,
    _cx1_alert_groups,
    _model_alert_groups,
)

CABECERA = "date,human_decision,model_output,ground_truth,clinician_pseudonym,subgroup"


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post(
        "/api/projects", json={"name": name, "domain": "libre"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _diario(n_por_grupo: int, override: dict[str, float], semilla: int) -> bytes:
    """Dos subgrupos (`a`, `b`), verdad independiente del modelo (misma FNR: sin CX-1)."""
    rng = random.Random(semilla)
    filas = [CABECERA]
    for i in range(2 * n_por_grupo):
        grupo = "a" if i % 2 else "b"
        modelo = rng.random() < 0.5
        humano = (not modelo) if rng.random() < override[grupo] else modelo
        verdad = rng.random() < 0.5
        dia = 1 + i % 28
        filas.append(
            f"2026-01-{dia:02d},{'refer' if humano else 'no-refer'},"
            f"{'refer' if modelo else 'no-refer'},{'refer' if verdad else 'no-refer'},"
            f"clin-{i % 5},{grupo}"
        )
    return ("\n".join(filas) + "\n").encode()


def _subir(client: TestClient, project_id: int, contenido: bytes) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/usage-logs/upload",
        files={"file": ("registro.csv", contenido, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text


def _evaluar(client: TestClient, project_id: int) -> dict:
    resp = client.post(f"/api/projects/{project_id}/cross/evaluate", headers=actor_headers())
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.text
    return resp.json()


def _alertas_cx6(session: Session, project_id: int) -> list[Alert]:
    session.expire_all()
    return list(
        session.exec(
            select(Alert).where(Alert.project_id == project_id, Alert.metric_key == "CX-6")
        ).all()
    )


def _monitor(session: Session, project_id: int, tipo: str) -> Monitor:
    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == tipo)
    ).first()
    assert monitor is not None
    return monitor


def _evaluacion(
    session: Session, proyecto: dict, tipo: str, *, version_id: int, worst: str
) -> Evaluation:
    ev = Evaluation(
        monitor_id=_monitor(session, proyecto["id"], tipo).id,
        project_id=proyecto["id"],
        model_version_id=version_id,
        worst_state=worst,
        status="ok",
    )
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return ev


def _alerta(
    session: Session, proyecto: dict, *, tipo: str, clave: str, grupo: str | None,
    status: str, evaluacion_id: int,
) -> Alert:
    fila = Alert(
        project_id=proyecto["id"],
        monitor_type=tipo,
        metric_key=clave,
        group_code=grupo,
        severity="alta",
        status=status,
        title="sembrada",
        last_evaluation_id=evaluacion_id,
    )
    session.add(fila)
    session.commit()
    session.refresh(fila)
    return fila


def _medida_cx1(session: Session, proyecto: dict, *, evaluacion_id: int, grupo: str) -> None:
    """CX-1 disparada en `grupo` en esa evaluación: lo que exige `_cx1_alert_groups`
    para contar la alerta en la versión de la evaluación."""
    session.add(
        Measurement(
            evaluation_id=evaluacion_id,
            project_id=proyecto["id"],
            monitor_type="cross",
            metric_key=f"cx1_override_z:{grupo}",
            value=-5.0,
            state="alerta",
            group_code=grupo,
        )
    )
    session.commit()


def _preparar_hasta_cx6(client: TestClient, session: Session, nombre: str) -> tuple[dict, Evaluation]:
    """Calibra la version y sube un diario donde `b` (el de menos override) es el ancla de CX-6."""
    proyecto = _crear_proyecto(client, nombre)
    _subir(client, proyecto["id"], _diario(200, {"a": 0.1, "b": 0.1}, semilla=1))
    _evaluar(client, proyecto["id"])
    session.expire_all()
    calibracion = session.exec(
        select(Evaluation)
        .where(Evaluation.project_id == proyecto["id"])
        .order_by(Evaluation.id.desc())  # type: ignore[union-attr]
    ).first()
    assert calibracion is not None
    _subir(client, proyecto["id"], _diario(300, {"a": 0.5, "b": 0.1}, semilla=2))
    return proyecto, calibracion


def test_control_sin_cx1_cx6_se_abre_en_el_ancla(client: TestClient, session: Session):
    proyecto, _ = _preparar_hasta_cx6(client, session, "cx6-control")
    _evaluar(client, proyecto["id"])
    alertas = _alertas_cx6(session, proyecto["id"])
    assert [a.group_code for a in alertas] == ["b"]


@pytest.mark.parametrize("estado", ESTADOS_ALERTA_VIVOS)
def test_d_alerta_cx1_viva_suprime_cx6_en_la_siguiente_evaluacion(
    client: TestClient, session: Session, estado: str
):
    proyecto, calibracion = _preparar_hasta_cx6(client, session, f"cx6-cx1-{estado}")
    _alerta(
        session, proyecto, tipo="cross", clave="CX-1", grupo="b", status=estado,
        evaluacion_id=calibracion.id,
    )
    _medida_cx1(session, proyecto, evaluacion_id=calibracion.id, grupo="b")
    assert _cx1_alert_groups(session, session.get(Project, proyecto["id"])) == {"b"}

    _evaluar(client, proyecto["id"])
    assert _alertas_cx6(session, proyecto["id"]) == []
    ultima = session.exec(
        select(Evaluation)
        .where(Evaluation.project_id == proyecto["id"])
        .order_by(Evaluation.id.desc())  # type: ignore[union-attr]
    ).first()
    medida = next(m for m in ultima.result_json["measurements"] if m["metric_key"] == "cx6_override_z:b")
    assert medida["state"] == "ok"
    assert medida["extra"]["cubierta_por"] == "CX-1"
    assert "CX-1" in medida["motivo"]


@pytest.mark.parametrize("estado", ["cerrada", "retirada"])
def test_alerta_cx1_cerrada_o_retirada_no_suprime(
    client: TestClient, session: Session, estado: str
):
    proyecto, calibracion = _preparar_hasta_cx6(client, session, f"cx6-cx1-{estado}")
    _alerta(
        session, proyecto, tipo="cross", clave="CX-1", grupo="b", status=estado,
        evaluacion_id=calibracion.id,
    )
    _medida_cx1(session, proyecto, evaluacion_id=calibracion.id, grupo="b")
    _evaluar(client, proyecto["id"])
    assert [a.group_code for a in _alertas_cx6(session, proyecto["id"])] == ["b"]


def test_f_alerta_cx1_de_una_version_anterior_no_cuenta(client: TestClient, session: Session):
    proyecto, _ = _preparar_hasta_cx6(client, session, "cx6-cx1-version-vieja")
    anterior = ModelVersion(project_id=proyecto["id"], label="v0-anterior")
    session.add(anterior)
    session.commit()
    session.refresh(anterior)
    assert anterior.id != proyecto["active_version_id"]
    ev_vieja = _evaluacion(session, proyecto, "cross", version_id=anterior.id, worst="alerta")
    _alerta(
        session, proyecto, tipo="cross", clave="CX-1", grupo="b", status="en_observacion",
        evaluacion_id=ev_vieja.id,
    )
    _medida_cx1(session, proyecto, evaluacion_id=ev_vieja.id, grupo="b")
    assert _cx1_alert_groups(session, session.get(Project, proyecto["id"])) == set()

    _evaluar(client, proyecto["id"])
    assert [a.group_code for a in _alertas_cx6(session, proyecto["id"])] == ["b"]


def test_e_alerta_de_fairness_en_observacion_excluye_los_grupos_aunque_el_ultimo_sea_ok(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, "fairness-en-observacion")
    version_id = proyecto["active_version_id"]
    # El modelo señaló con esta versión y la última evaluación ya volvió a ok.
    _evaluacion(session, proyecto, "fairness", version_id=version_id, worst="alerta")
    ev = _evaluacion(session, proyecto, "fairness", version_id=version_id, worst="ok")
    project = session.get(Project, proyecto["id"])

    # Sin alerta viva y con la ultima evaluacion en ok: nada excluido (como hoy).
    assert _model_alert_groups(session, project) == set()

    _alerta(
        session, proyecto, tipo="fairness", clave="disparate_impact", grupo=None,
        status="en_observacion", evaluacion_id=ev.id,
    )
    esperado = set(alerting.group_labels(alerting.last_batch_mapping(session, project)))
    assert esperado
    assert _model_alert_groups(session, project) == esperado


def test_e_el_camino_por_worst_state_se_conserva(client: TestClient, session: Session):
    """`inestable` puede no abrir fila en `Alert`: la union no lo pierde."""
    proyecto = _crear_proyecto(client, "fairness-inestable")
    _evaluacion(session, proyecto, "fairness", version_id=proyecto["active_version_id"], worst="inestable")
    project = session.get(Project, proyecto["id"])
    esperado = set(alerting.group_labels(alerting.last_batch_mapping(session, project)))
    assert esperado
    assert _model_alert_groups(session, project) == esperado


@pytest.mark.parametrize("caso", ["cerrada", "version_anterior", "otro_monitor"])
def test_e_alertas_que_no_cuentan_para_la_cascada(client: TestClient, session: Session, caso: str):
    proyecto = _crear_proyecto(client, f"fairness-no-cuenta-{caso}")
    project = session.get(Project, proyecto["id"])
    version_id = proyecto["active_version_id"]
    ev = _evaluacion(session, proyecto, "fairness", version_id=version_id, worst="ok")
    status, tipo, ev_id = "en_observacion", "fairness", ev.id
    if caso == "cerrada":
        status = "cerrada"
    elif caso == "version_anterior":
        anterior = ModelVersion(project_id=proyecto["id"], label="v0-anterior")
        session.add(anterior)
        session.commit()
        session.refresh(anterior)
        ev_id = _evaluacion(session, proyecto, "fairness", version_id=anterior.id, worst="alerta").id
        # El modelo solo señaló en la versión vieja; en la activa todo está en ok.
    else:
        tipo = "cross"
    _alerta(
        session, proyecto, tipo=tipo, clave="disparate_impact", grupo=None,
        status=status, evaluacion_id=ev_id,
    )
    assert _model_alert_groups(session, project) == set()


def test_cx6_abierta_pasa_a_observacion_cuando_aparece_una_cx1_viva_en_su_grupo(
    client: TestClient, session: Session
):
    """La supresión también alcanza a una CX-6 ya abierta: la medida pasa a `ok`
    con el motivo de CX-1 y la deja en observación, sin cerrarla."""
    proyecto, calibracion = _preparar_hasta_cx6(client, session, "cx6-abierta-luego-cx1")
    _evaluar(client, proyecto["id"])
    assert [a.status for a in _alertas_cx6(session, proyecto["id"])] == ["abierta"]

    _alerta(
        session, proyecto, tipo="cross", clave="CX-1", grupo="b", status="abierta",
        evaluacion_id=calibracion.id,
    )
    _medida_cx1(session, proyecto, evaluacion_id=calibracion.id, grupo="b")
    _evaluar(client, proyecto["id"])
    alertas = _alertas_cx6(session, proyecto["id"])
    assert [(a.group_code, a.status) for a in alertas] == [("b", "en_observacion")]


def test_cx1_viva_cuenta_aunque_last_evaluation_id_sea_de_otra_version(
    client: TestClient, session: Session
):
    """Una alerta ya en `en_observacion` no mueve `last_evaluation_id`: la versión se
    acota por la medida de CX-1 disparada en la versión activa, no por ese campo."""
    proyecto, calibracion = _preparar_hasta_cx6(client, session, "cx6-cx1-last-eval-viejo")
    anterior = ModelVersion(project_id=proyecto["id"], label="v0-anterior")
    session.add(anterior)
    session.commit()
    session.refresh(anterior)
    ev_vieja = _evaluacion(session, proyecto, "cross", version_id=anterior.id, worst="ok")
    _alerta(
        session, proyecto, tipo="cross", clave="CX-1", grupo="b", status="en_observacion",
        evaluacion_id=ev_vieja.id,
    )
    _medida_cx1(session, proyecto, evaluacion_id=calibracion.id, grupo="b")
    assert _cx1_alert_groups(session, session.get(Project, proyecto["id"])) == {"b"}
