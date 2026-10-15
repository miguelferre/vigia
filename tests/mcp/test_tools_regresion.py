"""El MCP con modelos de regresión, sin tools nuevas
(siguen siendo 39).

Un regresor lineal de horas (`y = 60 + 3 a + 2 b`) con un atributo protegido (`edad`), para que
la línea base tenga etiquetas, grupos y un ONNX que la reproduce.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

N = 400
RANGO = [[40, 81]]
# Medidas de equidad sobre la pertenencia al rango favorable (solo con rango) y medidas de
# error por grupo (con o sin rango).
CLAVES_PERTENENCIA = {"statistical_parity_difference", "average_odds_difference", "impact_score"}
CLAVES_ERROR_GRUPO = {"mean_error_difference", "mean_absolute_error_difference"}


def _regresor() -> tuple[object, pd.DataFrame]:
    from sklearn.linear_model import LinearRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    rng = np.random.default_rng(11)
    a = rng.normal(0, 3, N)
    b = rng.normal(0, 5, N)
    y = 60 + 3 * a + 2 * b + rng.normal(0, 2, N)
    x = pd.DataFrame({"a": a, "b": b})
    pipe = Pipeline([("sc", StandardScaler()), ("reg", LinearRegression())]).fit(x, y)
    pred = pipe.predict(x)
    datos = pd.DataFrame(
        {
            "id": [f"r{i}" for i in range(N)],
            "prediction": np.round(pred, 6),
            "label": np.round(y, 4),
            "a": np.round(a, 4),
            "b": np.round(b, 4),
            "edad": rng.integers(20, 90, N),
        }
    )
    return pipe, datos


def _onnx(pipe) -> bytes:
    pytest.importorskip("skl2onnx", reason="skl2onnx no está instalado en este venv")
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType

    return convert_sklearn(
        pipe, initial_types=[("a", FloatTensorType([None, 1])), ("b", FloatTensorType([None, 1]))]
    ).SerializeToString()


def _onnx_clasificador() -> bytes:
    pytest.importorskip("skl2onnx", reason="skl2onnx no está instalado en este venv")
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    rng = np.random.default_rng(2)
    x = pd.DataFrame({"a": rng.normal(0, 1, 200), "b": rng.normal(0, 1, 200)})
    clf = Pipeline(
        [("ct", ColumnTransformer([("num", StandardScaler(), ["a", "b"])])), ("clf", LogisticRegression())]
    ).fit(x, (x["a"] + x["b"] > 0).astype(int))
    return convert_sklearn(
        clf, initial_types=[("a", FloatTensorType([None, 1])), ("b", FloatTensorType([None, 1]))]
    ).SerializeToString()


MAPEO = {
    "prediction_col": "prediction",
    "label_col": "label",
    "id_col": "id",
    "feature_cols": ["a", "b"],
    "protected_attr_col": "edad",
    "protected_kind": "numeric_ranges",
    "unpriv_groups": [[65, 120]],
    "priv_groups": [[0, 64]],
}


async def _alta(llamar_tool, sesion, nombre: str, **extra) -> dict:
    error, proyecto = await llamar_tool(
        sesion,
        "create_project",
        {"name": nombre, "deployment_stage": "desarrollo", "task_type": "regression", **extra},
    )
    assert not error, proyecto
    return proyecto


async def _linea_base(llamar_tool, sesion, proyecto: dict, tmp_path: Path, datos: pd.DataFrame, mapeo=None):
    csv = tmp_path / "base.csv"
    datos.to_csv(csv, index=False)
    error, subida = await llamar_tool(
        sesion,
        "upload_dataset",
        {"project_id": proyecto["id"], "file_path": str(csv), "kind": "combined", "role": "baseline",
         "mapping": mapeo or MAPEO},
    )
    assert not error, subida
    assert subida["ingest_job"]["status"] == "terminado", subida["ingest_job"]
    return subida


# --- alta y plantilla ----------------------------------------------------------------


async def test_create_project_de_regresion_con_unidad_y_rango(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        proyecto = await _alta(
            llamar_tool, sesion, "reg-alta", target_unit="horas", favorable_ranges=RANGO
        )
    assert proyecto["task_type"] == "regression"
    assert proyecto["target_unit"] == "horas"
    assert proyecto["favorable_ranges"] == [[40.0, 81.0]]
    assert proyecto["favorable_label"] is None


async def test_create_project_de_regresion_sin_rango_es_valido(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        proyecto = await _alta(llamar_tool, sesion, "reg-sin-rango", target_unit="dias")
    assert proyecto["favorable_ranges"] in (None, [])


async def test_unidad_y_rango_tambien_van_en_la_plantilla_y_set_mapping_template_los_acepta(
    sesion_mcp, llamar_tool
):
    async with sesion_mcp as sesion:
        proyecto = await _alta(
            llamar_tool, sesion, "reg-plantilla",
            mapping_template={"prediction_col": "prediction", "target_unit": "horas",
                              "favorable_ranges": RANGO},
        )
        assert proyecto["target_unit"] == "horas"
        error, parchado = await llamar_tool(
            sesion, "set_mapping_template",
            {"project_id": proyecto["id"], "motivo": "mision",
             "mapping_template": {"prediction_col": "prediction", "label_col": "label",
                                  "target_unit": "dias", "favorable_ranges": [[0, 10], [20, None]]}},
        )
    assert not error, parchado


async def test_un_favorable_label_en_regresion_da_422_que_nombra_el_campo(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(
            sesion, "create_project",
            {"name": "reg-fav", "deployment_stage": "desarrollo", "task_type": "regression",
             "favorable_label": "alto"},
        )
    assert error
    assert "favorable_label" in str(texto)


# --- propuesta de umbrales -----------------------------------------------------------


async def test_la_propuesta_de_regresion_con_rango_trae_error_deriva_y_equidad(
    sesion_mcp, llamar_tool, tmp_path
):
    _pipe, datos = _regresor()
    async with sesion_mcp as sesion:
        proyecto = await _alta(
            llamar_tool, sesion, "reg-propuesta", target_unit="horas", favorable_ranges=RANGO
        )
        await _linea_base(llamar_tool, sesion, proyecto, tmp_path, datos)
        error, propuesta = await llamar_tool(sesion, "get_threshold_proposal", {"project_id": proyecto["id"]})
    assert not error, propuesta
    por_monitor = {m["monitor_type"]: m["propuestas"] for m in propuesta["monitors"]}
    claves_calidad = {p["metric_key"] for p in por_monitor["quality"]}
    assert {"mean_absolute_error", "root_mean_squared_error", "r2", "mean_error"} <= claves_calidad
    assert "prediction_drift_score" in {p["metric_key"] for p in por_monitor["drift"]}
    # Con rango, la equidad sobre la pertenencia tiene propuesta.
    claves_equidad = {p["metric_key"] for p in por_monitor["fairness"]}
    assert CLAVES_PERTENENCIA <= claves_equidad, claves_equidad
    assert CLAVES_ERROR_GRUPO <= claves_equidad, claves_equidad
    # Forma de siempre: las filas llevan el umbral de hoy y su origen.
    assert all("origen_actual" in p and "value" in p for p in por_monitor["quality"])


async def test_la_propuesta_de_regresion_sin_rango_no_lista_equidad_por_pertenencia(
    sesion_mcp, llamar_tool, tmp_path
):
    """Sin rango el atributo protegido sigue ahí: la equidad lista solo el error por grupo."""
    _pipe, datos = _regresor()
    async with sesion_mcp as sesion:
        proyecto = await _alta(llamar_tool, sesion, "reg-propuesta-sin-rango", target_unit="horas")
        await _linea_base(llamar_tool, sesion, proyecto, tmp_path, datos)
        error, propuesta = await llamar_tool(sesion, "get_threshold_proposal", {"project_id": proyecto["id"]})
    assert not error, propuesta
    por_monitor = {m["monitor_type"]: m["propuestas"] for m in propuesta["monitors"]}
    assert "quality" in por_monitor
    claves_equidad = {p["metric_key"] for p in por_monitor["fairness"]}
    assert CLAVES_ERROR_GRUPO <= claves_equidad, claves_equidad
    assert not (CLAVES_PERTENENCIA & claves_equidad), claves_equidad


# --- medidas y explicabilidad --------------------------------------------------------


async def test_las_tools_de_medidas_y_explicabilidad_documentan_la_regresion(sesion_mcp):
    async with sesion_mcp as sesion:
        tools = {t.name: t.description or "" for t in (await sesion.list_tools()).tools}
    assert "unidad del proyecto" in tools["get_measurements"]
    assert "unpriv" in tools["get_measurements"]
    assert "prediction_value" in tools["explain_row"]
    assert "regresión" in tools["explain_row"] and "clase" in tools["explain_row"]
    assert "REGRESIÓN" in tools["explain_global"]


async def test_explain_row_rechaza_clase_en_regresion_y_devuelve_prediction_value(
    sesion_mcp, llamar_tool, tmp_path
):
    pipe, datos = _regresor()
    onnx = tmp_path / "regresor.onnx"
    onnx.write_bytes(_onnx(pipe))
    async with sesion_mcp as sesion:
        proyecto = await _alta(
            llamar_tool, sesion, "reg-explica", target_unit="horas", favorable_ranges=RANGO
        )
        subida = await _linea_base(llamar_tool, sesion, proyecto, tmp_path, datos)
        batch_id = subida["ingest_job"]["result"]["batch_id"]
        error, versiones = await llamar_tool(sesion, "list_versions", {"project_id": proyecto["id"]})
        assert not error, versiones
        version_id = versiones["versions"][0]["id"]
        error, artefacto = await llamar_tool(
            sesion, "upload_model_artifact", {"version_id": version_id, "file_path": str(onnx)}
        )
        assert not error, artefacto
        error, con_clase = await llamar_tool(
            sesion, "explain_row",
            {"version_id": version_id, "batch_id": batch_id, "row_seq": 0, "clase": 1},
        )
        assert error
        assert "regresión" in str(con_clase)
        error, local = await llamar_tool(
            sesion, "explain_row", {"version_id": version_id, "batch_id": batch_id, "row_seq": 0}
        )
    assert not error, local
    texto = str(local)
    assert "prediction_value" in texto


# --- modelo ejecutable -----------------------------------------------------------------


async def test_un_clasificador_en_un_proyecto_de_regresion_da_el_mensaje_de_modelo_ejecutable(
    sesion_mcp, llamar_tool, tmp_path
):
    _pipe, datos = _regresor()
    onnx = tmp_path / "clasificador.onnx"
    onnx.write_bytes(_onnx_clasificador())
    async with sesion_mcp as sesion:
        proyecto = await _alta(llamar_tool, sesion, "reg-clasificador", target_unit="horas")
        await _linea_base(llamar_tool, sesion, proyecto, tmp_path, datos)
        _e, versiones = await llamar_tool(sesion, "list_versions", {"project_id": proyecto["id"]})
        error, texto = await llamar_tool(
            sesion, "upload_model_artifact",
            {"version_id": versiones["versions"][0]["id"], "file_path": str(onnx)},
        )
    assert error
    assert "clasificador" in str(texto)


async def test_un_regresor_que_no_reproduce_la_linea_base_da_la_mediana_de_la_diferencia(
    sesion_mcp, llamar_tool, tmp_path
):
    """El ONNX es un regresor, pero sus cifras no coinciden con la línea base: 422 con la
    mediana de la diferencia."""
    from sklearn.linear_model import LinearRegression

    pipe, datos = _regresor()
    otro = pipe.__class__(pipe.steps).fit(datos[["a", "b"]], datos["label"] + 25.0)
    assert isinstance(otro.steps[-1][1], LinearRegression)
    onnx = tmp_path / "otro_regresor.onnx"
    onnx.write_bytes(_onnx(otro))
    async with sesion_mcp as sesion:
        proyecto = await _alta(llamar_tool, sesion, "reg-mediana", target_unit="horas")
        await _linea_base(llamar_tool, sesion, proyecto, tmp_path, datos)
        _e, versiones = await llamar_tool(sesion, "list_versions", {"project_id": proyecto["id"]})
        error, texto = await llamar_tool(
            sesion, "upload_model_artifact",
            {"version_id": versiones["versions"][0]["id"], "file_path": str(onnx)},
        )
    assert error
    assert "mediana" in str(texto)


async def test_un_regresor_en_un_proyecto_de_clasificacion_da_el_mensaje_de_modelo_ejecutable(
    sesion_mcp, llamar_tool, tmp_path
):
    pipe, datos = _regresor()
    onnx = tmp_path / "regresor.onnx"
    onnx.write_bytes(_onnx(pipe))
    binario = datos.assign(
        prediction=(datos["prediction"] > 40).astype(int), label=(datos["label"] > 40).astype(int)
    )
    async with sesion_mcp as sesion:
        error, proyecto = await llamar_tool(
            sesion, "create_project", {"name": "bin-regresor", "deployment_stage": "desarrollo"}
        )
        assert not error, proyecto
        await _linea_base(
            llamar_tool, sesion, proyecto, tmp_path, binario, {**MAPEO, "favorable_label": 1}
        )
        _e, versiones = await llamar_tool(sesion, "list_versions", {"project_id": proyecto["id"]})
        error, texto = await llamar_tool(
            sesion, "upload_model_artifact",
            {"version_id": versiones["versions"][0]["id"], "file_path": str(onnx)},
        )
    assert error
    assert "regresor" in str(texto)


async def test_las_fichas_de_las_tools_de_la_capa_humana_y_del_modelo_hablan_de_regresion(sesion_mcp):
    async with sesion_mcp as sesion:
        tools = {t.name: t.description or "" for t in (await sesion.list_tools()).tools}
    assert "cifras" in tools["upload_usage_log"]
    assert "rango favorable" in tools["upload_usage_log"]
    assert "es un clasificador" in tools["upload_model_artifact"]
    assert "es un regresor" in tools["upload_model_artifact"]
    assert "favorable_ranges" in tools["create_project"]
    assert "target_unit" in tools["upload_dataset"]
    assert "cambios" in tools["get_overrides"]
    assert "diferencia_media" in tools["get_overrides"]


async def test_ninguna_ficha_dice_que_la_regresion_llega_despues(sesion_mcp):
    """Quita de las docstrings todo lo que diga que la API rechaza `regression` o que la
    regresión «llega en una versión futura», y la equidad multiclase sin propuesta."""
    async with sesion_mcp as sesion:
        tools = (await sesion.list_tools()).tools
    for t in tools:
        d = t.description or ""
        assert "llega en R" not in d, t.name
        assert "aún no está disponible" not in d, t.name
        assert "no tiene propuesta desde la línea base" not in d, t.name


# --- siguen 39 ---------------------------------------------------------------------------


async def test_siguen_39_tools(sesion_mcp):
    async with sesion_mcp as sesion:
        nombres = {t.name for t in (await sesion.list_tools()).tools}
    assert len(nombres) == 39
    assert "get_overrides" in nombres


def test_docs_mcp_documenta_los_parametros_y_valores_nuevos():
    doc = (Path(__file__).resolve().parents[2] / "docs" / "mcp.md").read_text(encoding="utf-8")
    for pieza in ("target_unit", "favorable_ranges", 'by="cambios"', "diferencia_media", "prediction_value",
                  "es un clasificador", "## Modelos de regresión"):
        assert pieza in doc, pieza
    assert "llega en R" not in doc
