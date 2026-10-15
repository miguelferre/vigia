"""Tools de la demo guiada."""

from __future__ import annotations


async def test_run_scenario(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "run_scenario",
            {"scenario_key": "timeline_completo", "with_human": True, "play": True},
        )
    assert not error
    assert resultado["run"]["id"] > 0
    assert resultado["play_job"]["status"] in ("terminado", "en_curso")


async def test_next_phase(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        error, creado = await llamar_tool(
            sesion, "run_scenario", {"scenario_key": "timeline_completo", "play": False}
        )
        assert not error
        error, resultado = await llamar_tool(sesion, "next_phase", {"run_id": creado["id"]})
    assert not error
    assert resultado["status"] in ("terminado", "en_curso")


async def test_lab_generate(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "lab_generate",
            {
                "run_id": proyecto_demo["run_id"],
                "phase_key": "e2_evento",
                "actor": "claude-code-tests",
                "motivo": "laboratorio MCP",
            },
        )
    assert not error
    assert resultado["status"] in ("terminado", "en_curso", "error")
