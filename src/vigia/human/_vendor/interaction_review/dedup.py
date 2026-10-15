"""Finding deduplication: the missing PRODUCT step.

The persistent anti-pattern of p3 (and worse in p3n): the block-by-block sweep emits the
SAME problem several times, usually citing a different guideline each time
(e.g. "onboarding sin reciclaje" appeared 7 times via HAX-G1, HAX-G12, PAIR-UN-2,
PAIR-MM-1, PAIR-EF-2, PAIR-DE-1...). ~60-100 findings for ~15 real problems.
A human auditor does not want to read the same problem five times.

This step COLLAPSES near-duplicate findings into one representative that MERGES the
guidelines of all its members. The output is "one finding per problem, annotated
with all the guidelines it violates" -> more actionable, not less.

Principles (consistent with the project): it is DETERMINISTIC and lives in the
CODE, without an LLM. It does not look at the golden or the adjudications (in production they do not exist):
it groups only by the CONTENT of the finding. The similarity is lexical (not deep
semantic) on purpose: reproducible, auditable and free. The validity of the threshold is
measured separately (scripts/dedup_report.py) against adjudications that this step never sees:
it must not merge distinct real problems (purity) nor lower the coverage (recall).

The grouping is by REPRESENTATIVE (not single-linkage): each finding is compared with
the representatives of the already-open clusters and joins the most similar one above the
threshold, or opens a new cluster. It avoids the transitive chaining (A~B, B~C => A~C) that
would over-merge. The result is stable with respect to the input order (that of the sweep).
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from .schemas import Finding, Severity

# Similarity threshold to consider two findings the SAME problem. Calibrated
# offline (scripts/dedup_report.py) over the p3/p3n runs of EII: the most
# aggressive value that keeps PURITY at 0 in p3 (does not merge distinct golden) and preserves
# the coverage. Below 0.60 the conflations begin; see docs/RESULTADOS.md.
DEFAULT_THRESHOLD: float = 0.60

# For the title ratio (which captures the same title rewritten) to HELP, we also require
# a minimum of real vocabulary overlap. Without this guard, titles with the
# same TEMPLATE but a different problem ("Falta de comunicacion de X al clinico")
# would merge: the calibration confirmed it (variant 'max' -> impurity spiked).
_SEQ_REQUIRES_JACCARD: float = 0.25

# Stopwords (es) that survive the length filter and only add noise to the
# lexical similarity. Short and conservative list: only functional words, no domain
# term (modelo/sistema/medico... DO discriminate and are kept).
_STOPWORDS: frozenset[str] = frozenset(
    """del las los con por para una uno que sin mas muy pero como sus este esta esto
    ese esa eso entre sobre cuando donde ante tras desde hacia hasta son han hay ser
    sea fue era cada the and for""".split()
)

_SEVERITY_RANK = {Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _norm(s: str) -> str:
    """Normalizes text for comparison: without accents, lowercase, collapsed spaces."""
    return re.sub(r"\s+", " ", _strip_accents(s).lower()).strip()


def _tokens(s: str) -> set[str]:
    """Bag of content tokens: without accents, >=3 chars, no stopwords."""
    words = re.findall(r"[a-z0-9]+", _strip_accents(s).lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b)


def text_similarity(a: str, b: str) -> float:
    """Jaccard of content tokens between two free texts (0..1).

    Reusable outside the dedup: the judge uses it to WIDEN the golden candidates
    by text similarity (not only by shared guideline id), which is
    the measurement debt documented in TESTPLAN (a finding that cites the
    'wrong' guideline was left without a candidate and produced a false failure).
    """
    return _jaccard(_tokens(a), _tokens(b))


def _signature_tokens(f: Finding) -> set[str]:
    # Title + locus: what identifies the PROBLEM. The evidence and the rationale are
    # long and noisy (they would inflate false similarities); the title carries the topic.
    return _tokens(f"{f.title} {f.locus}")


def similarity(a: Finding, b: Finding) -> float:
    """How similar two findings are as the 'same problem' (0..1).

    Combines two signals:
    - Jaccard of (title+locus) tokens: overlap of the problem's vocabulary.
    - Sequence ratio of the normalized title: captures the same title rewritten, but
      ONLY if there is already a minimum of vocabulary overlap (_SEQ_REQUIRES_JACCARD); if not,
      titles with the same template and a different problem would merge (see calibration).
    It does NOT require sharing a guideline: the typical duplicate cites a DIFFERENT guideline.
    """
    jac = _jaccard(_signature_tokens(a), _signature_tokens(b))
    if jac < _SEQ_REQUIRES_JACCARD:
        return jac
    seq = SequenceMatcher(None, _norm(a.title), _norm(b.title)).ratio()
    return max(jac, seq)


def _union_guidelines(members: list[Finding]) -> list[str]:
    """Union of guideline_ids preserving the order of first appearance."""
    seen: dict[str, None] = {}
    for f in members:
        for gid in f.guideline_ids:
            seen.setdefault(gid, None)
    return list(seen)


def _representative(members: list[Finding]) -> Finding:
    """The most complete member of the cluster: grounded > severe > rich in text > first."""

    def richness(f: Finding) -> int:
        return len(f.evidence) + len(f.rationale) + len(f.recommendation)

    return max(
        members,
        key=lambda f: (
            f.is_grounded(),
            _SEVERITY_RANK.get(f.severity, 0),
            richness(f),
        ),
    )


def _merge(members: list[Finding]) -> Finding:
    """Merges a cluster into one finding: the representative + merged guidelines.

    `merged_count` is CUMULATIVE (how many raw findings it represents in total), not
    "how many were merged in this pass": re-deduplicating an already-deduplicated list
    preserves the counter, and merging already-merged findings adds up correctly.
    """
    if len(members) == 1:
        return members[0]  # single: kept as is (including its merged_count).
    rep = _representative(members)
    severity = max(members, key=lambda f: _SEVERITY_RANK.get(f.severity, 0)).severity
    anti = rep.anti_pattern or next((f.anti_pattern for f in members if f.anti_pattern), None)
    return rep.model_copy(
        update={
            "guideline_ids": _union_guidelines(members),
            "severity": severity,
            "anti_pattern": anti,
            "merged_count": sum(f.merged_count for f in members),
        }
    )


def cluster(
    findings: list[Finding], threshold: float = DEFAULT_THRESHOLD
) -> list[list[Finding]]:
    """Groups near-duplicate findings into clusters of members, stable by input order.

    Grouping by REPRESENTATIVE (the first member of each open cluster), not single-linkage,
    to avoid transitive over-merging. Shared with the offline validation scripts
    (scripts/dedup_report.py) so they audit the SAME grouping the product uses.
    """
    clusters: list[list[Finding]] = []
    reps: list[Finding] = []  # provisional representative (the first of each cluster)
    for f in findings:
        best_i, best_sim = -1, threshold
        for i, rep in enumerate(reps):
            s = similarity(f, rep)
            if s >= best_sim:
                best_i, best_sim = i, s
        if best_i >= 0:
            clusters[best_i].append(f)
        else:
            clusters.append([f])
            reps.append(f)
    return clusters


def deduplicate(
    findings: list[Finding], threshold: float = DEFAULT_THRESHOLD
) -> list[Finding]:
    """Collapses near-duplicate findings. Stable with respect to the input order.

    Returns one finding per cluster (representative with merged guidelines and
    `merged_count`), in the order in which each cluster was opened. Idempotent for
    well-separated clusters (the common case), but NOT guaranteed in general: the merged
    representative can end up more similar to a neighboring cluster than the original
    first member was, so a second pass may merge clusters the first left apart.
    """
    return [_merge(c) for c in cluster(findings, threshold)]
