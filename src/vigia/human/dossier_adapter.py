"""Adaptador del dossier de auditoría: junto a `human/ir_adapter.py`,
el único módulo que importa `interaction_review`.

Reconstruye el markdown de cada plantilla desde las respuestas estructuradas
del frontend (`human/dossier_markdown.py`), construye el `Dossier` del
paquete, calcula su sha256 y corre la revisión (`b0`, `p3` o `auto`) en
memoria, sin ficheros temporales ni variables de entorno fuera de
`llm_environment` (`human/llm_env.py`, reexportado aquí).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from vigia.human import informe_revision
from vigia.human._vendor.interaction_review import __version__ as PACKAGE_VERSION
from vigia.human._vendor.interaction_review.dedup import deduplicate
from vigia.human._vendor.interaction_review.guidelines import all_guidelines
from vigia.human._vendor.interaction_review.ingest import build_dossier, extract_answers
from vigia.human._vendor.interaction_review.llm import LLMNotConfigured, gen_model
from vigia.human._vendor.interaction_review.regulatory import crosswalk as _crosswalk
from vigia.human._vendor.interaction_review.router import route as _route
from vigia.human._vendor.interaction_review.schemas import Dossier, Finding, Guideline
from vigia.human.dossier_import import traducir_errores
from vigia.human.dossier_markdown import (
    render_form_markdown,
    render_inventory_markdown,
    sha256_dossier,
)
from vigia.human.llm_env import llm_environment

__all__ = [
    "PACKAGE_VERSION",
    "REVIEW_APPROACHES",
    "DossierInvalido",
    "DossierMarkdown",
    "LLMNotConfigured",
    "ReviewResult",
    "assemble_dossier",
    "assemble_markdown",
    "corpus_hash",
    "llm_environment",
    "provenance",
    "reconstruir_respuestas",
    "run_review",
    "validar_dossier_importado",
]

REVIEW_APPROACHES = ("b0", "p3", "auto")


@dataclass(frozen=True)
class DossierMarkdown:
    """Markdown ensamblado de las tres plantillas y su sha256."""

    profile_md: str
    experience_md: str
    inventory_md: str
    sha256: str


def assemble_markdown(
    *,
    profile: dict[str, str] | None,
    experience: dict[str, str] | None,
    inventory: dict[str, str] | None,
    telemetry_text: str | None,
    preguntas_por_formulario: dict[str, list[dict]] | None = None,
) -> DossierMarkdown:
    """Reconstruye el markdown de las tres plantillas desde las respuestas
    estructuradas. `preguntas_por_formulario` es el resultado de
    `GET /content/dossier-plantillas` (claves `system_card`,
    `usage_experience`, `document_inventory`, cada una con su lista
    `preguntas`); sin él, toda clave de respuesta se trata como texto libre.
    """
    preguntas = preguntas_por_formulario or {}
    profile_md = render_form_markdown(
        "System card (technical profile)", profile or {}, preguntas.get("system_card")
    )
    experience_md = render_form_markdown(
        "Usage experience (end user)", experience or {}, preguntas.get("usage_experience")
    )
    inventory_md = render_inventory_markdown(
        "Document inventory", inventory or {}, preguntas.get("document_inventory")
    )
    sha = sha256_dossier(profile_md, experience_md, inventory_md, telemetry_text)
    return DossierMarkdown(profile_md, experience_md, inventory_md, sha)


def _referencia_linea_base(baseline_batch: dict[str, Any]) -> str:
    """Línea de referencia del lote base para anteponer a
    `summary`: `{"id", "seq", "phase_label"}`, la misma forma que `first_batch`
    de `ProjectState` (`services/projects.py:project_state`)."""
    seq = baseline_batch.get("seq")
    etiqueta = baseline_batch.get("phase_label")
    partes = [f"lote #{seq}" if seq is not None else "lote sin número"]
    if etiqueta:
        partes.append(str(etiqueta))
    return f"Línea base: {' · '.join(partes)}."


def assemble_dossier(
    md: DossierMarkdown,
    *,
    telemetry_text: str | None,
    system_name: str,
    domain: str,
    summary: str = "",
    baseline_batch: dict[str, Any] | None = None,
) -> Dossier:
    """`ingest.build_dossier` con los tres textos ya reconstruidos.

    Lanza `ValueError` (mensaje literal del paquete, «No template had
    answers. Were the ✍️ blanks filled in?») si ninguna plantilla trae
    respuesta; el servicio lo traduce a 422.

    `baseline_batch` (opcional): el `first_batch` del proyecto
    (`ProjectState`/`project_state`, `id`/`seq`/`phase_label`), si el llamador
    lo tiene a mano. Se antepone a `summary` como referencia del dossier. Lo
    pasa `services/dossiers_review_job.py`, que es donde se arma el dossier
    que va a la revisión; la validación de `services/dossiers.py` no lo
    necesita.
    """
    resumen = summary
    if baseline_batch is not None:
        referencia = _referencia_linea_base(baseline_batch)
        resumen = f"{referencia}\n\n{summary}" if summary else referencia
    return build_dossier(
        profile_texts=[md.profile_md],
        experience_texts=[md.experience_md],
        inventory_text=md.inventory_md,
        telemetry_text=telemetry_text,
        system_name=system_name,
        domain=domain,
        summary=resumen,
    )


class DossierInvalido(ValueError):
    """El `dossier.json` no valida contra `schemas.Dossier` del paquete.
    `str(exc)` es el mensaje en español con los campos que fallan."""


def validar_dossier_importado(datos: dict[str, Any]) -> Dossier:
    """Valida el contenido de un `dossier.json` con el `Dossier` del paquete.
    Lanza `DossierInvalido` con el campo que falla, en español."""
    try:
        return Dossier.model_validate(datos)
    except ValidationError as exc:
        raise DossierInvalido(traducir_errores(exc.errors(include_input=False))) from exc


def reconstruir_respuestas(markdown: str) -> list[tuple[str, str]]:
    """`(pregunta, respuesta)` que `build_dossier` extrae de un markdown de
    plantilla: lo que ve de verdad el revisor (se compara contra esto)."""
    return extract_answers(markdown)


def _select_guidelines(corpus: str) -> tuple[Guideline, ...]:
    """`corpus="todas"` (por defecto) es `all_guidelines()`; si no, subconjunto
    por prefijo (`hax`, `pair`, `ix`, separados por coma), como
    `_select_guidelines` de `mcp_server.py` en el paquete."""
    if not corpus or corpus == "todas":
        return all_guidelines()
    alias = {"hax": "HAX", "pair": "PAIR", "ix": "IX"}
    prefijos = {alias.get(c.strip().lower(), c.strip().upper()) for c in corpus.split(",") if c.strip()}
    return tuple(g for g in all_guidelines() if g.corpus.value in prefijos)


def corpus_hash(guidelines: tuple[Guideline, ...]) -> str:
    """sha256 de las directrices cargadas."""
    payload = json.dumps(
        [g.model_dump(mode="json") for g in guidelines], sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def provenance(*, approach: str) -> dict[str, str]:
    """`meta` del informe (`informe_revision`): `"deterministic (no model)"` en `b0`,
    como `_provenance` de `mcp_server.py` en el paquete."""
    # `gen_model()` lee `GEN_MODEL` del entorno ya fijado por `llm_environment` y,
    # si está vacío, aplica el modelo por defecto del paquete para ese backend.
    modelo = "deterministic (no model)" if approach == "b0" else gen_model()
    return {
        "date": datetime.now(UTC).isoformat(),
        "tool_version": PACKAGE_VERSION,
        "model": modelo,
    }


@dataclass(frozen=True)
class ReviewResult:
    findings: list[dict]
    crosswalk: dict[str, list[dict]]
    report_html: str
    n_findings: int
    corpus_hash: str
    prompt_sha256: str | None
    # Modelo efectivo (`gen_model()` del paquete); `None` en `b0`.
    model: str | None


def run_review(
    dossier: Dossier,
    *,
    approach: str,
    corpus: str = "todas",
    dedup: bool = True,
    incluir_crosswalk: bool = True,
) -> ReviewResult:
    """Corre `b0`, `p3` o `auto` sobre `dossier`.

    `b0` ignora `dedup`: su fuente no llama al LLM y `dedup` solo aplica a
    `p3`/`auto`. Puede lanzar `LLMNotConfigured` u otra
    excepción del paquete si `p3`/`auto` no tienen backend disponible: el
    servicio la captura y deja la fila en `status="error"`.
    """
    from vigia.human._vendor.interaction_review.approaches import b0_checklist, p3_pipeline

    guidelines = _select_guidelines(corpus)
    lista_guidelines = list(guidelines)
    findings: list[Finding]
    if approach == "b0":
        findings = b0_checklist.run(dossier, lista_guidelines)
    elif approach == "p3":
        findings = p3_pipeline.run(dossier, lista_guidelines)
        if dedup:
            findings = deduplicate(findings)
    elif approach == "auto":
        findings, _eleccion = _route(dossier, lista_guidelines)
    else:  # pragma: no cover - validado antes en el servicio
        raise ValueError(f"approach desconocido: {approach!r}")

    crosswalk_dict: dict[str, list[dict]] = {}
    if incluir_crosswalk:
        crudo = _crosswalk(findings)
        crosswalk_dict = {
            fw: [{"ref": ref, "guidelines": gids} for ref, gids in items] for fw, items in crudo.items()
        }

    # El informe lo dibuja Vigía en español con los tokens del tema.
    html = informe_revision.dibujar(
        informe_revision.Revision(
            dossier=dossier,
            findings=findings,
            approach=approach,
            incluir_crosswalk=incluir_crosswalk,
            meta=provenance(approach=approach),
        )
    )

    prompt_sha256: str | None = None
    if approach != "b0":
        # El paquete no expone el prompt ensamblado sin llamar al modelo: se
        # usa el sha256 del fichero de prompts como sustituto documentado.
        from vigia.human._vendor.interaction_review import prompts as _prompts_mod

        with open(_prompts_mod.__file__, "rb") as f:
            prompt_sha256 = hashlib.sha256(f.read()).hexdigest()

    return ReviewResult(
        findings=[f.model_dump(mode="json") for f in findings],
        crosswalk=crosswalk_dict,
        report_html=html,
        n_findings=len(findings),
        corpus_hash=corpus_hash(guidelines),
        prompt_sha256=prompt_sha256,
        model=None if approach == "b0" else gen_model(),
    )
