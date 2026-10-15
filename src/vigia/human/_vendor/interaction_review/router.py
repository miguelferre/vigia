"""Routing by difficulty: the results map, automated.

Conclusion of the experiment (RESULTS.md): with a strong model, in EASY cases the
single prompt (b1) is enough and is the most concise; in HARD cases STRUCTURE is needed
(b1 is unstable, one run went to 0) and the pipeline (p3) is the robust option. The difficulty
is NOT known a priori, so the router INFERS it:

1. Runs b1 (cheap, concise).
2. Asks the model whether there are AREAS left uncovered (reuses the gap-check from A4).
3. If there are gaps (or b1 came out thin, its failure mode: instability) -> ESCALATES to p3 + dedup.
   Otherwise, it stays with b1.

This way the best of each cell of the map is obtained: concise when possible, exhaustive when
needed; and the escalation due to "thin b1" covers exactly b1's instability (the run to 0).
It is NOT a rung of the ladder (it is not compared in `compare`): it is the PRODUCT layer.
"""

from __future__ import annotations

from .approaches._generator import generate  # noqa: F401  (ensures backend loaded)
from .approaches.a4_agent import _assess_gaps
from .approaches.b1_single_prompt import run as run_b1
from .approaches.p3_pipeline import run as run_p3
from .dedup import deduplicate
from .schemas import Dossier, Finding, Guideline

# If b1 brings fewer grounded findings than this, we treat it as "thin" and escalate
# even if the gap-check does not ask for it: it shields against b1's instability (run to 0).
MIN_B1_GROUNDED: int = 3


def route(dossier: Dossier, guidelines: list[Guideline]) -> tuple[list[Finding], str]:
    """Chooses b1 (easy) or p3+dedup (hard) based on the coverage. Returns (findings, choice)."""
    by_id = {g.id: g for g in guidelines}
    b1 = run_b1(dossier, guidelines)
    grounded = [f for f in b1 if f.is_grounded()]

    decision = _assess_gaps(guidelines, b1)
    real_gaps = bool(decision.get("seguir")) and any(
        i in by_id for i in decision.get("guideline_ids", [])
    )
    thin = len(grounded) < MIN_B1_GROUNDED

    if real_gaps or thin:
        motivo = "sparse b1" if thin and not real_gaps else "coverage gaps"
        # Keep b1's findings (already generated, and it sometimes catches what p3 misses) and
        # merge with p3; dedup collapses the overlap. Recall-first (beta>1), so we do not
        # throw paid-for signal away.
        merged = deduplicate(b1 + run_p3(dossier, guidelines))
        return merged, f"p3+dedup (escalated: {motivo}, b1∪p3)"
    return b1, "b1 (easy case: sufficient coverage)"
