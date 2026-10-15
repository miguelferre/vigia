"""Umbral de AUC-PR relativo a la prevalencia y
umbrales desde la línea base en multiclase."""
from __future__ import annotations

import numpy as np
import pandas as pd

from vigia.core.calibration import monitor_de_umbral, umbrales_linea_base_multiclase
from vigia.core.quality import evaluate_quality, resolver_umbral_relativo
from vigia.core.schema import (
    COL_BATCH,
    COL_LABEL,
    COL_PREDICTION,
    COL_PROB,
    COL_SEQ,
    COL_VERSION,
    MonitorType,
    QualityConfig,
    State,
)
from vigia.core.thresholds import DEFAULT_QUALITY_THRESHOLDS

from ._datos_multiclase import CLASES, canonico, historia, tarea


def _binario(n: int, prevalencia: float, seed: int, batch: int = 0, seq_start: int = 0):
    """Modelo binario discreto con prevalencia baja: AUC-PR modesto."""
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < prevalencia).astype(float)
    p = np.clip(0.18 + 0.30 * y + rng.normal(0, 0.18, n), 0.01, 0.99)
    return pd.DataFrame(
        {
            COL_SEQ: range(seq_start, seq_start + n),
            COL_BATCH: batch,
            COL_VERSION: "v1",
            COL_PREDICTION: (p >= 0.5).astype(int),
            COL_PROB: p,
            COL_LABEL: y,
        }
    )


def test_umbral_de_fabrica_de_auc_pr_es_relativo_a_la_prevalencia():
    umbral = next(t for t in DEFAULT_QUALITY_THRESHOLDS.thresholds if t.metric_key == "area_under_pr")
    assert umbral.relativo_a == "prevalencia" and umbral.value == 0.80


def test_seis_por_ciento_de_positivos_sin_alerta_desde_la_linea_base():
    """El AUC-PR de un modelo útil con un 6 % de positivos ronda 0,1 a 0,3:
    con el umbral absoluto de 0,70 alertaba en el primer lote."""
    base = _binario(4000, 0.06, seed=1)
    lote = _binario(4000, 0.06, seed=2, batch=1, seq_start=4000)
    h = pd.concat([base, lote], ignore_index=True)
    res = evaluate_quality(
        h, batch_seq=1, config=QualityConfig(), thresholds=DEFAULT_QUALITY_THRESHOLDS, baseline=base
    )
    pr = next(m for m in res.measurements if m.metric_key == "area_under_pr")
    assert pr.value < 0.70  # el umbral viejo habría saltado
    assert pr.state in (State.ok, State.aviso), (pr.value, pr.threshold_low, pr.state)
    extra = pr.extra["umbral_relativo"]
    assert abs(extra["prevalencia"] - base[COL_LABEL].mean()) < 1e-12
    esperado = extra["prevalencia"] + 0.8 * (extra["auc_pr_linea_base"] - extra["prevalencia"])
    assert abs(pr.threshold_low - esperado) < 1e-12
    assert 0.0 < pr.threshold_low < 0.70


def test_sin_linea_base_area_under_pr_es_sin_datos_con_motivo():
    lote = _binario(500, 0.3, seed=3)
    res = evaluate_quality(
        lote, batch_seq=0, config=QualityConfig(), thresholds=DEFAULT_QUALITY_THRESHOLDS
    )
    pr = next(m for m in res.measurements if m.metric_key == "area_under_pr")
    assert pr.state == State.sin_datos and pr.value is None
    assert "pendiente de la línea base" in pr.motivo
    assert pr.extra["valor_calculado"] is not None
    # el resto de métricas se evalúa
    acc = next(m for m in res.measurements if m.metric_key == "accuracy")
    assert acc.state != State.sin_datos


