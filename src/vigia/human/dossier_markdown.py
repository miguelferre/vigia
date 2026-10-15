"""Reconstrucción del markdown de las plantillas de `interaction_review` desde
las respuestas estructuradas del frontend.

Sin importar `interaction_review`: solo texto. `human/dossier_adapter.py` es
quien alimenta el resultado a `ingest.build_dossier`. Partido de
`dossier_adapter.py` porque el conjunto pasaba de 9 KB.
"""

from __future__ import annotations

import hashlib

__all__ = ["render_form_markdown", "render_inventory_markdown", "sha256_dossier"]

# ✍️ = U+270D (WRITING HAND) + U+FE0F (variation selector), el marcador que
# `interaction_review.ingest.extract_answers` busca para delimitar una
# respuesta.
_PEN = "✍️"

# Marcadores que `interaction_review.ingest._is_structural` reconoce como el
# principio de una pregunta o sección nueva (tras `strip()`).
# `_is_question_bullet` admite `- ` y `* ` seguidos de `**` o `[`.
_MARCADORES_ESTRUCTURALES = ("#", "---", ">", "**", "- **", "- [", "* **", "* [")


def _es_linea_estructural(linea: str) -> bool:
    """Replica `_is_structural` del paquete: una línea (recortada) que
    empieza por uno de los marcadores, o que contiene el marcador ✍
    (confundiría al parser con una respuesta nueva)."""
    recortada = linea.strip()
    if not recortada:
        return False
    if recortada.startswith(_MARCADORES_ESTRUCTURALES):
        return True
    return "🎯" in recortada or "✍" in recortada


def _sanear_respuesta(texto: str) -> str:
    """Sanea una respuesta multilínea antes de volcarla al markdown que lee
    `interaction_review.ingest.extract_answers`.

    Sin este saneado, una línea de continuación que empezara por uno de los
    marcadores estructurales del parser (`#`, `---`, `>`, `**`, una viñeta
    en negrita o casilla `- **`/`- [`) se interpretaría como el principio de
    una pregunta o sección nueva, y el resto de la respuesta se perdería en
    silencio. Regla: cada línea de continuación (todas menos la primera)
    que, tras `strip()`, empiece por uno de esos marcadores se escapa con
    `\\` por delante; y cualquier carácter ✍ literal dentro de la respuesta
    (en cualquier línea) se sustituye por ✎ para no crear un marcador de
    respuesta espurio.
    """
    lineas = texto.split("\n")
    saneadas = []
    for i, linea in enumerate(lineas):
        linea = linea.replace("✍️", "✎").replace("✍", "✎")
        if i > 0 and _es_linea_estructural(linea):
            linea = f"\\{linea}"
        saneadas.append(linea)
    return "\n".join(saneadas)


def _resolver_pregunta(clave: str, preguntas: list[dict] | None) -> tuple[str, str]:
    """`(seccion, texto)` para una clave de respuesta: id de una plantilla real
    (`GET /content/dossier-plantillas`) o texto libre de la pregunta.

    Si la clave es un `id` conocido, usa su `seccion` y `texto`; si no,
    sección «Otras respuestas» y la clave como texto de la pregunta (así el
    ejemplo `{"¿Qué hace el sistema?": "..."}`, sigue valiendo).
    """
    if preguntas:
        for p in preguntas:
            if p.get("id") == clave:
                return p.get("seccion", ""), p.get("texto", clave)
    return "Otras respuestas", clave


def render_form_markdown(
    titulo: str, respuestas: dict[str, str], preguntas: list[dict] | None = None
) -> str:
    """Markdown de un formulario (perfil o experiencia de uso).

    `# {titulo}\n\n---\n\n` y, por cada respuesta no vacía,
    `## {seccion}\n\n- **{texto}**\n  ✍️ {respuesta}\n\n`, en el orden de
    `respuestas`. La respuesta pasa por `_sanear_respuesta` antes de
    volcarse: ver su docstring.
    """
    partes = [f"# {titulo}", "", "---", ""]
    for clave, respuesta in respuestas.items():
        texto_respuesta = (respuesta or "").strip()
        if not texto_respuesta:
            continue
        seccion, texto = _resolver_pregunta(clave, preguntas)
        partes.append(f"## {seccion}")
        partes.append("")
        partes.append(f"- **{texto}**")
        partes.append(f"  {_PEN} {_sanear_respuesta(texto_respuesta)}")
        partes.append("")
    return "\n".join(partes)


def render_inventory_markdown(
    titulo: str, respuestas: dict[str, str], preguntas: list[dict] | None = None
) -> str:
    """Markdown del inventario de documentos.

    Respuesta vacía o «no» (sin distinguir mayúsculas) deja
    `- [ ] **{doc}**` sin respuesta; cualquier otra deja
    `- [x] **{doc}**\n  - Quién lo tiene / formato:\n    ✍️ {respuesta}`,
    también saneada (`_sanear_respuesta`).
    """
    partes = [f"# {titulo}", "", "---", ""]
    for clave, respuesta in respuestas.items():
        _seccion, doc = _resolver_pregunta(clave, preguntas)
        texto_respuesta = (respuesta or "").strip()
        if not texto_respuesta or texto_respuesta.lower() == "no":
            partes.append(f"- [ ] **{doc}**")
        else:
            partes.append(f"- [x] **{doc}**")
            partes.append("  - Quién lo tiene / formato:")
            partes.append(f"    {_PEN} {_sanear_respuesta(texto_respuesta)}")
        partes.append("")
    return "\n".join(partes)


def sha256_dossier(
    profile_md: str, experience_md: str, inventory_md: str, telemetry_text: str | None
) -> str:
    """sha256 del markdown ensamblado: las tres plantillas más
    `telemetry_text`, en ese orden."""
    ensamblado = "\n".join([profile_md, experience_md, inventory_md, telemetry_text or ""])
    return hashlib.sha256(ensamblado.encode("utf-8")).hexdigest()
