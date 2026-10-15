"""Deriva y equidad multiclase, y el motor de
punta a punta con `evaluate_batch(task=...)`."""
from __future__ import annotations

import numpy as np
import pandas as pd

from vigia.core.drift import (
    confidence_drift,
    confidence_drift_multiclase,
    drift_categorical,
    evaluate_drift,
    prediction_drift_multiclase,
)
from vigia.core.engine import History, MonitorSettings, evaluate_batch
from vigia.core.fairness import evaluate_fairness
from vigia.core.schema import (
    COL_PREDICTION_CLASS,
    DriftConfig,
    FairnessConfig,
    State,
    col_prob,
)
from vigia.core.thresholds import DEFAULT_DRIFT_THRESHOLDS, DEFAULT_FAIRNESS_THRESHOLDS

from ._datos_multiclase import CLASES, canonico, historia, mapeo, tarea


def test_confianza_con_k_2_es_la_de_siempre_bit_a_bit():
    """Con dos columnas [1-p, p] el histograma, JS, KS y PSI son los de
    `confidence_drift` (edges `linspace(0.5, 1)`)."""
    rng = np.random.default_rng(0)
    pb, pc = rng.beta(2, 2, 800), rng.beta(3, 2, 700)
    binario = confidence_drift(pb, pc, bins=20, psi_bins=10)
    multi = confidence_drift_multiclase(
        np.c_[1 - pb, pb], np.c_[1 - pc, pc], classes=("0", "1"), bins=20, psi_bins=10
    )
    assert binario == multi


def test_confianza_multiclase_no_pierde_filas_bajo_0_5():
    base = canonico(600, seed=1, fuerza=0.3)  # modelo flojo: confianza cercana a 1/3
    cur = canonico(600, seed=2, fuerza=0.3, batch=1)
    cols = [col_prob(i) for i in range(3)]
    r = confidence_drift_multiclase(
        base[cols].to_numpy(), cur[cols].to_numpy(), classes=tuple(CLASES)
    )
    assert r["bin_edges"][0] == 1 / 3 and r["bin_edges"][-1] == 1.0
    assert sum(r["bin_counts_base"]) == 600 and sum(r["bin_counts_actual"]) == 600
    assert min(base[cols].max(axis=1)) >= 1 / 3 - 1e-12


def test_by_class_usa_el_texto_de_la_clase_en_el_orden_del_proyecto():
    base = canonico(500, seed=3)
    cur = canonico(500, seed=4, batch=1)
    cols = [col_prob(i) for i in range(3)]
    r = confidence_drift_multiclase(
        base[cols].to_numpy(),
        cur[cols].to_numpy(),
        classes=tuple(CLASES),
        base_pred=base[COL_PREDICTION_CLASS].to_numpy(),
        cur_pred=cur[COL_PREDICTION_CLASS].to_numpy(),
    )
    assert list(r["by_class"]) == CLASES
    suma = np.sum([v["bin_counts_base"] for v in r["by_class"].values()], axis=0)
    assert list(suma) == r["bin_counts_base"]


def test_prediccion_js_ve_un_movimiento_entre_clases_no_favorables():
    """La tasa del conjunto favorable (alta) no se mueve; la distribución sí."""
    rng = np.random.default_rng(0)
    base = pd.Series(rng.choice(CLASES, 1000, p=[0.3, 0.4, 0.3]))
    cur = pd.Series(rng.choice(CLASES, 1000, p=[0.3, 0.1, 0.6]))
    r = prediction_drift_multiclase(base, cur, tuple(CLASES), ("alta",))
    assert abs(r["diff"]) < 0.06  # tasa de la favorable casi igual
    assert r["score"] > 0.25
    assert r["clase_mayor_cambio"] in ("media", "baja")
    assert abs(r["cambio_mayor"]) > 0.25
    esperado = drift_categorical("x", base, cur)["js"]
    assert r["score"] == esperado


def test_evaluate_drift_multiclase_mismo_reparto_es_ok_y_con_deriva_alerta():
    base = canonico(800, seed=5)
    estable = canonico(800, seed=6, batch=1, seq_start=800)
    movido = canonico(800, seed=7, batch=1, seq_start=800, desplazar_a=2)
    feat = ["edad", "sexo"]
    ok = evaluate_drift(
        base, estable, config=DriftConfig(), thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=feat, task=tarea(),
    )
    mal = evaluate_drift(
        base, movido, config=DriftConfig(), thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=feat, task=tarea(),
    )
    p_ok = next(m for m in ok.measurements if m.metric_key == "prediction_drift_score")
    p_mal = next(m for m in mal.measurements if m.metric_key == "prediction_drift_score")
    assert p_ok.state in (State.ok, State.aviso) and p_mal.state == State.alerta
    assert mal.details["prediction"]["clase_mayor_cambio"] == "baja"
    assert "by_class" in mal.details["confidence"]