def test_una_caida_real_del_auc_pr_si_alerta():
    base = _binario(3000, 0.2, seed=4)
    peor = _binario(3000, 0.2, seed=5, batch=1, seq_start=3000)
    peor[COL_PROB] = np.clip(peor[COL_PROB].to_numpy() * 0 + 0.3 + np.random.default_rng(1).normal(0, 0.2, 3000), 0.01, 0.99)
    h = pd.concat([base, peor], ignore_index=True)
    res = evaluate_quality(
        h, batch_seq=1, config=QualityConfig(), thresholds=DEFAULT_QUALITY_THRESHOLDS, baseline=base
    )
    pr = next(m for m in res.measurements if m.metric_key == "area_under_pr")
    assert pr.state == State.alerta


def test_resolver_umbral_relativo_sin_dos_resultados_dice_por_que():
    umbral = next(t for t in DEFAULT_QUALITY_THRESHOLDS.thresholds if t.metric_key == "area_under_pr")
    una_clase = _binario(300, 0.0, seed=6)
    valor, extra, motivo = resolver_umbral_relativo(umbral, una_clase)
    assert valor is None and extra is None and "pendiente de la línea base" in motivo


def test_umbrales_linea_base_multiclase_incluyen_titulares_y_deriva_de_prediccion():
    base = canonico(1200, seed=11)
    umbrales = umbrales_linea_base_multiclase(base, tarea(), semilla=0, n_remuestreos=60)
    claves = {t.metric_key: t for t in umbrales}
    assert set(claves) == {"accuracy", "f1_measure", "area_under_roc", "prediction_drift_score"}
    assert all(t.origen == "linea_base" for t in umbrales)
    assert claves["accuracy"].value >= 1 / 3  # suelo de 1/k
    assert claves["accuracy"].kind.value == "lower_limit"
    assert claves["prediction_drift_score"].kind.value == "upper_limit"
    assert claves["prediction_drift_score"].value > 0
    assert monitor_de_umbral("accuracy") == MonitorType.quality
    assert monitor_de_umbral("prediction_drift_score") == MonitorType.drift
    # una línea base sana no alerta con sus propios umbrales
    from vigia.core.quality import evaluate_quality as eq
    from vigia.core.schema import MonitorThresholds

    q = MonitorThresholds(thresholds=[t for t in umbrales if monitor_de_umbral(t.metric_key) == MonitorType.quality])
    lote = canonico(1000, seed=12, batch=1, seq_start=1200)
    res = eq(historia(base, lote), batch_seq=1, config=QualityConfig(), thresholds=q, task=tarea())
    for clave in ("accuracy", "f1_measure", "area_under_roc"):
        m = next(x for x in res.measurements if x.metric_key == clave and x.group_code is None)
        assert m.state in (State.ok, State.aviso), (clave, m.value, m.threshold_low)


def test_el_suelo_de_exactitud_es_uno_sobre_k(monkeypatch):
    """El suelo actúa: si el percentil de remuestreo cae por debajo de 1/k, el
    umbral sube a 1/k. Se fuerza un percentil bajo para probarlo."""
    import vigia.core.calibration as cal

    base = canonico(900, seed=13, fuerza=0.05)
    real = cal.np.percentile
    monkeypatch.setattr(
        cal.np, "percentile", lambda a, q, *args, **kw: real(a, q, *args, **kw) * 0.2
    )
    u = umbrales_linea_base_multiclase(base, tarea(), semilla=0, n_remuestreos=40)
    acc = next(t for t in u if t.metric_key == "accuracy")
    assert abs(acc.value - 1 / len(CLASES)) < 1e-5


def test_el_umbral_de_deriva_de_prediccion_crece_con_lotes_pequenos():
    """El backend pasa el tamaño de lote real; con lotes más pequeños el
    ruido de Jensen-Shannon es mayor y el umbral no puede quedarse en el de 1000."""
    base = canonico(2000, seed=21)
    grande = umbrales_linea_base_multiclase(base, tarea(), semilla=0, n_remuestreos=80, tamano_lote=1000)
    pequeno = umbrales_linea_base_multiclase(base, tarea(), semilla=0, n_remuestreos=80, tamano_lote=200)
    g = next(t for t in grande if t.metric_key == "prediction_drift_score").value
    c = next(t for t in pequeno if t.metric_key == "prediction_drift_score").value
    assert c > g
