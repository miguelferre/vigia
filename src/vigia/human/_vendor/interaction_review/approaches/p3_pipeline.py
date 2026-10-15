"""p3 - Deterministic pipeline (NOT an agent): sweep by aspect blocks.

Hypothesis (from the B1 data): a single pass covers ~38% per run but the union
of several reaches ~73%; that is, a single pass leaves aspects out. p3 makes one
FOCUSED pass per guideline block and merges the findings, to raise recall
per run without losing anchoring.

FIXED flow (no autonomous model decisions): N passes (one per block) -> merge.
That is what distinguishes it from an agent (A4): here the control flow is decided by the code.
"""

from __future__ import annotations

from ._generator import generate
from ..schemas import Dossier, Finding, Guideline

# Interaction aspect blocks -> guideline ids. They cover ALL of HAX-18 + PAIR + IX.
BUCKETS: dict[str, list[str]] = {
    "presentacion_y_confianza": ["HAX-G2", "HAX-G4", "HAX-G11", "PAIR-ET-1", "PAIR-ET-2", "PAIR-ET-3"],
    "correccion_y_feedback": ["HAX-G9", "HAX-G15", "HAX-G16", "PAIR-FC-1", "PAIR-FC-2", "IX-1"],
    "invocacion_alertas_tiempo": ["HAX-G3", "HAX-G5", "HAX-G7", "HAX-G8"],
    "onboarding_modelo_mental": ["HAX-G1", "PAIR-MM-1", "PAIR-MM-2", "PAIR-UN-1", "PAIR-UN-2"],
    "robustez_evolucion_supervision": [
        "HAX-G6", "HAX-G10", "HAX-G12", "HAX-G13", "HAX-G14", "HAX-G17", "HAX-G18",
        "PAIR-EF-1", "PAIR-EF-2", "PAIR-DE-1", "IX-2",
    ],
}


def run(dossier: Dossier, guidelines: list[Guideline]) -> list[Finding]:
    by_id = {g.id: g for g in guidelines}
    collected: list[Finding] = []
    for bucket, ids in BUCKETS.items():
        gl = [by_id[i] for i in ids if i in by_id]
        if not gl:
            continue
        collected.extend(generate(dossier, gl, few_shot=False, label=f"p3-{bucket}"))
    # Unique and stable re-id (the per-block labels would collide in the index).
    return [f.model_copy(update={"id": f"p3-{n:03d}"}) for n, f in enumerate(collected, start=1)]
