"""Los 7 resources del servidor MCP. Solo lectura: el
cliente MCP los lee, no los invoca; espejan `content/` y la API por HTTP."""

from __future__ import annotations

from vigia.mcp.client import get_client


def registrar(mcp) -> None:
    @mcp.resource("schema://tables", title="Esquema de la base de datos")
    async def schema_tables() -> dict:
        """El esquema de la base de datos, introspeccionado en vivo."""
        return await get_client().get("/schema/tables")

    @mcp.resource("glossary://", title="Glosario")
    async def glossary() -> dict:
        """El glosario de conceptos no métricos."""
        return await get_client().get("/content/glosario")

    @mcp.resource("metrics-help://{metric}", title="Ayuda de una métrica")
    async def metrics_help(metric: str) -> dict:
        """La ayuda de una métrica: qué mide y su fórmula."""
        todas = await get_client().get("/content/metricas")
        if metric not in todas:
            raise ValueError(f"métrica no reconocida: {metric!r}")
        return todas[metric]

    @mcp.resource("state://project/{id}", title="Estado de un proyecto")
    async def project_state(id: str) -> dict:
        """Estado de un proyecto: datos del proyecto y resumen de explicabilidad."""
        if not id.isascii() or not id.isdigit():
            raise ValueError(f"id de proyecto no válido: {id!r}; debe ser un número entero")
        id = str(int(id))
        client = get_client()
        project = await client.get(f"/projects/{id}")
        explanations = await client.get(f"/projects/{id}/explanations/summary")
        return {"project": project, "explanations": explanations}

    @mcp.resource("presentacion://", title="Presentación")
    async def presentacion() -> dict:
        """Las diapositivas de la presentación de Vigía."""
        return await get_client().get("/content/presentacion")

    @mcp.resource("demo://guion", title="Guion de la demo")
    async def demo_guion() -> dict:
        """El guion completo de la demo guiada."""
        return await get_client().get("/content/demo")

    @mcp.resource("guia://uso", title="Guía de uso")
    async def guia_uso() -> dict:
        """La sección «Guía de uso» de /ayuda."""
        return await get_client().get("/content/guia-uso")
