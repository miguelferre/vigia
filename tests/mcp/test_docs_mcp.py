"""`docs/mcp.md` lista exactamente las tools, los prompts y los resources registrados."""

from __future__ import annotations

import re
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs" / "mcp.md"


def _seccion(texto: str, titulo: str) -> str:
    inicio = texto.index(titulo)
    fin = texto.find("\n## ", inicio + 1)
    return texto[inicio : fin if fin != -1 else len(texto)]


async def test_docs_mcp_lista_las_tools_registradas(sesion_mcp):
    texto = DOC.read_text(encoding="utf-8")
    tabla = _seccion(texto, "## Las 39 tools")
    documentadas = set(re.findall(r"^\| `([a-z_]+)` \|", tabla, flags=re.MULTILINE))
    async with sesion_mcp as sesion:
        registradas = {t.name for t in (await sesion.list_tools()).tools}
    assert documentadas == registradas
    assert len(registradas) == 39


async def test_docs_mcp_lista_prompts_y_resources(sesion_mcp):
    texto = DOC.read_text(encoding="utf-8")
    async with sesion_mcp as sesion:
        prompts = {p.name for p in (await sesion.list_prompts()).prompts}
        plantillas = {r.uriTemplate for r in (await sesion.list_resource_templates()).resourceTemplates}
        fijos = {str(r.uri) for r in (await sesion.list_resources()).resources}
    for nombre in prompts:
        assert f"`{nombre}(" in _seccion(texto, "## Los 3 prompts")
    seccion = _seccion(texto, "## Los 7 resources")
    for uri in plantillas | fijos:
        assert uri in seccion, uri
