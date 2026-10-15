"""El modelo ejecutable y la explicabilidad de una regresión.
Pickle con scikit-learn y ONNX con `skl2onnx` (se salta si falta).
"""

from __future__ import annotations

import io

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api import _datos_multiclase as d
from tests.api import _datos_regresion as r
from tests.api.conftest import actor_headers
from vigia.app.models import ModelVersion
from vigia.app.services import model_registry
from vigia.core.schema import TaskSpec

HUMANO = actor_headers("miguel")


def _regresor(df: pd.DataFrame, columnas: tuple[str, str] = ("x1", "x2")):
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LinearRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    pipe = Pipeline(
        [
            ("ct", ColumnTransformer([("num", StandardScaler(), list(columnas))])),
            ("reg", LinearRegression()),
        ]
    )
    pipe.fit(df[list(columnas)], df["label"])
    return pipe


def _proyecto_con_modelo(client: TestClient, nombre: str, *, n: int = 300):
    """Línea base cuya predicción ES la del modelo (sin ruido), para que el modelo la reproduzca."""
    df = r.filas_regresion(n)
    pipe = _regresor(df)
    df["prediction"] = np.round(pipe.predict(df[["x1", "x2"]]), 6)
    proyecto = r.crear_proyecto_regresion(client, nombre)
    r.subir_e_ingerir(client, proyecto, df)
    return proyecto, pipe


def _pickle(modelo) -> bytes:
    buf = io.BytesIO()
    joblib.dump(modelo, buf)
    return buf.getvalue()


def _subir(client: TestClient, version_id: int, contenido: bytes, kind: str = "pickle"):
    return d.subir_modelo(
        client, version_id, contenido, kind=kind, confirmar=kind == "pickle",
        nombre="modelo.pkl" if kind == "pickle" else "modelo.onnx",
    )


def _onnx(pipe, columnas: tuple[str, str] = ("x1", "x2")) -> bytes:
    pytest.importorskip("skl2onnx", reason="skl2onnx no está instalado")
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType

    return convert_sklearn(
        pipe,
        initial_types=[(c, FloatTensorType([None, 1])) for c in columnas],
    ).SerializeToString()


# ---------------------------------------------------------------------------
# Alta del artefacto
# ---------------------------------------------------------------------------


def test_un_pickle_de_regresor_se_acepta_si_reproduce_la_prediccion_de_la_linea_base(client: TestClient):
    p, pipe = _proyecto_con_modelo(client, "r5-mod-pickle-ok")
    resp = _subir(client, p["active_version_id"], _pickle(pipe))
    assert resp.status_code == 200, resp.text
    assert resp.json()["artifact_kind"] == "pickle"
    with Session(client.app.state.engine) as s:
        version = s.get(ModelVersion, p["active_version_id"])
        assert version.model_kind == "executable"
        task = TaskSpec(task_type="regression", unidad=r.UNIDAD)
        predict_fn = model_registry.get_predict_fn(version, task)
    valores = predict_fn(pd.DataFrame({"x1": [0.0, 1.0], "x2": [0.0, 1.0]}))
    assert valores.shape == (2,)  # `(n,)`, el valor predicho en la unidad
    assert valores[1] > valores[0]


def test_un_pickle_de_otro_modelo_da_422_con_la_diferencia_mediana(client: TestClient):
    p, _pipe = _proyecto_con_modelo(client, "r5-mod-pickle-otro")
    otro = _regresor(r.filas_regresion(300, semilla=77).assign(label=lambda x: -x["label"]))
    resp = _subir(client, p["active_version_id"], _pickle(otro))
    assert resp.status_code == 422, resp.text
    assert "99" in resp.text and "diferencia mediana" in resp.text
    leido = client.get(f"/api/projects/{p['id']}").json()
    assert next(v for v in leido["versions"] if v["id"] == p["active_version_id"])["artifact_kind"] is None


def test_un_pickle_clasificador_en_un_proyecto_de_regresion_da_422(client: TestClient):
    from sklearn.linear_model import LogisticRegression

    p, _pipe = _proyecto_con_modelo(client, "r5-mod-pickle-clasificador")
    df = r.filas_regresion(200)
    clasificador = LogisticRegression().fit(df[["x1", "x2"]], (df["label"] > 12).astype(int))
    resp = _subir(client, p["active_version_id"], _pickle(clasificador))
    assert resp.status_code == 422, resp.text
    assert "es un clasificador" in resp.text and "regresión" in resp.text


