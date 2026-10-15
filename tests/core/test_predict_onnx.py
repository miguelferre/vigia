"""Validación y predicción sobre un modelo ONNX.

El modelo de prueba es un `Pipeline` de scikit-learn pequeño (una columna
numérica, una categórica en texto) convertido con `skl2onnx`, igual que un modelo
real. `admission_type_id` simula Diabetes 130: un
identificador que llega como entero en los datos crudos pero que el modelo
entrenó como texto, así que el modelo ONNX declara su entrada como
`tensor(string)`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType, StringTensorType
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from vigia.core.predict_onnx import (
    ModeloEjecutableInvalido,
    build_artifact_inputs,
    cast_frame_to_kinds,
    load_session,
    sanitize_onnx_name,
    session_predict_proba,
    validate_and_load,
)


def _onnx_bytes(tmp_path):
    """Un `Pipeline` (numérica `age` + categórica en texto `admission_type_id`,
    saneada por skl2onnx: sin guiones que sanear aquí a propósito, ese caso
    lo cubre `test_sanitize_onnx_name_*`) convertido a ONNX en disco."""
    df = pd.DataFrame(
        {
            "age": [25.0, 40.0, 55.0, 30.0, 60.0, 22.0, 48.0, 33.0],
            "admission_type_id": ["1", "2", "3", "1", "2", "3", "1", "2"],
        }
    )
    y = [0, 1, 0, 1, 0, 1, 0, 1]
    ct = ColumnTransformer(
        [
            ("num", "passthrough", ["age"]),
            ("cat", OneHotEncoder(handle_unknown="ignore"), ["admission_type_id"]),
        ]
    )
    pipe = Pipeline([("ct", ct), ("clf", LogisticRegression())])
    pipe.fit(df, y)

    initial_types = [
        ("age", FloatTensorType([None, 1])),
        ("admission_type_id", StringTensorType([None, 1])),
    ]
    onx = convert_sklearn(pipe, initial_types=initial_types)
    ruta = tmp_path / "modelo.onnx"
    ruta.write_bytes(onx.SerializeToString())
    return ruta


def test_sanitize_onnx_name_guion_a_guion_bajo_y_prefijo_si_empieza_en_digito():
    assert sanitize_onnx_name("education-num") == "education_num"
    assert sanitize_onnx_name("3_abc") == "_3_abc"
    assert sanitize_onnx_name("age") == "age"


def test_build_artifact_inputs_orden_y_kind_por_tipo_declarado(tmp_path):
    session = load_session(_onnx_bytes(tmp_path))
    inputs = build_artifact_inputs(session, ["age", "admission_type_id"])
    assert [i["name"] for i in inputs] == ["age", "admission_type_id"]
    por_nombre = {i["name"]: i for i in inputs}
    assert por_nombre["age"]["kind"] == "numerica"
    # admission_type_id es un entero en los datos crudos, pero el
    # modelo lo declaró como texto: el `kind` sale del modelo, no del dtype.
    assert por_nombre["admission_type_id"]["kind"] == "categorica"
    assert por_nombre["admission_type_id"]["type"] == "tensor(string)"


def test_build_artifact_inputs_columna_del_mapeo_sin_entrada_da_error(tmp_path):
    session = load_session(_onnx_bytes(tmp_path))
    with pytest.raises(ModeloEjecutableInvalido, match="columna_que_no_existe"):
        build_artifact_inputs(session, ["age", "columna_que_no_existe"])


def test_cast_frame_to_kinds_entero_a_texto_sin_punto_r2n2():
    artifact_inputs = [
        {"name": "age", "kind": "numerica"},
        {"name": "admission_type_id", "kind": "categorica"},
    ]
    # admission_type_id llega como float64 (típico de un CSV leído con
    # pandas cuando la columna tiene huecos en otra fila): 1.0, no "1".
    df = pd.DataFrame({"age": [30, 45], "admission_type_id": [1.0, 3.0]})
    casteado = cast_frame_to_kinds(df, artifact_inputs)
    assert list(casteado["admission_type_id"]) == ["1", "3"]
    assert pd.api.types.is_numeric_dtype(casteado["age"])


def test_cast_frame_to_kinds_columna_que_falta_da_error():
    artifact_inputs = [{"name": "no_esta", "kind": "numerica"}]
    with pytest.raises(ModeloEjecutableInvalido, match="no_esta"):
        cast_frame_to_kinds(pd.DataFrame({"age": [1]}), artifact_inputs)


def test_session_predict_proba_dan_n_2_y_suman_uno(tmp_path):
    session = load_session(_onnx_bytes(tmp_path))
    artifact_inputs = build_artifact_inputs(session, ["age", "admission_type_id"])
    predict_fn = session_predict_proba(session, artifact_inputs)
    # admission_type_id crudo como entero: cast_frame_to_kinds lo
    # convierte a texto antes de que llegue al modelo.
    X = pd.DataFrame({"age": [25.0, 60.0], "admission_type_id": [1, 2]})
    probs = predict_fn(X)
    assert probs.shape == (2, 2)
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-5)


def test_validate_and_load_ok_con_fila_de_linea_base(tmp_path):
    baseline_row = pd.Series({"age": 40, "admission_type_id": 2})
    session, artifact_inputs = validate_and_load(
        _onnx_bytes(tmp_path), ["age", "admission_type_id"], baseline_row
    )
    assert session is not None
    assert len(artifact_inputs) == 2


def test_validate_and_load_columna_no_en_mapeo_da_422_con_motivo_en_espanol(tmp_path):
    baseline_row = pd.Series({"age": 40, "admission_type_id": 2, "otra": 1})
    with pytest.raises(ModeloEjecutableInvalido) as excinfo:
        validate_and_load(_onnx_bytes(tmp_path), ["age", "otra"], baseline_row)
    mensaje = str(excinfo.value)
    assert "otra" in mensaje
    assert "Traceback" not in mensaje


def test_validate_and_load_sin_feature_cols_da_error(tmp_path):
    with pytest.raises(ModeloEjecutableInvalido, match="feature_cols"):
        validate_and_load(tmp_path / "no_se_llega_a_abrir.onnx", [], pd.Series({"a": 1}))
