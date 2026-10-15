"""Correcciones del servicio: etiquetas tardías y `sin_datos` en binario y multiclase,
`nan` en el registro de uso de una regresión y motivo de la alerta."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api import _datos_multiclase as d
from vigia.app.models import Evaluation
from vigia.app.services.human_layer import _candidato_revision_cero, _parse_cifra
from vigia.core.schema import State, TaskSpec


def _filas_binario(n: int, semilla: int, prefijo: str, *, acierto: float = 0.9, etiqueta: bool = True):
    rng = np.random.default_rng(semilla)
    real = rng.integers(0, 2, size=n)
    acierta = rng.random(n) < acierto
    pred = np.where(acierta, real, 1 - real)
    return pd.DataFrame(
        {
            "id": [f"{prefijo}{i}" for i in range(n)],
            "prediction": pred,
            "label": real if etiqueta else [""] * n,
            "prob": np.clip(np.where(pred == 1, 0.75, 0.25) + rng.normal(0, 0.05, n), 0.01, 0.99).round(4),
            "edad": rng.integers(20, 80, size=n),
        }
    )


def _csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode()


def _proyecto_binario(client: TestClient, nombre: str) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": nombre, "domain": "libre", "store_features": True},
        headers=d.actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


_MAPEO_BINARIO = {
    "prediction_col": "prediction",
    "label_col": "label",
    "id_col": "id",
    "favorable_label": 1,
    "probability_col": "prob",
    "feature_cols": ["edad"],
}


def _ingerir(client, proyecto, df, *, rol, mapeo, evaluar, kind="combined"):
    sub = d.subir(client, proyecto["id"], _csv(df), rol=rol, kind=kind)
    resp = d.mapear(client, sub["dataset"]["id"], mapeo)
    assert resp.status_code == 200, resp.text
    trabajo = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"], evaluar=evaluar)
    assert trabajo["status"] == "terminado", trabajo
    return trabajo["result"]


def _evaluaciones(client, batch_id):
    with Session(client.app.state.engine) as s:
        return list(s.exec(select(Evaluation).where(Evaluation.batch_id == batch_id)).all())


def _alertas(client, proyecto_id):
    resp = client.get(f"/api/projects/{proyecto_id}/alerts", params={"limit": 200})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


# ---------------------------------------------------------------------------
# Etiquetas tardías en binario
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("evaluar", [True, False])
def test_binario_las_etiquetas_tardias_declaran_lotes(client: TestClient, evaluar: bool):
    proyecto = _proyecto_binario(client, f"back-260-bin-{evaluar}")
    _ingerir(client, proyecto, _filas_binario(200, 1, "base"), rol="baseline", mapeo=_MAPEO_BINARIO, evaluar=False)
    sin = _filas_binario(80, 2, "p", etiqueta=False)
    lote = _ingerir(client, proyecto, sin, rol="production", mapeo=_MAPEO_BINARIO, evaluar=True)["batch_id"]
    antes = len(_evaluaciones(client, lote))
    etiquetas = _filas_binario(80, 2, "p")[["id", "label"]]
    res = _ingerir(
        client, proyecto, etiquetas, rol="production", kind="feedback", evaluar=evaluar,
        mapeo={"id_col": "id", "label_col": "label"},
    )
    assert res["lotes_con_verdad"] == [lote]
    if evaluar:
        assert res["lotes_reevaluados"] == [lote] and res["lotes_a_reevaluar"] == [], res.get("evaluate_motivo")
        assert {e.trigger for e in _evaluaciones(client, lote)[antes:]} == {"feedback_tardio"}
    else:
        assert res["lotes_a_reevaluar"] == [lote] and res["lotes_reevaluados"] == []
        assert "evaluate_motivo" in res
        assert len(_evaluaciones(client, lote)) == antes


def test_multiclase_las_etiquetas_tardias_declaran_lotes(client: TestClient):
    proyecto, _s, _t = d.linea_base_multiclase(client, "back-260-multi", n=300)
    sin = pd.DataFrame(d.filas_multiclase(120, seed=5, prefijo_id="q", etiquetas=False))
    lote = _ingerir(client, proyecto, sin, rol="production", mapeo=d.mapeo_multiclase(), evaluar=True)["batch_id"]
    con = pd.DataFrame(d.filas_multiclase(120, seed=5, prefijo_id="q"))[["id", "label"]]
    res = _ingerir(
        client, proyecto, con, rol="production", kind="feedback", evaluar=False,
        mapeo={"id_col": "id", "label_col": "label"},
    )
    assert res["lotes_con_verdad"] == [lote]
    assert res["lotes_a_reevaluar"] == [lote]
    assert "evaluate_motivo" in res


# ---------------------------------------------------------------------------
# `sin_datos` en binario: `sin_datos` no es recuperación
# ---------------------------------------------------------------------------


def _evaluacion_y_monitor(client, proyecto_id):
    from vigia.app.models import Monitor, Project

    with Session(client.app.state.engine) as s:
        ev = s.exec(select(Evaluation).order_by(Evaluation.id.desc())).first()
        assert ev is not None
        mon = s.exec(select(Monitor).where(Monitor.id == ev.monitor_id)).one()
        return s, s.get(Project, proyecto_id), mon, ev


@pytest.mark.parametrize("tipo", ["binario", "multiclase"])
def test_sin_datos_no_pasa_la_alerta_a_observacion_en_binario_y_multiclase(client: TestClient, tipo: str):
    from vigia.app.models import Alert
    from vigia.app.services import alerting

    if tipo == "binario":
        proyecto = _proyecto_binario(client, "back-261-bin")
        _ingerir(client, proyecto, _filas_binario(300, 1, "base"), rol="baseline", mapeo=_MAPEO_BINARIO, evaluar=False)
        _ingerir(client, proyecto, _filas_binario(300, 2, "p"), rol="production", mapeo=_MAPEO_BINARIO, evaluar=True)
    else:
        proyecto, _s, _t = d.linea_base_multiclase(client, "back-261-multi", n=300, evaluar=True)
    s, project, monitor, ev = _evaluacion_y_monitor(client, proyecto["id"])
    with s:
        def candidato(estado):
            return [{"metric_key": "accuracy", "group_code": None, "state": estado, "value": 0.5}]

        alerting.sync_candidates(s, project, monitor, ev, candidato(State.alerta))
        fila = s.exec(select(Alert).where(Alert.project_id == project.id, Alert.metric_key == "accuracy")).one()
        assert fila.status == "abierta"
        alerting.sync_candidates(s, project, monitor, ev, candidato(State.sin_datos))
        s.refresh(fila)
        assert fila.status == "abierta" and fila.observation_count == 0
        alerting.sync_candidates(s, project, monitor, ev, candidato(State.ok))
        s.refresh(fila)
        assert fila.status == "en_observacion" and fila.observation_count == 1


# ---------------------------------------------------------------------------
# `nan` en el registro de uso de una regresión
# ---------------------------------------------------------------------------


def _tarea_regresion() -> TaskSpec:
    return TaskSpec(task_type="regression", unidad="mg/dl")


def test_nan_da_422_con_la_fila_y_el_blanco_sigue_siendo_nulo():
    from fastapi import HTTPException

    tarea = _tarea_regresion()
    for valor in ("nan", " NaN ", "NAN"):
        with pytest.raises(HTTPException) as e:
            _parse_cifra(valor, tarea, fila_n=7, columna="human_value")
        assert e.value.status_code == 422 and "fila 7" in e.value.detail
    assert _parse_cifra("", tarea, fila_n=7, columna="human_value") is None
    assert _parse_cifra("   ", tarea, fila_n=7, columna="human_value") is None
    assert _parse_cifra("38.5", tarea, fila_n=7, columna="human_value") == 38.5


# ---------------------------------------------------------------------------
# El motivo de la alerta no niega correcciones que existen
# ---------------------------------------------------------------------------


def _medida(valor, n, n_override):
    return SimpleNamespace(
        metric_key="human_review_zero", group_code=None, state=State.aviso, value=valor,
        motivo="ningún profesional ha corregido al modelo en 7150 decisiones",
        extra={"n": n, "n_override": n_override},
    )


def test_el_motivo_con_correcciones_dice_cuantas():
    c = _candidato_revision_cero(_medida(0.008, 7150, 57))
    assert c["motivo"] == "solo 57 de 7150 decisiones se apartaron del modelo"
    assert "ningún" not in c["motivo"]


def test_el_motivo_con_cero_correcciones_no_cambia():
    c = _candidato_revision_cero(_medida(0.0, 7150, 0))
    assert c["motivo"].startswith("ningún profesional ha corregido")
