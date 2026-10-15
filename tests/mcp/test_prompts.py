"""Los 3 prompts devuelven algo no vacío."""

from __future__ import annotations


def _texto(resultado) -> str:
    return "\n".join(m.content.text for m in resultado.messages if hasattr(m.content, "text"))


async def test_demo_guiada(sesion_mcp):
    async with sesion_mcp as sesion:
        resultado = await sesion.get_prompt("demo_guiada", {})
    assert _texto(resultado)


async def test_diagnostico_de_alerta(sesion_mcp, proyecto_demo):
    async with sesion_mcp as sesion:
        resultado = await sesion.get_prompt(
            "diagnostico_de_alerta", {"alert_id": str(proyecto_demo["alert_id"])}
        )
    assert _texto(resultado)


async def test_informe_semanal(sesion_mcp, proyecto_demo):
    async with sesion_mcp as sesion:
        resultado = await sesion.get_prompt(
            "informe_semanal",
            {
                "project_id": str(proyecto_demo["project_id"]),
                "since": "2020-01-01",
                "until": "2030-01-01",
            },
        )
    assert _texto(resultado)
