"""Los tokens que el informe de la revisión incrusta son los de
`frontend/src/themes/tokens.css` (tema personal) y pasan el contraste.

El backend instalado no lleva `frontend/`: `informe_tokens.py` es la copia en
tiempo de ejecución y este test es lo que la mantiene en sync."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from vigia.human import informe_tokens

REPO = Path(__file__).resolve().parents[2]
TOKENS_CSS = REPO / "frontend" / "src" / "themes" / "tokens.css"

pytestmark = pytest.mark.skipif(not TOKENS_CSS.is_file(), reason="sin frontend/ (instalación sin fuentes)")

_REGLA = re.compile(r"([^{}]+)\{([^{}]*)\}")
_TEMA = re.compile(r"data-theme=[\"']?miguel[\"']?\]")
_TOKEN = re.compile(r"--([\w-]+):\s*([^;]+);")


def _leer(css: str) -> dict[bool, dict[str, str]]:
    """Tokens del tema miguel por modo. Tolera comillas opcionales, listas de
    selectores, `:root`/`html` delante, varias reglas por modo (la última gana)
    y comentarios; el modo oscuro es todo selector del tema con `.dark`."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    salida: dict[bool, dict[str, str]] = {}
    for selectores, cuerpo in _REGLA.findall(css):
        for sel in selectores.split(","):
            if _TEMA.search(sel):
                oscuro = ".dark" in sel
                salida.setdefault(oscuro, {}).update({k: v.strip() for k, v in _TOKEN.findall(cuerpo)})
    return salida


@pytest.fixture(scope="module")
def css() -> dict[bool, dict[str, str]]:
    bloques = _leer(TOKENS_CSS.read_text(encoding="utf-8"))
    assert set(bloques) == {False, True}, "tokens.css debe tener el bloque miguel claro y el oscuro"
    return bloques


@pytest.mark.parametrize(("oscuro", "copia"), [(False, informe_tokens.CLARO), (True, informe_tokens.OSCURO)])
def test_valores_iguales_a_tokens_css(css, oscuro, copia):
    fuente = css[oscuro]
    for nombre, valor in copia.items():
        assert nombre in fuente, f"--{nombre} ya no existe en tokens.css"
        assert fuente[nombre].upper() == valor.upper(), f"--{nombre} ({'oscuro' if oscuro else 'claro'})"


def test_mismos_tokens_en_claro_y_oscuro():
    assert set(informe_tokens.CLARO) == set(informe_tokens.OSCURO) == set(informe_tokens.tokens_usados())


def test_fuentes_iguales_a_tokens_css(css):
    for oscuro in (False, True):
        assert css[oscuro]["font-sans"] == informe_tokens.FUENTE_TEXTO
        assert css[oscuro]["font-display-family"] == informe_tokens.FUENTE_TITULO


def _contraste():
    ruta = REPO / "build" / "contraste.py"
    spec = importlib.util.spec_from_file_location("vigia_build_contraste", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.contraste


# (texto, fondo, mínimo): los pares que dibuja el informe, con los mismos
# mínimos que `build/contraste.py` exige a la app para ese tipo de uso.
_PARES = (
    ("foreground", "background", 7.0),
    ("foreground", "card", 4.5),
    ("foreground", "muted", 4.5),
    ("muted-foreground", "background", 7.0),
    ("muted-foreground", "card", 4.5),
    ("link", "background", 4.5),
    ("link", "card", 4.5),
    ("state-on-fill", "state-alert", 4.5),
    ("state-on-fill", "state-warn", 4.5),
    ("state-on-fill", "state-unstable", 4.5),
    # no textuales: barra de gravedad, borde de la etiqueta y número del hallazgo sin anclaje
    ("state-alert", "card", 3.0),
    ("state-warn-fill", "card", 3.0),
    ("state-warn-fill", "background", 3.0),
    ("state-unstable", "card", 3.0),
    ("state-warn", "card", 3.0),
    ("state-ok", "card", 3.0),
)


@pytest.mark.parametrize(("nombre", "tokens"), [("claro", informe_tokens.CLARO), ("oscuro", informe_tokens.OSCURO)])
def test_contraste_de_los_pares_del_informe(nombre, tokens):
    contraste = _contraste()
    fallos = [
        f"{a} / {b}: {contraste(tokens[a], tokens[b]):.2f} < {minimo}"
        for a, b, minimo in _PARES
        if contraste(tokens[a], tokens[b]) < minimo
    ]
    assert not fallos, f"{nombre}: " + "; ".join(fallos)
