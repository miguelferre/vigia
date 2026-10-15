"""Tools de evaluación, medidas y explicabilidad."""

from __future__ import annotations


async def test_get_measurements(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "get_measurements",
            {
                "project_id": proyecto_demo["project_id"],
                "monitor_type": "fairness",
                "metric_key": "disparate_impact",
            },
        )
    assert not error
    assert "items" in resultado


async def test_run_evaluation(sesion_mcp, proyecto_demo, llamar_tool):
    batches = proyecto_demo["batches"]
    assert batches, "el guion timeline_completo debe dejar al menos un lote"
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion, "run_evaluation", {"batch_id": batches[0]["id"], "timeout_s": 30}
        )
    assert not error
    assert resultado["status"] in ("terminado", "en_curso")


async def test_explain_global(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion, "explain_global", {"version_id": proyecto_demo["version_id"]}
        )
    assert not error
    assert resultado["status"] in ("terminado", "en_curso")


async def test_explain_row(sesion_mcp, proyecto_demo, llamar_tool, cliente_http):
    # Un lote de la versión que se explica (la API rechaza el de otra versión)
    # y su primera fila.
    batches = [b for b in proyecto_demo["batches"] if b["model_version_id"] == proyecto_demo["version_id"]]
    assert batches
    registros = await cliente_http.get(f"/api/batches/{batches[0]['id']}/records?limit=1")
    row_seq = registros.json()["items"][0]["seq"]
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "explain_row",
            {"version_id": proyecto_demo["version_id"], "batch_id": batches[0]["id"], "row_seq": row_seq},
        )
    assert not error, resultado
    assert resultado["status"] in ("terminado", "en_curso")
