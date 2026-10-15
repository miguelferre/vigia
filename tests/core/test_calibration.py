"""Tests de vigia.core.calibration.proponer_umbrales: al
menos el 99% de los lotes estables de una población sintética quedan del
lado bueno del umbral propuesto, y un efecto de logit 1,5 se detecta.
Poblaciones sintéticas generadas aquí mismo, sin ficheros fuera del repo.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from vigia.core.calibration import PropuestaUmbral, proponer_umbrales
from vigia.core.fairness import fairness_metrics
from vigia.core.schema import (
    COL_BATCH,
    COL_CLINICIAN,
    COL_GROUP,
    COL_ID,
    COL_LABEL,
    COL_PREDICTION,
    COL_PROB,
    COL_PROTECTED,
    COL_SEQ,
    COL_SUBGROUP,
    COL_TS,
    COL_VERSION,
    FairnessConfig,
    MonitorType,
    ThresholdKind,
)


def _poblacion(n: int, seed: int, *, sesgo_logit: float = 0.0, tasa_base: float = 0.5) -> pd.DataFrame:
    """Réplica mínima de la población de `test_fairness_lote.py` (no se
    importa entre módulos de test: `tests/` no es un paquete regular)."""
    rng = np.random.default_rng(seed)
    grupo = rng.integers(0, 2, size=n)
    logit_base = math.log(tasa_base / (1 - tasa_base))
    logit = logit_base + sesgo_logit * (grupo - 0.5)
    prob = 1.0 / (1.0 + np.exp(-logit))
    prediccion = (rng.random(n) < prob).astype(int)
    ruido = rng.random(n) < 0.10
    etiqueta = np.where(ruido, 1 - prediccion, prediccion).astype(float)
    return pd.DataFrame(
        {
            COL_SEQ: range(n),
            COL_BATCH: 0,
            COL_VERSION: "v1",
            COL_ID: [f"id{i}" for i in range(n)],
            COL_TS: None,
            COL_PREDICTION: prediccion,
            COL_PROB: prob,
            COL_LABEL: etiqueta,
            COL_PROTECTED: grupo,
            COL_GROUP: grupo,
            COL_CLINICIAN: None,
            COL_SUBGROUP: None,
        }
    )


def _lado_bueno(valor: float, kind: ThresholdKind, umbral: float) -> bool:
    if kind == ThresholdKind.lower_limit:
        return valor >= umbral
    return valor <= umbral


def test_proponer_umbrales_monitor_no_calibrable():
    baseline = _poblacion(100, seed=0)
    with pytest.raises(ValueError):
        proponer_umbrales(baseline, MonitorType.drift)


def test_proponer_umbrales_baseline_vacia():
    baseline = _poblacion(0, seed=0)
    propuestas = proponer_umbrales(baseline, MonitorType.fairness)
    assert propuestas
    assert all(p.value is None and p.motivo for p in propuestas)


def test_proponer_umbrales_fairness_cobertura_99():
    baseline = _poblacion(20_000, seed=100, sesgo_logit=0.0)
    propuestas = proponer_umbrales(
        baseline,
        MonitorType.fairness,
        tamano_lote=1000,
        n_remuestreos=200,
        cobertura=0.99,
        semilla=1,
        fairness_config=FairnessConfig(),
    )
    assert all(isinstance(p, PropuestaUmbral) for p in propuestas)
    con_valor = {p.metric_key: p for p in propuestas if p.value is not None}
    assert con_valor, "ninguna métrica se pudo calibrar"

    # 500 lotes estables de validación, de una tirada de semillas distinta
    # de la que usa `proponer_umbrales` por dentro (remuestreo propio, no el
    # de la calibración): al menos el 99% del lado bueno.
    rng = np.random.default_rng(999)
    n_validacion = 500
    aciertos: dict[str, int] = {k: 0 for k in con_valor}
    total: dict[str, int] = {k: 0 for k in con_valor}
    for _ in range(n_validacion):
        idx = rng.integers(0, len(baseline), size=1000)
        lote = baseline.iloc[idx]
        m = fairness_metrics(lote, min_group=FairnessConfig().min_group)
        for clave, propuesta in con_valor.items():
            valor = m.get(clave)
            if valor is None:
                continue
            total[clave] += 1
            if _lado_bueno(float(valor), propuesta.kind, propuesta.value):
                aciertos[clave] += 1

    for clave in con_valor:
        assert total[clave] > 0, clave
        cobertura_medida = aciertos[clave] / total[clave]
        assert cobertura_medida >= 0.99, f"{clave}: {cobertura_medida:.3f}"


def test_proponer_umbrales_fairness_efecto_logit_1_5_detectado():
    baseline = _poblacion(20_000, seed=200, sesgo_logit=0.0)
    propuestas = proponer_umbrales(
        baseline,
        MonitorType.fairness,
        tamano_lote=1000,
        n_remuestreos=150,
        cobertura=0.99,
        semilla=2,
        fairness_config=FairnessConfig(),
    )
    con_valor = {p.metric_key: p for p in propuestas if p.value is not None}
    assert con_valor

    detectado_en_alguna_semilla = False
    for seed in range(5):
        lote_con_efecto = _poblacion(1000, seed=1000 + seed, sesgo_logit=1.5)
        m = fairness_metrics(lote_con_efecto, min_group=FairnessConfig().min_group)
        for clave, propuesta in con_valor.items():
            valor = m.get(clave)
            if valor is None:
                continue
            if not _lado_bueno(float(valor), propuesta.kind, propuesta.value):
                detectado_en_alguna_semilla = True
    assert detectado_en_alguna_semilla


def test_proponer_umbrales_quality_valor_linea_base():
    baseline = _poblacion(2000, seed=300, sesgo_logit=0.0)
    propuestas = proponer_umbrales(
        baseline,
        MonitorType.quality,
        tamano_lote=500,
        n_remuestreos=50,
        semilla=3,
    )
    assert propuestas
    con_valor = [p for p in propuestas if p.value is not None]
    assert con_valor
    assert any(p.valor_linea_base is not None for p in con_valor)


def test_proponer_umbrales_quality_sin_etiquetas_motivo():
    baseline = _poblacion(500, seed=400)
    baseline[COL_LABEL] = float("nan")
    propuestas = proponer_umbrales(baseline, MonitorType.quality, n_remuestreos=20)
    assert propuestas
    assert all(p.value is None and p.motivo for p in propuestas)


def test_proponer_umbrales_quality_sin_probabilidad_propone_lo_que_no_la_usa():
    """Con la probabilidad toda nula (alta sin mapear probabilidad),
    la calidad no sale vacía: las métricas de matriz de confusión se
    proponen y las que usan la probabilidad traen el motivo."""
    baseline = _poblacion(2000, seed=500)
    baseline[COL_PROB] = float("nan")
    propuestas = {
        p.metric_key: p
        for p in proponer_umbrales(
            baseline, MonitorType.quality, tamano_lote=500, n_remuestreos=50, semilla=5
        )
        if p.metric_key != "label_skew"
    }
    con_prob = {"area_under_roc", "area_under_pr", "log_loss", "gini_coefficient", "brier_score"}
    for clave in con_prob & propuestas.keys():
        assert propuestas[clave].value is None
        assert "probabilidad" in (propuestas[clave].motivo or "")
    sin_prob = [p for k, p in propuestas.items() if k not in con_prob]
    assert sin_prob
    for p in sin_prob:
        assert p.value is not None and p.valor_linea_base is not None, p.metric_key
    assert propuestas["accuracy"].value is not None


def test_acotar_tasas_de_calidad_al_rango_alcanzable():
    """Un umbral de tasa por encima de 1 no vigilaría nada: se acota."""
    from vigia.core.calibration import _acotar

    assert _acotar("false_positive_rate", 1.1156, MonitorType.quality) == 1.0
    assert _acotar("accuracy", -0.1, MonitorType.quality) == 0.0
    assert _acotar("matthews_correlation_coefficient", -1.3, MonitorType.quality) == -1.0
    assert _acotar("log_loss", 3.0, MonitorType.quality) == 3.0
    assert _acotar("false_positive_rate", 1.2, MonitorType.fairness) == 1.2


def test_proponer_umbrales_quality_acotadas_al_rango():
    baseline = _poblacion(2000, seed=510)
    propuestas = proponer_umbrales(
        baseline, MonitorType.quality, tamano_lote=200, n_remuestreos=50, semilla=6
    )
    for p in propuestas:
        if p.value is not None and p.metric_key in {"false_positive_rate", "accuracy", "precision"}:
            assert 0.0 <= p.value <= 1.0, p.metric_key


def test_proponer_umbrales_quality_probabilidad_parcialmente_nula():
    """Unas pocas filas con probabilidad nula tampoco vacían la calidad."""
    baseline = _poblacion(2000, seed=520)
    baseline.loc[baseline.index[:20], COL_PROB] = float("nan")
    propuestas = proponer_umbrales(
        baseline, MonitorType.quality, tamano_lote=500, n_remuestreos=50, semilla=7
    )
    por_clave = {p.metric_key: p for p in propuestas}
    assert por_clave["accuracy"].value is not None
    assert por_clave["area_under_roc"].value is None
    assert "probabilidad" in (por_clave["area_under_roc"].motivo or "")
