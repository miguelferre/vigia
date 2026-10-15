"""`upload_model_artifact` (error y camino feliz) y `compare_versions`."""

from __future__ import annotations

import numpy as np
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType
from sklearn.linear_model import LogisticRegression

CSV = (
    "id,prediction,label,Age\n"
    + "".join(f"{i},{i % 2},{(i + (i % 3 == 0)) % 2},{30 + i}\n" for i in range(1, 41))
).encode()
MAPEO = {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "feature_cols": ["Age"],
         "favorable_label": 1}


def _onnx_pequeno() -> bytes:
    """Regresión logística de una columna numérica `Age`, convertida a ONNX."""
    x = np.array([[25.0], [40.0], [55.0], [30.0], [60.0], [22.0], [48.0], [33.0]], dtype=np.float32)
    modelo = LogisticRegression().fit(x, [0, 1, 0, 1, 0, 1, 0, 1])
    onx = convert_sklearn(modelo, initial_types=[("Age", FloatTensorType([None, 1]))])
    return onx.SerializeToString()


async def _proyecto(llamar_tool, sesion, nombre: str = "modelo-mcp") -> dict:
    error, proyecto = await llamar_tool(
        sesion, "create_project", {"name": nombre, "deployment_stage": "validacion"}
    )
    assert not error, proyecto
    return proyecto


async def test_upload_model_artifact_onnx_camino_feliz(sesion_mcp, llamar_tool, tmp_path):
    csv = tmp_path / "base.csv"
    csv.write_bytes(CSV)
    onnx = tmp_path / "modelo.onnx"
    onnx.write_bytes(_onnx_pequeno())
    async with sesion_mcp as sesion:
        proyecto = await _proyecto(llamar_tool, sesion)
        version_id = proyecto["active_version_id"]
        error, subida = await llamar_tool(
            sesion,
            "upload_dataset",
            {"project_id": proyecto["id"], "file_path": str(csv), "kind": "combined",
             "role": "baseline", "mapping": MAPEO},
        )
        assert not error, subida
        error, artefacto = await llamar_tool(
            sesion, "upload_model_artifact", {"version_id": version_id, "file_path": str(onnx)}
        )
        assert not error, artefacto
        _e, lista = await llamar_tool(sesion, "list_versions", {"project_id": proyecto["id"]})
    assert artefacto["artifact_kind"] == "onnx"
    assert artefacto["model_kind"] == "executable"
    assert len(artefacto["artifact_sha256"]) == 64
    assert [i["name"] for i in artefacto["artifact_inputs"]] == ["Age"]
    assert artefacto["artifact_inputs"][0]["kind"] == "numerica"
    (v1,) = lista["versions"]
    assert v1["artifact_kind"] == "onnx" and v1["artifact_uploaded_at"]


async def test_upload_model_artifact_pickle_exige_confirmacion(sesion_mcp, llamar_tool, tmp_path):
    pkl = tmp_path / "modelo.joblib"
    pkl.write_bytes(b"no es un modelo")
    async with sesion_mcp as sesion:
        proyecto = await _proyecto(llamar_tool, sesion)
        args = {"version_id": proyecto["active_version_id"], "file_path": str(pkl)}
        error, texto = await llamar_tool(sesion, "upload_model_artifact", args)
        assert error and "confirm_pickle=true" in str(texto)
        # Con la confirmación la tool sí llama a la API, que rechaza un fichero que no es un pickle.
        error, texto = await llamar_tool(sesion, "upload_model_artifact", {**args, "confirm_pickle": True})
    assert error
    assert str(texto)[:3].isdigit(), texto  # error de la API, con su código por delante


async def test_upload_model_artifact_tipo_desconocido(sesion_mcp, llamar_tool, tmp_path):
    raro = tmp_path / "modelo.bin"
    raro.write_bytes(b"x")
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(
            sesion, "upload_model_artifact", {"version_id": 1, "file_path": str(raro)}
        )
    assert error and "artifact_kind" in str(texto)


async def test_compare_versions(sesion_mcp, llamar_tool, tmp_path):
    csv = tmp_path / "datos.csv"
    csv.write_bytes(CSV)
    async with sesion_mcp as sesion:
        proyecto = await _proyecto(llamar_tool, sesion)
        v1 = proyecto["active_version_id"]
        error, v2 = await llamar_tool(
            sesion,
            "create_version",
            {"project_id": proyecto["id"], "label": "v2", "motivo": "reentrenado con datos nuevos"},
        )
        assert not error, v2
        for version in (v1, v2["id"]):
            for rol in ("baseline", "production"):
                error, subida = await llamar_tool(
                    sesion,
                    "upload_dataset",
                    {"project_id": proyecto["id"], "file_path": str(csv), "kind": "combined",
                     "role": rol, "mapping": MAPEO, "model_version_id": version},
                )
                assert not error, subida
        error, comparacion = await llamar_tool(
            sesion, "compare_versions", {"project_id": proyecto["id"], "a": v1, "b": v2["id"]}
        )
    assert not error, comparacion
    assert comparacion["version_a"]["id"] == v1
    assert comparacion["version_b"]["id"] == v2["id"]
    assert {"filas", "alertas_vivas", "nota_alertas"} <= set(comparacion)
    assert comparacion["filas"], comparacion
    assert all(f["direccion"] in {"mejora", "empeora", "igual", "sin_datos"} for f in comparacion["filas"])
