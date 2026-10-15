"""Contraste WCAG 2 de los temas de Vigía.

La cabecera de `frontend/src/themes/tokens.css` documenta una tabla de ratios
de contraste y cita un `contraste.py` "de la sesión de consolidación" que
nunca llegó a versionarse (una revisión anterior de la interfaz).
Este módulo es ese script: existe para que la tabla de la cabecera se pueda
regenerar cada vez que cambian los tokens, en vez de mantenerse a mano.

Qué hace: lee `tokens.css`, extrae los valores hexadecimales de cada
variante (`html[data-theme="miguel"]` y esa misma con `.dark`; las estéticas
privadas viven en `build/contraste_privado.py`, listado en
`build/publico/privados.txt`, y entran solo si el fichero existe) y calcula, para una lista
fija de combinaciones de tokens, la luminancia relativa y el ratio de
contraste tal como los define WCAG 2 (fórmula sRGB estándar: linealizar cada
canal y ponderarlos 0.2126/0.7152/0.0722; el ratio es
`(L_claro + 0.05) / (L_oscuro + 0.05)`).

Cómo se ejecuta:

    .venv\\Scripts\\python.exe build/contraste.py --matriz

Imprime una fila por combinación con su mínimo exigido y una columna por
variante, marcando con `(!)` las que quedan por debajo del mínimo.
`--temas miguel` (coma para varios) limita las columnas a esos temas; con el
build público solo existe `miguel`.

Regla del código de salida: las combinaciones están etiquetadas por
categoría. Las de categoría "texto" (texto sobre superficie, insignias
rellenas, series de gráfica y colores de estado: todo lo que no sea borde ni
separación de superficies) y "grafico" (rellenos no textuales que necesitan
3:1 para distinguirse del fondo: luces, líneas superiores y series de
gráfica) hacen fallar el script si bajan del
mínimo, y el proceso termina con código 1, salvo las que estén en
`FALLOS_CONOCIDOS`: sin esa lista el script saldría siempre con 1 por los
avisos que ya se arrastraban y dejaría de servir como puerta de regresión.
Las de categoría "borde" (contraste del token
`border` contra fondo o tarjeta), "foco" (el anillo de foco `ring` contra el
fondo, umbral no-texto de 3:1) y "separacion" (cuánto se distingue una
superficie de otra, p. ej. la tarjeta del fondo) se marcan igual con `(!)`
pero nunca hacen fallar el script: son ratios de separación entre superficies
o decorativos, no de legibilidad de texto, y se revisan aparte por estética.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKENS_CSS = REPO_ROOT / "frontend" / "src" / "themes" / "tokens.css"

# Orden de columnas en la tabla impresa.
VARIANTES_PUBLICAS: tuple[tuple[str, str, bool], ...] = (
    ("miguel claro", "miguel", False),
    ("miguel oscuro", "miguel", True),
)

# (etiqueta, token_a, token_b, minimo, categoria)
# categoria "texto": hace fallar el script si baja del minimo.
# categoria "borde" / "separacion": se marca con (!) pero nunca hace fallar.
Combo = tuple[str, str, str, float, str]

COMBOS: tuple[Combo, ...] = (
    ("foreground / background", "foreground", "background", 7.00, "texto"),
    ("foreground / card", "foreground", "card", 4.50, "texto"),
    ("muted-foreground / background", "muted-foreground", "background", 7.00, "texto"),
    ("muted-foreground / card", "muted-foreground", "card", 4.50, "texto"),
    ("card-foreground / background", "card-foreground", "background", 7.00, "texto"),
    ("card-foreground / card", "card-foreground", "card", 4.50, "texto"),
    ("muted-foreground / muted", "muted-foreground", "muted", 4.50, "texto"),
    ("border / background", "border", "background", 3.00, "borde"),
    ("border / card", "border", "card", 3.00, "borde"),
    ("primary-foreground / primary", "primary-foreground", "primary", 4.50, "texto"),
    ("accent-foreground / accent", "accent-foreground", "accent", 4.50, "texto"),
    ("secondary-foreground / secondary", "secondary-foreground", "secondary", 4.50, "texto"),
    ("card / background (separacion)", "card", "background", 1.25, "separacion"),
    ("muted / card (separacion)", "muted", "card", 1.08, "separacion"),
    ("secondary / card (separacion)", "secondary", "card", 1.08, "separacion"),
    ("chart-1 / card", "chart-1", "card", 3.00, "texto"),
    ("chart-1 / background", "chart-1", "background", 3.00, "texto"),
    ("chart-2 / card", "chart-2", "card", 3.00, "texto"),
    ("chart-2 / background", "chart-2", "background", 3.00, "texto"),
    ("chart-3 / card", "chart-3", "card", 3.00, "texto"),
    ("chart-3 / background", "chart-3", "background", 3.00, "texto"),
    ("chart-4 / card", "chart-4", "card", 3.00, "texto"),
    ("chart-4 / background", "chart-4", "background", 3.00, "texto"),
    ("state-ok / card", "state-ok", "card", 3.00, "texto"),
    ("state-ok / background", "state-ok", "background", 3.00, "texto"),
    ("state-warn / card", "state-warn", "card", 3.00, "texto"),
    ("state-warn / background", "state-warn", "background", 3.00, "texto"),
    ("state-alert / card", "state-alert", "card", 3.00, "texto"),
    ("state-alert / background", "state-alert", "background", 3.00, "texto"),
    ("state-unstable / card", "state-unstable", "card", 3.00, "texto"),
    ("state-unstable / background", "state-unstable", "background", 3.00, "texto"),
    ("state-nodata / card", "state-nodata", "card", 3.00, "texto"),
    ("state-nodata / background", "state-nodata", "background", 3.00, "texto"),
    ("state-on-fill / state-warn", "state-on-fill", "state-warn", 4.50, "texto"),
    ("state-on-fill / state-alert", "state-on-fill", "state-alert", 4.50, "texto"),
    ("chip-active-foreground / chip-active", "chip-active-foreground", "chip-active", 4.50, "texto"),
    ("link / background", "link", "background", 4.50, "texto"),
    ("ring / background", "ring", "background", 3.00, "foco"),
    ("foreground-tertiary / background", "foreground-tertiary", "background", 4.50, "texto"),
    ("foreground-tertiary / card", "foreground-tertiary", "card", 4.50, "texto"),
    ("risk-medium / card", "risk-medium", "card", 3.00, "texto"),
    ("risk-medium / background", "risk-medium", "background", 3.00, "texto"),
    ("state-warn-fill / card", "state-warn-fill", "card", 3.00, "grafico"),
    ("state-warn-fill / background", "state-warn-fill", "background", 3.00, "grafico"),
    ("line / card (separacion)", "line", "card", 1.08, "separacion"),
    ("line-2 / card (separacion)", "line-2", "card", 1.08, "separacion"),
)

# Fallos de texto conocidos, como (combinación, columna). Se listan uno a uno
# para que el script siga sirviendo de puerta: sale 1 si aparece un fallo
# NUEVO, no por estos. Al arreglar uno, bórralo de aquí. Los de las estéticas
# privadas viven en `contraste_privado.py`.
FALLOS_CONOCIDOS_PUBLICOS: frozenset[tuple[str, str]] = frozenset()

# Estéticas privadas (build/publico/privados.txt): columnas, CSS y fallos
# conocidos. Sin el fichero (árbol público) no hay ninguna.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from contraste_privado import (  # type: ignore[import-not-found]
        FALLOS_CONOCIDOS_PRIVADOS,
        TOKENS_CSS_PRIVADOS,
        VARIANTES_PRIVADAS,
    )
except ImportError:
    FALLOS_CONOCIDOS_PRIVADOS = frozenset()
    TOKENS_CSS_PRIVADOS = ()
    VARIANTES_PRIVADAS = ()

VARIANTES: tuple[tuple[str, str, bool], ...] = (*VARIANTES_PUBLICAS, *VARIANTES_PRIVADAS)
FALLOS_CONOCIDOS: frozenset[tuple[str, str]] = FALLOS_CONOCIDOS_PUBLICOS | FALLOS_CONOCIDOS_PRIVADOS

_BLOCK_RE = re.compile(r'html\[data-theme="(\w+)"\](\.dark)?\s*\{([^}]*)\}')
_TOKEN_RE = re.compile(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})")


def leer_variantes(css: str) -> dict[tuple[str, bool], dict[str, str]]:
    """Extrae, por variante (tema, oscuro), el diccionario token -> hex."""
    variantes: dict[tuple[str, bool], dict[str, str]] = {}
    for tema, sufijo_dark, cuerpo in _BLOCK_RE.findall(css):
        variantes[(tema, bool(sufijo_dark))] = dict(_TOKEN_RE.findall(cuerpo))
    return variantes


def _linealizar(canal: float) -> float:
    if canal <= 0.03928:
        return canal / 12.92
    return ((canal + 0.055) / 1.055) ** 2.4


def luminancia(hex_color: str) -> float:
    """Luminancia relativa WCAG 2 de un color `#RRGGBB`."""
    valor = hex_color.lstrip("#")
    r, g, b = (int(valor[i : i + 2], 16) / 255 for i in (0, 2, 4))
    r, g, b = _linealizar(r), _linealizar(g), _linealizar(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(hex_a: str, hex_b: str) -> float:
    """Ratio de contraste WCAG 2 entre dos colores `#RRGGBB`."""
    l_a, l_b = luminancia(hex_a), luminancia(hex_b)
    claro, oscuro = max(l_a, l_b), min(l_a, l_b)
    return (claro + 0.05) / (oscuro + 0.05)


def _celda(valor: float, minimo: float) -> str:
    texto = f"{valor:.2f}"
    return f"{texto}(!)" if valor < minimo else texto


def construir_matriz(
    variantes: dict[tuple[str, bool], dict[str, str]],
    columnas: tuple[tuple[str, str, bool], ...] | None = None,
) -> tuple[list[list[str]], list[tuple[str, str]]]:
    """Devuelve las filas de la tabla y los fallos de texto, como (combinación, columna)."""
    filas: list[list[str]] = []
    fallos_texto: list[tuple[str, str]] = []
    for etiqueta, token_a, token_b, minimo, categoria in COMBOS:
        fila = [etiqueta, f"{minimo:.2f}"]
        for nombre_col, tema, oscuro in columnas or VARIANTES:
            tokens = variantes.get((tema, oscuro), {})
            hex_a, hex_b = tokens.get(token_a), tokens.get(token_b)
            if hex_a is None or hex_b is None:
                fila.append("n/d")
                continue
            valor = contraste(hex_a, hex_b)
            fila.append(_celda(valor, minimo))
            if categoria in ("texto", "grafico") and valor < minimo:
                fallos_texto.append((etiqueta, nombre_col))
        filas.append(fila)
    return filas, fallos_texto


def imprimir_matriz(
    filas: list[list[str]], columnas: tuple[tuple[str, str, bool], ...] | None = None
) -> None:
    ancho_etiqueta = max(len(f[0]) for f in filas)
    ancho_min = 6
    ancho_col = 14
    cabecera = [
        "combinacion".ljust(ancho_etiqueta),
        "min".rjust(ancho_min),
        *(nombre.rjust(ancho_col) for nombre, _tema, _oscuro in columnas or VARIANTES),
    ]
    print(" ".join(cabecera))
    for etiqueta, minimo, *valores in filas:
        linea = [etiqueta.ljust(ancho_etiqueta), minimo.rjust(ancho_min)]
        linea.extend(valor.rjust(ancho_col) for valor in valores)
        print(" ".join(linea))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--matriz",
        action="store_true",
        help="imprime la tabla de ratios de las variantes",
    )
    parser.add_argument(
        "--temas",
        default=None,
        help="temas a medir, separados por comas (por defecto, todos los del build)",
    )
    args = parser.parse_args(argv)

    if not args.matriz:
        parser.print_help()
        return 0

    columnas = VARIANTES
    if args.temas:
        pedidos = {t.strip() for t in args.temas.split(",") if t.strip()}
        desconocidos = pedidos - {tema for _n, tema, _o in VARIANTES}
        if desconocidos:
            parser.error(f"tema desconocido en este build: {', '.join(sorted(desconocidos))}")
        columnas = tuple(v for v in VARIANTES if v[1] in pedidos)

    css = "\n".join(
        ruta.read_text(encoding="utf-8") for ruta in (TOKENS_CSS, *TOKENS_CSS_PRIVADOS) if ruta.exists()
    )
    variantes = leer_variantes(css)
    filas, fallos_texto = construir_matriz(variantes, columnas)
    imprimir_matriz(filas, columnas)

    visibles = {nombre for nombre, _t, _o in columnas}
    conocidos = {f for f in FALLOS_CONOCIDOS if f[1] in visibles}
    nuevos = [f for f in fallos_texto if f not in FALLOS_CONOCIDOS]
    arreglados = sorted(conocidos - set(fallos_texto))
    if arreglados:
        print()
        print("Ya no fallan (bórralos de FALLOS_CONOCIDOS):")
        for etiqueta, columna in arreglados:
            print(f"  {etiqueta} en {columna}")
    if nuevos:
        print()
        print("Fallos de texto o gráfico nuevos:")
        for etiqueta, columna in nuevos:
            print(f"  {etiqueta} en {columna}")
        return 1
    print()
    print("Ningún fallo de texto nuevo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
