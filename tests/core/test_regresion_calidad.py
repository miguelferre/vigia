"""Calidad de regresión."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    median_absolute_error,
    r2_score,
    root_mean_squared_error,
)

from vigia.core.engine import MonitorSettings, evaluate_batch
from vigia.core.quality import evaluate_quality, quality_metrics
from vigia.core.quality_regresion import (
    MOTIVO_R2_SIN_VARIANZA,
    metricas_regresion,
    pred_vs_real,
)
from vigia.core.schema import (
    CLAVES_CALIDAD_REGRESION,
    CLAVES_CALIDAD_REGRESION_DETALLE,
    COL_LABEL_VALUE,
    COL_PREDICTION_VALUE,
    DatosNoValidos,
    MonitorThresholds,
    QualityConfig,
    State,
    Threshold,
    ThresholdKind,
)

from ._datos_regresion import crudo, historia, tarea


def _frame(n=300, seed=0, **kw):
    h, t = historia([crudo(n, seed=seed, **kw)])
    return h.frame(), t


def _evaluar(frame, t, thresholds=None, **kw):
    return evaluate_quality(
        frame,
        batch_seq=0,
        config=QualityConfig(),
        thresholds=thresholds or MonitorThresholds(),
        task=t,
        **kw,
    )


# --------------------------------------------------------------------------
# Valores contra sklearn.metrics en 1e-9
# --------------------------------------------------------------------------


def test_metricas_igual_que_sklearn_en_1e_9():
    frame, _ = _frame()
    y = frame[COL_LABEL_VALUE].to_numpy()
    yhat = frame[COL_PREDICTION_VALUE].to_numpy()
    m = metricas_regresion(frame)
    assert m["n"] == len(frame)
    assert m["mean_absolute_error"] == pytest.approx(mean_absolute_error(y, yhat), abs=1e-9)
    assert m["root_mean_squared_error"] == pytest.approx(root_mean_squared_error(y, yhat), abs=1e-9)
    assert m["mean_squared_error"] == pytest.approx(mean_squared_error(y, yhat), abs=1e-9)
    assert m["median_absolute_error"] == pytest.approx(median_absolute_error(y, yhat), abs=1e-9)
    assert m["r2"] == pytest.approx(r2_score(y, yhat), abs=1e-9)
    # Sesgo medio = media de (predicción - real); negativo es infraestimar
    assert m["mean_error"] == pytest.approx(float(np.mean(yhat - y)), abs=1e-9)
    assert m["motivo_r2"] is None


def test_el_signo_del_sesgo_negativo_es_infraestimar():
    df = pd.DataFrame({COL_LABEL_VALUE: [10.0, 20.0, 30.0], COL_PREDICTION_VALUE: [8.0, 18.0, 28.0]})
    assert metricas_regresion(df)["mean_error"] == pytest.approx(-2.0)


def test_quality_metrics_con_tarea_de_regresion_da_las_metricas_de_regresion():
    frame, t = _frame()
    assert quality_metrics(frame, task=t) == metricas_regresion(frame)


def test_evaluate_quality_publica_cuatro_titulares_y_dos_de_detalle_sin_matriz():
    frame, t = _frame()
    r = _evaluar(frame, t)
    claves = [m.metric_key for m in r.measurements]
    for clave in (*CLAVES_CALIDAD_REGRESION, *CLAVES_CALIDAD_REGRESION_DETALLE, "n"):
        assert clave in claves
    for clave in ("tp", "fp", "fn", "tn", "accuracy", "log_loss"):
        assert clave not in claves
    assert "confusion" not in r.details and "confusion_matrix" not in r.details
    assert r.window.n == len(frame) and r.window.complete


# --------------------------------------------------------------------------
# Details
# --------------------------------------------------------------------------


def test_details_residuos_pred_vs_real_y_etiqueta():
    frame, t = _frame(500)
    d = _evaluar(frame, t).details
    assert d["task_type"] == "regression" and d["unidad"] == "horas"
    res = d["residuos"]
    assert len(res["bin_edges"]) == 21 and len(res["counts"]) == 20
    assert sum(res["counts"]) == res["n"] == 500
    e = frame[COL_PREDICTION_VALUE].to_numpy() - frame[COL_LABEL_VALUE].to_numpy()
    assert res["media"] == pytest.approx(float(e.mean()), abs=1e-9)
    assert res["desviacion"] == pytest.approx(float(e.std(ddof=1)), abs=1e-9)
    filas = d["pred_vs_real"]
    assert 2 <= len(filas) <= 10 and sum(f["n"] for f in filas) == 500
    for f in filas:
        assert set(f) == {"decil", "pred_media", "real_media", "real_p10", "real_p90", "n"}
        assert f["real_p10"] <= f["real_media"] <= f["real_p90"] or f["n"] < 5
    # los deciles van de menor a mayor predicción
    assert [f["pred_media"] for f in filas] == sorted(f["pred_media"] for f in filas)
    et = d["etiqueta"]
    assert et["media"] == pytest.approx(float(frame[COL_LABEL_VALUE].mean()), abs=1e-9)
    assert len(et["histograma"]["bin_edges"]) == 21 and sum(et["histograma"]["counts"]) == 500


def test_pred_vs_real_une_los_cortes_repetidos_de_una_salida_en_escalones():
    y = np.array([1.0, 2.0, 3.0, 4.0] * 50)
    yhat = np.array([10.0, 10.0, 20.0, 20.0] * 50)  # solo dos valores
    filas = pred_vs_real(y, yhat)
    assert len(filas) == 2 and sum(f["n"] for f in filas) == 200
    assert pred_vs_real(np.array([]), np.array([])) == []


# --------------------------------------------------------------------------
# Casos borde
# --------------------------------------------------------------------------


def test_con_varianza_nula_da_sin_datos_con_motivo_nunca_menos_infinito():
    df = crudo(200)
    df["y"] = 42.0
    h, t = historia([df])
    r = _evaluar(h.frame(), t)
    medida = {m.metric_key: m for m in r.measurements}["r2"]
    assert medida.value is None and medida.state == State.sin_datos
    assert medida.motivo == MOTIVO_R2_SIN_VARIANZA
    assert math.isfinite(metricas_regresion(h.frame())["mean_absolute_error"])
    assert metricas_regresion(h.frame())["r2"] is None


def test_varianza_nula_tambien_con_umbrales_de_r2_puestos():
    df = crudo(200)
    df["y"] = 42.0
    h, t = historia([df])
    umbrales = MonitorThresholds(
        thresholds=[Threshold(metric_key="r2", kind=ThresholdKind.lower_limit, value=0.5)]
    )
    medida = {m.metric_key: m for m in _evaluar(h.frame(), t, umbrales).measurements}["r2"]
    assert medida.state == State.sin_datos and medida.motivo == MOTIVO_R2_SIN_VARIANZA


def test_menos_de_min_feedback_filas_con_etiqueta_los_cuatro_titulares_sin_datos():
    h, t = historia([crudo(50)])
    r = _evaluar(h.frame(), t)
    por_clave = {m.metric_key: m for m in r.measurements}
    for clave in CLAVES_CALIDAD_REGRESION:
        assert por_clave[clave].state == State.sin_datos
        assert "solo hay 50 filas etiquetadas" in por_clave[clave].motivo
    assert por_clave["n"].value == 50.0
    assert r.window.complete is False
    assert "residuos" not in r.details


def test_sin_etiquetas_no_hay_calidad_y_no_se_llama_a_validar_probabilidad():
    df = crudo(200)
    df["y"] = np.nan
    h, t = historia([df])
    r = _evaluar(h.frame(), t)  # no lanza DatosNoValidos por una probabilidad que no existe
    assert all(
        m.state == State.sin_datos for m in r.measurements if m.metric_key in CLAVES_CALIDAD_REGRESION
    )


def test_un_frame_sin_las_columnas_de_valor_da_un_mensaje_en_espanol():
    frame, _ = _frame()
    with pytest.raises(DatosNoValidos, match="falta el valor"):
        metricas_regresion(frame.drop(columns=[COL_PREDICTION_VALUE]))


# --------------------------------------------------------------------------
# Sin valor de fábrica, los titulares esperan a la línea base
# --------------------------------------------------------------------------


def test_sin_umbrales_los_titulares_esperan_a_la_linea_base():
    frame, t = _frame()
    r = _evaluar(frame, t)
    por_clave = {m.metric_key: m for m in r.measurements}
    for clave in CLAVES_CALIDAD_REGRESION:
        m = por_clave[clave]
        assert m.state == State.sin_datos and m.value is None
        assert m.motivo == "umbral pendiente de la línea base"
        assert m.extra["umbral_pendiente"] is True
        assert m.extra["valor_calculado"] == pytest.approx(metricas_regresion(frame)[clave])
    for clave in CLAVES_CALIDAD_REGRESION_DETALLE:
        assert por_clave[clave].state == State.ok and por_clave[clave].value is not None
    assert r.worst_state == State.sin_datos
    assert {x["metric_key"] for x in r.metricas_sin_datos()} == set(CLAVES_CALIDAD_REGRESION)


def test_con_umbrales_de_la_linea_base_clasifica_y_alerta():
    frame, t = _frame()
    umbrales = MonitorThresholds(
        thresholds=[
            Threshold(metric_key="mean_absolute_error", kind=ThresholdKind.upper_limit, value=1.0),
            Threshold(metric_key="r2", kind=ThresholdKind.lower_limit, value=0.2),
            Threshold(metric_key="mean_error", kind=ThresholdKind.lower_limit, value=-5.0),
            Threshold(metric_key="mean_error", kind=ThresholdKind.upper_limit, value=5.0),
        ]
    )
    por_clave = {m.metric_key: m for m in _evaluar(frame, t, umbrales).measurements}
    assert por_clave["mean_absolute_error"].state == State.alerta  # MAE ~3,2 > 1
    assert por_clave["mean_absolute_error"].value == pytest.approx(
        metricas_regresion(frame)["mean_absolute_error"]
    )
    assert por_clave["r2"].state == State.ok
    assert por_clave["mean_error"].state == State.ok
    # un titular sin su umbral sigue esperando aunque otros ya lo tengan
    assert por_clave["root_mean_squared_error"].state == State.sin_datos


def test_la_deteccion_de_un_sesgo_con_signo_usa_los_dos_lados():
    h, t = historia([crudo(400, seed=0), crudo(400, seed=1, desplazamiento=-6.0)])
    umbrales = MonitorThresholds(
        thresholds=[
            Threshold(metric_key="mean_error", kind=ThresholdKind.lower_limit, value=-1.0),
            Threshold(metric_key="mean_error", kind=ThresholdKind.upper_limit, value=1.0),
        ]
    )
    sano = evaluate_quality(
        h.frame(), batch_seq=0, config=QualityConfig(), thresholds=umbrales, task=t
    )
    sesgado = evaluate_quality(
        h.frame(), batch_seq=1, config=QualityConfig(), thresholds=umbrales, task=t
    )
    assert {m.metric_key: m for m in sano.measurements}["mean_error"].state == State.ok
    medida = {m.metric_key: m for m in sesgado.measurements}["mean_error"]
    assert medida.state == State.alerta and medida.value < -1.0  # infraestima


# --------------------------------------------------------------------------
# Rango favorable en calidad
# --------------------------------------------------------------------------


def test_con_rango_label_rate_prediction_rate_y_label_skew_sobre_la_pertenencia():
    h, t = historia([crudo(400, seed=0), crudo(400, seed=1)])
    r = evaluate_batch(h, 1, MonitorSettings.defaults(), task=t)["quality"]
    por_clave = {m.metric_key: m for m in r.measurements}
    frame = h.batch(1)
    assert por_clave["label_rate"].value == pytest.approx(float(frame["label"].mean()))
    assert por_clave["prediction_rate"].value == pytest.approx(float(frame["prediction"].mean()))
    # La tasa de la línea base es la pertenencia, no la media del valor real
    base = h.baseline_for("v1")
    assert h.label_rate_baseline("v1") == pytest.approx(float(base["label"].mean()))
    assert h.label_rate_baseline("v1") <= 1.0
    assert por_clave["label_skew"].value == pytest.approx(
        por_clave["label_rate"].value - h.label_rate_baseline("v1")
    )


def test_sin_rango_no_hay_label_skew_ni_tasas_de_pertenencia():
    h, t = historia([crudo(400, seed=0), crudo(400, seed=1)], rangos=[])
    r = evaluate_batch(h, 1, MonitorSettings.defaults(), task=t)["quality"]
    claves = {m.metric_key for m in r.measurements}
    assert claves.isdisjoint({"label_skew", "label_rate", "prediction_rate"})
    assert tarea(rangos=[]).sin_rango_favorable
