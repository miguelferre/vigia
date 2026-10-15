"""Tool de auditoría: `run_dossier_review`."""

from __future__ import annotations


async def test_run_dossier_review(sesion_mcp, proyecto_demo, cliente_http, llamar_tool):
    creado = await cliente_http.post(
        f"/api/projects/{proyecto_demo['project_id']}/dossiers",
        json={
            "actor": "claude-code-tests",
            "motivo": "dossier de prueba MCP",
            "profile": {"objetivo": "prueba del servidor MCP"},
        },
        headers={"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"},
    )
    assert creado.status_code == 200, creado.text
    dossier_id = creado.json()["id"]

    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "run_dossier_review",
            {
                "dossier_id": dossier_id,
                "actor": "claude-code-tests",
                "motivo": "revisión MCP",
                "approach": "b0",
            },
        )
    assert not error
    assert resultado["status"] in ("terminado", "en_curso", "error")
