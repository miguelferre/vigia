"""Una tool por familia deja un evento `actor_kind="agente"` con su `correlation_id`."""

from __future__ import annotations

import uuid

from vigia.mcp import client as mcp_client


async def test_set_monitor_deja_evento_agente(sesion_mcp, proyecto_demo, cliente_http, llamar_tool):
    monitores = await cliente_http.get(f"/api/projects/{proyecto_demo['project_id']}/monitors")
    monitor_id = monitores.json()["items"][0]["id"]
    async with sesion_mcp as sesion:
        error, _resultado = await llamar_tool(
            sesion,
            "set_monitor",
            {"monitor_id": monitor_id, "actor": "claude-code-tests", "motivo": "evento agente", "enabled": True},
        )
    assert not error

    eventos = (
        await cliente_http.get(
            "/api/events", params={"object_type": "monitor", "object_id": monitor_id}
        )
    ).json()["items"]
    agente = next(e for e in eventos if e["actor_kind"] == "agente")
    assert agente["action"] == "monitor.configurado"


async def test_act_on_alert_deja_evento_agente(sesion_mcp, proyecto_demo, cliente_http, llamar_tool, monkeypatch):
    alert_id = proyecto_demo["alert_id"]
    cid_fijo = uuid.uuid4()
    monkeypatch.setattr(mcp_client.uuid, "uuid4", lambda: cid_fijo)
    async with sesion_mcp as sesion:
        error, _resultado = await llamar_tool(
            sesion,
            "act_on_alert",
            {
                "alert_id": alert_id,
                "accion": "acknowledge",
                "actor": "claude-code-tests",
                "motivo": "triaje MCP",
            },
        )
    assert not error
    eventos = (
        await cliente_http.get("/api/events", params={"object_type": "alert", "object_id": alert_id})
    ).json()["items"]
    agente = next(e for e in eventos if e["actor_kind"] == "agente" and e["action"] == "alerta.reconocida")
    assert agente is not None
    assert agente["correlation_id"] == str(cid_fijo)