def test_deriva_multiclase_sin_probabilidad_da_confianza_sin_datos_con_motivo():
    base = canonico(300, seed=8)
    cur = canonico(300, seed=9, batch=1, seq_start=300)
    cols = [col_prob(i) for i in range(3)]
    base[cols] = np.nan
    res = evaluate_drift(
        base, cur, config=DriftConfig(), thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=["edad"], task=tarea(),
    )
    conf = next(m for m in res.measurements if m.metric_key == "confidence_drift_score")
    assert conf.state == State.sin_datos and "no publica probabilidad" in conf.motivo


def test_equidad_con_conjunto_favorable_calcula_como_en_binario_y_da_tabla_por_clase():
    h = historia(canonico(600, seed=10, favorables=("alta", "media")))
    res = evaluate_fairness(
        h, batch_seq=0, config=FairnessConfig(min_records=200),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS, task=tarea(favorables=("alta", "media")),
    )
    sin_tarea = evaluate_fairness(
        h, batch_seq=0, config=FairnessConfig(min_records=200),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
    )
    assert [m.model_dump() for m in res.measurements] == [m.model_dump() for m in sin_tarea.measurements]
    tabla = res.details["fairness"]["por_clase"]
    assert list(tabla) == CLASES
    celda = tabla["alta"]
    assert {"unpriv", "priv", "razon"} == set(celda)
    assert celda["unpriv"]["n"] + celda["priv"]["n"] == 200  # ventana de los últimos 200
    assert celda["razon"] is not None
    assert "fairness" not in sin_tarea.details


def test_equidad_sin_conjunto_favorable_da_exactitud_y_f1_por_grupo_y_estado_sin_datos():
    h = historia(canonico(600, seed=11, favorables=None))
    res = evaluate_fairness(
        h, batch_seq=0, config=FairnessConfig(), thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
        task=tarea(favorables=None),
    )
    por_clave = {(m.metric_key, m.group_code): m for m in res.measurements}
    motivo = "sin conjunto favorable: solo calidad por grupo"
    for clave in ("statistical_parity_difference", "disparate_impact", "false_negative_rate_difference"):
        m = por_clave[(clave, None)]
        assert m.value is None and m.state == State.sin_datos and m.motivo == motivo
    for grupo in ("unpriv", "priv"):
        assert por_clave[("accuracy", grupo)].value is not None
        assert por_clave[("f1_measure", grupo)].state == State.ok
        assert por_clave[("n", grupo)].value > 0
        assert por_clave[("accuracy", grupo)].threshold_low is None
    a, b = por_clave[("accuracy", "unpriv")].value, por_clave[("accuracy", "priv")].value
    assert abs(por_clave[("accuracy_difference", None)].value - (a - b)) < 1e-12
    assert abs(por_clave[("accuracy_ratio", None)].value - a / b) < 1e-12
    assert res.worst_state == State.sin_datos


def test_evaluate_batch_multiclase_de_punta_a_punta():
    t = tarea()
    h = History()
    m = mapeo()
    h.add_batch(canonico(600, seed=20), mapping=m, model_version="v1")
    h.freeze_baseline(0, "v1")
    h.add_batch(canonico(600, seed=21, batch=1, seq_start=600), mapping=m, model_version="v1")
    res = evaluate_batch(h, 1, MonitorSettings.defaults(), task=t)
    assert set(res) == {"fairness", "quality", "drift"}
    q = {(x.metric_key, x.group_code): x for x in res["quality"].measurements}
    assert q[("accuracy", None)].state == State.sin_datos  # umbral pendiente
    assert ("precision", "clase:alta") in q
    assert res["quality"].details["confusion_matrix"]["classes"] == CLASES
    assert res["drift"].details["prediction"]["metodo"] == "jensen_shannon"
    assert "por_clase" in res["fairness"].details["fairness"]


def test_evaluate_batch_sin_conjunto_favorable_no_inventa_tasa_de_etiqueta_cero():
    t = tarea(favorables=None)
    h = History()
    m = mapeo(favorables=None)
    h.add_batch(canonico(400, seed=22, favorables=None), mapping=m, model_version="v1")
    h.freeze_baseline(0, "v1")
    h.add_batch(canonico(400, seed=23, favorables=None, batch=1, seq_start=400), mapping=m, model_version="v1")
    res = evaluate_batch(h, 1, MonitorSettings.defaults(), task=t)
    q = {x.metric_key: x for x in res["quality"].measurements if x.group_code is None}
    assert q["label_skew"].value is None
    assert q["label_skew"].motivo == "sin conjunto favorable: solo calidad por grupo"
    assert res["fairness"].worst_state == State.sin_datos


