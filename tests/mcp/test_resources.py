"""Los 7 resources devuelven algo no vacío."""

from __future__ import annotations

import json


async def _leer(sesion_mcp, uri: str):
    async with sesion_mcp as sesion:
        resultado = await sesion.read_resource(uri)
    assert resultado.contents
    texto = resultado.contents[0].text
    return json.loads(texto)


async def test_schema_tables(sesion_mcp):
    datos = await _leer(sesion_mcp, "schema://tables")
    assert datos["tables"]


async def test_glossary(sesion_mcp):
    datos = await _leer(sesion_mcp, "glossary://")
    assert datos


async def test_metrics_help(sesion_mcp):
    todas = await _leer(sesion_mcp, "metrics-help://disparate_impact")
    assert todas


async def test_state_project(sesion_mcp, proyecto_demo):
    datos = await _leer(sesion_mcp, f"state://project/{proyecto_demo['project_id']}")
    assert datos["project"]["id"] == proyecto_demo["project_id"]
    assert "explanations" in datos


async def test_presentacion(sesion_mcp):
    datos = await _leer(sesion_mcp, "presentacion://")
    assert datos


async def test_demo_guion(sesion_mcp):
    datos = await _leer(sesion_mcp, "demo://guion")
    assert datos


async def test_guia_uso(sesion_mcp):
    datos = await _leer(sesion_mcp, "guia://uso")
    assert datos