def test_un_pickle_regresor_en_un_proyecto_de_clasificacion_da_422(client: TestClient):
    pipe = _regresor(r.filas_regresion(200))
    proyecto, _s, _t = d.linea_base_multiclase(client, "r5-mod-pickle-regresor-en-multi", n=300)
    resp = _subir(client, proyecto["active_version_id"], _pickle(pipe))
    assert resp.status_code == 422, resp.text
    assert "es un regresor" in resp.text
    # Y en binario igual.
    binario = client.post("/api/projects", json={"name": "r5-mod-regresor-en-binario"}, headers=HUMANO).json()
    df = r.filas_regresion(120)
    df["label"] = (df["label"] >= 12).astype(int)
    df["prediction"] = (df["prediction"] >= 12).astype(int)
    sub = d.subir(client, binario["id"], r.a_csv(df))
    assert d.mapear(
        client, sub["dataset"]["id"],
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": 1,
         "feature_cols": ["x1", "x2"]},
    ).status_code == 200
    assert d.ingerir(client, sub["dataset"]["id"], binario["active_version_id"])["status"] == "terminado"
    resp = _subir(client, binario["active_version_id"], _pickle(pipe))
    assert resp.status_code == 422 and "es un regresor" in resp.text


def test_un_onnx_de_regresor_se_acepta_y_da_el_valor_en_n(client: TestClient):
    p, pipe = _proyecto_con_modelo(client, "r5-mod-onnx-ok")
    resp = _subir(client, p["active_version_id"], _onnx(pipe), kind="onnx")
    assert resp.status_code == 200, resp.text
    assert resp.json()["artifact_kind"] == "onnx"
    with Session(client.app.state.engine) as s:
        version = s.get(ModelVersion, p["active_version_id"])
        predict_fn = model_registry.get_predict_fn(version, TaskSpec(task_type="regression"))
    valores = predict_fn(pd.DataFrame({"x1": [0.0, 1.0, 2.0], "x2": [0.0, 0.0, 0.0]}))
    assert valores.shape == (3,) and valores[0] < valores[1] < valores[2]


def test_un_onnx_clasificador_en_un_proyecto_de_regresion_da_422(client: TestClient):
    """Con las entradas del proyecto (`x1`, `x2`), para que el 422 sea el del tipo y no el de
    «no hay una entrada para estas columnas»."""
    pytest.importorskip("skl2onnx", reason="skl2onnx no está instalado")
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    p, _pipe = _proyecto_con_modelo(client, "r5-mod-onnx-clasificador")
    df = r.filas_regresion(200)
    clasificador = Pipeline(
        [
            ("ct", ColumnTransformer([("num", StandardScaler(), ["x1", "x2"])])),
            ("clf", LogisticRegression()),
        ]
    ).fit(df[["x1", "x2"]], (df["label"] > 12).astype(int))
    resp = _subir(client, p["active_version_id"], _onnx(clasificador), kind="onnx")
    assert resp.status_code == 422, resp.text
    assert "es un clasificador" in resp.text and "regresión" in resp.text
    assert "no tiene una entrada" not in resp.text


def test_un_onnx_regresor_en_un_proyecto_de_clasificacion_da_422(client: TestClient):
    """Con las entradas del proyecto multiclase (`longitud`, `enlaces`): el 422 es el del tipo."""
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"longitud": rng.normal(50, 20, 200), "enlaces": rng.normal(1, 0.5, 200)})
    df["label"] = 2 * df["longitud"] + df["enlaces"]
    pipe = _regresor(df, ("longitud", "enlaces"))
    proyecto, _s, _t = d.linea_base_multiclase(client, "r5-mod-onnx-regresor-en-multi", n=300)
    resp = _subir(client, proyecto["active_version_id"], _onnx(pipe, ("longitud", "enlaces")), kind="onnx")
    assert resp.status_code == 422, resp.text
    assert "regresor" in resp.text
    assert "no tiene una entrada" not in resp.text


def test_un_onnx_de_otro_modelo_da_422_con_la_diferencia_mediana(client: TestClient):
    p, _pipe = _proyecto_con_modelo(client, "r5-mod-onnx-otro")
    otro = _regresor(r.filas_regresion(300, semilla=77).assign(label=lambda x: -x["label"]))
    resp = _subir(client, p["active_version_id"], _onnx(otro), kind="onnx")
    assert resp.status_code == 422, resp.text
    assert "diferencia mediana" in resp.text


