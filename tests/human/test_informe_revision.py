"""`human/informe_revision.py` dibuja el informe de la
revisión en español, con los mismos datos que el informe viejo del paquete."""

from __future__ import annotations

import html as html_mod
import json
import re
from pathlib import Path

import pytest

pytest.importorskip("vigia.human._vendor.interaction_review")

from vigia.human import informe_revision
from vigia.human._vendor.interaction_review.approaches import b0_checklist
from vigia.human._vendor.interaction_review.guidelines import all_guidelines
from vigia.human._vendor.interaction_review.regulatory import crosswalk
from vigia.human._vendor.interaction_review.schemas import Dossier, Finding, Severity

CASOS = Path(__file__).resolve().parents[1] / "fixtures" / "casos-externos"
CASOS_B0 = ["compas", "epic-sepsis", "sistema-bueno"]


def _dossier(caso: str) -> Dossier:
    datos = json.loads((CASOS / caso / "dossier.json").read_text(encoding="utf-8"))
    return Dossier.model_validate(datos)


def _hallazgos_sinteticos() -> list[Finding]:
    """Los tres niveles de gravedad, anclado y sin anclar, consolidado y con
    texto que hay que escapar."""
    return [
        Finding(
            id="f1",
            title="El profesional no ve cuándo el modelo duda <b>nunca</b>",
            guideline_ids=["HAX-G2", "PAIR-FC-2"],
            locus="Pantalla de resultado del triaje",
            evidence='«Solo enseña "refer" o "no-refer"»',
            anti_pattern="Confianza sin calibrar",
            severity=Severity.HIGH,
            rationale="Sin incertidumbre visible, el profesional no sabe cuándo contrastar.",
            recommendation="Mostrar la confianza del modelo junto a cada resultado.",
            merged_count=3,
        ),
        Finding(
            id="f2",
            title="No hay forma de corregir un resultado",
            guideline_ids=["HAX-G9"],
            locus="Flujo de revisión",
            evidence="El manual no menciona la corrección.",
            severity=Severity.MEDIUM,
            rationale="Los errores se repiten.",
            recommendation="Añadir un botón de corrección.",
        ),
        Finding(id="f3", title="Aviso genérico", guideline_ids=["HAX-G1"], severity=Severity.LOW),
    ]


_META = {"date": "2026-10-06T12:30:00+00:00", "tool_version": "0.1.0", "model": "deterministic (no model)"}


def _revision(findings, **kw):
    return informe_revision.Revision(
        dossier=Dossier.model_validate(
            {
                "system_name": "Triaje de digestivo <demo>",
                "domain": "Atención primaria",
                "sources": [
                    {"id": "s1", "kind": "technician", "label": "Perfil", "content": "texto"},
                    {"id": "s2", "kind": "end_user", "label": "Uso", "content": "texto"},
                ],
            }
        ),
        findings=findings,
        approach="b0",
        meta=_META,
        **kw,
    )


# --------------------------------------------------------------------------- #
# Marco en español
# --------------------------------------------------------------------------- #
# Cadenas fijas del marco viejo (`report_html.py:41-155,301-383`).
_MARCO_VIEJO = [
    r"Findings", r"Severity", r"Remediation", r"Summary", r"Guidelines?", r"Approach", r"Sources",
    r"Anchored", r"Not anchored", r"Consolidat(?:ion|es)", r"Evidence", r"Locus", r"Recommendation",
    r"Anti-pattern", r"Why it matters", r"Why these map", r"Regulatory crosswalk", r"raw findings",
    r"Human-AI interaction layer review", r"Tool version", r"Generated", r"legal opinion",
    r"Curated actions", r"No findings", r"Requirements touched", r"max severity",
    r"\bHigh\b", r"\bMedium\b", r"\bLow\b", r"\bModel:", r"\bReview\b", r"interaction-layer extension",
    r"\bby the\b", r"\band\b",
]


def _texto_visible(doc: str) -> str:
    sin_estilo = re.sub(r"<style>.*?</style>", "", doc, flags=re.DOTALL)
    # Los títulos de directriz llevan el original inglés entre paréntesis (HAX); es contenido, no marco.
    sin_titulos = re.sub(r'<span class="gtit">.*?</span>', "", sin_estilo, flags=re.DOTALL)
    return html_mod.unescape(re.sub(r"<[^>]+>", " ", sin_titulos))


def test_lang_es_y_marco_sin_ingles():
    doc = informe_revision.dibujar(_revision(_hallazgos_sinteticos()))
    assert '<html lang="es"' in doc
    assert "lang='en'" not in doc and 'lang="en"' not in doc
    texto = _texto_visible(doc)
    # Las directrices, las medidas y el mapa regulatorio vienen del paquete (contenido,
    # no marco); se comprueban las palabras del marco viejo sobre lo que dibuja Vigía.
    marco = re.sub(r'<div class="rem-item".*?</div>', "", doc, flags=re.DOTALL)
    marco = re.sub(r'<div class="cw-fw">.*?</div>\s*</div>', "", marco, flags=re.DOTALL)
    texto = _texto_visible(marco)
    encontradas = [p for p in _MARCO_VIEJO if re.search(p, texto)]
    assert encontradas == [], encontradas


