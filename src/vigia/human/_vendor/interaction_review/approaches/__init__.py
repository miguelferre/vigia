"""Review approaches (the plan's 'complexity ladder').

They all share the same signature so the comparison is fair:

    run(dossier: Dossier, guidelines: list[Guideline]) -> list[Finding]

Ladder:
  - b0: deterministic checklist (no LLM). The floor.
  - b1: single zero-shot prompt.           (F2)
  - b2: single few-shot prompt.            (F2)
  - p3: deterministic pipeline (NOT an agent). (only if the data calls for it)
  - a4: agent.                             (only if the data calls for it)
"""

from __future__ import annotations

from typing import Callable

from .a4_agent import run as run_a4
from .b0_checklist import run as run_b0
from .b1_single_prompt import run as run_b1
from .b1x_exhaustivo import run as run_b1x
from .b2_few_shot import run as run_b2
from .p3_neutral import run as run_p3n
from .p3_pipeline import run as run_p3
from ..schemas import Dossier, Finding, Guideline

Approach = Callable[[Dossier, list[Guideline]], list[Finding]]

REGISTRY: dict[str, Approach] = {
    "b0": run_b0,    # deterministic checklist (no LLM)
    "b1": run_b1,    # single zero-shot prompt
    "b1x": run_b1x,  # single EXHAUSTIVE prompt (structure vs quantity ablation)
    "b2": run_b2,    # single few-shot prompt
    "p3": run_p3,    # deterministic pipeline: sweep by SEMANTIC blocks (NOT an agent)
    "p3n": run_p3n,  # p3 with a NEUTRAL partition by `group` (test A2: block overfitting)
    "a4": run_a4,    # agent: loop with control flow decided by the model
}

__all__ = [
    "REGISTRY", "Approach",
    "run_b0", "run_b1", "run_b1x", "run_b2", "run_p3", "run_p3n", "run_a4",
]
