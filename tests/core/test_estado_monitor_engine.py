"""Sobre el motor real: `label_skew` sin línea base."""
from __future__ import annotations

from vigia.core.engine import History, MonitorSettings, evaluate_batch
from vigia.core.schema import HARNESS_FEEDBACK_MAPPING, State

MOTIVO = "sin línea base congelada para esta versión"


def _calidad(baseline_canonico, *, congelar: bool):
    history = History()
    seq = history.add_batch(
        baseline_canonico, mapping=HARNESS_FEEDBACK_MAPPING, model_version="v1", phase_label="b1"
    )
    if congelar:
        history.freeze_baseline(seq, "v1")
    return evaluate_batch(history, seq, MonitorSettings.defaults())["quality"]


def test_sin_linea_base_label_skew_sin_datos_no_tapa_un_monitor_sano(baseline_canonico):
    calidad = _calidad(baseline_canonico, congelar=False)
    medidas = {m.metric_key: m for m in calidad.measurements}
    assert medidas["label_skew"].state == State.sin_datos
    assert medidas["label_skew"].motivo == MOTIVO
    evaluadas = [
        m.state
        for m in calidad.measurements
        if m.state != State.sin_datos and (m.threshold_low is not None or m.threshold_high is not None)
    ]
    assert evaluadas, "el caso necesita alguna métrica con umbral evaluada"
    assert calidad.worst_state != State.sin_datos
    enumeradas = calidad.to_dict()["details"]["metricas_sin_datos"]
    assert {"metric_key": "label_skew", "group_code": None, "motivo": MOTIVO} in enumeradas


def test_con_linea_base_no_hay_faltantes_de_label_skew(baseline_canonico):
    calidad = _calidad(baseline_canonico, congelar=True)
    faltan = calidad.to_dict()["details"].get("metricas_sin_datos", [])
    assert all(f["metric_key"] != "label_skew" for f in faltan)
