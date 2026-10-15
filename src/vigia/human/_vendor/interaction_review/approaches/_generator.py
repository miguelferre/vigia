"""Findings generation via LLM, shared by B1 (zero-shot) and B2 (few-shot)."""

from __future__ import annotations

import os

from .. import llm, prompts
from ..schemas import Dossier, Finding, Guideline, Severity


def gen_temperature() -> float:
    # Temperature > 0 on purpose: we want variability across the k runs
    # so we can measure stability.
    return float(os.environ.get("GEN_TEMPERATURE", "1.0"))


def _to_finding(label: str, idx: int, raw: dict) -> Finding:
    sev = raw.get("severity", "medium")
    try:
        severity = Severity(sev)
    except ValueError:
        severity = Severity.MEDIUM
    return Finding(
        id=f"{label}-{idx:03d}",
        title=str(raw.get("title", "")).strip() or "(no title)",
        guideline_ids=[str(g) for g in raw.get("guideline_ids", []) if str(g).strip()],
        locus=str(raw.get("locus", "")).strip(),
        evidence=str(raw.get("evidence", "")).strip(),
        anti_pattern=(raw.get("anti_pattern") or None),
        severity=severity,
        rationale=str(raw.get("rationale", "")).strip(),
        recommendation=str(raw.get("recommendation", "")).strip(),
    )


def generate(
    dossier: Dossier, guidelines: list[Guideline], *, few_shot: bool, label: str, extra: str = ""
) -> list[Finding]:
    """One LLM call -> list of Finding. `label` prefixes the ids (b1/b2).

    `extra`: optional additional instruction in the prompt (e.g. push exhaustiveness in B1x).
    """
    user = prompts.generator_user(dossier, guidelines, few_shot=few_shot, extra=extra)
    out = llm.call_structured(
        model=llm.gen_model(),
        system=prompts.GENERATOR_SYSTEM,
        user=user,
        tool=prompts.FINDINGS_TOOL,
        temperature=gen_temperature(),
    )
    raw_findings = out.get("findings", []) if isinstance(out, dict) else []
    # Robustness: Anthropic's tool-use does not guarantee the structure like the local `format`.
    # If 'findings' comes as a dict, take its values; discard items that are not objects.
    if isinstance(raw_findings, dict):
        raw_findings = list(raw_findings.values())
    items = [rf for rf in raw_findings if isinstance(rf, dict)]
    return [_to_finding(label, i, rf) for i, rf in enumerate(items, start=1)]
