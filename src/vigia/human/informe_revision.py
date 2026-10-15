"""Informe HTML de la revisión del dossier, en español y con el tema de Vigía.

Sustituye a `report_html.render_findings_html` del paquete: reutiliza sus
funciones de datos (`remediations_for`, `crosswalk`, `framework_names`,
`guideline_notes`) y dibuja el marco aquí. Cambia el render, no el contenido:
mismos hallazgos, mismas severidades y mismo mapa regulatorio, con las mismas
clases CSS estructurales (`finding`, `pill`, `g`, `cw-row`, `rem-item`), de modo
que un extractor de datos lee igual el informe viejo y el nuevo.

Una sola página, sin red ni scripts: se sirve en `<iframe sandbox="">`, que no
hereda las variables CSS de la aplicación, así que los tokens del tema personal
(`informe_tokens`) se incrustan al generar. Con `modo="auto"` el oscuro va por
`prefers-color-scheme`; `modo="claro"` u `"oscuro"` lo fija (el selector de modo
de la app no llega al iframe: `Informe.tsx` pasa el suyo). Al imprimir se vuelve
al claro.

`revision` es un `Revision` o un diccionario con sus mismas claves. Es lo que
`dossier_adapter.run_review` ya tiene a mano (`dossier`, `findings`, `approach`,
`incluir_crosswalk`, `meta`), y lo que se reconstruye al leer una revisión
guardada (`desde_guardada`).
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ._vendor.interaction_review.regulatory import crosswalk, framework_names, guideline_notes
from ._vendor.interaction_review.report import remediations_for
from ._vendor.interaction_review.schemas import Dossier, Finding, Severity
from .informe_tokens import (
    CLARO,
    FUENTE_MONO,
    FUENTE_TEXTO,
    FUENTE_TITULO,
    OSCURO,
    TEMAS,
    bloque_variables,
)

__all__ = ["MARCO_ES", "Revision", "desde_guardada", "dibujar"]

# Etiqueta de cabecera y atribución del pie por prefijo de directriz, en el
# orden canónico del paquete (`report_html._CORPUS_LABELS`).
_CORPUS: tuple[tuple[str, str, str], ...] = (
    ("HAX", "HAX-18", "HAX-18 (Microsoft)"),
    ("PAIR", "PAIR", "PAIR (Google)"),
    ("IX", "IX", "IX (extensión de la capa de interacción)"),
)

_SEVERIDAD = {Severity.HIGH: "Alta", Severity.MEDIUM: "Media", Severity.LOW: "Baja"}
_SEVERIDAD_FEMENINA = {"high": "alta", "medium": "media", "low": "baja"}

_ENFOQUE = {
    "b0": "b0 (lista de comprobación determinista)",
    "p3": "p3 (con modelo)",
    "auto": "auto (el enfoque lo elige el revisor)",
}

_SIN_MODELO_EN = "deterministic (no model)"
_SIN_MODELO_ES = "determinista (sin modelo)"

# Cadenas fijas del marco, juntas para que un test pueda leerlas todas.
MARCO_ES: dict[str, str] = {
    "kicker": "Revisión de la capa de interacción humano-IA",
    "enfoque": "Enfoque",
    "fuentes": "Fuentes",
    "directrices": "Directrices",
    "hallazgos": "Hallazgos",
    "anclados": "Anclados",
    "gravedad_alta": "Gravedad alta",
    "consolidacion": "Consolidación",
    "anclado": "Anclado",
    "sin_anclaje": "Sin anclaje",
    "punto": "Punto del sistema",
    "sin_punto": "(sin punto concreto)",
    "evidencia": "Evidencia",
    "sin_evidencia": "(sin evidencia)",
    "antipatron": "Antipatrón",
    "por_que": "Por qué importa",
    "recomendacion": "Recomendación",
    "medidas": "Medidas correctoras",
    "mapa": "Mapa regulatorio",
    "por_que_mapa": "Por qué se asocian",
    "sin_hallazgos": "Sin hallazgos: el sistema no muestra problemas de interacción detectables.",
}


@dataclass
class Revision:
    """Lo que el informe necesita de una revisión terminada.

    - `dossier`: `Dossier` del paquete, o un diccionario con `system_name`,
      `domain` y `sources` (lista) o `n_sources` (entero).
    - `findings`: lista de `Finding` o de sus diccionarios (`findings_json`).
    - `approach`: `b0`, `p3` o `auto`.
    - `incluir_crosswalk`: añade el mapa regulatorio.
    - `meta`: `{"date", "tool_version", "model"}`, como `provenance` de
      `dossier_adapter`; opcional.
    """

    dossier: Dossier | Mapping[str, Any]
    findings: list[Finding] | list[Mapping[str, Any]]
    approach: str
    incluir_crosswalk: bool = True
    meta: Mapping[str, Any] | None = field(default=None)


def _esc(texto: object) -> str:
    return html.escape("" if texto is None else str(texto))


def _como_revision(revision: Revision | Mapping[str, Any]) -> Revision:
    if isinstance(revision, Revision):
        return revision
    return Revision(
        dossier=revision["dossier"],
        findings=revision["findings"],
        approach=revision["approach"],
        incluir_crosswalk=revision.get("incluir_crosswalk", revision.get("include_crosswalk", True)),
        meta=revision.get("meta"),
    )


def _hallazgos(brutos: list[Any]) -> list[Finding]:
    return [f if isinstance(f, Finding) else Finding.model_validate(f) for f in brutos]


def _datos_dossier(dossier: Dossier | Mapping[str, Any]) -> tuple[str, str, int | None]:
    """`(system_name, domain, n_fuentes)`; `n_fuentes` es `None` si no se conoce."""
    if isinstance(dossier, Dossier):
        return dossier.system_name, dossier.domain, len(dossier.sources)
    fuentes = dossier.get("sources")
    n = len(fuentes) if isinstance(fuentes, list) else dossier.get("n_sources")
    return str(dossier.get("system_name", "")), str(dossier.get("domain", "")), n


def _corpus_presentes(findings: list[Finding]) -> list[tuple[str, str, str]]:
    prefijos = {gid.split("-", 1)[0] for f in findings for gid in f.guideline_ids}
    presentes = [fila for fila in _CORPUS if fila[0] in prefijos]
    return presentes or list(_CORPUS)


def _unir_y(elementos: list[str]) -> str:
    """«A», «A y B», «A, B y C»; «e» ante una palabra que empieza por i."""
    if len(elementos) <= 1:
        return "".join(elementos)
    ultimo = elementos[-1]
    nexo = "e" if ultimo[:1] in ("I", "i") and not ultimo.lower().startswith("ie") else "y"
    return f"{', '.join(elementos[:-1])} {nexo} {ultimo}"


def _fecha(valor: object) -> str:
    texto = str(valor)
    try:
        return datetime.fromisoformat(texto).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return texto


# --------------------------------------------------------------------------- #
# CSS: tokens del tema personal incrustados, claro por defecto, oscuro por
# `prefers-color-scheme` y de nuevo claro al imprimir.
# --------------------------------------------------------------------------- #
MODOS = ("auto", "claro", "oscuro")
_ESQUEMA = {"auto": "light dark", "claro": "light", "oscuro": "dark"}


def _css(tema: str, modo: str = "auto") -> str:
    if tema not in TEMAS:
        raise ValueError(f"tema desconocido para el informe: {tema!r}; válidos: {', '.join(TEMAS)}")
    if modo not in MODOS:
        raise ValueError(f"modo desconocido para el informe: {modo!r}; válidos: {', '.join(MODOS)}")
    if modo == "oscuro":
        variables = bloque_variables(OSCURO)
        oscuro = ""
    else:
        variables = bloque_variables(CLARO)
        oscuro = ""
        if modo == "auto":
            oscuro = (
                "@media (prefers-color-scheme: dark) {\n  :root {\n"
                + bloque_variables(OSCURO, sangria="    ")
                + "\n  }\n}\n"
            )
    return f""":root {{
{variables}
  --font-sans: {FUENTE_TEXTO};
  --font-display: {FUENTE_TITULO};
  --font-mono: {FUENTE_MONO};
  color-scheme: {_ESQUEMA[modo]};
}}
{oscuro}* {{ box-sizing: border-box; }}
html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{
  margin: 0; background: var(--background); color: var(--foreground);
  font-family: var(--font-sans); font-size: 16px; line-height: 1.55;
  overflow-wrap: anywhere;
}}
.sheet {{ max-width: 880px; margin: 0 auto; padding: 0 16px 64px; }}
@media (min-width: 640px) {{ .sheet {{ padding: 0 32px 80px; }} }}