def test_evaluate_batch_con_tarea_binaria_da_lo_mismo_que_sin_tarea(
    baseline_canonico, evento_canonico
):
    """`TaskSpec.binario()` no mueve nada (los 31 números de aceptación del motor)."""
    from vigia.core.schema import HARNESS_FEEDBACK_MAPPING, TaskSpec

    h = History()
    h.add_batch(baseline_canonico, mapping=HARNESS_FEEDBACK_MAPPING, model_version="v1")
    h.freeze_baseline(0, "v1")
    h.add_batch(evento_canonico, mapping=HARNESS_FEEDBACK_MAPPING, model_version="v1")
    a = evaluate_batch(h, 1, MonitorSettings.defaults())
    b = evaluate_batch(h, 1, MonitorSettings.defaults(), task=TaskSpec.binario())
    assert {k: v.to_dict() for k, v in a.items()} == {k: v.to_dict() for k, v in b.items()}


def test_equidad_sin_conjunto_favorable_recorre_todas_las_medidas_de_pertenencia():
    """Las 19 medidas de predicción y etiqueta dan `sin_datos` con el motivo
    y valor nulo, nunca un 0."""
    from vigia.core.fairness import _METRICAS_ETIQUETA, _METRICAS_PREDICCION

    h = historia(canonico(400, seed=31, favorables=None))
    res = evaluate_fairness(
        h, batch_seq=0, config=FairnessConfig(), thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
        task=tarea(favorables=None),
    )
    motivo = "sin conjunto favorable: solo calidad por grupo"
    claves = (*_METRICAS_PREDICCION, *_METRICAS_ETIQUETA)
    assert len(claves) == 19
    for clave in claves:
        ms = [m for m in res.measurements if m.metric_key == clave]
        assert ms, clave
        for m in ms:
            assert m.value is None and m.state == State.sin_datos and m.motivo == motivo, clave


def test_motor_con_cinco_clases_y_una_ausente_en_la_ventana():
    """k = 5 con una clase que no aparece: la medida de esa clase es `sin_datos`."""
    from vigia.core.quality import evaluate_quality
    from vigia.core.schema import QualityConfig
    from vigia.core.thresholds import DEFAULT_QUALITY_THRESHOLDS

    clases = ["a", "b", "c", "d", "e"]
    df = canonico(500, seed=32, clases=clases, pesos=[1, 1, 1, 1, 0.0], favorables=("a",))
    t = tarea(clases)
    res = evaluate_quality(
        historia(df), batch_seq=0, config=QualityConfig(),
        thresholds=DEFAULT_QUALITY_THRESHOLDS, task=t,
    )
    e = [m for m in res.measurements if m.group_code == "clase:e" and m.metric_key == "recall"]
    assert e and all(m.value is None and m.state == State.sin_datos for m in e)
    d = next(m for m in res.measurements if m.group_code == "clase:d" and m.metric_key == "recall")
    assert d.value is not None
    assert res.details["confusion_matrix"]["classes"] == clases


def test_sin_columnas_de_clase_hay_datos_no_validos_y_no_un_key_error():
    """Un frame sin `prediction_class` o `label_class` da 422, no 500."""
    import pytest

    from vigia.core.quality import evaluate_quality
    from vigia.core.schema import COL_LABEL_CLASS, DatosNoValidos, QualityConfig
    from vigia.core.thresholds import DEFAULT_QUALITY_THRESHOLDS

    base = canonico(300, seed=33)
    cur = canonico(300, seed=34, batch=1, seq_start=300)
    sin_pred = lambda d: d.drop(columns=[COL_PREDICTION_CLASS])
    with pytest.raises(DatosNoValidos, match="columna de clase"):
        evaluate_drift(
            sin_pred(base), cur, config=DriftConfig(), thresholds=DEFAULT_DRIFT_THRESHOLDS,
            feature_cols=["edad"], task=tarea(),
        )
    with pytest.raises(DatosNoValidos, match="columna de clase"):
        evaluate_fairness(
            historia(sin_pred(base)), batch_seq=0, config=FairnessConfig(),
            thresholds=DEFAULT_FAIRNESS_THRESHOLDS, task=tarea(favorables=("alta",)),
        )
    with pytest.raises(DatosNoValidos, match="columna de clase"):
        evaluate_quality(
            historia(base.drop(columns=[COL_LABEL_CLASS])), batch_seq=0,
            config=QualityConfig(), thresholds=DEFAULT_QUALITY_THRESHOLDS, task=tarea(),
        )
