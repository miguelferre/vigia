"""Tests de vigia.core.quality contra los números de aceptación de
los resultados esperados de los escenarios 1 y 2 (tolerancia: diferencias
abs < 5e-4, salvo donde se indica).
"""
from __future__ import annotations

import pandas as pd
import pytest
from pydantic import ValidationError

from vigia.core.loaders import concat_history, load_feedback, to_canonical
from vigia.core.quality import evaluate_quality, label_skew, quality_metrics, validar_probabilidad
from vigia.core.schema import (
    COL_BATCH,
    COL_LABEL,
    HARNESS_FEEDBACK_MAPPING,
    DatosNoValidos,
    QualityConfig,
    State,
)
from vigia.core.thresholds import DEFAULT_QUALITY_THRESHOLDS

TOL = 5e-4


@pytest.fixture
def e2_evento_canonico(e2_evento_feedback_path):
    fb = load_feedback(e2_evento_feedback_path)
    return to_canonical(fb, HARNESS_FEEDBACK_MAPPING, batch_seq=1, model_version="v1")


@pytest.fixture
def e2_recovery_canonico(e2_recovery_feedback_path):
    fb = load_feedback(e2_recovery_feedback_path)
    return to_canonical(
        fb, HARNESS_FEEDBACK_MAPPING, batch_seq=2, model_version="v1", seq_start=2000
    )


@pytest.fixture
def e2_historia(e2_evento_canonico, e2_recovery_canonico):
    return concat_history([e2_evento_canonico, e2_recovery_canonico])


def test_quality_metrics_baseline_e1(baseline_canonico):
    r = quality_metrics(baseline_canonico)
    assert abs(r["accuracy"] - 0.880) < TOL
    assert abs(r["precision"] - 0.882) < TOL
    assert abs(r["recall"] - 0.837) < TOL
    assert abs(r["f1_measure"] - 0.859) < TOL
    assert abs(r["area_under_roc"] - 0.853) < TOL
    assert abs(r["brier_score"] - 0.181) < TOL
    assert abs(r["gini_coefficient"] - 0.706) < TOL


def test_quality_metrics_evento_e1(evento_canonico):
    r = quality_metrics(evento_canonico)
    assert abs(r["accuracy"] - 0.860) < TOL


def test_label_skew_con_y_sin_referencia():
    assert label_skew(0.40, 0.30) is not None
    assert abs(label_skew(0.40, 0.30) - 0.10) < 1e-9
    assert label_skew(0.40, None) is None
    assert label_skew(None, 0.30) is None


def test_evaluate_quality_baseline_estados(baseline_canonico):
    res = evaluate_quality(
        baseline_canonico,
        batch_seq=0,
        config=QualityConfig(),
        thresholds=DEFAULT_QUALITY_THRESHOLDS,
        # El umbral de area_under_pr es relativo a la prevalencia y se
        # resuelve con la línea base congelada.
        baseline=baseline_canonico,
    )
    estados = res.states()
    con_umbral = [
        "accuracy",
        "area_under_roc",
        "area_under_pr",
        "true_positive_rate",
        "false_positive_rate",
        "precision",
        "recall",
        "f1_measure",
        "log_loss",
        "matthews_correlation_coefficient",
        "gini_coefficient",
        "brier_score",
    ]
    for clave in con_umbral:
        assert estados[clave] in (State.ok, State.aviso), (clave, estados[clave])
    assert res.window.kind == "batch"
    assert res.window.n == 450


def test_evaluate_quality_acumula_batch_pequeno(baseline_canonico, evento_canonico):
    historia = concat_history([baseline_canonico, evento_canonico])
    # batch pequeno sintetico (60 filas etiquetadas) encadenado tras los dos
    # batches ya presentes en la historia (0 y 1): se le asigna batch_seq=2.
    pequeno = evento_canonico.tail(60).copy()
    pequeno[COL_BATCH] = 2
    historia_con_pequeno = concat_history([historia, pequeno])
    res = evaluate_quality(
        historia_con_pequeno,
        batch_seq=2,
        config=QualityConfig(min_feedback=100),
        thresholds=DEFAULT_QUALITY_THRESHOLDS,
    )
    assert res.window.kind == "acumulado"
    assert set(res.window.batches) == {1, 2}
    assert res.window.n >= 100


def test_evaluate_quality_batch_pequeno_sin_historia():
    df = pd.DataFrame(
        {
            "seq": range(60),
            "batch_seq": [0] * 60,
            "model_version": ["v1"] * 60,
            "prediction": [1, 0] * 30,
            "prob_favorable": [0.6] * 60,
            "label": [1.0, 0.0] * 30,
        }
    )
    res = evaluate_quality(
        df,
        batch_seq=0,
        config=QualityConfig(min_feedback=100),
        thresholds=DEFAULT_QUALITY_THRESHOLDS,
    )
    estados = res.states()
    assert estados["accuracy"] == State.sin_datos
    assert res.window.motivo is not None


