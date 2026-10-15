"""Alta del artefacto del modelo ejecutable.

El modelo de prueba es el mismo en todos los tests: un `Pipeline` de
scikit-learn pequeño con una columna numérica (`age`), una categórica en
texto (`workclass`) y una que llega como entero en el CSV pero el modelo
entrenó como texto (`admission_type_id`, como `admission_type_id` en
Diabetes 130), convertido a ONNX con `skl2onnx`.
"""

from __future__ import annotations

import io
from unittest import mock

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType, StringTensorType
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sqlmodel import Session

from tests.api.conftest import actor_headers
from vigia.app.models import ModelVersion
from vigia.app.services import model_registry
from vigia.core import explain as core_explain

FEATURE_COLS = ["age", "workclass", "admission_type_id"]

_TRAIN_DF = pd.DataFrame(
    {
        "age": [25.0, 40.0, 55.0, 30.0, 60.0, 22.0, 48.0, 33.0],
        "workclass": ["privado", "publico", "privado", "autonomo", "publico", "privado", "autonomo", "publico"],
        # Entrenado como texto aunque en el CSV llegue como entero.
        "admission_type_id": ["1", "2", "3", "1", "2", "3", "1", "2"],
    }
)
_TRAIN_Y = [0, 1, 0, 1, 0, 1, 0, 1]


def _entrenar_pipeline() -> Pipeline:
    ct = ColumnTransformer(
        [
            ("num", "passthrough", ["age"]),
            ("cat", OneHotEncoder(handle_unknown="ignore"), ["workclass", "admission_type_id"]),
        ]
    )
    pipe = Pipeline([("ct", ct), ("clf", LogisticRegression())])
    pipe.fit(_TRAIN_DF, _TRAIN_Y)
    return pipe


def _onnx_bytes(pipe: Pipeline) -> bytes:
    initial_types = [
        ("age", FloatTensorType([None, 1])),
        ("workclass", StringTensorType([None, 1])),
        ("admission_type_id", StringTensorType([None, 1])),
    ]
    onx = convert_sklearn(pipe, initial_types=initial_types)
    return onx.SerializeToString()


def _csv_baseline() -> bytes:
    filas = [
        "id,prediction,label,age,workclass,admission_type_id",
        "p1,1,1,25,privado,1",
        "p2,0,1,40,publico,2",
        "p3,1,0,55,privado,3",
        "p4,0,1,30,autonomo,1",
        "p5,1,0,60,publico,2",
        "p6,0,0,22,privado,3",
        "p7,1,1,48,autonomo,1",
        "p8,0,0,33,publico,2",
    ]
    return ("\n".join(filas) + "\n").encode("utf-8")


# Pickle no declara el tipo de cada entrada como ONNX (`InferenceSession`):
# `model_registry._artifact_inputs_from_baseline` infiere "categorica" o
# "numerica" del tipo Python del valor de línea base, así que en los tests
# de pickle la columna categórica no puede parecer un número (a diferencia
# de `admission_type_id`, pensada para el saneado de tipos de ONNX): eso
# solo aplica a la ruta ONNX, la única con tipos declarados por el modelo.
PICKLE_FEATURE_COLS = ["age", "workclass"]
_TRAIN_DF_PICKLE = _TRAIN_DF[["age", "workclass"]]


def _entrenar_pipeline_pickle() -> Pipeline:
    ct = ColumnTransformer(
        [
            ("num", "passthrough", ["age"]),
            ("cat", OneHotEncoder(handle_unknown="ignore"), ["workclass"]),
        ]
    )
    pipe = Pipeline([("ct", ct), ("clf", LogisticRegression())])
    pipe.fit(_TRAIN_DF_PICKLE, _TRAIN_Y)
    return pipe


