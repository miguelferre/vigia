"""En pequeño, sin modelos públicos: mismo marco para LIME en
las dos rutas (entradas enteras), SHAP Kernel con semilla propia y tipos del
pickle tomados del modelo."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from vigia.app.services import model_registry
from vigia.core import explain as core_explain
from vigia.core.predict_onnx import ModeloEjecutableInvalido, cast_frame_to_kinds


def _pipeline_con_id_como_texto() -> tuple[Pipeline, pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(3)
    n = 120
    X = pd.DataFrame(
        {
            "edad": rng.integers(20, 80, n),
            "tipo_id": rng.choice(["1", "2", "3"], n),
            "peso": rng.normal(70, 10, n),
        }
    )
    y = ((X["edad"] > 50) ^ (X["tipo_id"] == "2")).astype(int).to_numpy()
    pre = ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), ["tipo_id"])], remainder="passthrough"
    )
    pipe = Pipeline([("pre", pre), ("rf", RandomForestClassifier(n_estimators=10, random_state=0))])
    pipe.fit(X, y)
    return pipe, X, y


def test_cast_redondea_las_entradas_enteras_y_deja_las_continuas():
    entradas = [
        {"name": "a", "type": "tensor(int64)", "kind": "numerica"},
        {"name": "b", "type": "float", "kind": "numerica"},
        {"name": "c", "type": "int", "kind": "numerica"},
    ]
    df = pd.DataFrame({"a": [23.97, 40.2], "b": [23.97, 40.2], "c": [1.6, 2.4]})
    fuera = cast_frame_to_kinds(df, entradas)
    assert fuera["a"].tolist() == [24.0, 40.0]
    assert fuera["b"].tolist() == [23.97, 40.2]
    assert fuera["c"].tolist() == [2.0, 2.0]


def test_pickle_toma_del_modelo_que_una_columna_entera_es_texto():
    pipe, _x, _ = _pipeline_con_id_como_texto()
    fila = pd.Series({"edad": 30, "tipo_id": 2, "peso": 71.5})  # el id llega como entero
    entradas = model_registry._inputs_pickle(["edad", "tipo_id", "peso"], fila, pipe)
    kinds = {e["name"]: e["kind"] for e in entradas}
    assert kinds == {"edad": "numerica", "tipo_id": "categorica", "peso": "numerica"}
    predict_fn = model_registry._predict_fn_sklearn(pipe, entradas)
    probs = predict_fn(pd.DataFrame([fila])[["edad", "tipo_id", "peso"]])
    assert probs.shape == (1, 2)


def test_error_de_prediccion_no_ensena_nombres_de_excepcion():
    class Roto:
        def predict_proba(self, _x):
            raise TypeError("boom interno")

    predict_fn = model_registry._predict_fn_sklearn(
        Roto(), [{"name": "a", "type": "float", "kind": "numerica"}]
    )
    with pytest.raises(ModeloEjecutableInvalido) as exc:
        predict_fn(pd.DataFrame({"a": [1.0]}))
    assert "TypeError" not in str(exc.value)
    assert "boom" not in str(exc.value)


def test_lime_entero_igual_con_dos_predictores_que_difieren_en_la_parte_decimal():
    """Con entradas enteras, un valor muestreado 23.97 y uno 24.0 dan lo mismo:
    el marco que llega al modelo es el redondeado en las dos rutas."""
    pipe, _x, _ = _pipeline_con_id_como_texto()
    entradas = [
        {"name": "edad", "type": "tensor(int64)", "kind": "numerica"},
        {"name": "tipo_id", "type": "tensor(string)", "kind": "categorica"},
        {"name": "peso", "type": "float", "kind": "numerica"},
    ]
    fn = model_registry._predict_fn_sklearn(pipe, entradas)
    a = fn(pd.DataFrame({"edad": [23.97], "tipo_id": ["2"], "peso": [70.0]}))
    b = fn(pd.DataFrame({"edad": [24.0], "tipo_id": ["2"], "peso": [70.0]}))
    assert np.array_equal(a, b)


def test_shap_global_reproducible_sin_semilla_del_llamador():
    """12 columnas: Kernel SHAP muestrea coaliciones (con 3 las enumeraría
    todas y sería determinista aunque faltara la semilla)."""
    pytest.importorskip("shap")
    rng = np.random.default_rng(5)
    cols = [f"x{i}" for i in range(12)]
    X = pd.DataFrame(rng.normal(size=(150, 12)), columns=cols)
    y = ((X["x0"] + X["x1"] * X["x2"] + X["x3"]) > 0).astype(int)
    modelo = RandomForestClassifier(n_estimators=10, random_state=0).fit(X, y)
    entradas = [{"name": c, "type": "float", "kind": "numerica"} for c in cols]
    fn = model_registry._predict_fn_sklearn(modelo, entradas)
    Xe = X.iloc[:6]
    r1 = core_explain.global_shap(fn, X, Xe)
    np.random.random(500)  # mueve el generador global entre las dos llamadas
    r2 = core_explain.global_shap(fn, X, Xe)
    assert [(f.feature, f.importance) for f in r1.features] == [
        (f.feature, f.importance) for f in r2.features
    ]


def test_pickle_columna_continua_con_fila_cero_entera_no_se_redondea():
    pipe, _x, _ = _pipeline_con_id_como_texto()
    fila = pd.Series({"edad": 30, "tipo_id": 2, "peso": 71})  # peso 71 en la fila 0
    entradas = model_registry._inputs_pickle(
        ["edad", "tipo_id", "peso"], fila, pipe, no_enteras={"peso"}
    )
    tipos = {e["name"]: e["type"] for e in entradas}
    assert tipos["peso"] == "float" and "int" in tipos["edad"]
    fuera = cast_frame_to_kinds(pd.DataFrame({"edad": [30.4], "tipo_id": ["2"], "peso": [71.4]}), entradas)
    assert fuera["peso"].tolist() == [71.4] and fuera["edad"].tolist() == [30.0]


def test_shap_global_restaura_el_generador_global_de_numpy():
    pytest.importorskip("shap")
    pipe, X, _ = _pipeline_con_id_como_texto()
    entradas = [
        {"name": "edad", "type": "int", "kind": "numerica"},
        {"name": "tipo_id", "type": "str", "kind": "categorica"},
        {"name": "peso", "type": "float", "kind": "numerica"},
    ]
    fn = model_registry._predict_fn_sklearn(pipe, entradas)
    np.random.seed(77)
    esperado = np.random.random(3)
    np.random.seed(77)
    core_explain.global_shap(fn, X, X.iloc[:4])
    assert np.array_equal(np.random.random(3), esperado)
