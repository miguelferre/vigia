"""Tool de alertas: `get_alerts` y `act_on_alert`."""

from __future__ import annotations


async def test_get_alerts(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(sesion, "get_alerts", {"project_id": proyecto_demo["project_id"]})
    assert not error
    assert "items" in resultado


async def test_act_on_alert_acknowledge(sesion_mcp, proyecto_demo, llamar_tool):
    alert_id = proyecto_demo["alert_id"]
    assert alert_id is not None, "el guion timeline_completo debe dejar al menos una alerta"
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "act_on_alert",
            {
                "alert_id": alert_id,
                "accion": "acknowledge",
                "actor": "claude-code-tests",
                "motivo": "triaje desde el MCP",
            },
        )
    assert not error
    assert resultado["status"] in ("reconocida", "en_observacion")