def _csv_baseline_pickle() -> bytes:
    filas = [
        "id,prediction,label,age,workclass",
        "p1,1,1,25,privado",
        "p2,0,1,40,publico",
        "p3,1,0,55,privado",
        "p4,0,1,30,autonomo",
        "p5,1,0,60,publico",
        "p6,0,0,22,privado",
        "p7,1,1,48,autonomo",
        "p8,0,0,33,publico",
    ]
    return ("\n".join(filas) + "\n").encode("utf-8")


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "libre", "store_features": True},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _preparar_proyecto_con_baseline(
    client: TestClient,
    name: str,
    *,
    csv_bytes: bytes | None = None,
    feature_cols: list[str] | None = None,
) -> tuple[dict, int, int]:
    """Proyecto `external_files` con un lote de línea base mapeado e ingerido
    (id, prediction, label, y `feature_cols`, por defecto las tres `FEATURE_COLS`)."""
    proyecto = _crear_proyecto(client, name)
    version_id = proyecto["active_version_id"]

    resp = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("baseline.csv", csv_bytes or _csv_baseline(), "text/csv")},
        data={"kind": "combined", "role": "baseline"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    dataset_id = resp.json()["dataset"]["id"]

    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "feature_cols": feature_cols or FEATURE_COLS,
        "favorable_label": 1,
    }
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": mapping, "privacy_decisions": {}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"model_version_id": version_id, "evaluate": False},
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    batch_id = job["result"]["batch_id"]

    resp = client.post(
        f"/api/model-versions/{version_id}/baseline",
        json={"batch_id": batch_id, "actor": "miguel", "motivo": "congelar línea base"},
    )
    # La ingesta de la línea base ya la congela: el POST /baseline da 409.
    assert resp.status_code == 409, resp.text
    assert "congelado" in resp.text, resp.text
    return proyecto, version_id, batch_id


def _subir_artefacto(
    client: TestClient,
    version_id: int,
    *,
    contenido: bytes,
    filename: str = "modelo.onnx",
    artifact_kind: str = "onnx",
    confirmacion_pickle: bool = False,
):
    return client.post(
        f"/api/model-versions/{version_id}/artifact",
        files={"file": (filename, contenido, "application/octet-stream")},
        data={"artifact_kind": artifact_kind, "confirmacion_pickle": str(confirmacion_pickle).lower()},
        headers=actor_headers("miguel"),
    )


# --- Subida y validación ---------------------------------------


def test_subida_onnx_ok_model_kind_pasa_a_executable_y_kinds_correctos(client: TestClient):
    proyecto, version_id, _ = _preparar_proyecto_con_baseline(client, "artefacto-onnx-ok")
    pipe = _entrenar_pipeline()

    resp = _subir_artefacto(client, version_id, contenido=_onnx_bytes(pipe))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["model_kind"] == "executable"
    assert body["artifact_kind"] == "onnx"
    assert len(body["artifact_sha256"]) == 64
    assert body["avisos"] == []
    por_nombre = {i["name"]: i for i in body["artifact_inputs"]}
    assert por_nombre["age"]["kind"] == "numerica"
    assert por_nombre["workclass"]["kind"] == "categorica"
    # El kind sale de lo que declara el modelo, no del CSV (donde
    # admission_type_id es un entero).
    assert por_nombre["admission_type_id"]["kind"] == "categorica"

    resp = client.get(f"/api/projects/{proyecto['id']}")
    assert resp.status_code == 200, resp.text
    version_activa = next(
        v for v in resp.json()["versions"] if v["id"] == version_id
    )
    assert version_activa["model_kind"] == "executable"
    assert version_activa["artifact_kind"] == "onnx"


