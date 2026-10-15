"""ONNX con k >= 2 clases, orden de clases, datos
externos e inferencia en un hilo. El modelo se fabrica en el test
con `skl2onnx` (diabetes 130: `["<30", ">30", "NO"]`)."""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("skl2onnx", reason="skl2onnx no está instalado: no se puede fabricar el ONNX de 3 clases")
onnx = pytest.importorskip("onnx", reason="onnx no está instalado")

from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from vigia.core.predict_onnx import (
    ModeloEjecutableInvalido,
    build_artifact_inputs,
    coincidencia_argmax,
    load_session,
    orden_clases_onnx,
    predecir_en_hilo,
    session_predict_proba,
    tiene_datos_externos,
    validate_and_load,
)
from vigia.core.schema import TaskSpec

CLASES_ENTRENAMIENTO = ["NO", ">30", "<30"]  # orden de aparición, no el alfabético
ALFABETICO = ["<30", ">30", "NO"]


def _datos(etiquetas):
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(300, 2)), columns=["a", "b"])
    puntuacion = np.c_[X.a, X.b, -X.a - X.b] + rng.normal(0, 0.4, (300, 3))
    y = np.array(etiquetas)[puntuacion.argmax(axis=1)]
    return X, y


def _modelo(tmp_path, etiquetas, *, zipmap=True, nombre="m.onnx"):
    X, y = _datos(etiquetas)
    clf = Pipeline(
        [
            ("ct", ColumnTransformer([("num", "passthrough", ["a", "b"])])),
            ("clf", LogisticRegression(max_iter=500)),
        ]
    ).fit(X, y)
    onx = convert_sklearn(
        clf,
        initial_types=[("a", FloatTensorType([None, 1])), ("b", FloatTensorType([None, 1]))],
        options={LogisticRegression: {"zipmap": zipmap}},
    )
    ruta = tmp_path / nombre
    ruta.write_bytes(onx.SerializeToString())
    return ruta, clf, X


def _tarea(clases):
    return TaskSpec(task_type="multiclass", classes=tuple(clases), favorables=(clases[0],))


@pytest.mark.parametrize("zipmap", [True, False])
def test_orden_de_clases_del_grafo_es_el_alfabetico_de_sklearn(tmp_path, zipmap):
    ruta, clf, _ = _modelo(tmp_path, CLASES_ENTRENAMIENTO, zipmap=zipmap)
    assert list(clf.classes_) == ALFABETICO
    assert orden_clases_onnx(ruta) == ALFABETICO
    assert orden_clases_onnx(ruta.read_bytes()) == ALFABETICO
    assert load_session(ruta).vigia_orden_clases == ALFABETICO


def test_orden_de_clases_enteras(tmp_path):
    ruta, _clf, _ = _modelo(tmp_path, [2, 0, 1])
    assert orden_clases_onnx(ruta) == ["0", "1", "2"]


def test_orden_de_clases_enteras_sin_zipmap_lee_classlabels_ints(tmp_path):
    """El `LinearClassifier` lleva las etiquetas enteras en `classlabels_ints`."""
    ruta, _clf, _ = _modelo(tmp_path, [2, 0, 1], zipmap=False)
    assert orden_clases_onnx(ruta) == ["0", "1", "2"]
    assert load_session(ruta).vigia_orden_clases == ["0", "1", "2"]


def test_fichero_que_onnx_no_lee_se_rechaza_sin_abrirlo(tmp_path):
    """Cierra por defecto: si no se puede leer para comprobar sus datos
    externos, no se abre con onnxruntime."""
    ruta = tmp_path / "roto.onnx"
    ruta.write_bytes(b"esto no es un modelo")
    with pytest.raises(ModeloEjecutableInvalido, match="ONNX"):
        load_session(ruta)


def test_coincidencia_argmax_con_longitudes_distintas_da_error_en_espanol(tmp_path):
    ruta, clf, X = _modelo(tmp_path, CLASES_ENTRENAMIENTO, zipmap=False)
    sesion = load_session(ruta)
    entradas = build_artifact_inputs(sesion, ["a", "b"])
    tarea = _tarea(ALFABETICO)
    fn = session_predict_proba(sesion, entradas, tarea)
    with pytest.raises(ValueError, match="mismo lote"):
        coincidencia_argmax(fn, X.iloc[:50], clf.predict(X.iloc[:40]), tarea)


@pytest.mark.parametrize("zipmap", [True, False])
def test_prediccion_k3_en_el_orden_de_las_clases_del_proyecto(tmp_path, zipmap):
    ruta, clf, X = _modelo(tmp_path, CLASES_ENTRENAMIENTO, zipmap=zipmap)
    sesion = load_session(ruta)
    entradas = build_artifact_inputs(sesion, ["a", "b"])
    declaradas = ["NO", "<30", ">30"]  # otro orden que el del grafo
    fn = session_predict_proba(sesion, entradas, _tarea(declaradas))
    probs = fn(X.iloc[:50])
    assert probs.shape == (50, 3)
    esperado = clf.predict_proba(X.iloc[:50])[:, [2, 0, 1]]  # NO, <30, >30
    assert np.allclose(probs, esperado, atol=1e-5)
    # el mismo orden que el grafo no reordena
    igual = session_predict_proba(sesion, entradas, _tarea(ALFABETICO))(X.iloc[:50])
    assert np.allclose(igual, clf.predict_proba(X.iloc[:50]), atol=1e-5)


