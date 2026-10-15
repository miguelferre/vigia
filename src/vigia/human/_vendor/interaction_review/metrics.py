"""Evaluation metrics against the golden set.

Implements the plan's definition of success (section 1):
recall, precision, genericity_rate, grounding_rate, tp_new, and the primary
F-beta metric subject to a genericity ceiling.

PRE-REGISTERED constants: they are fixed here, in code,
BEFORE seeing results, so as not to rationalize them after the fact.
"""

from __future__ import annotations

import statistics

from pydantic import BaseModel

from .schemas import (
    Adjudication,
    AdjudicationLabel,
    Finding,
    GoldenIssue,
    RevealedBy,
)

# --- Pre-registered parameters ---
# beta > 1 prioritizes recall: in auditing, failing to detect a real problem is worse
# than a false positive that is cheap to discard.
BETA: float = 2.0
# An approach with genericity_rate above this ceiling is NOT considered valid
# even if it has a good F-beta: spitting out generic findings is, by definition, a failure.
GENERICITY_THRESHOLD: float = 0.25


def f_beta(precision: float, recall: float, beta: float = BETA) -> float:
    """F-beta. Returns 0.0 if the denominator is 0."""
    b2 = beta * beta
    denom = b2 * precision + recall
    if denom == 0:
        return 0.0
    return (1 + b2) * (precision * recall) / denom


class RunMetrics(BaseModel):
    """Metrics of ONE run of an approach on the golden case."""

    approach: str
    n_findings: int
    n_golden: int
    recall: float
    precision: float
    genericity_rate: float
    grounding_rate: float
    tp_new: int
    fbeta: float
    meets_genericity_gate: bool
    primary_score: float  # F-beta if it passes the genericity gate, otherwise 0.0


def compute_run_metrics(
    approach: str,
    findings: list[Finding],
    adjudications: list[Adjudication],
    golden: list[GoldenIssue],
) -> RunMetrics:
    """Computes the metrics of a run.

    - recall: matched GoldenIssues (via TP_MATCH) / total golden.
    - precision: real findings (TP_MATCH + TP_NEW) / total findings.
    - genericity_rate: FP_GENERIC / total findings.
    - grounding_rate: findings with the 3 anchors / total findings
      (measured over the Finding objects, independent of the judge).

    Raises ValueError if the adjudications do not correspond to these findings
    (an id that is not among them, or the same finding adjudicated twice). Without
    this, mismatched --findings/--adjudications files silently produce nonsense
    (e.g. precision > 1 when there are more adjudications than findings).
    """
    finding_ids = {f.id for f in findings}
    seen: set[str] = set()
    for a in adjudications:
        if a.finding_id not in finding_ids:
            raise ValueError(
                f"Adjudication references unknown finding id {a.finding_id!r}. "
                "The adjudications do not match these findings (mismatched files?)."
            )
        if a.finding_id in seen:
            raise ValueError(f"Duplicate adjudication for finding id {a.finding_id!r}.")
        seen.add(a.finding_id)

    n = len(findings)
    by_label: dict[AdjudicationLabel, int] = {lbl: 0 for lbl in AdjudicationLabel}
    matched_golden: set[str] = set()
    for a in adjudications:
        by_label[a.label] += 1
        if a.label == AdjudicationLabel.TP_MATCH and a.matched_golden_id:
            matched_golden.add(a.matched_golden_id)

    tp = by_label[AdjudicationLabel.TP_MATCH] + by_label[AdjudicationLabel.TP_NEW]

    recall = len(matched_golden) / len(golden) if golden else 0.0
    precision = tp / n if n else 0.0
    genericity_rate = by_label[AdjudicationLabel.FP_GENERIC] / n if n else 0.0
    grounding_rate = sum(1 for f in findings if f.is_grounded()) / n if n else 0.0

    fb = f_beta(precision, recall)
    gate = genericity_rate <= GENERICITY_THRESHOLD

    return RunMetrics(
        approach=approach,
        n_findings=n,
        n_golden=len(golden),
        recall=recall,
        precision=precision,
        genericity_rate=genericity_rate,
        grounding_rate=grounding_rate,
        tp_new=by_label[AdjudicationLabel.TP_NEW],
        fbeta=fb,
        meets_genericity_gate=gate,
        primary_score=fb if gate else 0.0,
    )


class SubsetRecall(BaseModel):
    """Recall over the golden subset with a given `revealed_by`.

    It is the unit of the testimony ablation. Comparing the same
    subset (e.g. USER_ONLY) between the WITH-voice and WITHOUT-voice conditions measures whether the
    user's testimony contributes to recall or only to grounding.
    """

    revealed_by: RevealedBy
    n_golden: int
    n_matched: int
    recall: float


def recall_by_revealed_by(
    adjudications: list[Adjudication],
    golden: list[GoldenIssue],
) -> list[SubsetRecall]:
    """Breaks down recall by the source that reveals each GoldenIssue.

    Returns one entry per `revealed_by` value PRESENT in the golden
    (absent ones are omitted). The matching is the same as in `compute_run_metrics`:
    a golden is matched if some finding references it via TP_MATCH.
    """
    matched: set[str] = {
        a.matched_golden_id
        for a in adjudications
        if a.label == AdjudicationLabel.TP_MATCH and a.matched_golden_id
    }
    out: list[SubsetRecall] = []
    for rb in RevealedBy:
        subset = [g for g in golden if g.revealed_by == rb]
        if not subset:
            continue
        n_matched = sum(1 for g in subset if g.id in matched)
        out.append(
            SubsetRecall(
                revealed_by=rb,
                n_golden=len(subset),
                n_matched=n_matched,
                recall=n_matched / len(subset),
            )
        )
    return out


class Stat(BaseModel):
    """Mean and standard deviation of a metric over k runs."""

    mean: float
    std: float


class AggregateMetrics(BaseModel):
    """Aggregate of k runs of the same approach (mean +/- std)."""

    approach: str
    k: int
    recall: Stat
    precision: Stat
    genericity_rate: Stat
    grounding_rate: Stat
    primary_score: Stat


def _stat(values: list[float]) -> Stat:
    if not values:
        return Stat(mean=0.0, std=0.0)
    mean = statistics.mean(values)
    # pstdev (population): k is small and we describe exactly these k runs.
    std = statistics.pstdev(values) if len(values) > 1 else 0.0
    return Stat(mean=mean, std=std)


def aggregate(runs: list[RunMetrics]) -> AggregateMetrics:
    """Aggregates k RunMetrics of the same approach. Raises if the list is empty or mixes approaches."""
    if not runs:
        raise ValueError("aggregate() needs at least one run.")
    approaches = {r.approach for r in runs}
    if len(approaches) > 1:
        raise ValueError(f"aggregate() mixes different approaches: {approaches}")
    return AggregateMetrics(
        approach=runs[0].approach,
        k=len(runs),
        recall=_stat([r.recall for r in runs]),
        precision=_stat([r.precision for r in runs]),
        genericity_rate=_stat([r.genericity_rate for r in runs]),
        grounding_rate=_stat([r.grounding_rate for r in runs]),
        primary_score=_stat([r.primary_score for r in runs]),
    )


def beats(candidate: AggregateMetrics, baseline: AggregateMetrics) -> bool:
    """Decision rule of the plan: an approach 'beats' another if it improves the primary
    metric by a margin GREATER than the observed variance.

    Operationalization: the candidate's mean exceeds the baseline's by more than
    the sum of their standard deviations (margin > combined noise).
    """
    margin = candidate.primary_score.mean - baseline.primary_score.mean
    noise = candidate.primary_score.std + baseline.primary_score.std
    return margin > noise
