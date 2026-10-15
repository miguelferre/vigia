"""Contrato estático de `Informe.tsx` con el backend.

El proyecto no tiene vitest, así que el contrato entre la pestaña Informe y el
informe HTML se vigila desde pytest leyendo el fuente: el parámetro `modo` que
pasa el iframe tiene que ser uno de los que acepta `informe_revision`, y el
iframe no puede ganar permisos."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from vigia.human import informe_revision

INFORME_TSX = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "auditoria" / "Informe.tsx"
)

pytestmark = pytest.mark.skipif(
    not INFORME_TSX.is_file(), reason="sin frontend/ (instalación sin fuentes)"
)


@pytest.fixture(scope="module")
def fuente() -> str:
    return INFORME_TSX.read_text(encoding="utf-8")


def test_el_modo_que_pide_el_iframe_lo_acepta_el_backend(fuente):
    m = re.search(r"report\?modo=\$\{\s*resolvedDark\s*\?\s*\"(\w+)\"\s*:\s*\"(\w+)\"\s*\}", fuente)
    assert m, "Informe.tsx ya no pide ?modo= según resolvedDark"
    assert set(m.groups()) == {"claro", "oscuro"}
    assert set(m.groups()) <= set(informe_revision.MODOS)


def test_el_iframe_sigue_sin_permisos_y_con_altura_flexible(fuente):
    assert 'sandbox=""' in fuente
    assert "allow-" not in fuente
    assert "70vh" in fuente
    assert not re.search(r"(?<!min-)h-\[\d+rem\]", fuente), (
        "altura fija: se corta el informe en pantallas altas"
    )


def test_el_enlace_de_pestana_nueva_usa_la_misma_url(fuente):
    assert "href={src}" in fuente and "src={src}" in fuente
