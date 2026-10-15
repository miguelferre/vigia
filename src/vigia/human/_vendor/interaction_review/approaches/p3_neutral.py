"""p3-neutral (test A2) - Deterministic pipeline with a NEUTRAL partition of guidelines.

Overfitting control (R-A of the TESTPLAN): 'normal' p3 groups the guidelines into 5
SEMANTIC blocks made by hand knowing the case (p3_pipeline.BUCKETS). If that
fine-tuned grouping were the source of the advantage (and not the decomposition itself), p3
would not generalize: it would be overfitting to the case.

p3-neutral uses the partition from the AUTHORS THEMSELVES, already present in the data: the
`group` field of each guideline (the 4 phases of HAX-18: Initially / During /
When wrong / Over time; and the 6 PAIR chapters). There is no hand
design: the blocks are DERIVED from the data. If p3-neutral ~= p3 in recall, the advantage
is DECOMPOSING, not my blocks -> the improvement generalizes.

Same FIXED flow as p3 (one focused pass per block -> merge); the only thing that
changes is how the guidelines are grouped. It is still a pipeline, NOT an agent.
"""

from __future__ import annotations

from ._generator import generate
from ..schemas import Dossier, Finding, Guideline


def buckets_by_group(guidelines: list[Guideline]) -> dict[str, list[Guideline]]:
    """Groups by (corpus, group) preserving the order of appearance.

    Neutral by construction: the key is the corpus's official taxonomy, not a
    grouping of ours. With the hax+pair corpus this yields 4 (HAX phases) + 6 (PAIR chapters).
    """
    buckets: dict[str, list[Guideline]] = {}
    for g in guidelines:
        key = f"{g.corpus.value}:{g.group}"
        buckets.setdefault(key, []).append(g)
    return buckets


def _slug(key: str) -> str:
    out = key.lower()
    for ch in (" ", ":", "+", "/"):
        out = out.replace(ch, "-")
    return "-".join(p for p in out.split("-") if p)


def run(dossier: Dossier, guidelines: list[Guideline]) -> list[Finding]:
    collected: list[Finding] = []
    for key, gl in buckets_by_group(guidelines).items():
        if not gl:
            continue
        collected.extend(generate(dossier, gl, few_shot=False, label=f"p3n-{_slug(key)}"))
    # Unique and stable re-id (the per-block labels would collide in the index).
    return [f.model_copy(update={"id": f"p3n-{n:03d}"}) for n, f in enumerate(collected, start=1)]