/* Cabecera */
.masthead {{ padding: 36px 0 22px; border-bottom: 2px solid var(--line-2); margin-bottom: 28px; }}
.kicker {{
  font-size: 12px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
  color: var(--link); margin: 0 0 12px;
}}
.masthead h1 {{
  font-family: var(--font-display); font-size: 30px; line-height: 1.15; margin: 0 0 8px;
  font-weight: 600; letter-spacing: -.01em;
}}
@media (min-width: 640px) {{ .masthead h1 {{ font-size: 36px; }} }}
.masthead .domain {{ font-size: 17px; color: var(--muted-foreground); margin: 0; }}
.masthead .meta {{
  margin-top: 16px; font-size: 14px; color: var(--muted-foreground);
  display: flex; flex-wrap: wrap; gap: 4px 20px;
}}
.masthead .meta b {{ color: var(--foreground); font-weight: 600; }}

/* Resumen: tira de cifras */
.stats {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 14px; }}
@media (min-width: 640px) {{ .stats {{ grid-template-columns: repeat(4, 1fr); }} }}
.stat {{ background: var(--card); border: 1px solid var(--line-2); border-radius: 8px; padding: 14px 16px; }}
.stat .n {{ font-family: var(--font-display); font-size: 28px; font-weight: 600; line-height: 1.1;
  font-variant-numeric: tabular-nums; }}
