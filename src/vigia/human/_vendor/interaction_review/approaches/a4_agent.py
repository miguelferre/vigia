"""A4 - Agent: loop with control flow decided by the MODEL (not by code).

Key difference from p3 (fixed pipeline): p3 ALWAYS sweeps the same blocks. A4 makes
an initial broad pass and then, on each iteration, the MODEL decides (looking at what
it has so far) which areas are missing and whether another pass is worth it or it should stop.
That autonomy (what to investigate and when to finish, based on the state) is what makes it an agent.

Anti-loop guardrail: MAX_ITERS bounds the number of iterations (there is no open loop).
"""

from __future__ import annotations

from .. import llm, prompts
from ._generator import gen_temperature, generate
from ..schemas import Dossier, Finding, Guideline

MAX_ITERS = 4  # hard cap on iterations (1 broad + up to 3 targeted)


def _assess_gaps(guidelines: list[Guideline], findings: list[Finding]) -> dict:
    """AUTONOMOUS model decision: keep going? which guidelines to investigate now?"""
    payload = [{"title": f.title, "guideline_ids": f.guideline_ids} for f in findings]
    out = llm.call_structured(
        model=llm.gen_model(),
        system=prompts.AGENT_GAPS_SYSTEM,
        user=prompts.agent_gaps_user(guidelines, payload),
        tool=prompts.AGENT_GAPS_TOOL,
        temperature=gen_temperature(),
    )
    return out if isinstance(out, dict) else {"seguir": False, "guideline_ids": []}


def run(dossier: Dossier, guidelines: list[Guideline]) -> list[Finding]:
    by_id = {g.id: g for g in guidelines}
    findings: list[Finding] = generate(dossier, guidelines, few_shot=False, label="a4-it0")

    for it in range(1, MAX_ITERS):
        decision = _assess_gaps(guidelines, findings)
        if not decision.get("seguir"):
            break
        ids = [i for i in (decision.get("guideline_ids") or []) if i in by_id]
        if not ids:
            break
        target = [by_id[i] for i in ids]
        findings.extend(generate(dossier, target, few_shot=False, label=f"a4-it{it}"))

    return [f.model_copy(update={"id": f"a4-{n:03d}"}) for n, f in enumerate(findings, start=1)]
