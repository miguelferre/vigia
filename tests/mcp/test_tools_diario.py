"""Tools de solo lectura del diario y de ajustes. Junto con las de este
fichero completan las 39 tools; `test_list_tools_exactamente_39` vive aquí
porque es el fichero de la familia de lectura, la última en cargarse."""

from __future__ import annotations

NOMBRES_19_TOOLS = {
    "list_projects",
    "create_project",
    "upload_dataset",
    "set_monitor",
    "set_mapping_template",
    "reset_project",
    "run_evaluation",
    "get_measurements",
    "explain_global",
    "explain_row",
    "get_alerts",
    "act_on_alert",
    "run_scenario",
    "next_phase",
    "lab_generate",
    "run_dossier_review",
    "get_events",
    "export_report",
    "get_settings",
}

# Las 14 tools nuevas; con las 19 anteriores, 33; otras 6 suman 39.
NOMBRES_TOOLS_DIARIO = {
    "upload_usage_log",
    "evaluate_cross",
    "get_cross_latest",
    "get_deskilling",
    "get_overrides",
    "upload_outcomes",
    "get_outcomes",
    "create_dossier",
    "list_risks",
    "create_risk",
    "update_risk",
    "get_threshold_proposal",
    "get_alert",
    "get_job",
}
NOMBRES_TOOLS_R6 = {
    "list_versions",
    "create_version",
    "activate_version",
    "freeze_baseline",
    "upload_model_artifact",
    "compare_versions",
}
NOMBRES_39_TOOLS = NOMBRES_19_TOOLS | NOMBRES_TOOLS_DIARIO | NOMBRES_TOOLS_R6


async def test_list_tools_exactamente_39(sesion_mcp):
    async with sesion_mcp as sesion:
        listado = await sesion.list_tools()
    nombres = {t.name for t in listado.tools}
    assert nombres == NOMBRES_39_TOOLS
    assert len(NOMBRES_TOOLS_DIARIO) == 14
    assert len(NOMBRES_TOOLS_R6) == 6
    assert len(nombres) == 39


async def test_get_events(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion, "get_events", {"project_id": proyecto_demo["project_id"]}
        )
    assert not error
    assert "items" in resultado


async def test_get_settings(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(sesion, "get_settings", {})
    assert not error
    assert "data_dir" in resultado


async def test_export_report_diario(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, _resultado = await llamar_tool(sesion, "export_report", {"kind": "diario"})
    assert not error
