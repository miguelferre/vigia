"""Deriva, equidad y tasa de etiqueta de regresión."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from vigia.core.drift import (
    MOTIVO_PSI_POCOS_CORTES,
    evaluate_drift,
    label_drift_regresion,
    prediction_drift_regresion,
)
from vigia.core.engine import MonitorSettings, evaluate_batch
from vigia.core.fairness import evaluate_fairness
from vigia.core.loaders import to_canonical
from vigia.core.schema import (
    CLAVES_EQUIDAD_ERROR,
    COL_GROUP,
    COL_LABEL_VALUE,
    COL_PREDICTION_VALUE,
    MOTIVO_SIN_PROBABILIDAD,
    MOTIVO_SIN_RANGO,
    DriftConfig,
    FairnessConfig,
    MonitorThresholds,
    State,
    Threshold,
    ThresholdKind,
)

from ._datos_regresion import crudo, historia, mapeo, tarea

_PERTENENCIA = (
    "rate_unpriv",
    "rate_priv",
    "disparate_impact",
    "fairness_value",
    "impact_score",
    "statistical_parity_difference",
    "false_negative_rate_difference",
    "false_positive_rate_difference",
    "false_discovery_rate_difference",
    "false_omission_rate_difference",
    "error_rate_difference",
    "average_odds_difference",
    "average_abs_odds_difference",
    "fnr_unpriv",
    "fnr_priv",
    "fpr_unpriv",
    "fpr_priv",
    "tpr_unpriv",
    "tpr_priv",
)


def _umbral(clave, kind, valor):
    return Threshold(metric_key=clave, kind=kind, value=valor, origen="linea_base")


def _deriva(h, t, batch=1, thresholds=None):
    return evaluate_drift(
        h.baseline_for("v1"),
        h.batch(batch),
        config=DriftConfig(),
        thresholds=thresholds or MonitorThresholds(),
        feature_cols=["x"],
        task=t,
    )


def _equidad(h, t, batch=1, metodo="lote", thresholds=None, config=None):
    return evaluate_fairness(
        h.frame(),
        batch_seq=batch,
        config=config or FairnessConfig(),
        thresholds=thresholds or MonitorThresholds(),
        model_version="v1",
        interval_method=metodo,
        task=t,
    )


def _por_clave(r, grupo=None):
    return {
        (m.metric_key, m.group_code): m for m in r.measurements if grupo is None or m.group_code == grupo
    }


# --------------------------------------------------------------------------
# Deriva
# --------------------------------------------------------------------------


def test_prediction_drift_score_es_el_ks_de_la_prediccion_continua():
    h, t = historia([crudo(500, seed=0), crudo(500, seed=1, desplazamiento=5.0)])
    r = _deriva(h, t)
    base = h.baseline_for("v1")[COL_PREDICTION_VALUE].to_numpy()
    cur = h.batch(1)[COL_PREDICTION_VALUE].to_numpy()
    ks = stats.ks_2samp(base, cur)
    medida = {m.metric_key: m for m in r.measurements}["prediction_drift_score"]
    assert medida.extra["valor_calculado"] == pytest.approx(ks.statistic, abs=1e-12)
    d = r.details["prediction"]
    assert d["score"] == d["ks"] == pytest.approx(ks.statistic, abs=1e-12)
    assert d["ks_p"] == pytest.approx(ks.pvalue, abs=1e-12)
    assert d["diferencia_medias"] == pytest.approx(cur.mean() - base.mean(), abs=1e-9)
    assert d["media_base"] == pytest.approx(base.mean()) and d["media_actual"] == pytest.approx(cur.mean())
    assert d["psi"] is not None and d["psi_motivo"] is None
    assert d["psi"] > 0.1  # un desplazamiento de 5 unidades se ve en el PSI


def test_mismos_cortes_para_la_linea_base_y_el_lote():
    h, t = historia([crudo(500, seed=0), crudo(300, seed=1)])
    d = _deriva(h, t).details["prediction"]
    assert len(d["bin_edges"]) == 21
    assert len(d["bin_counts_base"]) == len(d["bin_counts_actual"]) == 20
    assert sum(d["bin_counts_base"]) == d["n_base"] == 500
    assert sum(d["bin_counts_actual"]) == d["n_actual"] == 300


def test_una_salida_en_pocos_escalones_da_el_motivo_del_psi_y_el_ks_decide():
    base, lote = crudo(400, seed=0), crudo(400, seed=1)
    base["p"] = np.where(base["p"] > 50, 60.0, 40.0)  # dos escalones: menos de 3 cortes
    lote["p"] = np.where(lote["p"] > 45, 60.0, 40.0)
    h, t = historia([base, lote])
    d = _deriva(h, t).details["prediction"]
    assert d["psi"] is None and d["psi_motivo"] == MOTIVO_PSI_POCOS_CORTES
    assert d["ks"] is not None and d["ks"] > 0.05
    assert len(d["bin_edges"]) == 21  # el histograma común se dibuja igual


def test_sin_umbral_la_prediccion_espera_a_la_linea_base_y_con_umbral_alerta():
    h, t = historia([crudo(500, seed=0), crudo(500, seed=1, desplazamiento=8.0)])
    sin = {m.metric_key: m for m in _deriva(h, t).measurements}
    assert sin["prediction_drift_score"].state == State.sin_datos
    assert sin["prediction_drift_score"].extra["umbral_pendiente"] is True
    umbrales = MonitorThresholds(
        thresholds=[_umbral("prediction_drift_score", ThresholdKind.upper_limit, 0.10)]
    )
    con = {m.metric_key: m for m in _deriva(h, t, thresholds=umbrales).measurements}
    assert con["prediction_drift_score"].state == State.alerta
    assert con["prediction_drift_score"].value > 0.2


def test_feature_drift_score_no_cambia_y_no_hay_confianza():
    h, t = historia([crudo(500, seed=0), crudo(500, seed=1)])
    r = _deriva(h, t)
    assert {m.metric_key for m in r.measurements} == {"prediction_drift_score", "feature_drift_score"}
    ks_x = stats.ks_2samp(h.baseline_for("v1")["x"], h.batch(1)["x"]).statistic
    assert {m.metric_key: m for m in r.measurements}["feature_drift_score"].value == pytest.approx(ks_x)
    assert "confidence" not in r.details and "clases_predichas" not in r.details


def test_la_deriva_de_la_etiqueta_solo_si_los_dos_lados_la_tienen():
    h, t = historia([crudo(300, seed=0), crudo(300, seed=1)])
    et = _deriva(h, t).details["etiqueta"]
    assert set(et) == {"ks", "ks_p", "diferencia_medias"}
    sin_etiqueta = crudo(300, seed=1)
    sin_etiqueta["y"] = np.nan
    h2, t2 = historia([crudo(300, seed=0), sin_etiqueta])
    assert "etiqueta" not in _deriva(h2, t2).details
    assert label_drift_regresion(np.array([np.nan]), np.array([1.0, 2.0])) is None


def test_funciones_con_listas_vacias_no_revientan():
    d = prediction_drift_regresion(np.array([]), np.array([1.0, 2.0]))
    assert d["score"] is None and d["psi"] is None


# --------------------------------------------------------------------------
# Equidad con rango favorable
# --------------------------------------------------------------------------


def _errores(h, batch, codigo):
    f = h.batch(batch)
    f = f[(f[COL_GROUP] == codigo) & f[COL_LABEL_VALUE].notna()]
    return (f[COL_PREDICTION_VALUE] - f[COL_LABEL_VALUE]).to_numpy()


def test_con_rango_publica_la_pertenencia_y_el_error_por_grupo():
    h, t = historia([crudo(400, seed=0), crudo(400, seed=1, recorte=6.0)])
    r = _equidad(h, t, metodo="lote")
    m = _por_clave(r)
    for clave in _PERTENENCIA:
        assert (clave, None) in m or (clave, "unpriv") in m or (clave, "priv") in m, clave
    assert m[("rate_unpriv", "unpriv")].value is not None  # la fórmula binaria sobre el 0/1
    e0, e1 = _errores(h, 1, 0), _errores(h, 1, 1)
    assert m[("mean_absolute_error", "unpriv")].value == pytest.approx(np.abs(e0).mean(), abs=1e-9)
    assert m[("mean_absolute_error", "priv")].value == pytest.approx(np.abs(e1).mean(), abs=1e-9)
    assert m[("mean_error", "unpriv")].value == pytest.approx(e0.mean(), abs=1e-9)
    assert m[("mean_error", "priv")].value == pytest.approx(e1.mean(), abs=1e-9)
    assert m[("n", "unpriv")].value == len(e0) and m[("n", "priv")].value == len(e1)
    # el recorte del grupo no privilegiado es un sesgo negativo (infraestima)
    assert m[("mean_error", "unpriv")].value < -4
    dif = m[("mean_error_difference", None)]
    assert dif.extra["valor_calculado"] == pytest.approx(e0.mean() - e1.mean(), abs=1e-9)
    assert m[("mean_absolute_error_difference", None)].extra["valor_calculado"] == pytest.approx(
        np.abs(e0).mean() - np.abs(e1).mean(), abs=1e-9
    )
    assert m[("mean_absolute_error_ratio", None)].extra["valor_calculado"] == pytest.approx(
        np.abs(e0).mean() / np.abs(e1).mean(), abs=1e-9
    )


def test_sin_probabilidad_y_detalles_del_violin_y_del_error():
    h, t = historia([crudo(400, seed=0), crudo(400, seed=1, recorte=6.0)])
    d = _equidad(h, t).details
    assert d["favorable_probability_motivo"] == MOTIVO_SIN_PROBABILIDAD
    assert "favorable_probability" not in d
    assert d["rangos_favorables"] == [[55.0, None]]
    epg = d["error_por_grupo"]
    assert epg["metodo_intervalo"] == "welch"
    assert set(epg["unpriv"]) == {"n", "mae", "sesgo", "motivo"}
    ppg = d["prediccion_por_grupo"]
    assert set(ppg["unpriv"]["cuantiles"]) == {"p5", "p25", "p50", "p75", "p95"}
    assert ppg["unpriv"]["histograma"]["bin_edges"] == ppg["priv"]["histograma"]["bin_edges"]
    assert sum(ppg["unpriv"]["histograma"]["counts"]) == ppg["unpriv"]["n"]
    assert ppg["unpriv"]["media"] < ppg["priv"]["media"]  # el recorte baja la predicción de `a`


def test_el_recorte_alerta_por_el_error_con_signo_y_un_lote_sano_no():
    h, t = historia([crudo(400, seed=0), crudo(400, seed=1, recorte=6.0), crudo(400, seed=2)])
    umbrales = MonitorThresholds(
        thresholds=[
            _umbral("mean_error_difference", ThresholdKind.lower_limit, -2.0),
            _umbral("mean_error_difference", ThresholdKind.upper_limit, 2.0),
            _umbral("mean_absolute_error_difference", ThresholdKind.upper_limit, 1.0),
            _umbral("mean_absolute_error_ratio", ThresholdKind.upper_limit, 1.2),
        ]
    )
    sano = _por_clave(_equidad(h, t, batch=2, thresholds=umbrales))
    cortado = _por_clave(_equidad(h, t, batch=1, thresholds=umbrales))
    for clave in CLAVES_EQUIDAD_ERROR:
        assert sano[(clave, None)].state in (State.ok, State.aviso), clave
        assert cortado[(clave, None)].state in (State.alerta, State.inestable), clave
    assert cortado[("mean_error_difference", None)].state == State.alerta
    assert cortado[("mean_error_difference", None)].value < -2.0  # no privilegiado menos privilegiado


def test_el_intervalo_es_el_de_welch_en_lote_y_no_hay_intervalo_en_ventanas():
    h, t = historia([crudo(400, seed=0), crudo(400, seed=1, recorte=6.0)])
    umbrales = MonitorThresholds(
        thresholds=[
            _umbral("mean_error_difference", ThresholdKind.lower_limit, -2.0),
            _umbral("mean_absolute_error_difference", ThresholdKind.upper_limit, 1.0),
        ]
    )
    lote = _por_clave(_equidad(h, t, thresholds=umbrales, metodo="lote"))
    e0, e1 = _errores(h, 1, 0), _errores(h, 1, 1)
    esperado = stats.ttest_ind(e0, e1, equal_var=False).confidence_interval(0.95)
    medida = lote[("mean_error_difference", None)]
    assert medida.interval_low == pytest.approx(esperado.low, abs=1e-9)
    assert medida.interval_high == pytest.approx(esperado.high, abs=1e-9)
    esperado_abs = stats.ttest_ind(np.abs(e0), np.abs(e1), equal_var=False).confidence_interval(0.95)
    abs_med = lote[("mean_absolute_error_difference", None)]
    assert abs_med.interval_low == pytest.approx(esperado_abs.low, abs=1e-9)
    ventanas = _por_clave(_equidad(h, t, thresholds=umbrales, metodo="ventanas"))
    assert ventanas[("mean_error_difference", None)].interval_low is None
    assert _equidad(h, t, metodo="ventanas").details["error_por_grupo"]["metodo_intervalo"] is None


def test_un_grupo_con_menos_de_min_group_filas_da_sin_datos_nunca_una_alerta():
    pequeno = crudo(400, seed=1, recorte=9.0)
    pequeno = pd.concat(
        [pequeno[pequeno["g"] == "b"], pequeno[pequeno["g"] == "a"].head(10)], ignore_index=True
    )
    h, t = historia([crudo(400, seed=0), pequeno])
    umbrales = MonitorThresholds(
        thresholds=[_umbral("mean_error_difference", ThresholdKind.lower_limit, -1.0)]
    )
    for metodo in ("lote", "ventanas"):
        m = _por_clave(_equidad(h, t, thresholds=umbrales, metodo=metodo))
        assert m[("mean_error", "unpriv")].value is None
        assert m[("mean_error", "unpriv")].state == State.sin_datos
        assert "grupo insuficiente: n=10" in m[("mean_error", "unpriv")].motivo
        diferencia = m[("mean_error_difference", None)]
        assert diferencia.state == State.sin_datos and diferencia.value is None
        assert m[("mean_error", "priv")].value is not None  # el otro grupo sí se publica


# --------------------------------------------------------------------------
# Sin rango favorable
# --------------------------------------------------------------------------


def test_sin_rango_las_19_medidas_de_pertenencia_dan_sin_datos_con_su_motivo():
    h, t = historia([crudo(400, seed=0), crudo(400, seed=1, recorte=6.0)], rangos=[])
    r = _equidad(h, t)
    por_clave = {(m.metric_key): m for m in r.measurements if m.metric_key in _PERTENENCIA}
    assert set(por_clave) == set(_PERTENENCIA)
    for m in por_clave.values():
        assert m.value is None and m.state == State.sin_datos and m.motivo == MOTIVO_SIN_RANGO
        assert "fragil" not in m.extra  # min_positives no se aplica sin rango
    assert r.details["motivo"] == MOTIVO_SIN_RANGO and r.details["sin_rango_favorable"] is True
    assert r.details["rangos_favorables"] == []
    # las de error por grupo se publican
    m = _por_clave(r)
    assert m[("mean_error", "unpriv")].value < -4
    assert ("n", "unpriv") in m and ("n", "priv") in m


@pytest.mark.parametrize("metodo", ["lote", "ventanas"])
def test_sin_rango_las_medidas_de_error_deciden_el_estado(metodo):
    h, t = historia([crudo(400, seed=0), crudo(400, seed=1, recorte=6.0), crudo(400, seed=2)], rangos=[])
    umbrales = MonitorThresholds(
        thresholds=[
            _umbral("mean_error_difference", ThresholdKind.lower_limit, -2.0),
            _umbral("mean_error_difference", ThresholdKind.upper_limit, 2.0),
        ]
    )
    assert _equidad(h, t, batch=1, thresholds=umbrales, metodo=metodo).worst_state == State.alerta
    assert _equidad(h, t, batch=2, thresholds=umbrales, metodo=metodo).worst_state == State.ok
    # sin umbrales todavía, el monitor espera a la línea base
    assert _equidad(h, t, batch=1, metodo=metodo).worst_state == State.sin_datos


def test_sin_atributo_protegido_el_motivo_lo_dice():
    m = mapeo().model_copy(update={"protected_attr_col": None, "unpriv_groups": [], "priv_groups": []})
    t = tarea()
    df = crudo(300)
    canon = to_canonical(df, m, task=t)
    r = evaluate_fairness(
        canon.assign(batch_seq=0, model_version="v1"),
        batch_seq=0,
        config=FairnessConfig(),
        thresholds=MonitorThresholds(),
        model_version="v1",
        interval_method="lote",
        task=t,
    )
    medida = _por_clave(r)[("mean_error", "unpriv")]
    assert medida.state == State.sin_datos and "no hay atributo protegido" in medida.motivo


# --------------------------------------------------------------------------
# Tasa de etiqueta de la línea base
# --------------------------------------------------------------------------


def test_label_rate_baseline_lee_la_pertenencia_y_sin_rango_no_existe_en_la_evaluacion():
    h, _ = historia([crudo(400, seed=0), crudo(400, seed=1)])
    tasa = h.label_rate_baseline("v1")
    assert 0.0 < tasa < 1.0  # la media del valor real (~50) no se cuela como tasa
    h2, t2 = historia([crudo(400, seed=0), crudo(400, seed=1)], rangos=[])
    r = evaluate_batch(h2, 1, MonitorSettings.defaults(), task=t2)
    assert "label_skew" not in {m.metric_key for m in r["quality"].measurements}
