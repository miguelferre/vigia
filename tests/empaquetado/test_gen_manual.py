"""El manual coincide con el contenido de la app y `docs/mcp.md`
cuenta las mismas tools que el servidor MCP."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from build import gen_manual

REPO = Path(__file__).resolve().parents[2]
PUBLICOS = ("README.md", "LICENSE", "NOTICE", "SEGURIDAD.md", "docs/mcp.md")


def _terminos_prohibidos() -> list[str]:
    ruta = REPO / "build" / "publico" / "terminos-prohibidos.txt"
    if not ruta.is_file():
        pytest.skip("falta build/publico/terminos-prohibidos.txt (no viaja en el árbol público)")
    lineas = ruta.read_text(encoding="utf-8")
    return [t.strip().lower() for t in lineas.splitlines() if t.strip() and not t.startswith("#")]


def test_manual_coincide_con_el_contenido():
    assert gen_manual.comprobar(gen_manual.generar()) == []


def test_check_falla_si_el_manual_cambia(tmp_path, monkeypatch):
    destino = tmp_path / "manual"
    destino.mkdir()
    for nombre in gen_manual.CAPITULOS_A_MANO:
        (destino / nombre).write_text("capitulo", encoding="utf-8")
    monkeypatch.setattr(gen_manual, "MANUAL_DIR", destino)
    generados = {destino / ruta.name: texto for ruta, texto in gen_manual.generar().items()}
    assert gen_manual.main(["--check"]) == 1  # vacio: nada coincide
    assert gen_manual.main([]) == 0
    assert gen_manual.main(["--check"]) == 0
    (destino / "uso.md").write_text("editado a mano\n", encoding="utf-8")
    assert gen_manual.main(["--check"]) == 1
    assert [p for p in gen_manual.comprobar(gen_manual.generar())] == ["docs/manual/uso.md no coincide con el contenido"]
    assert set(generados) == {destino / "README.md", destino / "uso.md", destino / "datos.md"}


def test_check_falla_si_falta_un_capitulo_a_mano(tmp_path, monkeypatch):
    monkeypatch.setattr(gen_manual, "MANUAL_DIR", tmp_path)
    problemas = gen_manual.comprobar({})
    assert len(problemas) == len(gen_manual.CAPITULOS_A_MANO)


def test_capitulos_a_mano_existen_y_el_indice_los_enlaza():
    indice = (REPO / "docs" / "manual" / "README.md").read_text(encoding="utf-8")
    for nombre in gen_manual.CAPITULOS_A_MANO:
        assert (REPO / "docs" / "manual" / nombre).is_file()
        assert f"({nombre})" in indice


def test_el_manual_lleva_todas_las_entradas_y_secciones():
    uso = json.loads(gen_manual.GUIA_USO_JSON.read_text(encoding="utf-8"))
    datos = json.loads(gen_manual.GUIA_DATOS_JSON.read_text(encoding="utf-8"))
    texto_uso = (REPO / "docs" / "manual" / "uso.md").read_text(encoding="utf-8")
    texto_datos = (REPO / "docs" / "manual" / "datos.md").read_text(encoding="utf-8")
    for e in uso["entradas"]:
        assert f"## {e['id']}. {e['titulo']}" in texto_uso
    for s in datos["secciones"]:
        assert f"## {s['titulo']}" in texto_datos


def test_el_manual_avisa_de_que_windows_puede_bloquear_un_fichero():
    # El manual dice que el zip no lleva firma digital y que Windows puede bloquearlo.
    texto = (REPO / "docs" / "manual" / "instalacion.md").read_text(encoding="utf-8")
    assert "no lleva firma digital" in texto
    assert "puede bloquear un fichero" in texto


def test_documentos_publicos_sin_terminos_prohibidos():
    # Ni rutas personales, ni cliente, ni documentos internos.
    ficheros = [REPO / n for n in PUBLICOS] + sorted((REPO / "docs" / "manual").glob("*.md"))
    prohibidos = _terminos_prohibidos()
    hallazgos = []
    for ruta in ficheros:
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
            bajas = linea.lower()
            hallazgos += [f"{ruta.name}:{n}: {t}" for t in prohibidos if t in bajas]
    assert hallazgos == []


def test_mcp_md_lista_las_tools_del_servidor():
    from vigia.mcp.server import mcp

    tools = sorted(t.name for t in asyncio.run(mcp.list_tools()))
    texto = (REPO / "docs" / "mcp.md").read_text(encoding="utf-8")
    assert len(tools) == 39
    assert "## Las 39 tools" in texto
    seccion = texto.split("## Las 39 tools", 1)[1].split("\n## ", 1)[0]
    en_tabla = sorted(re.findall(r"^\| `([a-z_]+)` \|", seccion, flags=re.MULTILINE))
    assert en_tabla == tools


@pytest.mark.parametrize("nombre", ["LICENSE", "NOTICE", "SEGURIDAD.md", "README.md"])
def test_documentos_de_la_raiz_existen(nombre):
    assert (REPO / nombre).is_file()


def test_licencia_mit_con_el_autor():
    licencia = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert licencia.startswith("MIT License")
    assert "Copyright (c) 2026 Miguel Ferreiro García" in licencia
