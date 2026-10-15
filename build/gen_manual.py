"""Genera `docs/manual/` en Markdown desde el contenido de la app.

Fuentes (la misma que ve la persona en Ayuda, una sola fuente):

- `src/vigia/content/guia-uso.json`   -> `docs/manual/uso.md`
- `src/vigia/content/guia-datos.json` -> `docs/manual/datos.md`

Dos capítulos se escriben a mano y el generador no los toca: `instalacion.md` y
`problemas.md`. Solo comprueba que existen y los enlaza en el índice
(`docs/manual/README.md`, que también se genera).

    .venv\\Scripts\\python.exe build/gen_manual.py [--check]

Sin argumentos escribe los tres ficheros. Con `--check` no escribe nada y sale
con 1 si el manual no coincide con el contenido, igual que
`build/gen_content.py --check`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "src" / "vigia" / "content"
MANUAL_DIR = REPO_ROOT / "docs" / "manual"

GUIA_USO_JSON = CONTENT_DIR / "guia-uso.json"
GUIA_DATOS_JSON = CONTENT_DIR / "guia-datos.json"

# Capítulos escritos a mano: el generador los enlaza y no los reescribe.
CAPITULOS_A_MANO = ("instalacion.md", "problemas.md")

INTRO_INDICE = (
    "Vigía vigila modelos de IA en producción en tu equipo, sin código. Este manual "
    "tiene cuatro capítulos."
)
AVISO_INDICE = (
    "Los datos de demostración y las plantillas son sintéticos. Vigía no "
    "desidentifica nada: sube solo datos ya desidentificados."
)
ENLACES_INDICE = (
    "Para operar Vigía con un asistente de IA, mira [`mcp.md`](../mcp.md). "
    "Para la seguridad, [`SEGURIDAD.md`](../../SEGURIDAD.md)."
)
_AVISO_GENERADO = (
    "Este capítulo es el mismo texto que la sección «{seccion}» de la Ayuda de Vigía."
)

__all__ = ["CAPITULOS_A_MANO", "generar", "main", "render_datos", "render_indice", "render_uso"]


def _celda(texto: Any) -> str:
    """Texto de una celda de tabla Markdown: sin saltos de línea ni barras sin escapar."""
    return str(texto if texto is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def _capitalizar(texto: str) -> str:
    texto = texto.strip()
    return texto[:1].upper() + texto[1:]


def _lista_numerada(pasos: list[str]) -> list[str]:
    return [f"{n}. {paso}" for n, paso in enumerate(pasos, start=1)]


def _tabla_columnas(columnas: list[dict[str, str]]) -> list[str]:
    filas = ["| Columna | Qué es | Valores | Ejemplo |", "|---|---|---|---|"]
    for c in columnas:
        filas.append(
            f"| `{_celda(c['nombre'])}` | {_celda(c['que_es'])} | {_celda(c['valores'])} "
            f"| `{_celda(c['ejemplo'])}` |"
        )
    return filas


def render_uso(guia: dict[str, Any]) -> str:
    """Capítulo «Guía de uso»: una sección por entrada de `guia-uso.json`."""
    entradas = guia["entradas"]
    out = [
        "# Guía de uso",
        "",
        _AVISO_GENERADO.format(seccion="Guía"),
        "",
        "| Nº | Tema |",
        "|---|---|",
    ]
    for e in entradas:
        out.append(f"| {e['id']} | {_celda(e['titulo'])} |")
    for e in entradas:
        out += ["", f"## {e['id']}. {e['titulo']}", "", f"**Para qué:** {e['para_que']}"]
        if e.get("ruta"):
            out += ["", f"**Pantalla:** `{e['ruta']}`"]
        out += [""] + _lista_numerada(e["pasos"])
    return "\n".join(out) + "\n"


def _render_seccion_datos(s: dict[str, Any]) -> list[str]:
    out = ["", f"## {s['titulo']}", "", s["para_que"], ""]
    out.append(f"**Cómo se sube en Vigía:** {s['tipo_en_vigia']}.")
    if s.get("nombre_plantilla"):
        out += ["", f"**Plantilla con datos sintéticos:** `{s['nombre_plantilla']}`."]
    if s["obligatorias"]:
        out += ["", "Columnas obligatorias:", ""] + _tabla_columnas(s["obligatorias"])
    if s["opcionales"]:
        out += ["", "Columnas opcionales:", ""] + _tabla_columnas(s["opcionales"])
    if s["notas"]:
        out.append("")
        out += [f"- {nota}" for nota in s["notas"]]
    return out


def render_datos(guia: dict[str, Any]) -> str:
    """Capítulo «Guía de datos»: formatos, clase favorable, codificación y una sección por fichero."""
    f = guia["formatos"]
    cf = guia["clase_favorable"]
    ci = guia["codificacion_inconclusa"]
    out = [
        f"# {guia['titulo']}",
        "",
        _AVISO_GENERADO.format(seccion="Datos"),
        "",
        guia["resumen"],
        "",
        f"> {guia['aviso_sintetico']}",
        "",
        f"## {f['titulo']}",
        "",
        f"- **Ficheros.** {f['ficheros']}",
        f"- **Separador.** {f['separador']}",
        f"- **Decimal.** {f['decimal']}",
        f"- **Codificación.** {f['codificacion']}",
        f"- **{f['excel'].split(':')[0]}.** {_capitalizar(f['excel'].split(':', 1)[1])}",
        f"- **Fechas ilegibles.** {f['fecha_ilegible']}",
        "",
        "Fechas admitidas:",
        "",
        "| Formato | Ejemplo | Nota |",
        "|---|---|---|",
    ]
    for fe in f["fechas"]:
        out.append(f"| {_celda(fe['formato'])} | `{_celda(fe['ejemplo'])}` | {_celda(fe['nota'])} |")
    out += ["", f"## {cf['titulo']}", "", cf["frase"], "", f"**{cf['pregunta']}**", ""]
    out += _lista_numerada(cf["pasos"])
    out += ["", "Ejemplos:", "", "| Caso | Valor favorable | Motivo |", "|---|---|---|"]
    for ej in cf["ejemplos"]:
        out.append(f"| {_celda(ej['caso'])} | {_celda(ej['favorable'])} | {_celda(ej['motivo'])} |")
    out += ["", f"## {ci['titulo']}", "", ci["texto"], ""] + _lista_numerada(ci["pasos"])
    for s in guia["secciones"]:
        out += _render_seccion_datos(s)
    return "\n".join(out) + "\n"


def render_indice() -> str:
    """Indice del manual: enlaza los capítulos generados y los escritos a mano."""
    lineas = [
        "# Manual de Vigía",
        "",
        INTRO_INDICE,
        "",
        "| Capítulo | Qué dice |",
        "|---|---|",
        "| [Instalación](instalacion.md) | Instalar el zip, arrancar, apagar y dónde quedan los datos |",
        "| [Guía de uso](uso.md) | Crear un modelo, subir datos, leer el cuadro y atender alertas |",
        "| [Guía de datos](datos.md) | Qué ficheros pide Vigía, sus columnas y sus formatos |",
        "| [Qué hacer si](problemas.md) | Bloqueos de Windows, primera carga lenta, ficheros que no se leen |",
        "",
        AVISO_INDICE,
        "",
        ENLACES_INDICE,
    ]
    return "\n".join(lineas) + "\n"


def generar() -> dict[Path, str]:
    """Ficheros generados: ruta de destino y su texto."""
    uso = json.loads(GUIA_USO_JSON.read_text(encoding="utf-8"))
    datos = json.loads(GUIA_DATOS_JSON.read_text(encoding="utf-8"))
    return {
        MANUAL_DIR / "README.md": render_indice(),
        MANUAL_DIR / "uso.md": render_uso(uso),
        MANUAL_DIR / "datos.md": render_datos(datos),
    }


def _leer(ruta: Path) -> str:
    """Texto del fichero con los finales de línea normalizados (un checkout con CRLF no falla)."""
    if not ruta.exists():
        return ""
    return ruta.read_text(encoding="utf-8").replace("\r\n", "\n")


def comprobar(generados: dict[Path, str]) -> list[str]:
    """Lista de problemas: capítulos a mano ausentes y ficheros que no coinciden."""
    problemas = [
        f"falta el capítulo escrito a mano docs/manual/{nombre}"
        for nombre in CAPITULOS_A_MANO
        if not (MANUAL_DIR / nombre).is_file()
    ]
    problemas += [
        f"docs/manual/{ruta.name} no coincide con el contenido"
        for ruta, texto in generados.items()
        if _leer(ruta) != texto
    ]
    return problemas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="no escribe nada; sale con 1 si el manual no coincide con lo generado",
    )
    args = parser.parse_args(argv)
    generados = generar()
    if args.check:
        problemas = comprobar(generados)
        if problemas:
            print("; ".join(problemas), file=sys.stderr)
            print("ejecuta build/gen_manual.py sin --check.", file=sys.stderr)
            return 1
        print("docs/manual/ coincide con lo generado.")
        return 0
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    for ruta, texto in generados.items():
        ruta.write_text(texto, encoding="utf-8", newline="\n")
        print(f"escrito {ruta}")
    faltan = [n for n in CAPITULOS_A_MANO if not (MANUAL_DIR / n).is_file()]
    if faltan:
        print(f"faltan capítulos escritos a mano: {', '.join(faltan)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
