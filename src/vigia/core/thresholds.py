"""Umbrales por defecto de cada monitor.

Constantes copiadas de `escenarios/shared/reconfigure.py` del harness de la
demo original (leído, no importado ni ejecutado).
"""
from __future__ import annotations

from vigia.core.schema import (
    DriftConfig,
    FairnessConfig,
    MonitorThresholds,
    MonitorType,
    QualityConfig,
    Threshold,
    ThresholdKind,
)

_LOWER = ThresholdKind.lower_limit
_UPPER = ThresholdKind.upper_limit


DEFAULT_FAIRNESS_THRESHOLDS = MonitorThresholds(
    thresholds=[
        Threshold(metric_key="fairness_value", kind=_LOWER, value=20.0),
        Threshold(metric_key="statistical_parity_difference", kind=_LOWER, value=-0.60),
        Threshold(metric_key="false_positive_rate_difference", kind=_LOWER, value=-0.25),
        Threshold(metric_key="false_negative_rate_difference", kind=_UPPER, value=0.55),
        Threshold(metric_key="error_rate_difference", kind=_UPPER, value=0.20),
        Threshold(metric_key="false_omission_rate_difference", kind=_LOWER, value=-0.20),
        Threshold(metric_key="false_discovery_rate_difference", kind=_UPPER, value=0.40),
        Threshold(metric_key="average_odds_difference", kind=_LOWER, value=-0.40),
        Threshold(metric_key="average_abs_odds_difference", kind=_UPPER, value=0.40),
        Threshold(metric_key="impact_score", kind=_LOWER, value=0.0),
    ]
)


DEFAULT_QUALITY_THRESHOLDS = MonitorThresholds(
    thresholds=[
        Threshold(metric_key="accuracy", kind=_LOWER, value=0.80),
        Threshold(metric_key="area_under_roc", kind=_LOWER, value=0.75),
        # Relativo a la prevalencia. `value` es la fracción de la
        # ventaja sobre el azar que se tolera conservar (0,8): el umbral es
        # `prevalencia + 0,8 x (AUC-PR de la línea base - prevalencia)` y lo
        # resuelve `core.quality` con la línea base congelada de la versión.
        Threshold(
            metric_key="area_under_pr", kind=_LOWER, value=0.80, relativo_a="prevalencia"
        ),
        Threshold(metric_key="true_positive_rate", kind=_LOWER, value=0.70),
        Threshold(metric_key="false_positive_rate", kind=_UPPER, value=0.30),
        Threshold(metric_key="precision", kind=_LOWER, value=0.70),
        Threshold(metric_key="recall", kind=_LOWER, value=0.70),
        Threshold(metric_key="f1_measure", kind=_LOWER, value=0.70),
        Threshold(metric_key="log_loss", kind=_UPPER, value=1.00),
        Threshold(metric_key="label_skew", kind=_LOWER, value=-0.5),
        Threshold(metric_key="label_skew", kind=_UPPER, value=0.5),
        Threshold(metric_key="matthews_correlation_coefficient", kind=_LOWER, value=0.60),
        Threshold(metric_key="gini_coefficient", kind=_LOWER, value=0.60),
        Threshold(metric_key="brier_score", kind=_UPPER, value=0.25),
    ]
)


DEFAULT_DRIFT_THRESHOLDS = MonitorThresholds(
    thresholds=[
        Threshold(metric_key="feature_drift_score", kind=_UPPER, value=0.15),
        Threshold(metric_key="prediction_drift_score", kind=_UPPER, value=0.08),
        Threshold(metric_key="confidence_drift_score", kind=_UPPER, value=0.30),
        Threshold(metric_key="model_quality_score", kind=_UPPER, value=0.10),
        Threshold(metric_key="output_metadata_drift_score", kind=_UPPER, value=0.15),
        Threshold(metric_key="input_metadata_drift_score", kind=_UPPER, value=0.15),
    ]
)


# Estabilidad de la explicación global, nDCG normalizado sobre el
# ranking de importancias frente a la referencia (ver core/explain.py), con
# umbral inferior 0,50.
DEFAULT_EXPLAIN_THRESHOLDS = MonitorThresholds(
    thresholds=[
        Threshold(metric_key="explain_stability_ndcg", kind=_LOWER, value=0.50),
    ]
)


DEFAULT_FAIRNESS_CONFIG = FairnessConfig()
DEFAULT_QUALITY_CONFIG = QualityConfig()
DEFAULT_DRIFT_CONFIG = DriftConfig()


def defaults_for(monitor: MonitorType) -> MonitorThresholds:
    if monitor == MonitorType.fairness:
        return DEFAULT_FAIRNESS_THRESHOLDS
    if monitor == MonitorType.quality:
        return DEFAULT_QUALITY_THRESHOLDS
    if monitor == MonitorType.drift:
        return DEFAULT_DRIFT_THRESHOLDS
    if monitor == MonitorType.explain:
        return DEFAULT_EXPLAIN_THRESHOLDS
    raise ValueError(f"sin umbrales por defecto para el monitor {monitor!r}")


def defaults_regresion(monitor: MonitorType, *, con_rango: bool) -> MonitorThresholds:
    """Umbrales de fábrica de un proyecto de regresión.

    Ningún valor de fábrica está en unidades de la salida: salen de la línea base
    al congelarla (`calibration.umbrales_linea_base_regresion`).

    - `quality`: vacío (los cuatro titulares esperan a la línea base).
    - `fairness`: con rango favorable, los umbrales binarios de hoy sobre la
      pertenencia (sin las claves de error, que salen de la línea base); sin
      rango, vacío.
    - `drift`: solo `feature_drift_score` (0,15), que es un KS sin unidad;
      `prediction_drift_score` espera a la línea base y `confidence_drift_score`
      no existe en regresión.
    - `explain`: los de hoy.

    Devuelve copias: quien llama puede editarlas sin tocar las tablas de fábrica."""
    match monitor:
        case MonitorType.quality:
            return MonitorThresholds()
        case MonitorType.fairness:
            if con_rango:
                return DEFAULT_FAIRNESS_THRESHOLDS.model_copy(deep=True)
            return MonitorThresholds()
        case MonitorType.drift:
            return MonitorThresholds(
                thresholds=[
                    t.model_copy(deep=True)
                    for t in DEFAULT_DRIFT_THRESHOLDS.thresholds
                    if t.metric_key == "feature_drift_score"
                ]
            )
        case MonitorType.explain:
            return DEFAULT_EXPLAIN_THRESHOLDS.model_copy(deep=True)
        case _:
            raise ValueError(f"sin umbrales por defecto para el monitor {monitor!r}")