.stat .l {{ font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted-foreground); margin-top: 4px; }}
.sev-bar {{ display: flex; height: 10px; border-radius: 5px; overflow: hidden;
  background: var(--line-2); margin-bottom: 8px; }}
.sev-bar span {{ display: block; }}
.sev-bar .s-high {{ background: var(--state-alert); }}
.sev-bar .s-medium {{ background: var(--state-warn-fill); }}
.sev-bar .s-low {{ background: var(--state-unstable); }}
.sev-legend {{ display: flex; flex-wrap: wrap; gap: 4px 18px; margin: 0 0 36px; padding: 0;
  list-style: none; font-size: 13px; color: var(--muted-foreground); }}
.sev-legend li::before {{ content: ""; display: inline-block; width: 9px; height: 9px;
  border-radius: 2px; margin-right: 6px; background: var(--lg); }}
.sev-legend .high {{ --lg: var(--state-alert); }}
.sev-legend .medium {{ --lg: var(--state-warn-fill); }}
.sev-legend .low {{ --lg: var(--state-unstable); }}

section.findings > h2, section.crosswalk > h2, section.remediation > h2 {{
  font-family: var(--font-display); font-size: 22px; font-weight: 600; margin: 0 0 12px;
  padding-bottom: 8px; border-bottom: 1px solid var(--line-2);
}}

/* Hallazgo */
.finding {{ background: var(--card); border: 1px solid var(--line-2); border-radius: 10px;
  padding: 18px 16px; margin-bottom: 14px; break-inside: avoid; }}
@media (min-width: 640px) {{
  .finding {{ display: grid; grid-template-columns: 44px 1fr; gap: 16px; padding: 22px 22px; }}
}}
.finding .idx {{ font-family: var(--font-display); font-size: 26px; color: var(--link);
  font-variant-numeric: tabular-nums; line-height: 1; margin-bottom: 8px; }}
