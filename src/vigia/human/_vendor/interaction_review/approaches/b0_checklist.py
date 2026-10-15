"""B0 - Deterministic checklist (no LLM). The floor of the baseline ladder.

By construction, B0 ignores the dossier content and emits a fixed question
per guideline. It is GENERIC on purpose: it does not anchor the findings in a locus
or in evidence from the concrete system. It serves to set the lowest bar: if an
LLM-based approach (B1) does not clearly beat this, the LLM is contributing nothing.
"""

from __future__ import annotations

from ..schemas import Dossier, Finding, Guideline


def run(dossier: Dossier, guidelines: list[Guideline]) -> list[Finding]:
    findings: list[Finding] = []
    for i, g in enumerate(guidelines, start=1):
        findings.append(
            Finding(
                id=f"b0-{i:03d}",
                title=f"Revisar guideline: {g.title}",
                guideline_ids=[g.id],
                # locus and evidence empty ON PURPOSE: B0 does not look at the system.
                locus="",
                evidence="",
                anti_pattern=g.anti_patterns[0] if g.anti_patterns else None,
                rationale=f"Comprobacion generica del cumplimiento de {g.id}.",
                recommendation=f"Verificar manualmente si el sistema cumple: {g.description}",
            )
        )
    return findings
