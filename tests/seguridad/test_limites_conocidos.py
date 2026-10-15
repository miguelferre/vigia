"""Controles que Vigía no aplica y que SEGURIDAD.md documenta.

Cada control lo vigilan sus tests originales, marcados
`xfail(strict=True)` en `test_mcp_llm_b.py` y `test_nav_b.py`. Aquí se comprueba
que el límite está escrito donde lo lee quien usa Vigía.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from vigia.mcp.server import mcp

RAIZ = Path(__file__).resolve().parents[2]


def _limites() -> str:
    texto = (RAIZ / "SEGURIDAD.md").read_text(encoding="utf-8")
    inicio = texto.index("## Qué no protege y qué hacer")
    fin = texto.find("\n## ", inicio + 1)
    return texto[inicio : fin if fin > 0 else None]


def test_seguridad_declara_la_confirmacion_del_agente():
    """«Qué no protege y qué hacer» dice que `confirm` lo fija el agente y aprueba el host."""
    limites = _limites()
    assert "`confirm`" in limites
    assert "host del MCP" in limites


def test_seguridad_declara_el_pickle_por_agente():
    """«Qué no protege y qué hacer» dice que un agente puede cargar un pickle si confirma."""
    limites = _limites()
    assert "pickle" in limites and "agente" in limites


@pytest.mark.parametrize("nombre", ["upload_model_artifact", "reset_project"])
def test_docstrings_de_confirm_nombran_al_host(nombre):
    """La descripción de cada tool con confirmación dice que aprueba el host del MCP."""
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    descripcion = tools[nombre].description or ""
    assert "host del MCP" in descripcion, descripcion[-300:]
