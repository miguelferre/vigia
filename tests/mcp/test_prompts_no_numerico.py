"""`paso`, `alert_id` y `project_id` de los 3 prompts (`prompts.py`) se
declaran `int`/`int | None`, pero el protocolo MCP entrega los argumentos de
un prompt siempre como `str` (`test_prompts.py` ya llama con `str(...)`).
Diagnóstico, no arreglo: no se toca `src/vigia/mcp/` (fuera de esta frontera).
"""

from __future__ import annotations

import pytest
from mcp.shared.exceptions import McpError


async def test_diagnostico_de_alerta_con_alert_id_no_numerico(sesion_mcp):
    async with sesion_mcp as sesion:
        with pytest.raises(McpError) as excinfo:
            await sesion.get_prompt("diagnostico_de_alerta", {"alert_id": "no-es-un-numero"})
    # FastMCP valida el argumento contra el type hint (pydantic) antes de
    # llamar a la función y traduce el fallo a un `McpError` de protocolo
    # (no una excepción Python sin más ni un resultado con `isError=True`).
    # El mensaje SÍ es claro: nombra el campo y por qué falla.
    mensaje = str(excinfo.value)
    assert "alert_id" in mensaje
    assert "no-es-un-numero" in mensaje or "valid integer" in mensaje.lower()


async def test_informe_semanal_con_project_id_no_numerico(sesion_mcp):
    async with sesion_mcp as sesion:
        with pytest.raises(McpError) as excinfo:
            await sesion.get_prompt(
                "informe_semanal",
                {"project_id": "no-es-un-numero", "since": "2020-01-01", "until": "2030-01-01"},
            )
    assert "project_id" in str(excinfo.value)


async def test_demo_guiada_con_paso_no_numerico(sesion_mcp):
    """`paso` es `int | None`: mismo diagnóstico que los dos anteriores."""
    async with sesion_mcp as sesion:
        with pytest.raises(McpError) as excinfo:
            await sesion.get_prompt("demo_guiada", {"paso": "no-es-un-numero"})
    assert "paso" in str(excinfo.value)
