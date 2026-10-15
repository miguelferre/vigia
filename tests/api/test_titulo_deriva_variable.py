"""El título de la alerta de `feature_drift_score` nombra la
variable del máximo, su valor, la categoría nueva y la marca de «sin categorías
comunes con la base». El dato sale de `result.details.features[]`."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api.test_ciclo_de_vida_proyecto import _alertas, _linea_base_y_evento
from vigia.app.models import Alert
from vigia.app.services import alerting


def _resultado(*filas: dict) -> dict:
    return {"details": {"features": list(filas)}}


def _categorica(feature: str, score: float, categorias: list, base: list, actual: list, **extra) -> dict:
    return {
        "feature": feature,
        "kind": "categorica",
        "score": score,
        "categories": categorias,
        "bin_counts_base": base,
        "bin_counts_actual": actual,
        "sin_valores_comunes": False,
        **extra,
    }


def test_detalle_nombra_la_variable_del_maximo_y_la_categoria_nueva():
    resultado = _resultado(
        {"feature": "importe", "kind": "numerica", "score": 0.035},
        _categorica("canal_presentacion", 0.203, ["app", "online", "presencial"], [0, 2130, 1870], [80, 486, 434]),
        _categorica("region", 0.127, ["n", "s"], [10, 10], [12, 8]),
    )
    assert (
        alerting._detalle_deriva("feature_drift_score", resultado)
        == "máximo en canal_presentacion (0,203), categoría nueva: app"
    )


def test_detalle_con_varias_categorias_nuevas_las_lista_y_recorta():
    resultado = _resultado(_categorica("c", 0.5, list("abcdef"), [5, 5, 0, 0, 0, 0], [1, 1, 1, 1, 1, 1]))
    assert (
        alerting._detalle_deriva("feature_drift_score", resultado)
        == "máximo en c (0,500), categorías nuevas: c, d, e y 1 más"
    )


def test_detalle_sin_valores_comunes_lo_dice_en_vez_de_listar_categorias():
    resultado = _resultado(
        _categorica(
            "fecha", 1.0, ["2026-01-05", "2026-01-12"], [9, 0], [0, 9], sin_valores_comunes=True
        )
    )
    assert (
        alerting._detalle_deriva("feature_drift_score", resultado)
        == "máximo en fecha (1,000), sin categorías comunes con la base"
    )


def test_detalle_de_una_numerica_solo_nombra_la_variable():
    resultado = _resultado({"feature": "Age", "kind": "numerica", "score": 0.189})
    assert alerting._detalle_deriva("feature_drift_score", resultado) == "máximo en Age (0,189)"


def test_detalle_ignora_nulos_y_nan_y_otras_metricas():
    resultado = _resultado(
        {"feature": "a", "score": None},
        {"feature": "b", "score": float("nan")},
        {"feature": "c", "score": 0.3},
    )
    assert alerting._detalle_deriva("feature_drift_score", resultado) == "máximo en c (0,300)"
    assert alerting._detalle_deriva("prediction_drift_score", resultado) is None
    assert alerting._detalle_deriva("feature_drift_score", None) is None
    assert alerting._detalle_deriva("feature_drift_score", {"details": {}}) is None
    assert alerting._detalle_deriva("feature_drift_score", _resultado({"feature": "a", "score": None})) is None


def test_la_cola_se_conserva_al_reconstruir_el_titulo_servido(session: Session):
    """`_titulo_actual` relee la etiqueta de la métrica y conserva el resto."""
    alerta = Alert(
        project_id=1,
        monitor_type="drift",
        metric_key="feature_drift_score",
        severity="alta",
        status="abierta",
        title="Etiqueta vieja: 0,203 (umbral <= 0,150), máximo en canal_presentacion (0,203), categoría nueva: app",
        opened_at="2026-10-02T10:00:00+00:00",
        updated_at="2026-10-02T10:00:00+00:00",
    )
    assert alerting._titulo_actual(session, alerta) == (
        "Deriva de características: 0,203 (umbral <= 0,150), máximo en canal_presentacion (0,203), "
        "categoría nueva: app"
    )


def test_la_alerta_de_deriva_abierta_por_el_motor_nombra_la_variable(client: TestClient):
    """De punta a punta con el guion de demo: el KS de `Age` (0,189) da el máximo."""
    proyecto, _base, _evento = _linea_base_y_evento(client, "c11-3-titulo-deriva")
    alerta = next(a for a in _alertas(client, proyecto["id"]) if a["metric_key"] == "feature_drift_score")
    assert alerta["title"].startswith("Deriva de características: 0,189 (umbral <= 0,150)")
    assert "máximo en Age (0,189)" in alerta["title"]
    detalle = client.get(f"/api/alerts/{alerta['id']}").json()
    assert "máximo en Age (0,189)" in detalle["title"]


def test_el_historial_de_deriva_guarda_la_variable_maxima_de_cada_lote(client: TestClient, session: Session):
    """El título se reescribe con la variable del último lote, pero cada
    entrada del historial lleva la suya, para saber qué cruzó en cada lote. Las
    entradas de una alerta de otra métrica siguen sin detalle."""
    from sqlmodel import select

    from tests.api.test_ciclo_de_vida_proyecto import _crear_proyecto
    from vigia.app.models import Evaluation, Monitor, Project

    proyecto = _crear_proyecto(client, "u3-04-historial-deriva")
    project = session.get(Project, proyecto["id"])
    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == project.id, Monitor.type == "drift")
    ).first()
    assert monitor is not None

    def evaluar(*filas: dict, metric_key: str = "feature_drift_score") -> Alert:
        evaluacion = Evaluation(
            monitor_id=monitor.id,
            project_id=project.id,
            model_version_id=project.active_version_id,
            trigger="manual",
            result_json=_resultado(*filas),
        )
        session.add(evaluacion)
        session.flush()
        alertas = alerting.sync_candidates(
            session,
            project,
            monitor,
            evaluacion,
            [{"metric_key": metric_key, "state": "alerta", "value": 0.4, "threshold_high": 0.15}],
        )
        session.commit()
        return alertas[0]

    primera = evaluar({"feature": "Age", "kind": "numerica", "score": 0.4}, {"feature": "Sex", "score": 0.1})
    segunda = evaluar({"feature": "Age", "kind": "numerica", "score": 0.2}, {"feature": "Sex", "score": 0.4})
    assert segunda.id == primera.id

    historial = client.get(f"/api/alerts/{primera.id}").json()["history"]
    assert [e["detalle"] for e in historial] == ["máximo en Age (0,400)", "máximo en Sex (0,400)"]
    assert "máximo en Sex (0,400)" in client.get(f"/api/alerts/{primera.id}").json()["title"]

    otra = evaluar({"feature": "Age", "score": 0.4}, metric_key="prediction_drift_score")
    historial_otra = client.get(f"/api/alerts/{otra.id}").json()["history"]
    assert [e["detalle"] for e in historial_otra] == [None]