@media (min-width: 640px) {{ .finding .idx {{ margin: 3px 0 0; }} }}
.finding.generic .idx {{ color: var(--state-warn); }}
.f-head {{ display: flex; align-items: center; gap: 8px 10px; flex-wrap: wrap; margin-bottom: 10px; }}
.f-head h3 {{ font-family: var(--font-display); font-size: 19px; margin: 0; font-weight: 600;
  line-height: 1.3; flex: 1 1 100%; }}
.pill {{ font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  padding: 3px 9px; border-radius: 999px; white-space: nowrap; }}
.pill.high {{ color: var(--state-on-fill); background: var(--state-alert); }}
.pill.medium {{ color: var(--state-on-fill); background: var(--state-warn); }}
.pill.low {{ color: var(--state-on-fill); background: var(--state-unstable); }}
.tag {{ font-size: 12px; padding: 2px 9px; border-radius: 999px; border: 1px solid;
  color: var(--muted-foreground); }}
.tag.ok {{ border-color: var(--state-ok); }}
.tag.warn {{ border-color: var(--state-warn); }}
.gids {{ font-family: var(--font-mono); font-size: 12.5px; margin: 0 0 12px; }}
.gids .g {{ display: inline-block; background: var(--muted); color: var(--foreground);
  padding: 1px 7px; border-radius: 4px; margin: 0 4px 4px 0; }}
.gids a.g {{ color: var(--link); text-decoration: none; border-bottom: 1px dashed var(--link); }}
dl.f-body {{ margin: 0; display: grid; grid-template-columns: 1fr; gap: 2px 18px; }}
@media (min-width: 640px) {{ dl.f-body {{ grid-template-columns: 132px 1fr; gap: 8px 18px; }} }}
dl.f-body dt {{ font-size: 12px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase;
  color: var(--muted-foreground); padding-top: 8px; }}
@media (min-width: 640px) {{ dl.f-body dt {{ padding-top: 3px; }} }}
dl.f-body dd {{ margin: 0; }}
dl.f-body dd.evidence {{ color: var(--muted-foreground); font-style: italic;
  border-left: 3px solid var(--primary); padding-left: 12px; }}
.merged {{ font-size: 13px; color: var(--muted-foreground); margin: 10px 0 0; }}

/* Mapa regulatorio y medidas correctoras */
section.crosswalk, section.remediation {{ margin-top: 44px; }}
.cw-note, .rem-note {{ font-size: 14px; color: var(--muted-foreground); margin: 0 0 18px; }}
.cw-fw {{ margin-bottom: 22px; }}
.cw-fw h3, .rem-item h3 {{ font-family: var(--font-display); font-size: 17px; margin: 0 0 8px;
  font-weight: 600; }}
.cw-row {{ display: grid; grid-template-columns: 1fr; gap: 2px 16px; padding: 8px 0;
  border-top: 1px solid var(--line-2); }}
@media (min-width: 640px) {{ .cw-row {{ grid-template-columns: 176px 1fr; }} }}
.cw-row .ref {{ font-family: var(--font-mono); font-size: 13px; font-weight: 600; }}
.cw-row .g {{ font-size: 14px; color: var(--muted-foreground); }}
.rem-item {{ background: var(--card); border: 1px solid var(--line-2); border-radius: 10px;
  padding: 14px 16px; margin-bottom: 12px; break-inside: avoid; }}
.rem-item .max-sev {{ font-family: var(--font-sans); font-size: 12px; color: var(--muted-foreground);
  font-weight: 400; }}
.rem-item ul {{ margin: 8px 0 0; padding-left: 20px; }}
.rem-item li {{ margin-bottom: 5px; }}

footer {{ margin-top: 40px; padding-top: 16px; border-top: 2px solid var(--line-2);
  font-size: 12.5px; color: var(--muted-foreground); }}

