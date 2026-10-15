"""Arreglos del MCP en regresión."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

N = 400
MAPEO = {
    "prediction_col": "prediction",
    "label_col": "label",
    "id_col": "id",
    "feature_cols": ["a", "b"],
}


def _datos(n: int = N, desde: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(5 + desde)
    a = rng.normal(0, 3, n)
    b = rng.normal(0, 5, n)
    y = 60 + 3 * a + 2 * b + rng.normal(0, 2, n)
    return pd.DataFrame(
        {
            "id": [f"r{desde + i}" for i in range(n)],
            "prediction": np.round(60 + 3 * a + 2 * b, 4),
            "label": np.round(y, 4),
            "a": np.round(a, 4),
            "b": np.round(b, 4),
        }
    )


async def _alta(llamar_tool, sesion, nombre: str, tipo: str, **extra) -> dict:
    error, proyecto = await llamar_tool(
        sesion,
        "create_project",
        {"name": nombre, "deployment_stage": "desarrollo", "task_type": tipo, **extra},
    )
    assert not error, proyecto
    return proyecto


async def _subir(llamar_tool, sesion, proyecto, ruta: Path, datos, **args):
    datos.to_csv(ruta, index=False)
    error, resp = await llamar_tool(
        sesion,
        "upload_dataset",
        {"project_id": proyecto["id"], "file_path": str(ruta), **args},
    )
    assert not error, resp
    return resp


# --- la unidad en las respuestas de medidas y de propuesta ------------------------------


async def test_regresion_con_unidad_la_trae_en_medidas_y_propuesta(
    sesion_mcp, llamar_tool, tmp_path
):
    async with sesion_mcp as sesion:
        proyecto = await _alta(llamar_tool, sesion, "m-unidad", "regression", target_unit="horas")
        await _subir(llamar_tool, sesion, proyecto, tmp_path / "base.csv", _datos(),
                     kind="combined", role="baseline", mapping=MAPEO)
        error, medidas = await llamar_tool(
            sesion, "get_measurements",
            {"project_id": proyecto["id"], "monitor_type": "quality", "metric_key": "mean_absolute_error"},
        )
        assert not error, medidas
        error, propuesta = await llamar_tool(sesion, "get_threshold_proposal", {"project_id": proyecto["id"]})
        assert not error, propuesta
    assert medidas["unidad"] == "horas"
    assert propuesta["unidad"] == "horas"


async def test_regresion_sin_unidad_la_trae_como_null(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        proyecto = await _alta(llamar_tool, sesion, "m-sin-unidad", "regression")
        error, medidas = await llamar_tool(
            sesion, "get_measurements",
            {"project_id": proyecto["id"], "monitor_type": "quality", "metric_key": "mean_absolute_error"},
        )
    assert not error, medidas
    assert "unidad" in medidas and medidas["unidad"] is None


async def test_clasificacion_no_trae_el_campo(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        proyecto = await _alta(llamar_tool, sesion, "m-binario", "binary")
        error, medidas = await llamar_tool(
            sesion, "get_measurements",
            {"project_id": proyecto["id"], "monitor_type": "quality", "metric_key": "accuracy"},
        )
    assert not error, medidas
    assert "unidad" not in medidas


async def test_docstrings_dicen_la_unidad(sesion_mcp):
    async with sesion_mcp as sesion:
        tools = {t.name: t.description or "" for t in (await sesion.list_tools()).tools}
        assert len(tools) == 39
    assert "`unidad`" in tools["get_measurements"]
    assert "`unidad`" in tools["get_threshold_proposal"]


# --- etiquetas tardías en el MCP --------------------------------------------------------


async def test_upload_dataset_de_etiquetas_sube_los_lotes_al_primer_nivel(
    sesion_mcp, llamar_tool, tmp_path
):
    async with sesion_mcp as sesion:
        proyecto = await _alta(llamar_tool, sesion, "m-tardias", "regression", target_unit="horas")
        await _subir(llamar_tool, sesion, proyecto, tmp_path / "base.csv", _datos(),
                     kind="combined", role="baseline", mapping=MAPEO)
        lote = _datos(120, desde=1000)
        sin_verdad = lote.drop(columns=["label"])
        mapa_lote = {k: v for k, v in MAPEO.items() if k != "label_col"}
        await _subir(llamar_tool, sesion, proyecto, tmp_path / "lote.csv", sin_verdad,
                     kind="payload", role="production", mapping=mapa_lote)
        etiquetas = lote[["id", "label"]]
        resp = await _subir(llamar_tool, sesion, proyecto, tmp_path / "etiquetas.csv", etiquetas,
                            kind="feedback", role="production",
                            mapping={"id_col": "id", "label_col": "label"})
    for campo in ("lotes_con_verdad", "lotes_reevaluados", "lotes_a_reevaluar"):
        assert campo in resp, resp
    assert len(resp["lotes_con_verdad"]) == 1
    # Con `evaluate` por defecto la API reevalúa; si no, dice cuáles faltan.
    assert resp["lotes_reevaluados"] == resp["lotes_con_verdad"] or resp["lotes_a_reevaluar"] == resp[
        "lotes_con_verdad"
    ]


async def test_un_dataset_que_no_es_de_etiquetas_no_trae_los_campos(sesion_mcp, llamar_tool, tmp_path):
    async with sesion_mcp as sesion:
        proyecto = await _alta(llamar_tool, sesion, "m-sin-tardias", "regression", target_unit="horas")
        resp = await _subir(llamar_tool, sesion, proyecto, tmp_path / "base.csv", _datos(),
                            kind="combined", role="baseline", mapping=MAPEO)
    assert "lotes_con_verdad" not in resp


async def test_el_docstring_dice_que_hacer_sin_reevaluar(sesion_mcp):
    async with sesion_mcp as sesion:
        tools = {t.name: t.description or "" for t in (await sesion.list_tools()).tools}
    texto = tools["upload_dataset"]
    assert "lotes_a_reevaluar" in texto and "run_evaluation" in texto


# --- unidad y rango desde la plantilla --------------------------------------------------


async def test_la_plantilla_fija_unidad_y_rango_antes_de_congelar(sesion_mcp, llamar_tool, tmp_path):
    async with sesion_mcp as sesion:
        proyecto = await _alta(llamar_tool, sesion, "m-plantilla", "regression")
        assert proyecto["target_unit"] is None
        error, _ = await llamar_tool(
            sesion, "set_mapping_template",
            {"project_id": proyecto["id"], "motivo": "fijar unidad y rango",
             "mapping_template": {**MAPEO, "target_unit": "horas", "favorable_ranges": [[40, 81]]}},
        )
        assert not error
        await _subir(llamar_tool, sesion, proyecto, tmp_path / "base.csv", _datos(),
                     kind="combined", role="baseline")
        error, medidas = await llamar_tool(
            sesion, "get_measurements",
            {"project_id": proyecto["id"], "monitor_type": "quality", "metric_key": "mean_absolute_error"},
        )
        assert not error, medidas
        error, propuesta = await llamar_tool(sesion, "get_threshold_proposal", {"project_id": proyecto["id"]})
        assert not error, propuesta
    assert medidas["unidad"] == "horas"
    assert propuesta["unidad"] == "horas"


def test_docs_mcp_lo_documenta():
    texto = (Path(__file__).resolve().parents[2] / "docs" / "mcp.md").read_text(encoding="utf-8")
    assert "set_mapping_template" in texto and "cambiarlos después da 409" in texto
    assert "lotes_a_reevaluar" in texto and "`unidad`" in texto


async def test_despues_de_congelar_la_unidad_ya_no_se_fija(sesion_mcp, llamar_tool, tmp_path):
    """Una línea base sin unidad ni rango queda así: fijarlos después da 409."""
    async with sesion_mcp as sesion:
        proyecto = await _alta(llamar_tool, sesion, "m-tarde", "regression")
        await _subir(llamar_tool, sesion, proyecto, tmp_path / "base.csv", _datos(),
                     kind="combined", role="baseline", mapping=MAPEO)
        error, texto = await llamar_tool(
            sesion, "set_mapping_template",
            {"project_id": proyecto["id"], "motivo": "tarde",
             "mapping_template": {**MAPEO, "target_unit": "horas"}},
        )
    assert error
    assert "409" in str(texto) or "congel" in str(texto).lower()