def test_evaluate_quality_e2_evento_alerta(e2_historia):
    """Valores recalculados y verificados de forma independiente sobre
    el batch aislado del evento E2 (2000 filas, sin acumular con baseline E1
    porque supera `min_feedback`). Sustituye el xfail anterior."""
    res = evaluate_quality(
        e2_historia,
        batch_seq=1,
        config=QualityConfig(),
        thresholds=DEFAULT_QUALITY_THRESHOLDS,
    )
    valores = {m.metric_key: m for m in res.measurements}
    assert abs(valores["accuracy"].value - 0.7140) < TOL
    assert valores["accuracy"].state == State.alerta
    assert abs(valores["true_positive_rate"].value - 0.6389) < TOL
    assert valores["true_positive_rate"].state == State.alerta
    assert abs(valores["f1_measure"].value - 0.7549) < TOL
    # 0,7549 dentro de la banda de aviso del 10 % sobre el umbral
    # inferior 0,70 (banda [0,70, 0,77)) -> aviso, sin alerta.
    assert valores["f1_measure"].state == State.aviso
    assert abs(valores["precision"].value - 0.9225) < TOL
    assert valores["precision"].state == State.ok
    assert res.states()["accuracy"] == State.alerta


def test_evaluate_quality_e2_recovery_ok(e2_historia):
    """Batch aislado del recovery E2 (3000 filas)."""
    res = evaluate_quality(
        e2_historia,
        batch_seq=2,
        config=QualityConfig(),
        thresholds=DEFAULT_QUALITY_THRESHOLDS,
    )
    valores = {m.metric_key: m for m in res.measurements}
    assert abs(valores["accuracy"].value - 0.9200) < TOL
    assert valores["accuracy"].state == State.ok
    assert abs(valores["true_positive_rate"].value - 0.9056) < TOL
    assert abs(valores["f1_measure"].value - 0.9128) < TOL
    assert abs(valores["precision"].value - 0.9201) < TOL
    assert abs(valores["area_under_roc"].value - 0.879) < TOL
    assert abs(valores["brier_score"].value - 0.1815) < TOL


def test_evaluate_quality_e2_acumulado_evento_recovery(e2_historia):
    """Acumulado evento+recovery (5000 filas), test informativo con
    la misma tolerancia."""
    r = quality_metrics(e2_historia[e2_historia[COL_LABEL].notna()])
    assert abs(r["accuracy"] - 0.8376) < TOL
    assert abs(r["true_positive_rate"] - 0.7726) < TOL
    assert abs(r["f1_measure"] - 0.8403) < TOL


