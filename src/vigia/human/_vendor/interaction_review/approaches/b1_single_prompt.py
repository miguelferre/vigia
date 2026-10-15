"""B1 - Single zero-shot prompt. The LLM baseline to beat."""

from __future__ import annotations

from ._generator import generate
from ..schemas import Dossier, Finding, Guideline


def run(dossier: Dossier, guidelines: list[Guideline]) -> list[Finding]:
    return generate(dossier, guidelines, few_shot=False, label="b1")
