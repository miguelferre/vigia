"""ONNX de un regresor. El modelo se fabrica en el test con
`skl2onnx` y el módulo se salta con motivo si no está."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip(
    "skl2onnx", reason="skl2onnx no está instalado: no se puede fabricar el ONNX del regresor"
)
pytest.importorskip("onnx", reason="onnx no está instalado")

from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType, StringTensorType
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from vigia.core.explain import global_permutation
from vigia.core.predict_onnx import (
    MENSAJE_ES_CLASIFICADOR,
    MENSAJE_ES_REGRESOR,
    ModeloEjecutableInvalido,
    build_artifact_inputs,
    coincidencia_valor,
    load_session,
    session_predict_proba,
    session_predict_value,
    validar_coincidencia_valor,
    validate_and_load,
)
from vigia.core.schema import TaskSpec

COLS = ["a", "c"]


def _frame_onnx(n=400, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({"a": rng.normal(size=n), "c": rng.choice(["u", "v", "w"], n)})
    y = 4 * X["a"] + X["c"].map({"u": 0.0, "v": 3.0, "w": -2.0}) + rng.normal(0, 0.2, n)
    return X, y.to_numpy()


def _tipos():
    return [("a", FloatTensorType([None, 1])), ("c", StringTensorType([None, 1]))]


def _preprocesado():
    return ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), ["c"]), ("num", "passthrough", ["a"])]
    )


def _guardar(tmp_path, modelo, nombre="m.onnx", **kw):
    onx = convert_sklearn(modelo, initial_types=_tipos(), **kw)
    ruta = tmp_path / nombre
    ruta.write_bytes(onx.SerializeToString())
    return ruta


@pytest.fixture(scope="module")
def regresor():
    X, y = _frame_onnx()
    modelo = Pipeline(
        [("ct", _preprocesado()), ("rf", RandomForestRegressor(n_estimators=20, random_state=0))]
    ).fit(X, y)
    return modelo, X, y


@pytest.fixture
def ruta_regresor(tmp_path, regresor):
    return _guardar(tmp_path, regresor[0])


def _tarea_regresion():
    return TaskSpec(task_type="regression")


def test_un_regresor_da_un_vector_con_la_paridad_de_predict(ruta_regresor, regresor):
    modelo, X, _ = regresor
    sesion = load_session(ruta_regresor)
    entradas = build_artifact_inputs(sesion, COLS)
    predict = session_predict_value(sesion, entradas)
    valores = predict(X)
    assert valores.shape == (len(X),) and valores.dtype == np.float64
    esperado = modelo.predict(X)
    assert np.all(np.abs(valores - esperado) <= 1e-4 * np.maximum(1.0, np.abs(esperado)))


def test_el_regresor_sirve_a_la_explicabilidad(ruta_regresor, regresor):
    _modelo, X, y = regresor
    sesion = load_session(ruta_regresor)
    predict = session_predict_value(sesion, build_artifact_inputs(sesion, COLS))
    r = global_permutation(predict, X, y=y, task=_tarea_regresion(), seed=0)
    assert r.params["scoring"] == "rmse_increase"
    assert {f.feature for f in r.features} == {"a", "c"}
    assert r.features[0].feature == "a"  # 4 unidades por desviación frente a ±3 de `c`


def test_validate_and_load_acepta_el_regresor_en_un_proyecto_de_regresion(ruta_regresor, regresor):
    _modelo, X, _ = regresor
    sesion, entradas = validate_and_load(ruta_regresor, COLS, X.iloc[0], _tarea_regresion())
    assert [e["name"] for e in entradas] == COLS and sesion is not None


def test_la_coincidencia_de_200_filas_con_la_linea_base_pasa_y_se_mide(ruta_regresor, regresor):
    modelo, X, _ = regresor
    muestra = X.iloc[:200]
    esperado = modelo.predict(muestra)
    sesion = load_session(ruta_regresor)
    predict = session_predict_value(sesion, build_artifact_inputs(sesion, COLS))
    assert coincidencia_valor(predict, muestra, esperado) == 1.0
    assert validar_coincidencia_valor(predict, muestra, esperado) == 1.0
    assert coincidencia_valor(predict, muestra, esperado + 0.5) == 0.0
    validate_and_load(
        ruta_regresor, COLS, X.iloc[0], _tarea_regresion(),
        muestra=muestra, valores_esperados=esperado,
    )


def test_el_modelo_equivocado_da_422_con_la_mediana_de_la_diferencia(ruta_regresor, regresor):
    modelo, X, _ = regresor
    muestra = X.iloc[:200]
    equivocado = modelo.predict(muestra) + 2.0
    with pytest.raises(ModeloEjecutableInvalido) as exc:
        validate_and_load(
            ruta_regresor, COLS, X.iloc[0], _tarea_regresion(),
            muestra=muestra, valores_esperados=equivocado,
        )
    texto = str(exc.value)
    assert "no reproduce" in texto and "mediana es 2" in texto and "0 %" in texto


def test_la_tolerancia_es_relativa_a_float32():
    # 1e-4 relativo a un valor de 5000 son 0,5; el float32 del ONNX no pasa de ahí
    esperado = np.array([5000.0, 6000.0])
    assert coincidencia_valor(lambda _x: esperado + 0.3, pd.DataFrame({"a": [1, 2]}), esperado) == 1.0
    assert coincidencia_valor(lambda _x: esperado + 3.0, pd.DataFrame({"a": [1, 2]}), esperado) == 0.0
    with pytest.raises(ValueError, match="deben ser las mismas"):
        coincidencia_valor(lambda _x: esperado[:1], pd.DataFrame({"a": [1]}), esperado)


@pytest.mark.parametrize("zipmap", [True, False])
def test_un_clasificador_en_un_proyecto_de_regresion_da_es_un_clasificador(tmp_path, zipmap):
    X, _ = _frame_onnx()
    clasificador = Pipeline([("ct", _preprocesado()), ("lr", LogisticRegression(max_iter=300))]).fit(
        X, (X["a"] > 0).astype(int)
    )
    ruta = _guardar(tmp_path, clasificador, options={LogisticRegression: {"zipmap": zipmap}})
    with pytest.raises(ModeloEjecutableInvalido) as exc:
        validate_and_load(ruta, COLS, X.iloc[0], _tarea_regresion())
    assert str(exc.value) == MENSAJE_ES_CLASIFICADOR
    assert "clasificador" in MENSAJE_ES_CLASIFICADOR


def test_un_modelo_con_mas_de_una_columna_de_salida_es_un_clasificador(tmp_path):
    X, y = _frame_onnx()
    dos = Pipeline([("ct", _preprocesado()), ("lin", LinearRegression())]).fit(X, np.c_[y, -y])
    ruta = _guardar(tmp_path, dos)
    with pytest.raises(ModeloEjecutableInvalido) as exc:
        validate_and_load(ruta, COLS, X.iloc[0], _tarea_regresion())
    assert str(exc.value) == MENSAJE_ES_CLASIFICADOR


@pytest.mark.parametrize(
    "tarea_clasificacion",
    [None, TaskSpec.binario(), TaskSpec(task_type="multiclass", classes=("x", "y", "z"), favorables=("x",))],
    ids=["sin_tarea", "binaria", "multiclase"],
)
def test_un_regresor_en_un_proyecto_de_clasificacion_da_es_un_regresor(
    ruta_regresor, regresor, tarea_clasificacion
):
    _modelo, X, _ = regresor
    with pytest.raises(ModeloEjecutableInvalido) as exc:
        validate_and_load(ruta_regresor, COLS, X.iloc[0], tarea_clasificacion)
    assert str(exc.value) == MENSAJE_ES_REGRESOR
    assert "regresor" in MENSAJE_ES_REGRESOR


def test_session_predict_proba_con_tarea_de_regresion_es_un_error_de_uso(ruta_regresor):
    sesion = load_session(ruta_regresor)
    with pytest.raises(ValueError, match="probabilidades por clase"):
        session_predict_proba(sesion, build_artifact_inputs(sesion, COLS), _tarea_regresion())


def test_el_resultado_de_la_clasificacion_no_cambia(tmp_path):
    # un clasificador binario sigue dando (n, 2) con y sin tarea binaria
    X, _ = _frame_onnx()
    clf = Pipeline([("ct", _preprocesado()), ("lr", LogisticRegression(max_iter=300))]).fit(
        X, (X["a"] > 0).astype(int)
    )
    ruta = _guardar(tmp_path, clf, options={LogisticRegression: {"zipmap": False}})
    sesion = load_session(ruta)
    entradas = build_artifact_inputs(sesion, COLS)
    a = session_predict_proba(sesion, entradas)(X.iloc[:10])
    b = session_predict_proba(sesion, entradas, TaskSpec.binario())(X.iloc[:10])
    assert a.shape == (10, 2) and np.array_equal(a, b)
    validate_and_load(ruta, COLS, X.iloc[0], TaskSpec.binario())