def test_clases_distintas_o_k_distinto_dan_error_en_espanol(tmp_path):
    ruta, _clf, X = _modelo(tmp_path, CLASES_ENTRENAMIENTO, zipmap=False)
    sesion = load_session(ruta)
    entradas = build_artifact_inputs(sesion, ["a", "b"])
    with pytest.raises(ModeloEjecutableInvalido, match="deben ser las mismas"):
        session_predict_proba(sesion, entradas, _tarea(["x", "y", "z"]))(X.iloc[:5])
    with pytest.raises(ModeloEjecutableInvalido, match="3 probabilidades por fila y el proyecto tiene 4"):
        session_predict_proba(sesion, entradas, _tarea(["<30", ">30", "NO", "otra"]))(X.iloc[:5])
    # sin tarea, un modelo de 3 clases sigue rechazándose como antes de la multiclase
    with pytest.raises(ModeloEjecutableInvalido, match="modelos binarios"):
        session_predict_proba(sesion, entradas)(X.iloc[:5])


def test_validate_and_load_acepta_1_k_con_tarea_multiclase(tmp_path):
    ruta, _clf, X = _modelo(tmp_path, CLASES_ENTRENAMIENTO)
    sesion, entradas = validate_and_load(ruta, ["a", "b"], X.iloc[0], _tarea(ALFABETICO))
    assert [e["name"] for e in entradas] == ["a", "b"] and sesion is not None
    with pytest.raises(ModeloEjecutableInvalido):
        validate_and_load(ruta, ["a", "b"], X.iloc[0])  # sin tarea: binario


def test_coincidencia_argmax_detecta_un_orden_de_clases_cambiado(tmp_path):
    ruta, clf, X = _modelo(tmp_path, CLASES_ENTRENAMIENTO, zipmap=False)
    sesion = load_session(ruta)
    sesion.vigia_orden_clases = None  # el grafo no dice su orden
    entradas = build_artifact_inputs(sesion, ["a", "b"])
    pred = clf.predict(X.iloc[:200])
    bien = coincidencia_argmax(
        session_predict_proba(sesion, entradas, _tarea(ALFABETICO)), X.iloc[:200], pred, _tarea(ALFABETICO)
    )
    mal = coincidencia_argmax(
        session_predict_proba(sesion, entradas, _tarea(["NO", "<30", ">30"])),
        X.iloc[:200], pred, _tarea(["NO", "<30", ">30"]),
    )
    assert bien >= 0.99 and mal < 0.9


def _modelo_con_inicializador(tmp_path):
    """MatMul con un inicializador de pesos: es el tensor que se externaliza."""
    from onnx import TensorProto, helper, numpy_helper

    pesos = numpy_helper.from_array(np.arange(6, dtype=np.float32).reshape(2, 3), name="w")
    grafo = helper.make_graph(
        [helper.make_node("MatMul", ["x", "w"], ["y"])],
        "g",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [None, 2])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [None, 3])],
        initializer=[pesos],
    )
    modelo = helper.make_model(grafo, opset_imports=[helper.make_opsetid("", 13)])
    modelo.ir_version = 8
    return modelo


def test_modelo_con_datos_externos_se_rechaza_antes_de_abrirlo(tmp_path):
    modelo = _modelo_con_inicializador(tmp_path)
    ruta = tmp_path / "ext.onnx"
    onnx.save_model(
        modelo, str(ruta), save_as_external_data=True, all_tensors_to_one_file=True,
        location="pesos.data", size_threshold=0,
    )
    assert (tmp_path / "pesos.data").exists()
    assert tiene_datos_externos(ruta)
    with pytest.raises(ModeloEjecutableInvalido, match="datos externos"):
        load_session(ruta)
    # el mismo modelo con los pesos dentro sí se abre
    dentro = tmp_path / "dentro.onnx"
    onnx.save_model(_modelo_con_inicializador(tmp_path), str(dentro))
    assert not tiene_datos_externos(dentro)
    assert load_session(dentro) is not None


def test_datos_externos_en_una_funcion_local_se_detectan():
    from onnx import TensorProto, helper, numpy_helper

    t = numpy_helper.from_array(np.zeros((2, 2), dtype=np.float32), name="c")
    t.data_location = TensorProto.EXTERNAL
    nodo = helper.make_node("Constant", [], ["o"], value=t)
    funcion = helper.make_function(
        "dom", "f", [], ["o"], [nodo], [helper.make_opsetid("", 13)]
    )
    grafo = helper.make_graph([], "g", [], [])
    modelo = helper.make_model(grafo, opset_imports=[helper.make_opsetid("", 13)])
    modelo.functions.append(funcion)
    assert tiene_datos_externos(modelo)


def test_modelo_sin_datos_externos_no_se_marca(tmp_path):
    ruta, _clf, _ = _modelo(tmp_path, CLASES_ENTRENAMIENTO)
    assert not tiene_datos_externos(ruta)


def test_prediccion_en_un_hilo_da_lo_mismo(tmp_path):
    ruta, _clf, X = _modelo(tmp_path, CLASES_ENTRENAMIENTO, zipmap=False)
    sesion = load_session(ruta)
    fn = session_predict_proba(sesion, build_artifact_inputs(sesion, ["a", "b"]), _tarea(ALFABETICO))
    directa = fn(X.iloc[:20])
    en_hilo = asyncio.run(predecir_en_hilo(fn, X.iloc[:20]))
    assert np.array_equal(directa, en_hilo)
