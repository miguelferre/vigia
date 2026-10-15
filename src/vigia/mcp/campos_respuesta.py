"""Campos que las tools del MCP suben al primer nivel de la respuesta.

- `unidad`: la `target_unit` del proyecto en las respuestas de medidas y de
  propuesta de umbrales de un proyecto de regresión. En clasificación no sale.
- Etiquetas tardías: `lotes_con_verdad`, `lotes_reevaluados`,
  `lotes_a_reevaluar` y `evaluate_motivo`, que la API da al ingerir un fichero de
  etiquetas. Se leen como diccionario, sin depender del esquema de la API.
"""

from __future__ import annotations

from typing import Any

from vigia.mcp.client import get_client

CAMPOS_TARDIOS = ("lotes_con_verdad", "lotes_reevaluados", "lotes_a_reevaluar", "evaluate_motivo")


async def con_unidad(project_id: int, respuesta: dict[str, Any]) -> dict[str, Any]:
    """Añade `unidad` (la `target_unit` o `null`) si el proyecto es de regresión."""
    proyecto = await get_client().get(f"/projects/{project_id}")
    if not isinstance(proyecto, dict):
        return respuesta
    match proyecto.get("task_type"):
        case "regression":
            respuesta["unidad"] = proyecto.get("target_unit") or None
        case "binary" | "multiclass" | None:
            pass
        case otro:
            raise ValueError(f"tipo de tarea desconocido: {otro!r}")
    return respuesta


def con_campos_tardios(respuesta: dict[str, Any], origen: Any) -> dict[str, Any]:
    """Copia al primer nivel los campos de etiquetas tardías que traiga `origen`."""
    if isinstance(origen, dict):
        for campo in CAMPOS_TARDIOS:
            if campo in origen:
                respuesta[campo] = origen[campo]
    return respuesta
