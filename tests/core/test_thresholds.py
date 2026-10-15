"""Tests de umbrales por defecto (copia exacta de reconfigure.py del harness de la demo original)."""
from __future__ import annotations

import pytest

from vigia.core.schema import MonitorType
from vigia.core.thresholds import (
    DEFAULT_DRIFT_THRESHOLDS,
    DEFAULT_EXPLAIN_THRESHOLDS,
    DEFAULT_FAIRNESS_CONFIG,
    DEFAULT_FAIRNESS_THRESHOLDS,
    DEFAULT_QUALITY_CONFIG,
    DEFAULT_QUALITY_THRESHOLDS,
    defaults_for,
)


def test_fairness_thresholds_cuenta_y_valores():
    mt = DEFAULT_FAIRNESS_THRESHOLDS
    assert len(mt.thresholds) == 10
    assert mt.limits("fairness_value") == (20.0, None)
    assert mt.limits("statistical_parity_difference") == (-0.60, None)
    assert mt.limits("false_positive_rate_difference") == (-0.25, None)
    assert mt.limits("false_negative_rate_difference") == (None, 0.55)
    assert mt.limits("error_rate_difference") == (None, 0.20)
    assert mt.limits("false_omission_rate_difference") == (-0.20, None)
    assert mt.limits("false_discovery_rate_difference") == (None, 0.40)
    assert mt.limits("average_odds_difference") == (-0.40, None)
    assert mt.limits("average_abs_odds_difference") == (None, 0.40)
    assert mt.limits("impact_score") == (0.0, None)


def test_quality_thresholds_cuenta_y_valores():
    mt = DEFAULT_QUALITY_THRESHOLDS
    assert len(mt.thresholds) == 14
    assert mt.limits("accuracy") == (0.80, None)
    assert mt.limits("area_under_roc") == (0.75, None)
    # El umbral de AUC-PR es relativo a la prevalencia; su `value`
    # es la fracción (0,8) de la ventaja sobre el azar que se tolera conservar,
    # así que `limits` no lo da como límite absoluto: lo resuelve el motor.
    assert mt.limits("area_under_pr") == (None, None)
    pr = next(t for t in mt.thresholds if t.metric_key == "area_under_pr")
    assert pr.relativo_a == "prevalencia" and pr.value == 0.80
    assert [t.metric_key for t in mt.thresholds if t.relativo_a] == ["area_under_pr"]
    assert mt.limits("true_positive_rate") == (0.70, None)
    assert mt.limits("false_positive_rate") == (None, 0.30)
    assert mt.limits("precision") == (0.70, None)
    assert mt.limits("recall") == (0.70, None)
    assert mt.limits("f1_measure") == (0.70, None)
    assert mt.limits("log_loss") == (None, 1.00)
    assert mt.limits("label_skew") == (-0.5, 0.5)
    assert mt.limits("matthews_correlation_coefficient") == (0.60, None)
    assert mt.limits("gini_coefficient") == (0.60, None)
    assert mt.limits("brier_score") == (None, 0.25)


def test_drift_thresholds_cuenta_y_valores():
    mt = DEFAULT_DRIFT_THRESHOLDS
    assert len(mt.thresholds) == 6
    assert mt.limits("feature_drift_score") == (None, 0.15)
    assert mt.limits("prediction_drift_score") == (None, 0.08)
    assert mt.limits("confidence_drift_score") == (None, 0.30)
    assert mt.limits("model_quality_score") == (None, 0.10)
    assert mt.limits("output_metadata_drift_score") == (None, 0.15)
    assert mt.limits("input_metadata_drift_score") == (None, 0.15)


def test_explain_thresholds_cuenta_y_valores():
    mt = DEFAULT_EXPLAIN_THRESHOLDS
    assert len(mt.thresholds) == 1
    assert mt.limits("explain_stability_ndcg") == (0.50, None)


def test_defaults_for():
    assert defaults_for(MonitorType.fairness) is DEFAULT_FAIRNESS_THRESHOLDS
    assert defaults_for(MonitorType.quality) is DEFAULT_QUALITY_THRESHOLDS
    assert defaults_for(MonitorType.drift) is DEFAULT_DRIFT_THRESHOLDS
    assert defaults_for(MonitorType.explain) is DEFAULT_EXPLAIN_THRESHOLDS
    with pytest.raises(ValueError):
        defaults_for(MonitorType.cross)


def test_configs_por_defecto():
    assert DEFAULT_FAIRNESS_CONFIG.min_records == 200
    assert DEFAULT_FAIRNESS_CONFIG.min_group == 20
    assert DEFAULT_QUALITY_CONFIG.min_feedback == 100