def test_subida_422_entrada_que_no_esta_en_el_mapeo(client: TestClient):
    """Un `feature_cols` con una columna que el modelo no tiene: 422."""
    proyecto = _crear_proyecto(client, "artefacto-columna-sin-modelo")
    version_id = proyecto["active_version_id"]
    csv = (
        b"id,prediction,label,age,workclass,otra_col\n"
        b"p1,1,1,25,privado,x\n"
        b"p2,0,1,40,publico,y\n"
        b"p3,1,0,55,privado,x\n"
    )
    resp = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("baseline.csv", csv, "text/csv")},
        data={"kind": "combined", "role": "baseline"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    dataset_id = resp.json()["dataset"]["id"]
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "feature_cols": ["age", "workclass", "otra_col"],
        "favorable_label": 1,
    }
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": mapping, "privacy_decisions": {}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"model_version_id": version_id, "evaluate": False},
    )
    assert resp.status_code == 200, resp.text
    batch_id = resp.json()["result"]["batch_id"]
    resp = client.post(
        f"/api/model-versions/{version_id}/baseline",
        json={"batch_id": batch_id, "actor": "miguel", "motivo": "congelar"},
    )
    # La ingesta de la línea base ya la congela: el POST /baseline da 409.
    assert resp.status_code == 409, resp.text
    assert "congelado" in resp.text, resp.text

    pipe = _entrenar_pipeline()
    resp = _subir_artefacto(client, version_id, contenido=_onnx_bytes(pipe))
    assert resp.status_code == 422, resp.text
    assert "otra_col" in resp.text
    assert "Traceback" not in resp.text


def test_subida_413_style_limite_200mb(client: TestClient, monkeypatch):
    """No se sube de verdad 200 MB: se baja el límite para el test."""
    _, version_id, _ = _preparar_proyecto_con_baseline(client, "artefacto-limite")
    monkeypatch.setattr(model_registry, "MAX_ARTIFACT_BYTES", 10)
    resp = _subir_artefacto(client, version_id, contenido=_onnx_bytes(_entrenar_pipeline()))
    assert resp.status_code == 422, resp.text
    assert "200 MB" in resp.text


# --- Explicación global y local sobre el modelo subido -----------------