def test_sin_variables_guardadas_el_modelo_no_se_acepta_a_ciegas(client: TestClient):
    """Sin variables en la línea base (`store_features=False`) ya falla la lectura de la fila
    de línea base, con la pauta de activarlas: el modelo no se acepta sin comprobar."""
    df = r.filas_regresion(300)
    pipe = _regresor(df)
    df["prediction"] = np.round(pipe.predict(df[["x1", "x2"]]), 6)
    proyecto = r.crear_proyecto_regresion(client, "r5-mod-sin-variables", store_features=False)
    r.subir_e_ingerir(client, proyecto, df)
    resp = _subir(client, proyecto["active_version_id"], _pickle(pipe))
    assert resp.status_code == 422 and "store_features" in resp.text, resp.text


def test_sin_valor_predicho_guardado_el_modelo_se_acepta_con_un_aviso(client: TestClient):
    """El resto del hueco: variables guardadas pero ningún `prediction_value` con qué
    comparar. El modelo se acepta y la respuesta dice que no se comprobó."""
    from sqlmodel import update

    from vigia.app.models import Record

    p, pipe = _proyecto_con_modelo(client, "r5-mod-sin-valor-guardado")
    with Session(client.app.state.engine) as s:
        s.exec(update(Record).where(Record.project_id == p["id"]).values(prediction_value=None))
        s.commit()
    resp = _subir(client, p["active_version_id"], _pickle(pipe))
    assert resp.status_code == 200, resp.text
    assert model_registry.AVISO_SIN_COMPROBAR_VALORES in resp.json()["avisos"]
    # Con el valor guardado, el aviso no sale.
    p2, pipe2 = _proyecto_con_modelo(client, "r5-mod-con-valor-guardado")
    ok = _subir(client, p2["active_version_id"], _pickle(pipe2))
    assert model_registry.AVISO_SIN_COMPROBAR_VALORES not in ok.json()["avisos"]


# ---------------------------------------------------------------------------
# Explicabilidad
# ---------------------------------------------------------------------------


def _explicar(client: TestClient, version_id: int, ruta: str, cuerpo: dict):
    return client.post(f"/api/model-versions/{version_id}/explain/{ruta}", json=cuerpo, headers=HUMANO)


def test_la_explicacion_global_ordena_por_aumento_del_rmse(client: TestClient):
    p, pipe = _proyecto_con_modelo(client, "r5-mod-explica-global")
    assert _subir(client, p["active_version_id"], _pickle(pipe)).status_code == 200
    v = p["active_version_id"]
    resp = _explicar(client, v, "global", {"kind": "permutation"})
    assert resp.status_code == 200 and resp.json()["status"] == "terminado", resp.text
    resultado = client.get(f"/api/model-versions/{v}/explanations").json()["items"][0]["result"]
    nombres = [f["feature"] for f in resultado["features"]]
    assert nombres[0] == "x1"  # 3 x1 + 2 x2: x1 pesa más
    assert resultado["features"][0]["importance"] > resultado["features"][1]["importance"] > 0
    assert "clase_explicada" not in resultado and "probabilities" not in resultado


def test_la_explicacion_local_lleva_el_valor_predicho_y_la_global_rechaza_clase(client: TestClient):
    p, pipe = _proyecto_con_modelo(client, "r5-mod-explica-local")
    assert _subir(client, p["active_version_id"], _pickle(pipe)).status_code == 200
    v = p["active_version_id"]
    batch_id = client.get(f"/api/projects/{p['id']}/batches").json()["items"][0]["id"]
    resp = _explicar(client, v, "local", {"batch_id": batch_id, "row_seq": 0})
    assert resp.status_code == 200 and resp.json()["status"] == "terminado", resp.text
    local = next(
        e for e in client.get(f"/api/model-versions/{v}/explanations").json()["items"]
        if e["kind"] == "local_lime"
    )["result"]
    assert local.get("prediction_value") is not None
    esperado = float(pipe.predict(r.filas_regresion(300)[["x1", "x2"]].iloc[[0]])[0])
    assert local["prediction_value"] == pytest.approx(esperado, rel=1e-3, abs=1e-3)
    # Una regresión no tiene clases que elegir: 422 en global y en local.
    for ruta, cuerpo in (
        ("global", {"kind": "permutation", "clase": "alto"}),
        ("local", {"batch_id": batch_id, "row_seq": 0, "clase": "alto"}),
    ):
        malo = _explicar(client, v, ruta, cuerpo)
        assert malo.status_code == 422, malo.text
        assert "regresión" in malo.text and "clases" in malo.text