@media print {{
  :root {{
{bloque_variables(CLARO, sangria="    ")}
  }}
  body {{ background: #fff; font-size: 11pt; }}
  .sheet {{ max-width: none; padding: 0; }}
  .stats, .finding, .cw-fw, .rem-item, .sev-bar {{ break-inside: avoid; }}
  a {{ color: inherit; text-decoration: none; }}
}}
"""


# --------------------------------------------------------------------------- #
# Piezas
# --------------------------------------------------------------------------- #
def _fila(dt: str, valor: str, *, clase: str = "") -> str:
    dd = f'<dd class="{clase}">' if clase else "<dd>"
    return f"<dt>{_esc(dt)}</dt>{dd}{_esc(valor)}</dd>"


def _hallazgo_html(f: Finding, idx: int, ids_medidas: set[str]) -> str:
    anclado = f.is_grounded()
    sev = f.severity.value
    m = MARCO_ES
    partes: list[str] = [f'<article class="finding{"" if anclado else " generic"}">']
    partes.append(f'<div class="idx">{idx:02d}</div><div class="f-main">')

    partes.append('<div class="f-head">')
    partes.append(f"<h3>{_esc(f.title)}</h3>")
    partes.append(f'<span class="pill {sev}">{_esc(_SEVERIDAD.get(f.severity, sev))}</span>')
    if anclado:
        partes.append(f'<span class="tag ok">&#10003; {_esc(m["anclado"])}</span>')
    else:
        partes.append(f'<span class="tag warn">&#9888; {_esc(m["sin_anclaje"])}</span>')
    partes.append("</div>")

    if f.guideline_ids:
        # Los hallazgos de gravedad alta enlazan sus directrices con las medidas correctoras.
        enlazar = f.severity is Severity.HIGH
        chips = "".join(
            f'<a class="g" href="#rem-{_esc(g)}">{_esc(g)}</a>'
            if enlazar and g in ids_medidas
            else f'<span class="g">{_esc(g)}</span>'
            for g in f.guideline_ids
        )
        partes.append(f'<p class="gids">{chips}</p>')

    partes.append('<dl class="f-body">')
    partes.append(_fila(m["punto"], f.locus or m["sin_punto"]))
    partes.append(_fila(m["evidencia"], f.evidence or m["sin_evidencia"], clase="evidence"))
    if f.anti_pattern:
        partes.append(_fila(m["antipatron"], f.anti_pattern))
    if f.rationale:
        partes.append(_fila(m["por_que"], f.rationale))
    if f.recommendation:
        partes.append(_fila(m["recomendacion"], f.recommendation))
    partes.append("</dl>")

    if f.merged_count > 1:
        partes.append(f'<p class="merged">Consolida {f.merged_count} hallazgos en bruto.</p>')
    partes.append("</div></article>")
    return "".join(partes)


def _medidas_html(findings: list[Finding]) -> str:
    filas = remediations_for(findings)
    if not filas:
        return ""
    partes = ['<section class="remediation">', f"<h2>{_esc(MARCO_ES['medidas'])}</h2>"]
    partes.append(
        '<p class="rem-note">Acciones seleccionadas para las directrices que citan los hallazgos '
        "de gravedad media o alta. Son genéricas por directriz (no específicas del sistema) y "
        "completan la recomendación de cada hallazgo, que sí está anclada a este sistema.</p>"
    )
    for g, sev in filas:
        partes.append(f'<div class="rem-item" id="rem-{_esc(g.id)}">')
        partes.append(
            f"<h3>{_esc(g.id)} &middot; <span class=\"gtit\">{_esc(g.title)}</span> "
            f'<span class="max-sev">(gravedad máxima: {_esc(_SEVERIDAD_FEMENINA.get(sev.value, sev.value))})'
            "</span></h3>"
        )
        partes.append("<ul>" + "".join(f"<li>{_esc(r)}</li>" for r in g.remediations) + "</ul>")
        partes.append("</div>")
    partes.append("</section>")
    return "".join(partes)


def _mapa_html(findings: list[Finding]) -> str:
    cw = crosswalk(findings)
    if not cw:
        return ""
    nombres = framework_names()
    partes = ['<section class="crosswalk">', f"<h2>{_esc(MARCO_ES['mapa'])}</h2>"]
    partes.append(
        '<p class="cw-note">Requisitos que tocan los hallazgos, con la directriz que los ancla. '
        "Es orientativo, <b>no es una opinión jurídica</b>: su aplicación depende del "
        "papel de la organización y de si el sistema es de alto riesgo.</p>"
    )
    for fw, items in cw.items():
        partes.append('<div class="cw-fw">')
        partes.append(f"<h3>{_esc(nombres.get(fw, fw))}</h3>")
        for ref, gids in items:
            partes.append(
                f'<div class="cw-row"><span class="ref">{_esc(ref)}</span>'
                f'<span class="g">{_esc(", ".join(gids))}</span></div>'
            )
        partes.append("</div>")
    notas = guideline_notes({gid for f in findings for gid in f.guideline_ids})
    if notas:
        partes.append(f'<div class="cw-fw"><h3>{_esc(MARCO_ES["por_que_mapa"])}</h3>')
        for gid, nota in notas:
            partes.append(
                f'<div class="cw-row"><span class="ref">{_esc(gid)}</span>'
                f'<span class="g">{_esc(nota)}</span></div>'
            )
        partes.append("</div>")
    partes.append("</section>")
    return "".join(partes)


def _procedencia(meta: Mapping[str, Any] | None, approach: str) -> str:
    if not meta:
        return ""
    bits: list[str] = []
    if meta.get("date"):
        bits.append(f"Fecha: {_fecha(meta['date'])}")
    if meta.get("tool_version"):
        bits.append(f"Versión de la herramienta: {meta['tool_version']}")
    modelo = meta.get("model")
    if modelo == _SIN_MODELO_EN or (not modelo and approach == "b0"):
        modelo = _SIN_MODELO_ES
    if modelo:
        bits.append(f"Modelo: {modelo}")
    return _esc(" · ".join(bits)) + " · " if bits else ""


# --------------------------------------------------------------------------- #
# Entrada
# --------------------------------------------------------------------------- #
def dibujar(
    revision: Revision | Mapping[str, Any], *, tema: str = "miguel", modo: str = "auto"
) -> str:
    """HTML autocontenido del informe, en español. `tema` es el del build
    (`miguel`; no hay otro). `modo` es `auto` (sigue al sistema), `claro`
    u `oscuro`. Todo el texto dinámico va escapado."""
    rev = _como_revision(revision)
    findings = _hallazgos(list(rev.findings))
    nombre, dominio, n_fuentes = _datos_dossier(rev.dossier)
    m = MARCO_ES

    n = len(findings)
    anclados = sum(1 for f in findings if f.is_grounded())
    pct = round(anclados / n * 100) if n else 0
    en_bruto = sum(f.merged_count for f in findings)
    cuentas = {s: sum(1 for f in findings if f.severity is s) for s in Severity}

    doc: list[str] = ['<!doctype html><html lang="es"><head><meta charset="utf-8">']
    doc.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    doc.append(f'<meta name="color-scheme" content="{_ESQUEMA.get(modo, "")}">')
    doc.append(f"<title>Revisión · {_esc(nombre)}</title>")
    doc.append(f"<style>{_css(tema, modo)}</style></head><body><main class='sheet'>")

    corpus = _corpus_presentes(findings)
    etiquetas = " · ".join(etiqueta for _p, etiqueta, _a in corpus)
    doc.append("<header class='masthead'>")
    doc.append(f"<p class='kicker'>{_esc(m['kicker'])}</p>")
    doc.append(f"<h1>{_esc(nombre)}</h1>")
    doc.append(f"<p class='domain'>{_esc(dominio)}</p>")
    meta_html = f"<span><b>{m['enfoque']}:</b> {_esc(_ENFOQUE.get(rev.approach, rev.approach))}</span>"
    if n_fuentes is not None:
        meta_html += f"<span><b>{m['fuentes']}:</b> {_esc(n_fuentes)}</span>"
    meta_html += f"<span><b>{m['directrices']}:</b> {_esc(etiquetas)}</span>"
    doc.append(f"<div class='meta'>{meta_html}</div></header>")

    consolidacion = f"{en_bruto}→{n}" if en_bruto > n else "n/a"
    doc.append("<div class='stats'>")
    for valor, etiqueta in (
        (str(n), m["hallazgos"]),
        (f"{pct}%", m["anclados"]),
        (str(cuentas[Severity.HIGH]), m["gravedad_alta"]),
        (consolidacion, m["consolidacion"]),
    ):
        doc.append(f"<div class='stat'><div class='n'>{_esc(valor)}</div><div class='l'>{_esc(etiqueta)}</div></div>")
    doc.append("</div>")

    if n:
        doc.append("<div class='sev-bar' role='img' aria-label='Reparto por gravedad'>")
        for sev, clase in ((Severity.HIGH, "s-high"), (Severity.MEDIUM, "s-medium"), (Severity.LOW, "s-low")):
            ancho = cuentas[sev] / n * 100
            if ancho:
                doc.append(f"<span class='{clase}' style='width:{ancho:.1f}%'></span>")
        doc.append("</div><ul class='sev-legend'>")
        for sev in (Severity.HIGH, Severity.MEDIUM, Severity.LOW):
            doc.append(f"<li class='{sev.value}'>{_SEVERIDAD[sev]}: {cuentas[sev]}</li>")
        doc.append("</ul>")

    ids_medidas = {g.id for g, _ in remediations_for(findings)}
    doc.append(f"<section class='findings'><h2>{_esc(m['hallazgos'])}</h2>")
    if findings:
        doc.extend(_hallazgo_html(f, i, ids_medidas) for i, f in enumerate(findings, 1))
    else:
        doc.append(f"<p><em>{_esc(m['sin_hallazgos'])}</em></p>")
    doc.append("</section>")

    doc.append(_medidas_html(findings))
    if rev.incluir_crosswalk:
        doc.append(_mapa_html(findings))

    atribucion = _unir_y([a for _p, _e, a in corpus])
    doc.append(
        f"<footer>{_procedencia(rev.meta, rev.approach)}Generado por el revisor de la capa de "
        f"interacción humano-IA · hallazgos anclados a {_esc(atribucion)}. "
        "El mapa regulatorio es orientativo, no una opinión jurídica.</footer>"
    )
    doc.append("</main></body></html>")
    return "".join(doc)


def desde_guardada(
    *,
    system_name: str,
    domain: str,
    approach: str,
    findings_json: list[Mapping[str, Any]],
    incluir_crosswalk: bool,
    n_fuentes: int | None = None,
    fecha: str | None = None,
    version_paquete: str | None = None,
    modelo: str | None = None,
    tema: str = "miguel",
    modo: str = "auto",
) -> str:
    """Redibuja una revisión guardada: lo que hay en la fila
    `DossierReview` (`findings_json`, `package_version`, `model`,
    `finished_at`) y en su `Dossier` (`system_name`, `domain`).

    `incluir_crosswalk` es `bool(fila.crosswalk_json)`: una revisión lanzada
    sin mapa regulatorio guarda `{}`. Los hallazgos y el mapa salen de las
    mismas funciones del paquete, así que el contenido es el de la revisión
    original; solo cambia el marco."""
    meta = {"date": fecha, "tool_version": version_paquete, "model": modelo}
    return dibujar(
        Revision(
            dossier={"system_name": system_name, "domain": domain, "n_sources": n_fuentes},
            findings=list(findings_json),
            approach=approach,
            incluir_crosswalk=incluir_crosswalk,
            meta=meta,
        ),
        tema=tema,
        modo=modo,
    )