def test_marco_en_espanol_presente():
    doc = informe_revision.dibujar(_revision(_hallazgos_sinteticos()))
    for cadena in (
        "Revisión de la capa de interacción humano-IA", "Enfoque:", "Fuentes:", "Directrices:",
        "Hallazgos", "Anclados", "Gravedad alta", "Consolidación", "Punto del sistema",
        "Evidencia", "Antipatrón", "Por qué importa", "Recomendación", "Medidas correctoras",
        "Mapa regulatorio", "Por qué se asocian", "Consolida 3 hallazgos en bruto",
        "gravedad máxima: alta", "no es una opinión jurídica", "Fecha: 2026-10-06 12:30 UTC",
        "Modelo: determinista (sin modelo)", "anclados a HAX-18 (Microsoft) y PAIR (Google).",
    ):
        assert cadena in doc, cadena


def test_sin_hallazgos_y_sin_mapa():
    doc = informe_revision.dibujar(_revision([]))
    assert "Sin hallazgos" in doc
    assert 'class="crosswalk"' not in doc and 'class="remediation"' not in doc
    assert "HAX-18 (Microsoft), PAIR (Google) e IX" in doc  # sin hallazgos nombra el marco completo


def test_incluir_crosswalk_false_quita_el_mapa():
    con = informe_revision.dibujar(_revision(_hallazgos_sinteticos(), incluir_crosswalk=True))
    sin = informe_revision.dibujar(_revision(_hallazgos_sinteticos(), incluir_crosswalk=False))
    assert 'class="crosswalk"' in con
    assert 'class="crosswalk"' not in sin
    assert 'class="remediation"' in sin  # las medidas no dependen del mapa


def test_escapa_el_texto_dinamico():
    doc = informe_revision.dibujar(_revision(_hallazgos_sinteticos()))
    assert "<b>nunca</b>" not in doc
    assert "&lt;b&gt;nunca&lt;/b&gt;" in doc
    assert "Triaje de digestivo &lt;demo&gt;" in doc


def test_acepta_diccionarios():
    doc = informe_revision.dibujar(
        {
            "dossier": {"system_name": "Sistema", "domain": "Dominio", "n_sources": 4},
            "findings": [f.model_dump(mode="json") for f in _hallazgos_sinteticos()],
            "approach": "p3",
            "meta": {"date": "2026-10-06T12:30:00+00:00", "model": "claude-x"},
        }
    )
    assert "Fuentes:</b> 4" in doc
    assert "p3 (con modelo)" in doc
    assert "Modelo: claude-x" in doc


def test_tema_desconocido_falla():
    with pytest.raises(ValueError, match="tema desconocido"):
        informe_revision.dibujar(_revision([]), tema="otro")


# --------------------------------------------------------------------------- #
# Tema
# --------------------------------------------------------------------------- #
def test_css_con_tokens_oscuro_e_impresion():
    doc = informe_revision.dibujar(_revision(_hallazgos_sinteticos()))
    assert "@media (prefers-color-scheme: dark)" in doc
    assert "@media print" in doc
    assert "--primary: #6E5AB8" in doc and "--primary: #BFAEE8" in doc
    assert "Segoe UI Variable" in doc
    # Sin red, sin scripts, sin marca ajena
    assert "<script" not in doc and "http://" not in doc and "https://" not in doc
    assert "@import" not in doc
    # El literal va por partes para no romper `test_privados_aislados`.
    assert "g" + "mv" not in doc.lower() and "ap" + "tos" not in doc.lower()
    # la impresión vuelve a los tokens claros aunque el sistema esté en oscuro
    imprimir = doc[doc.index("@media print"):]
    assert "--background: #F6F5F9" in imprimir


# --------------------------------------------------------------------------- #
# Mismo contenido que el informe viejo
# --------------------------------------------------------------------------- #
def _extraer(doc: str) -> dict:
    """Datos del informe, leídos de las clases estructurales que comparten el
    informe viejo y el nuevo."""
    hallazgos = []
    for bloque in re.findall(r'<article class="finding[^"]*">(.*?)</article>', doc, flags=re.DOTALL):
        hallazgos.append(
            {
                "titulo": html_mod.unescape(re.search(r"<h3>(.*?)</h3>", bloque, re.DOTALL).group(1)),
                "gravedad": re.search(r'<span class="pill (\w+)">', bloque).group(1),
                "directrices": re.findall(r'<(?:span|a) class="g"[^>]*>([^<]+)</', bloque),
            }
        )
    mapa = [
        (html_mod.unescape(ref), html_mod.unescape(gids))
        for ref, gids in re.findall(r'<div class="cw-row"><span class="ref">(.*?)</span><span class="g">(.*?)</span>', doc)
    ]
    medidas = re.findall(r'<div class="rem-item" id="rem-([^"]+)">', doc)
    return {"hallazgos": hallazgos, "mapa": mapa, "medidas": medidas}


