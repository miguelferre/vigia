"""Estado de las alertas.

Cada test comprueba el control seguro de un apunte; ver `HUELLAS`.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api import conftest as _api
from tests.api.test_alerts import (
    _alertas,
    _ingerir,
    _preparar_con_evento,
    _subir_y_mapear,
)
from vigia.app.models import Alert
from vigia.app.services import alerting

# Fixtures de tests/api/conftest.py: app, client, data_dir y settings.
app, client, data_dir, settings = _api.app, _api.client, _api.data_dir, _api.settings

HUELLAS = {
    "test_lote_de_version_no_activa_no_mueve_las_alertas": (
        "alerting/alert-state-keyed-by-project-not-model-version"
    ),
    "test_lote_de_la_version_activa_si_mueve_las_alertas": (
        "alerting/alert-state-keyed-by-project-not-model-version"
    ),
    "test_alerta_cerrada_rechaza_accion_con_409": "closed-alert-actions",
    "test_alerta_cerrada_rechaza_protocolo_con_409": "closed-alert-actions",
    "test_accion_en_lote_salta_la_alerta_cerrada": "closed-alert-actions",
    "test_triaje_con_copia_vieja_no_duplica_el_hito": "duplicate-milestone-stale-copy",
    "test_investigacion_con_copia_vieja_no_duplica_el_hito": "duplicate-milestone-stale-copy",
    "test_decision_con_copia_vieja_no_duplica_el_hito": "duplicate-milestone-stale-copy",
}

_ACTOR = {"actor": "clara", "motivo": "reviso la alerta"}


def _primera_abierta(client: TestClient, project_id: int) -> int:
    return _alertas(client, project_id, status="abierta")[0]["id"]


def _cerrar(client: TestClient, alert_id: int) -> None:
    resp = client.post(f"/api/alerts/{alert_id}/close", json={**_ACTOR, "motivo": "resuelta"})
    assert resp.status_code == 200, resp.text


def _hitos(client: TestClient, alert_id: int, hito: str) -> int:
    historial = client.get(f"/api/alerts/{alert_id}").json()["history"]
    return sum(1 for h in historial if h.get("hito") == hito)


# --- Alertas por proyecto y versión del modelo -------------------------------


def _con_v2_activa(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    pid = proyecto["id"]
    v1 = client.get(f"/api/projects/{pid}").json()["active_version_id"]
    resp = client.post(
        f"/api/projects/{pid}/versions",
        json={"label": "v2", "model_kind": "external_files", "actor": "clara", "motivo": "prueba"},
    )
    assert resp.status_code in (200, 201), resp.text
    v2 = resp.json()["id"]
    resp = client.post(f"/api/model-versions/{v2}/activate", json=_ACTOR)
    assert resp.status_code == 200, resp.text
    return pid, v1, v2


def _lote_limpio(client: TestClient, pid: int, version_id: int) -> dict:
    ds = _subir_y_mapear(client, pid, "01_baseline_feedback.json", role="production")
    return _ingerir(client, ds["id"], model_version_id=version_id, evaluate=True)


def test_lote_de_version_no_activa_no_mueve_las_alertas(client: TestClient):
    """El lote de una version que no es la activa se evalua y se guarda, pero no
    cambia el estado de las alertas del proyecto."""
    pid, v1, _ = _con_v2_activa(client)
    antes = {a["id"]: (a["status"], a["observation_count"]) for a in _alertas(client, pid)}
    assert antes
    resultado = _lote_limpio(client, pid, v1)
    assert resultado.get("batch_id")
    despues = {a["id"]: (a["status"], a["observation_count"]) for a in _alertas(client, pid)}
    assert despues == antes


def test_lote_de_la_version_activa_si_mueve_las_alertas(client: TestClient):
    """Control positivo: el mismo lote limpio en la version activa sigue pasando
    las alertas vivas a observacion."""
    pid, _, v2 = _con_v2_activa(client)
    antes = {a["id"]: a["status"] for a in _alertas(client, pid)}
    _lote_limpio(client, pid, v2)
    despues = {a["id"]: a["status"] for a in _alertas(client, pid)}
    assert despues != antes
    assert "en_observacion" in despues.values()


# --- Alerta cerrada ----------------------------------------------------------


def test_alerta_cerrada_rechaza_accion_con_409(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _primera_abierta(client, proyecto["id"])
    _cerrar(client, alert_id)
    resp = client.post(
        f"/api/alerts/{alert_id}/actions", json={**_ACTOR, "action": "escalar"}
    )
    assert resp.status_code == 409, resp.text
    assert client.get(f"/api/alerts/{alert_id}").json()["actions"] == []


def test_alerta_cerrada_rechaza_protocolo_con_409(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _primera_abierta(client, proyecto["id"])
    _cerrar(client, alert_id)
    resp = client.put(
        f"/api/alerts/{alert_id}/protocol", json={**_ACTOR, "protocolo_md": "# nuevo"}
    )
    assert resp.status_code == 409, resp.text


def test_accion_en_lote_salta_la_alerta_cerrada(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _primera_abierta(client, proyecto["id"])
    _cerrar(client, alert_id)
    resp = client.post(
        f"/api/projects/{proyecto['id']}/alerts/bulk",
        json={**_ACTOR, "alert_ids": [alert_id], "action": "escalar"},
    )
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["applied"] == 0
    assert [s["alert_id"] for s in cuerpo["skipped"]] == [alert_id]


# --- Hito duplicado con una copia vieja --------------------------------------


def _copia_vieja(client: TestClient, alert_id: int) -> tuple[Session, Alert]:
    """Una sesion que cargo la alerta antes de que otra peticion la cambiara."""
    sesion = Session(client.app.state.engine)
    return sesion, sesion.get(Alert, alert_id)


def test_triaje_con_copia_vieja_no_duplica_el_hito(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _primera_abierta(client, proyecto["id"])
    sesion, vieja = _copia_vieja(client, alert_id)
    with sesion:
        resp = client.post(f"/api/alerts/{alert_id}/acknowledge", json=_ACTOR)
        assert resp.status_code == 200, resp.text
        with pytest.raises(HTTPException) as exc:
            alerting.acknowledge(sesion, vieja, actor="ana", motivo="a la vez")
        assert exc.value.status_code == 409
    assert _hitos(client, alert_id, "triaje") == 1


def test_investigacion_con_copia_vieja_no_duplica_el_hito(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _primera_abierta(client, proyecto["id"])
    client.post(f"/api/alerts/{alert_id}/acknowledge", json=_ACTOR)
    sesion, vieja = _copia_vieja(client, alert_id)
    with sesion:
        resp = client.post(
            f"/api/alerts/{alert_id}/investigate", json={**_ACTOR, "hallazgos": "uno"}
        )
        assert resp.status_code == 200, resp.text
        with pytest.raises(HTTPException) as exc:
            alerting.investigate(sesion, vieja, actor="ana", motivo="a la vez", hallazgos="dos")
        assert exc.value.status_code == 409
    assert _hitos(client, alert_id, "investigacion") == 1


def test_decision_con_copia_vieja_no_duplica_el_hito(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _primera_abierta(client, proyecto["id"])
    client.post(f"/api/alerts/{alert_id}/acknowledge", json=_ACTOR)
    client.post(f"/api/alerts/{alert_id}/investigate", json={**_ACTOR, "hallazgos": "uno"})
    sesion, vieja = _copia_vieja(client, alert_id)
    with sesion:
        resp = client.post(
            f"/api/alerts/{alert_id}/decide", json={**_ACTOR, "acciones": [{"key": "escalar"}]}
        )
        assert resp.status_code == 200, resp.text
        with pytest.raises(HTTPException) as exc:
            alerting.decide(
                sesion, vieja, actor="ana", motivo="a la vez", acciones=[{"key": "escalar"}]
            )
        assert exc.value.status_code == 409
    assert _hitos(client, alert_id, "decision") == 1
    assert len(client.get(f"/api/alerts/{alert_id}").json()["actions"]) == 1
