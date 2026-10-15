"""Tokens del tema personal para el informe de la revisión.

El informe se sirve en un `<iframe sandbox="">`: sin mismo origen ni
scripts, no hereda las variables CSS de la aplicación. Por eso los valores
de `frontend/src/themes/tokens.css` (bloques `html[data-theme="miguel"]` y
`html[data-theme="miguel"].dark`) se copian aquí y se incrustan al generar.

El backend instalado no lleva `frontend/`, así que esta copia es la fuente en
tiempo de ejecución. `tests/human/test_informe_tokens.py` la compara con
`tokens.css` (solo los tokens que usa el informe): si cambian los tokens de
la app, ese test falla hasta que se actualice este módulo.
"""

from __future__ import annotations

__all__ = [
    "CLARO",
    "FUENTE_MONO",
    "FUENTE_TEXTO",
    "FUENTE_TITULO",
    "OSCURO",
    "TEMAS",
    "bloque_variables",
    "tokens_usados",
]

TEMAS = ("miguel",)

# Tokens de `tokens.css` que el informe lee, con el mismo nombre (sin `--`).
CLARO: dict[str, str] = {
    "background": "#F6F5F9",
    "foreground": "#1F1B2E",
    "card": "#FFFFFF",
    "line-2": "#E6E3EE",
    "primary": "#6E5AB8",
    "muted": "#E1E5F8",
    "muted-foreground": "#55506A",
    "state-ok": "#1F8A5B",
    "state-warn": "#B45309",
    "state-warn-fill": "#B2800A",
    "state-alert": "#C62828",
    "state-unstable": "#2C6FD1",
    "state-on-fill": "#FFFFFF",
    "link": "#6E5AB8",
}

OSCURO: dict[str, str] = {
    "background": "#18181B",
    "foreground": "#F0F0F3",
    "card": "#2B2B31",
    "line-2": "#3D3D44",
    "primary": "#BFAEE8",
    "muted": "#35353D",
    "muted-foreground": "#CDCCD3",
    "state-ok": "#4CC38A",
    "state-warn": "#F2A33C",
    "state-warn-fill": "#D4A62A",
    "state-alert": "#F07171",
    "state-unstable": "#6FA8F5",
    "state-on-fill": "#1A1626",
    "link": "#BFAEE8",
}

# `--font-sans` y `--font-display-family` del tema (iguales en claro y oscuro).
FUENTE_TEXTO = '"Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif'
FUENTE_TITULO = '"Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif'
FUENTE_MONO = 'ui-monospace, "Cascadia Code", Consolas, "Liberation Mono", monospace'


def tokens_usados() -> frozenset[str]:
    """Nombres de token que el informe copia de `tokens.css`."""
    return frozenset(CLARO)


def bloque_variables(tokens: dict[str, str], *, sangria: str = "  ") -> str:
    """Declaraciones `--token: valor;` de un conjunto de tokens, una por línea."""
    return "\n".join(f"{sangria}--{nombre}: {valor};" for nombre, valor in tokens.items())