def test_evaluate_quality_batch_sin_filas_no_mezcla_version():
    """Hallazgo 4.1: si `batch_seq` no tiene filas propias en `df_history` y
    no se pasa `model_version`, no se debe caer a la historia completa (que
    podria mezclar versiones sin avisar): todas las medidas quedan
    `sin_datos` con `window.motivo` "batch sin filas"."""
    df = pd.DataFrame(
        {
            "seq": range(10),
            "batch_seq": [0] * 5 + [1] * 5,
            "model_version": ["v1"] * 5 + ["v2"] * 5,
            "prediction": [1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
            "prob_favorable": [0.6] * 10,
            "label": [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        }
    )
    res = evaluate_quality(
        df,
        batch_seq=99,
        config=QualityConfig(min_feedback=8),
        thresholds=DEFAULT_QUALITY_THRESHOLDS,
    )
    estados = res.states()
    assert all(estado == State.sin_datos for estado in estados.values())
    assert res.window.batches == []
    assert res.window.motivo == "batch sin filas"
    assert res.window.model_version is None


def test_evaluate_quality_batch_sin_filas_con_model_version_filtra():
    """Con `model_version` explicito, se filtra por ella en vez de caer a
    `sin_datos`: no es el mismo caso que el hallazgo 4.1."""
    df = pd.DataFrame(
        {
            "seq": range(10),
            "batch_seq": [0] * 10,
            "model_version": ["v1"] * 5 + ["v2"] * 5,
            "prediction": [1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
            "prob_favorable": [0.6] * 10,
            "label": [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        }
    )
    res = evaluate_quality(
        df,
        batch_seq=99,
        config=QualityConfig(min_feedback=5),
        thresholds=DEFAULT_QUALITY_THRESHOLDS,
        model_version="v1",
    )
    assert res.window.n == 5
    assert res.window.model_version == "v1"


def test_min_feedback_menor_que_1_rechazado_por_schema():
    """Hallazgo 4.2: `QualityConfig.min_feedback` no admite valores <= 0."""
    with pytest.raises(ValidationError):
        QualityConfig(min_feedback=0)


def _frame_con_probabilidad(valores_prob):
    n = len(valores_prob)
    return pd.DataFrame(
        {
            "seq": range(n),
            "batch_seq": [0] * n,
            "model_version": ["v1"] * n,
            "prediction": ([1, 0] * (n // 2 + 1))[:n],
            "prob_favorable": valores_prob,
            "label": ([1.0, 0.0] * (n // 2 + 1))[:n],
        }
    )


def test_validar_probabilidad_nulos_lanza_datos_no_validos():
    """Nulos entre las filas con etiqueta lanzan DatosNoValidos con el
    recuento N de M y el nombre generico de columna por defecto."""
    df = _frame_con_probabilidad([0.6, 0.4, float("nan"), 0.5, float("nan")])
    with pytest.raises(DatosNoValidos) as exc_info:
        validar_probabilidad(df)
    mensaje = str(exc_info.value)
    assert "2 de 5 filas nulas o fuera de 0 a 1" in mensaje
    assert "revisa la columna de probabilidad del mapeo" in mensaje


def test_validar_probabilidad_fuera_de_rango_lanza_datos_no_validos():
    df = _frame_con_probabilidad([0.6, 1.5, -0.1, 0.5, 0.2])
    with pytest.raises(DatosNoValidos) as exc_info:
        validar_probabilidad(df)
    assert "2 de 5 filas nulas o fuera de 0 a 1" in str(exc_info.value)


def test_validar_probabilidad_con_columna_original_la_nombra():
    """El motor no conoce el nombre de columna del fichero: quien lo sabe
    lo completa con `columna_original`."""
    df = _frame_con_probabilidad([float("nan"), 0.4, 0.5, 0.6, 0.2])
    with pytest.raises(DatosNoValidos) as exc_info:
        validar_probabilidad(df, columna_original="prob_modelo")
    assert "revisa la columna prob_modelo del mapeo" in str(exc_info.value)


def test_validar_probabilidad_valida_no_lanza():
    df = _frame_con_probabilidad([0.6, 0.4, 0.5, 0.5, 0.2])
    validar_probabilidad(df)  # no debe lanzar


def test_quality_metrics_probabilidad_invalida_lanza_antes_de_calcular():
    """`quality_metrics` valida antes de tocar sklearn (1,5 y nulos)."""
    df = _frame_con_probabilidad([0.6, 1.5, 0.4, 0.5, 0.2])
    with pytest.raises(DatosNoValidos):
        quality_metrics(df)


def test_evaluate_quality_probabilidad_invalida_propaga_datos_no_validos():
    """El camino completo (`evaluate_quality`, el que usa el motor) también
    lanza `DatosNoValidos`, para que la ingesta y la evaluación suelta lo
    capturen."""
    n = 120
    valores = [0.6] * n
    valores[10] = float("nan")
    df = pd.DataFrame(
        {
            "seq": range(n),
            "batch_seq": [0] * n,
            "model_version": ["v1"] * n,
            "prediction": [1, 0] * (n // 2),
            "prob_favorable": valores,
            "label": [1.0, 0.0] * (n // 2),
        }
    )
    with pytest.raises(DatosNoValidos):
        evaluate_quality(
            df,
            batch_seq=0,
            config=QualityConfig(min_feedback=100),
            thresholds=DEFAULT_QUALITY_THRESHOLDS,
        )


def test_evaluate_quality_sin_filas_etiquetadas_no_revienta():
    """Hallazgo 4.2: con `n == 0` la evaluacion degrada a `sin_datos` aunque
    `min_feedback` sea 1 (el minimo admitido), sin lanzar la excepcion de
    sklearn sobre un frame vacio."""
    df = pd.DataFrame(
        {
            "seq": [0, 1],
            "batch_seq": [0, 0],
            "model_version": ["v1", "v1"],
            "prediction": [1, 0],
            "prob_favorable": [0.6, 0.4],
            "label": [float("nan"), float("nan")],
        }
    )
    res = evaluate_quality(
        df,
        batch_seq=0,
        config=QualityConfig(min_feedback=1),
        thresholds=DEFAULT_QUALITY_THRESHOLDS,
    )
    estados = res.states()
    assert estados["accuracy"] == State.sin_datos
    assert res.window.motivo is not None
