"""Explicabilidad de regresión."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from vigia.core.explain import (
    evaluate_explain,
    global_permutation,
    global_shap,
    local_lime,
    shap_available,
)
from vigia.core.schema import MonitorThresholds, TaskSpec

from ._datos_regresion import tarea


def _datos(n=400, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n)})
    y = 3 * X["a"] + 0.1 * X["b"] + rng.normal(0, 0.1, n)
    return X, y.to_numpy()


def _vector(X: pd.DataFrame) -> np.ndarray:
    return (3 * X["a"] + 0.1 * X["b"]).to_numpy()


def _columna(X: pd.DataFrame) -> np.ndarray:
    return _vector(X).reshape(-1, 1)


# --------------------------------------------------------------------------
# Permutación
# --------------------------------------------------------------------------


@pytest.mark.parametrize("predict_fn", [_vector, _columna], ids=["n", "n_por_1"])
def test_permutacion_con_y_ordena_por_aumento_del_rmse_y_a_va_primero(predict_fn):
    X, y = _datos()
    r = global_permutation(predict_fn, X, y=y, task=tarea(), seed=1)
    assert r.available and r.params["scoring"] == "rmse_increase"
    assert [f.feature for f in r.features] == ["a", "b"]
    # `a` pesa mucho (3 unidades por desviación) y `b` casi nada; el aumento del RMSE
    # es del orden del efecto de la variable, en la unidad de la salida
    assert r.features[0].importance > 2.0
    assert abs(r.features[1].importance) < 0.2
    assert r.clase_explicada is None


def test_la_permutacion_con_y_continua_no_trunca_la_etiqueta_a_entero():
    # un valor real entre 0 y 1 se truncaría a 0 con `.astype(int)`: ningún valor distinto
    X, _ = _datos()

    def pequeno(Z):
        return 0.5 + _vector(Z) / 60

    y = pequeno(X)
    assert y.min() > 0 and y.max() < 1
    r = global_permutation(pequeno, X, y=y, task=tarea(), seed=1)
    assert r.params["scoring"] == "rmse_increase"
    assert r.features[0].feature == "a" and r.features[0].importance > 0.02


def test_sin_y_la_sensibilidad_media_y_a_va_primero():
    X, _ = _datos()
    r = global_permutation(_vector, X, task=tarea(), seed=1)
    assert r.params["scoring"] == "sensibilidad_media"
    assert [f.feature for f in r.features] == ["a", "b"]


def test_con_y_constante_cae_a_la_sensibilidad_media():
    X, _ = _datos()
    r = global_permutation(_vector, X, y=np.full(len(X), 5.0), task=tarea(), seed=1)
    assert r.params["scoring"] == "sensibilidad_media"


def test_es_determinista_con_la_semilla():
    X, y = _datos()
    a = global_permutation(_vector, X, y=y, task=tarea(), seed=3)
    b = global_permutation(_vector, X, y=y, task=tarea(), seed=3)
    assert [(f.feature, f.importance) for f in a.features] == [
        (f.feature, f.importance) for f in b.features
    ]


def test_una_salida_con_mas_de_una_columna_no_se_indexa_en_silencio():
    X, y = _datos()

    def dos_columnas(Z):
        return np.c_[_vector(Z), _vector(Z)]

    with pytest.raises(ValueError, match="único valor"):
        global_permutation(dos_columnas, X, y=y, task=tarea())


# --------------------------------------------------------------------------
# LIME y SHAP
# --------------------------------------------------------------------------


def test_lime_en_regresion_devuelve_el_valor_predicho_y_no_probabilidades():
    pytest.importorskip("lime")
    X, _ = _datos()
    fila = X.iloc[7]
    r = local_lime(_vector, X, fila, task=tarea(), seed=0, row_seq=7)
    assert r.available and r.kind == "local_lime" and r.row_seq == 7
    assert r.prediction_value == pytest.approx(3 * fila["a"] + 0.1 * fila["b"], abs=1e-9)
    assert r.prob_favorable is None and r.probabilities is None and r.clase_explicada is None
    assert r.features[0].feature == "a"
    # las contribuciones de LIME están en la unidad de la salida: `a` pesa mucho más que `b`
    pesos = {f.feature: abs(f.importance) for f in r.features}
    assert pesos["a"] > 5 * pesos["b"]
    d = r.to_dict()
    assert "prediction_value" in d and "probabilities" not in d and "clase_explicada" not in d


def test_lime_en_regresion_con_una_variable_categorica():
    pytest.importorskip("lime")
    rng = np.random.default_rng(0)
    n = 300
    X = pd.DataFrame(
        {"a": rng.normal(size=n), "c": rng.choice(["u", "v"], n)}
    )
    peso = {"u": 0.0, "v": 5.0}

    def predict(Z):
        return (2 * Z["a"] + Z["c"].map(peso)).to_numpy(dtype=float)

    r = local_lime(predict, X, X.iloc[3], categorical_cols=["c"], task=tarea(), seed=0)
    assert r.prediction_value == pytest.approx(float(predict(X.iloc[[3]])[0]))
    assert {f.feature for f in r.features} == {"a", "c"}


def test_clase_en_una_explicacion_de_regresion_da_error():
    X, y = _datos()
    with pytest.raises(ValueError, match="no tiene clase"):
        global_permutation(_vector, X, y=y, task=tarea(), clase="alta")
    with pytest.raises(ValueError, match="no tiene clase"):
        local_lime(_vector, X, X.iloc[0], task=tarea(), clase="alta")
    with pytest.raises(ValueError, match="no tiene clase"):
        global_shap(_vector, X, X.iloc[:5], task=tarea(), clase="alta")


@pytest.mark.skipif(not shap_available()[0], reason="shap no disponible en este equipo")
@pytest.mark.parametrize("predict_fn", [_vector, _columna], ids=["n", "n_por_1"])
def test_shap_con_salida_de_una_columna(predict_fn):
    X, _ = _datos(200)
    r = global_shap(predict_fn, X, X.iloc[:20], task=tarea(), nsamples=60, seed=0)
    assert r.available
    assert [f.feature for f in r.features] == ["a", "b"]
    assert r.features[0].importance > 10 * r.features[1].importance


def test_evaluate_explain_y_el_ndcg_no_cambian_con_regresion():
    X, y = _datos()
    ref = global_permutation(_vector, X, y=y, task=tarea(), seed=1)
    actual = global_permutation(_vector, X, y=y, task=tarea(), seed=2)
    r = evaluate_explain(actual, ref, thresholds=MonitorThresholds(), model_version="v1", batch_seq=1)
    assert r.measurements[0].metric_key == "explain_stability_ndcg"
    assert r.measurements[0].value == pytest.approx(1.0, abs=1e-6)


def test_sin_tarea_o_binaria_la_permutacion_sigue_siendo_la_de_siempre():
    X, _ = _datos()

    def prob(Z):
        p = 1 / (1 + np.exp(-_vector(Z)))
        return np.c_[1 - p, p]

    y = (_vector(X) > 0).astype(float)
    r = global_permutation(prob, X, y=y, seed=1)
    assert r.params["scoring"] == "auroc_drop"
    r2 = global_permutation(prob, X, y=y, task=TaskSpec.binario(), seed=1)
    assert [(f.feature, f.importance) for f in r.features] == [
        (f.feature, f.importance) for f in r2.features
    ]
