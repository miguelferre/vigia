"""El estático compilado con `VITE_TEMA=miguel` no lleva la estética privada.

`frontend/vite.config.ts` deja en `index.html` la marca
`<meta name="vigia-tema" content="...">`. Si el estático de `src/vigia/static`
no se compiló con `miguel` (build completo, o sin compilar), el test sobre el
estático se salta; el buscador se prueba aparte con carpetas sintéticas.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = REPO_ROOT / "src" / "vigia" / "static"

# Construidos por partes: este fichero no debe nombrar la estética privada.
TERMINOS = ("g" + "mv", "ap" + "tos")
_MARCA = re.compile(r'<meta\s+name="vigia-tema"\s+content="([^"]*)"')
_TEXTO = {".html", ".js", ".css", ".json", ".svg", ".txt", ".map", ".webmanifest"}


def tema_compilado(static: Path) -> str | None:
    """Valor de la marca de `index.html`, o `None` si no hay estático o no la lleva."""
    index = static / "index.html"
    if not index.is_file():
        return None
    m = _MARCA.search(index.read_text(encoding="utf-8", errors="replace"))
    return m.group(1) if m else None


def buscar_terminos(static: Path) -> list[tuple[str, str]]:
    """Pares (fichero relativo, término) de cada término prohibido hallado, sin distinguir mayúsculas."""
    hallados: list[tuple[str, str]] = []
    for ruta in sorted(static.rglob("*")):
        if not ruta.is_file() or ruta.suffix.lower() not in _TEXTO:
            continue
        texto = ruta.read_text(encoding="utf-8", errors="replace").lower()
        rel = ruta.relative_to(static).as_posix()
        hallados.extend((rel, t) for t in TERMINOS if t in texto)
    return hallados


def test_el_estatico_de_miguel_no_lleva_la_estetica_privada():
    tema = tema_compilado(STATIC)
    if tema != "miguel":
        pytest.skip(f"el estático no se compiló con VITE_TEMA=miguel (marca: {tema!r})")
    assert buscar_terminos(STATIC) == []


def test_el_buscador_encuentra_los_terminos_y_lee_la_marca(tmp_path: Path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(
        '<head><meta name="vigia-tema" content="miguel"></head>', encoding="utf-8"
    )
    assert tema_compilado(tmp_path) == "miguel"
    assert buscar_terminos(tmp_path) == []
    (tmp_path / "assets" / "a.css").write_text("html[data-theme=" + TERMINOS[0] + "]{}", encoding="utf-8")
    (tmp_path / "assets" / "b.js").write_text("font:" + TERMINOS[1].upper(), encoding="utf-8")
    assert buscar_terminos(tmp_path) == [
        ("assets/a.css", TERMINOS[0]),
        ("assets/b.js", TERMINOS[1]),
    ]


def test_sin_estatico_no_hay_marca(tmp_path: Path):
    assert tema_compilado(tmp_path) is None