def test_explicacion_global_y_local_sobre_executable(client: TestClient):
    _, version_id, batch_id = _preparar_proyecto_con_baseline(client, "artefacto-explica")
    resp = _subir_artefacto(client, version_id, contenido=_onnx_bytes(_entrenar_pipeline()))
    assert resp.status_code == 200, resp.text

    resp = client.post(
        f"/api/model-versions/{version_id}/explain/global", json={"kind": "shap"}
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    explicacion = job["result"]
    assert explicacion["available"] is True
    nombres = {f["feature"] for f in explicacion["result"]["features"]}
    assert nombres == set(FEATURE_COLS)

    registros = client.get(f"/api/batches/{batch_id}/records").json()["items"]
    fila0 = registros[0]

    resp = client.post(
        f"/api/model-versions/{version_id}/explain/local",
        json={"batch_id": batch_id, "row_seq": fila0["seq"]},
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    explicacion_local = job["result"]
    assert explicacion_local["available"] is True
    assert explicacion_local["kind"] == "local_lime"
    assert 0.0 <= explicacion_local["result"]["prob_favorable"] <= 1.0


def test_explain_409_sin_artefacto_pide_subir_onnx(client: TestClient):
    _, version_id, _ = _preparar_proyecto_con_baseline(client, "artefacto-sin-subir")
    resp = client.post(
        f"/api/model-versions/{version_id}/explain/global", json={"kind": "permutation"}
    )
    assert resp.status_code == 409, resp.text
    assert "ONNX" in resp.text


# --- Pickle solo con confirmación, aviso y sha256 recomprobado -------


def test_pickle_sin_confirmacion_da_422_sin_ejecutarse(client: TestClient):
    _, version_id, _ = _preparar_proyecto_con_baseline(client, "artefacto-pickle-sin-confirmar")
    contenido = io.BytesIO()
    joblib.dump(_entrenar_pipeline(), contenido)

    with mock.patch("pickle.load") as m_pickle, mock.patch.object(
        model_registry.joblib, "load"
    ) as m_joblib:
        resp = _subir_artefacto(
            client,
            version_id,
            contenido=contenido.getvalue(),
            filename="modelo.joblib",
            artifact_kind="pickle",
            confirmacion_pickle=False,
        )
        assert resp.status_code == 422, resp.text
        assert "pickle" in resp.text.lower()
        m_pickle.assert_not_called()
        m_joblib.assert_not_called()


def test_onnx_ruta_por_defecto_nunca_llama_pickle_load_ni_joblib_load(client: TestClient):
    _, version_id, _ = _preparar_proyecto_con_baseline(client, "artefacto-onnx-sin-pickle")
    with mock.patch("pickle.load") as m_pickle, mock.patch.object(
        model_registry.joblib, "load"
    ) as m_joblib:
        resp = _subir_artefacto(client, version_id, contenido=_onnx_bytes(_entrenar_pipeline()))
        assert resp.status_code == 200, resp.text
        m_pickle.assert_not_called()
        m_joblib.assert_not_called()


def test_pickle_con_confirmacion_sube_y_avisa(client: TestClient):
    _, version_id, _ = _preparar_proyecto_con_baseline(
        client,
        "artefacto-pickle-ok",
        csv_bytes=_csv_baseline_pickle(),
        feature_cols=PICKLE_FEATURE_COLS,
    )
    contenido = io.BytesIO()
    joblib.dump(_entrenar_pipeline_pickle(), contenido)

    resp = _subir_artefacto(
        client,
        version_id,
        contenido=contenido.getvalue(),
        filename="modelo.joblib",
        artifact_kind="pickle",
        confirmacion_pickle=True,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["artifact_kind"] == "pickle"
    assert body["avisos"] == [model_registry.AVISO_PICKLE]


def test_pickle_fichero_cambiado_tras_el_alta_da_409_al_cargar(client: TestClient, session: Session):
    _, version_id, _ = _preparar_proyecto_con_baseline(
        client,
        "artefacto-pickle-manipulado",
        csv_bytes=_csv_baseline_pickle(),
        feature_cols=PICKLE_FEATURE_COLS,
    )
    contenido = io.BytesIO()
    joblib.dump(_entrenar_pipeline_pickle(), contenido)
    resp = _subir_artefacto(
        client,
        version_id,
        contenido=contenido.getvalue(),
        filename="modelo.joblib",
        artifact_kind="pickle",
        confirmacion_pickle=True,
    )
    assert resp.status_code == 200, resp.text

    version = session.get(ModelVersion, version_id)
    with open(version.artifact_path, "ab") as f:
        f.write(b"\x00manipulado")

    with mock.patch.object(model_registry.joblib, "load") as m_joblib:
        with pytest.raises(HTTPException) as excinfo:
            model_registry.get_predict_fn(version)
        assert excinfo.value.status_code == 409
        m_joblib.assert_not_called()


# --- Paridad SHAP entre ONNX y joblib, dentro de 1e-6 -----------------


def test_paridad_shap_onnx_vs_joblib_dentro_de_1e6():
    from vigia.core import predict_onnx

    pipe = _entrenar_pipeline()
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "modelo.onnx"
        ruta.write_bytes(_onnx_bytes(pipe))
        session_onnx = predict_onnx.load_session(ruta)
        artifact_inputs = predict_onnx.build_artifact_inputs(session_onnx, FEATURE_COLS)

    predict_fn_onnx = predict_onnx.session_predict_proba(session_onnx, artifact_inputs)
    predict_fn_pickle = model_registry._predict_fn_sklearn(pipe, artifact_inputs)

    X = _TRAIN_DF.copy()
    X["admission_type_id"] = X["admission_type_id"].astype(int)  # como llegaría del CSV

    np.random.seed(2026)
    r_onnx = core_explain.global_shap(predict_fn_onnx, X, X)
    np.random.seed(2026)
    r_pickle = core_explain.global_shap(predict_fn_pickle, X, X)

    assert r_onnx.available, r_onnx.motivo
    assert r_pickle.available, r_pickle.motivo
    imp_onnx = {f.feature: f.importance for f in r_onnx.features}
    imp_pickle = {f.feature: f.importance for f in r_pickle.features}
    assert set(imp_onnx) == set(FEATURE_COLS) == set(imp_pickle)
    for feature, valor in imp_onnx.items():
        assert valor == pytest.approx(imp_pickle[feature], abs=1e-6)


# --- Aviso de pickle anterior a la corrección de tipos ----------


def test_aviso_tipos_antiguos_funcion_pura():
    antes = "2026-09-28T10:00:00.000000+00:00"
    despues = "2026-09-29T00:00:00.000000+00:00"
    assert model_registry.aviso_tipos_antiguos("pickle", antes) == model_registry.AVISO_TIPOS_ANTIGUOS
    assert model_registry.aviso_tipos_antiguos("pickle", despues) is None
    assert model_registry.aviso_tipos_antiguos("onnx", antes) is None
    assert model_registry.aviso_tipos_antiguos("pickle", None) is None
    assert model_registry.aviso_tipos_antiguos(None, antes) is None
    assert "vuelve a subirlo" in model_registry.AVISO_TIPOS_ANTIGUOS


def _subir_pickle(client: TestClient, nombre: str) -> tuple[dict, int]:
    proyecto, version_id, _ = _preparar_proyecto_con_baseline(
        client,
        nombre,
        csv_bytes=_csv_baseline_pickle(),
        feature_cols=PICKLE_FEATURE_COLS,
    )
    contenido = io.BytesIO()
    joblib.dump(_entrenar_pipeline_pickle(), contenido)
    resp = _subir_artefacto(
        client,
        version_id,
        contenido=contenido.getvalue(),
        filename="modelo.joblib",
        artifact_kind="pickle",
        confirmacion_pickle=True,
    )
    assert resp.status_code == 200, resp.text
    return proyecto, version_id


def _version_en_detalle(client: TestClient, proyecto_id: int, version_id: int) -> dict:
    resp = client.get(f"/api/projects/{proyecto_id}")
    assert resp.status_code == 200, resp.text
    return next(v for v in resp.json()["versions"] if v["id"] == version_id)


def test_pickle_reciente_no_lleva_aviso_de_tipos(client: TestClient):
    proyecto, version_id = _subir_pickle(client, "artefacto-pickle-sin-aviso")
    assert _version_en_detalle(client, proyecto["id"], version_id)["aviso_tipos"] is None


def test_pickle_anterior_al_29_sep_lleva_aviso_en_la_version_y_en_la_explicacion(
    client: TestClient, session: Session
):
    proyecto, version_id = _subir_pickle(client, "artefacto-pickle-antiguo")

    version = session.get(ModelVersion, version_id)
    version.artifact_uploaded_at = "2026-09-20T09:00:00.000000+00:00"
    session.add(version)
    session.commit()

    assert (
        _version_en_detalle(client, proyecto["id"], version_id)["aviso_tipos"]
        == model_registry.AVISO_TIPOS_ANTIGUOS
    )

    resp = client.post(
        f"/api/model-versions/{version_id}/explain/global", json={"kind": "permutation"}
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    assert job["result"]["aviso_tipos"] == model_registry.AVISO_TIPOS_ANTIGUOS

    listado = client.get(f"/api/model-versions/{version_id}/explanations").json()["items"]
    assert listado and all(e["aviso_tipos"] == model_registry.AVISO_TIPOS_ANTIGUOS for e in listado)


def test_onnx_antiguo_no_lleva_aviso_de_tipos(client: TestClient, session: Session):
    proyecto, version_id, _ = _preparar_proyecto_con_baseline(client, "artefacto-onnx-sin-aviso")
    assert _subir_artefacto(client, version_id, contenido=_onnx_bytes(_entrenar_pipeline())).status_code == 200
    version = session.get(ModelVersion, version_id)
    version.artifact_uploaded_at = "2026-09-01T09:00:00.000000+00:00"
    session.add(version)
    session.commit()
    assert _version_en_detalle(client, proyecto["id"], version_id)["aviso_tipos"] is None