def _esperado(findings: list[Finding]) -> dict:
    return {
        "hallazgos": [
            {"titulo": f.title, "gravedad": f.severity.value, "directrices": list(f.guideline_ids)}
            for f in findings
        ],
        "n_filas_mapa": sum(len(items) for items in crosswalk(findings).values()),
    }


def _comprobar(findings: list[Finding], doc_nuevo: str) -> None:
    nuevo = _extraer(doc_nuevo)
    esperado = _esperado(findings)
    assert nuevo["hallazgos"] == esperado["hallazgos"]
    refs = [(ref, ", ".join(g)) for items in crosswalk(findings).values() for ref, g in items]
    assert [fila for fila in nuevo["mapa"] if fila in refs] == refs
    assert len(nuevo["mapa"]) >= esperado["n_filas_mapa"]


@pytest.mark.parametrize("caso", CASOS_B0)
def test_mismos_datos_que_el_informe_viejo_con_b0(caso):
    dossier = _dossier(caso)
    findings = b0_checklist.run(dossier, list(all_guidelines()))
    nuevo = informe_revision.dibujar(
        informe_revision.Revision(dossier=dossier, findings=findings, approach="b0", meta=_META)
    )
    _comprobar(findings, nuevo)

    # Si el paquete vendorizado aún trae el renderizador viejo, se compara contra él.
    try:
        from vigia.human._vendor.interaction_review.report_html import render_findings_html
    except ImportError:  # report_html.py no se vendoriza si nada más lo usa
        return
    viejo = render_findings_html(dossier, findings, "b0", include_crosswalk=True, meta=_META)
    assert _extraer(viejo) == _extraer(nuevo)


def test_mismos_datos_que_el_informe_viejo_con_gravedades_mezcladas():
    findings = _hallazgos_sinteticos()
    dossier = _revision(findings).dossier
    nuevo = informe_revision.dibujar(_revision(findings))
    _comprobar(findings, nuevo)
    try:
        from vigia.human._vendor.interaction_review.report_html import render_findings_html
    except ImportError:
        return
    viejo = render_findings_html(dossier, findings, "b0", include_crosswalk=True, meta=_META)
    assert _extraer(viejo) == _extraer(nuevo)


def test_las_gravedades_altas_enlazan_con_las_medidas():
    doc = informe_revision.dibujar(_revision(_hallazgos_sinteticos()))
    datos = _extraer(doc)
    assert "HAX-G2" in datos["medidas"]
    assert 'href="#rem-HAX-G2"' in doc
    # el hallazgo bajo no arrastra medidas
    assert "HAX-G1" not in datos["medidas"]


# --------------------------------------------------------------------------- #
# Redibujar una revisión guardada
# --------------------------------------------------------------------------- #
def test_desde_guardada_redibuja_con_findings_json():
    findings = _hallazgos_sinteticos()
    guardado = [f.model_dump(mode="json") for f in findings]
    doc = informe_revision.desde_guardada(
        system_name="Triaje",
        domain="Atención primaria",
        approach="b0",
        findings_json=guardado,
        incluir_crosswalk=True,
        n_fuentes=5,
        fecha="2026-09-20T08:00:00+00:00",
        version_paquete="0.1.0",
        modelo=None,
    )
    assert '<html lang="es"' in doc
    assert "Fuentes:</b> 5" in doc
    assert "Modelo: determinista (sin modelo)" in doc
    assert "Fecha: 2026-09-20 08:00 UTC" in doc
    assert _extraer(doc)["hallazgos"] == _esperado(findings)["hallazgos"]


def test_desde_guardada_sin_fuentes_ni_meta():
    doc = informe_revision.desde_guardada(
        system_name="S", domain="D", approach="p3", findings_json=[], incluir_crosswalk=False
    )
    assert "Fuentes:" not in doc
    assert "Fecha:" not in doc


# --------------------------------------------------------------------------- #
# Modo de color (el selector de la app no llega al iframe)
# --------------------------------------------------------------------------- #
def test_modo_claro_oscuro_y_auto():
    findings = _hallazgos_sinteticos()
    auto = informe_revision.dibujar(_revision(findings))
    claro = informe_revision.dibujar(_revision(findings), modo="claro")
    oscuro = informe_revision.dibujar(_revision(findings), modo="oscuro")
    assert "prefers-color-scheme: dark" in auto
    assert "prefers-color-scheme" not in claro and "--background: #18181B" not in claro
    assert "prefers-color-scheme" not in oscuro
    assert oscuro.index("--background: #18181B") < oscuro.index("@media print")
    # al imprimir siempre vuelve el claro
    assert "--background: #F6F5F9" in oscuro[oscuro.index("@media print") :]
    assert 'content="dark"' in oscuro and 'content="light"' in claro


def test_modo_desconocido_falla():
    with pytest.raises(ValueError, match="modo desconocido"):
        informe_revision.dibujar(_revision([]), modo="sepia")
