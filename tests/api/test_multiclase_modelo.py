"""El modelo ejecutable con `k` clases y la
explicación por clase.

Pickle de una regresión logística multinomial de scikit-learn y, cuando el motor
lo admite, ONNX con `skl2onnx`.
"""

from __future__ import annotations

import io
import time

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api import _datos_multiclase as d
from tests.api.conftest import actor_headers
from vigia.app.models import ModelVersion
from vigia.app.services import model_registry
from vigia.core.schema import TaskSpec

CLASES = d.CLASES
ALFABETICO = sorted(CLASES)


def _proyecto_con_modelo(client: TestClient, nombre: str, *, clases: list[str] | None = None, n: int = 300):
    """Proyecto multiclase con la línea base que produce un modelo real."""
    clases = clases or CLASES
    pipe, filas = d.modelo_y_filas(n, clases=clases)
    p = d.crear_proyecto_multiclase(client, nombre, clases=clases)
    sub = d.subir(client, p["id"], d.a_csv(filas))
    resp = d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase(clases, feature_cols=["longitud", "enlaces"]))
    assert resp.status_code == 200, resp.text
    trabajo = d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])
    assert trabajo["status"] == "terminado", trabajo
    return p, pipe


def _pickle(pipe) -> bytes:
    buf = io.BytesIO()
    joblib.dump(pipe, buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Pickle con k clases
# ---------------------------------------------------------------------------


def test_un_modelo_de_cinco_clases_se_acepta_y_la_version_pasa_a_ejecutable(client: TestClient):
    p, pipe = _proyecto_con_modelo(client, "r4-modelo-ok")
    resp = d.subir_modelo(client, p["active_version_id"], _pickle(pipe), kind="pickle", confirmar=True, nombre="m.pkl")
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["model_kind"] == "executable"
    assert [i["name"] for i in cuerpo["artifact_inputs"]] == ["longitud", "enlaces"]


def test_el_modelo_da_k_columnas_en_el_orden_de_las_clases_del_proyecto(client: TestClient):
    """`modelo.classes_` es alfabético y el proyecto declara otro orden; la
    función de predicción reordena las columnas."""
    p, pipe = _proyecto_con_modelo(client, "r4-modelo-orden")
    assert list(pipe.classes_) == ALFABETICO != CLASES
    assert d.subir_modelo(client, p["active_version_id"], _pickle(pipe), kind="pickle", confirmar=True, nombre="m.pkl").status_code == 200
    task = TaskSpec(task_type="multiclass", classes=tuple(CLASES), favorables=("permitido",))
    with Session(client.app.state.engine) as s:
        version = s.get(ModelVersion, p["active_version_id"])
        predict_fn = model_registry.get_predict_fn(version, task)
    import pandas as pd

    X = pd.DataFrame({"longitud": [30.0, 100.0, 170.0], "enlaces": [0.0, 1.0, 2.0]})
    probs = predict_fn(X)
    assert probs.shape == (3, 5)
    # La primera fila es "permitido" (centro 30) y la columna 0 es la de "permitido".
    assert int(probs[0].argmax()) == 0
    assert int(probs[1].argmax()) == CLASES.index("spam")
    assert probs.sum(axis=1) == pytest.approx([1.0, 1.0, 1.0], abs=1e-6)


def test_un_modelo_con_otras_clases_da_422_con_los_dos_ordenes(client: TestClient):
    p, _pipe = _proyecto_con_modelo(client, "r4-modelo-otras-clases")
    otro, _filas = d.modelo_y_filas(200, clases=["a", "b", "c"])
    resp = d.subir_modelo(client, p["active_version_id"], _pickle(otro), kind="pickle", confirmar=True, nombre="m.pkl")
    assert resp.status_code == 422, resp.text
    assert "(1, 5)" in resp.text or "no son las del proyecto" in resp.text
    # El artefacto vigente no cambia: nada a medias.
    leido = client.get(f"/api/projects/{p['id']}").json()
    assert next(v for v in leido["versions"] if v["id"] == p["active_version_id"])["artifact_kind"] is None


def test_el_argmax_distinto_de_la_linea_base_da_422_con_el_orden_leido_y_el_declarado(
    client: TestClient,
):
    """Un modelo con las mismas clases pero que no es el que dio la línea base."""
    p, _pipe = _proyecto_con_modelo(client, "r4-modelo-otro-modelo")
    otro, _filas = d.modelo_y_filas(200, clases=list(reversed(CLASES)), seed=5)
    resp = d.subir_modelo(client, p["active_version_id"], _pickle(otro), kind="pickle", confirmar=True, nombre="m.pkl")
    assert resp.status_code == 422, resp.text
    texto = resp.text
    assert "99" in texto and "coincide" in texto
    assert "Orden de clases que lee" in texto and "Orden declarado" in texto
    assert "permitido, spam, odio, desnudez, violencia" in texto


def test_el_binario_sigue_pidiendo_dos_probabilidades(client: TestClient):
    """Un proyecto binario con un modelo de tres clases: `(1, 2)` como siempre."""
    from tests.api.test_model_artifacts import (
        PICKLE_FEATURE_COLS,
        _csv_baseline_pickle,
        _preparar_proyecto_con_baseline,
    )

    _proyecto, version_id, _lote = _preparar_proyecto_con_baseline(
        client, "r4-binario-3-clases", csv_bytes=_csv_baseline_pickle(), feature_cols=PICKLE_FEATURE_COLS
    )
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder

    X = pd.DataFrame(
        {"age": [20.0, 30, 40, 50, 60, 70], "workclass": ["privado", "publico", "autonomo"] * 2}
    )
    tres = Pipeline(
        [
            ("ct", ColumnTransformer([("n", "passthrough", ["age"]), ("c", OneHotEncoder(handle_unknown="ignore"), ["workclass"])])),
            ("clf", LogisticRegression()),
        ]
    ).fit(X, ["a", "b", "c", "a", "b", "c"])
    resp = d.subir_modelo(client, version_id, _pickle(tres), kind="pickle", confirmar=True, nombre="m.pkl")
    assert resp.status_code == 422, resp.text
    assert "(1, 2)" in resp.text


class _Lento:
    """Un modelo que tarda más que el límite de la validación."""

    classes_ = np.array(CLASES)

    def predict_proba(self, frame):
        time.sleep(1.5)
        return np.full((len(frame), 5), 0.2)


def test_una_inferencia_que_no_termina_da_422_sin_bloquear(client: TestClient, monkeypatch):
    p, _pipe = _proyecto_con_modelo(client, "r4-modelo-lento")
    monkeypatch.setattr(model_registry, "SEGUNDOS_MAXIMOS_INFERENCIA", 0.2)
    inicio = time.monotonic()
    resp = d.subir_modelo(client, p["active_version_id"], _pickle(_Lento()), kind="pickle", confirmar=True, nombre="m.pkl")
    assert resp.status_code == 422, resp.text
    assert "tarda más de" in resp.text
    # No esperó a que acabara el modelo ni dos veces el límite.
    assert time.monotonic() - inicio < 1.4


# ---------------------------------------------------------------------------
# La clase en los endpoints de explicación
# ---------------------------------------------------------------------------


def _con_modelo_subido(client: TestClient, nombre: str):
    p, pipe = _proyecto_con_modelo(client, nombre)
    resp = d.subir_modelo(client, p["active_version_id"], _pickle(pipe), kind="pickle", confirmar=True, nombre="m.pkl")
    assert resp.status_code == 200, resp.text
    return p


def test_una_clase_que_no_esta_en_el_proyecto_da_422_en_global_y_en_local(client: TestClient):
    p = _con_modelo_subido(client, "r4-explica-422")
    v = p["active_version_id"]
    for ruta, cuerpo in (
        (f"/api/model-versions/{v}/explain/global", {"kind": "permutation", "clase": "inventada"}),
        (f"/api/model-versions/{v}/explain/local", {"batch_id": 1, "row_seq": 0, "clase": "inventada"}),
    ):
        resp = client.post(ruta, json=cuerpo, headers=actor_headers("miguel"))
        assert resp.status_code == 422, resp.text
        assert "inventada" in resp.text and "elige una de ellas" in resp.text


def test_un_proyecto_binario_no_tiene_selector_de_clase(client: TestClient):
    from tests.api.test_model_artifacts import (
        PICKLE_FEATURE_COLS,
        _csv_baseline_pickle,
        _entrenar_pipeline_pickle,
        _preparar_proyecto_con_baseline,
    )

    _proyecto, version_id, _lote = _preparar_proyecto_con_baseline(
        client, "r4-explica-binario", csv_bytes=_csv_baseline_pickle(), feature_cols=PICKLE_FEATURE_COLS
    )
    assert d.subir_modelo(client, version_id, _pickle(_entrenar_pipeline_pickle()), kind="pickle", confirmar=True, nombre="m.pkl").status_code == 200
    resp = client.post(
        f"/api/model-versions/{version_id}/explain/global",
        json={"kind": "permutation", "clase": 1},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422
    assert "proyectos multiclase" in resp.text




def test_la_explicacion_global_por_clase_devuelve_la_clase_explicada(client: TestClient):
    p = _con_modelo_subido(client, "r4-explica-clase")
    v = p["active_version_id"]
    resp = client.post(
        f"/api/model-versions/{v}/explain/global",
        json={"kind": "permutation", "clase": "spam"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.json()
    explicaciones = client.get(f"/api/model-versions/{v}/explanations").json()["items"]
    resultado = explicaciones[0]["result"]
    assert resultado.get("clase_explicada") == "spam"


def test_la_explicacion_local_sin_clase_explica_la_clase_predicha(client: TestClient):
    p = _con_modelo_subido(client, "r4-explica-local")
    v = p["active_version_id"]
    resp = client.post(
        f"/api/model-versions/{v}/explain/local",
        json={"batch_id": 1, "row_seq": 0},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.json()
    resultado = client.get(f"/api/model-versions/{v}/explanations").json()["items"][0]["result"]
    assert resultado.get("clase_explicada") in CLASES
    assert len(resultado.get("probabilities") or []) == 5


# ---------------------------------------------------------------------------
# ONNX con k clases
# ---------------------------------------------------------------------------


def _onnx(pipe, *, zipmap: bool = True) -> bytes:
    pytest.importorskip("skl2onnx", reason="skl2onnx no está instalado")
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType

    opciones = None if zipmap else {id(pipe.steps[-1][1]): {"zipmap": False}}
    return convert_sklearn(
        pipe,
        initial_types=[("longitud", FloatTensorType([None, 1])), ("enlaces", FloatTensorType([None, 1]))],
        options=opciones,
    ).SerializeToString()


@pytest.mark.parametrize("zipmap", [True, False])
def test_un_onnx_de_cinco_clases_se_acepta_aunque_su_orden_no_sea_el_declarado(
    client: TestClient, zipmap: bool
):
    p, pipe = _proyecto_con_modelo(client, f"r4-onnx-ok-{zipmap}")
    assert list(pipe.classes_) == ALFABETICO != CLASES
    resp = d.subir_modelo(client, p["active_version_id"], _onnx(pipe, zipmap=zipmap))
    assert resp.status_code == 200, resp.text
    assert resp.json()["artifact_kind"] == "onnx"
    # La función de predicción da las columnas en el orden del proyecto.
    task = TaskSpec(task_type="multiclass", classes=tuple(CLASES), favorables=("permitido",))
    with Session(client.app.state.engine) as s:
        predict_fn = model_registry.get_predict_fn(s.get(ModelVersion, p["active_version_id"]), task)
    import pandas as pd

    probs = predict_fn(pd.DataFrame({"longitud": [30.0, 100.0], "enlaces": [0.0, 1.0]}))
    assert probs.shape == (2, 5)
    assert int(probs[0].argmax()) == 0 and int(probs[1].argmax()) == CLASES.index("spam")


def test_un_onnx_con_otras_clases_da_422_con_las_dos_listas(client: TestClient):
    p, _pipe = _proyecto_con_modelo(client, "r4-onnx-otras-clases")
    otro, _filas = d.modelo_y_filas(200, clases=["a", "b", "c", "d", "e"])
    resp = d.subir_modelo(client, p["active_version_id"], _onnx(otro))
    assert resp.status_code == 422, resp.text
    assert "a, b, c, d, e" in resp.text and "permitido" in resp.text


def test_un_onnx_de_otro_modelo_con_las_mismas_clases_da_422_por_el_argmax(client: TestClient):
    p, _pipe = _proyecto_con_modelo(client, "r4-onnx-otro-modelo")
    otro, _filas = d.modelo_y_filas(200, clases=list(reversed(CLASES)), seed=5)
    resp = d.subir_modelo(client, p["active_version_id"], _onnx(otro))
    assert resp.status_code == 422, resp.text
    assert "99" in resp.text and "Orden de clases que lee" in resp.text and "Orden declarado" in resp.text
    # Y el artefacto vigente no cambia.
    leido = client.get(f"/api/projects/{p['id']}").json()
    assert next(v for v in leido["versions"] if v["id"] == p["active_version_id"])["artifact_kind"] is None


def test_el_onnx_de_cinco_clases_explica_por_clase(client: TestClient):
    p, pipe = _proyecto_con_modelo(client, "r4-onnx-explica")
    assert d.subir_modelo(client, p["active_version_id"], _onnx(pipe)).status_code == 200
    v = p["active_version_id"]
    resp = client.post(
        f"/api/model-versions/{v}/explain/global",
        json={"kind": "permutation", "clase": "odio"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200 and resp.json()["status"] == "terminado", resp.text
    assert client.get(f"/api/model-versions/{v}/explanations").json()["items"][0]["result"][
        "clase_explicada"
    ] == "odio"


def test_sin_conjunto_favorable_se_explica_la_clase_mayoritaria_de_la_linea_base(client: TestClient):
    from collections import Counter

    pipe, filas = d.modelo_y_filas(300)
    p = d.crear_proyecto_multiclase(client, "r4-explica-sin-favorable", mapping_template=None)
    sub = d.subir(client, p["id"], d.a_csv(filas))
    resp = d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase(favorable_label=[]))
    assert resp.status_code == 200, resp.text
    assert d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])["status"] == "terminado"
    assert d.subir_modelo(client, p["active_version_id"], _pickle(pipe), kind="pickle", confirmar=True, nombre="m.pkl").status_code == 200
    v = p["active_version_id"]
    resp = client.post(
        f"/api/model-versions/{v}/explain/global", json={"kind": "permutation"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200 and resp.json()["status"] == "terminado", resp.text
    mayoritaria = Counter(f["label"] for f in filas).most_common(1)[0][0]
    resultado = client.get(f"/api/model-versions/{v}/explanations").json()["items"][0]["result"]
    assert resultado["clase_explicada"] == mayoritaria


def test_un_tiempo_agotado_no_se_reintenta_con_otra_lectura_de_tipos():
    import time

    from vigia.app.services import model_registry as mr

    with pytest.raises(mr._ErrorSinReintento) as exc:
        mr._con_limite(time.sleep, 2, segundos=0.05)
    assert "más de 0 segundos" in str(exc.value)
    # El error de clases distintas tampoco se reintenta.
    assert issubclass(mr._ErrorSinReintento, mr.ModeloEjecutableInvalido)
