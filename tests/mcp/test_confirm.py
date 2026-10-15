"""`act_on_alert(accion="close")` y `reset_project` exigen `confirm=true` (acciones destructivas)."""

from __future__ import annotations


async def test_close_sin_confirm_falla_antes_de_llamar_a_la_api(sesion_mcp, proyecto_demo, cliente_http, llamar_tool):
    alert_id = proyecto_demo["alert_id"]
    assert alert_id is not None
    async with sesion_mcp as sesion:
        error, _resultado = await llamar_tool(
            sesion,
            "act_on_alert",
            {"alert_id": alert_id, "accion": "close", "actor": "claude-code-tests", "motivo": "sin confirmar"},
        )
    assert error
    alerta = (await cliente_http.get(f"/api/alerts/{alert_id}")).json()
    assert alerta["status"] != "cerrada"


async def test_close_con_confirm_cierra(sesion_mcp, proyecto_demo, llamar_tool):
    alert_id = proyecto_demo["alert_id"]
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "act_on_alert",
            {
                "alert_id": alert_id,
                "accion": "close",
                "actor": "claude-code-tests",
                "motivo": "cierre confirmado",
                "confirm": True,
            },
        )
    assert not error
    assert resultado["status"] == "cerrada"


async def test_reset_project_sin_confirm_falla_antes_de_llamar_a_la_api(
    sesion_mcp, proyecto_demo, cliente_http, llamar_tool
):
    """`reset_project` exige `confirm=true` como `close`."""
    project_id = proyecto_demo["project_id"]
    async with sesion_mcp as sesion:
        error, _resultado = await llamar_tool(
            sesion,
            "reset_project",
            {"project_id": project_id, "actor": "claude-code-tests", "motivo": "sin confirmar"},
        )
    assert error
    lotes = (await cliente_http.get(f"/api/projects/{project_id}/batches")).json()["items"]
    assert lotes
    eventos = (
        await cliente_http.get("/api/events", params={"object_type": "project", "object_id": project_id})
    ).json()["items"]
    assert not [e for e in eventos if e["action"] == "proyecto.reiniciado"]


async def test_reset_project_con_confirm_deja_el_proyecto_virgen(
    sesion_mcp, proyecto_demo, cliente_http, llamar_tool
):
    project_id = proyecto_demo["project_id"]
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "reset_project",
            {
                "project_id": project_id,
                "actor": "claude-code-tests",
                "motivo": "empezar de nuevo con otro mapeo",
                "confirm": True,
            },
        )
    assert not error, resultado
    assert resultado["project_id"] == project_id
    assert resultado["deleted"]["batches"] > 0
    assert (await cliente_http.get(f"/api/projects/{project_id}/batches")).json()["items"] == []
    # Conserva el proyecto y sus monitores.
    assert (await cliente_http.get(f"/api/projects/{project_id}")).status_code == 200
    assert (await cliente_http.get(f"/api/projects/{project_id}/monitors")).json()["items"]
    eventos = (
        await cliente_http.get("/api/events", params={"object_type": "project", "object_id": project_id})
    ).json()["items"]
    agente = next(e for e in eventos if e["actor_kind"] == "agente" and e["action"] == "proyecto.reiniciado")
    assert agente["actor_id"] == "claude-code-tests"


async def test_reset_project_esta_marcada_como_destructiva(sesion_mcp):
    async with sesion_mcp as sesion:
        listado = await sesion.list_tools()
    herramienta = next(t for t in listado.tools if t.name == "reset_project")
    assert herramienta.annotations is not None
    assert herramienta.annotations.destructiveHint is True
