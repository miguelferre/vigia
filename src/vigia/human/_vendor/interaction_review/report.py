"""Rendering of reports in text/markdown (the v1 output is CLI, never a UI)."""

from __future__ import annotations

from .metrics import AggregateMetrics
from .schemas import Dossier, Finding, Guideline, Severity

_SEV_RANK = {Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}


def remediations_for(findings: list[Finding]) -> list[tuple[Guideline, Severity]]:
    """Guidelines with curated remediations cited by at least one medium/high finding, each paired
    with the max severity among the findings citing it. Ordered by that severity (high first) then
    id, deduplicated to one entry per guideline (p3 routinely has several findings cite the same
    guideline). Low-only findings pull in no remediation guidance; the render layer consumes this.
    """
    from .guidelines import guidelines_by_id

    by_id = guidelines_by_id()
    max_sev: dict[str, Severity] = {}
    for f in findings:
        if f.severity is Severity.LOW:
            continue
        for gid in f.guideline_ids:
            g = by_id.get(gid)
            if g is None or not g.remediations:
                continue
            cur = max_sev.get(gid)
            if cur is None or _SEV_RANK[f.severity] > _SEV_RANK[cur]:
                max_sev[gid] = f.severity
    rows = [(by_id[gid], sev) for gid, sev in max_sev.items()]
    rows.sort(key=lambda r: (-_SEV_RANK[r[1]], r[0].id))
    return rows


def render_regulatory_crosswalk(findings: list[Finding]) -> str:
    """'Evidence of conformity' section: which AI Act / NIST AI RMF requirements
    the findings touch, and through which guideline. Indicative, not a legal opinion.
    """
    from .regulatory import crosswalk, framework_names, guideline_notes

    cw = crosswalk(findings)
    lines: list[str] = ["## Regulatory crosswalk (indicative)", ""]
    if not cw:
        lines.append("_(The findings do not cite guidelines mapped to a regulatory framework.)_")
        return "\n".join(lines)
    lines.append(
        "Requirements touched by the findings above, with the guideline that anchors them. "
        "**Not a legal opinion**: applicability depends on the role and whether the "
        "system is high-risk."
    )
    lines.append("")
    names = framework_names()
    for fw, items in cw.items():
        lines.append(f"### {names.get(fw, fw)}")
        for ref, gids in items:
            lines.append(f"- **{ref}**: {', '.join(gids)}")
        lines.append("")
    # Level 2: transitive inheritance from the Eticas AI Risk Taxonomy (guidelines/eticas/).
    from . import eticas as _eticas
    from .regulatory import eticas_concepts

    concept_ids = eticas_concepts({gid for f in findings for gid in f.guideline_ids})
    inherited = _eticas.inherited(concept_ids) if concept_ids else {}
    if inherited:
        touched = ", ".join(_eticas.concept_label(c) for c in concept_ids)
        lines.append("### Inherited via Eticas AI Risk Taxonomy (transitive, indicative)")
        lines.append(
            f"_Eticas concepts touched: {touched}. Each already maps to these external frameworks "
            "(inherited, not maintained here):_"
        )
        for fw in sorted(inherited, key=_eticas.framework_name):
            lines.append(f"- **{_eticas.framework_name(fw)}**: {'; '.join(inherited[fw])}")
        lines.append("")

    notes = guideline_notes({gid for f in findings for gid in f.guideline_ids})
    if notes:
        lines.append("### Why these map")
        for gid, nota in notes:
            lines.append(f"- **{gid}**: {nota}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_META_FIELDS = (("date", "Generated"), ("tool_version", "Tool version"), ("model", "Generator model"))


def render_findings_md(
    dossier: Dossier, findings: list[Finding], approach: str, *, meta: dict | None = None
) -> str:
    """Findings report in markdown. `meta` (optional) adds provenance lines (date/model/version)."""
    lines: list[str] = []
    lines.append(f"# Interaction layer review - {dossier.system_name}")
    lines.append("")
    lines.append(f"- **Domain:** {dossier.domain}")
    lines.append(f"- **Approach:** {approach}")
    lines.append(f"- **Sources:** {len(dossier.sources)}")
    lines.append(f"- **Findings:** {len(findings)}")
    grounded = sum(1 for f in findings if f.is_grounded())
    pct = (grounded / len(findings) * 100) if findings else 0.0
    lines.append(f"- **Anchored (guideline+locus+evidence):** {grounded}/{len(findings)} ({pct:.0f}%)")
    # If deduplicated, the report consolidates several raw findings into each one.
    raw = sum(f.merged_count for f in findings)
    if raw > len(findings):
        lines.append(f"- **Deduplicated:** {raw} raw findings consolidated into {len(findings)}.")
    if meta:
        for key, label in _META_FIELDS:
            if meta.get(key):
                lines.append(f"- **{label}:** {meta[key]}")
    lines.append("")

    rem_rows = remediations_for(findings)
    rem_ids = {g.id for g, _ in rem_rows}

    for f in findings:
        flag = "OK" if f.is_grounded() else "GENERIC?"
        merged = f" _(consolidates {f.merged_count})_" if f.merged_count > 1 else ""
        lines.append(f"## [{flag}] {f.title}{merged}")
        lines.append("")
        lines.append(f"- **Guidelines:** {', '.join(f.guideline_ids) or '(none)'}")
        lines.append(f"- **Severity:** {f.severity.value}")
        lines.append(f"- **Locus:** {f.locus or '(no concrete locus)'}")
        lines.append(f"- **Evidence:** {f.evidence or '(no evidence)'}")
        if f.anti_pattern:
            lines.append(f"- **Anti-pattern:** {f.anti_pattern}")
        if f.rationale:
            lines.append(f"- **Why it matters here:** {f.rationale}")
        if f.recommendation:
            lines.append(f"- **Recommendation:** {f.recommendation}")
        # High-severity findings get a pointer to the curated remediation section below.
        if f.severity is Severity.HIGH:
            pts = [gid for gid in f.guideline_ids if gid in rem_ids]
            if pts:
                lines.append(f"- **Remediation guidance:** see {', '.join(pts)} below")
        lines.append("")

    if rem_rows:
        lines.append("## Remediation guidance (per cited guideline)")
        lines.append("")
        lines.append(
            "Curated actions for the guidelines cited by the medium/high findings above. These are "
            "generic by guideline (not system-specific); use them to complement each finding's own "
            "recommendation, which is anchored to this system."
        )
        lines.append("")
        for g, sev in rem_rows:
            lines.append(f"### {g.id} - {g.title} _(max severity: {sev.value})_")
            for r in g.remediations:
                lines.append(f"- {r}")
            lines.append("")
    return "\n".join(lines)


def render_metrics_md(aggregates: list[AggregateMetrics]) -> str:
    """Comparative table of approaches (mean +/- std over k runs)."""
    lines: list[str] = []
    lines.append("# Approach comparison")
    lines.append("")
    lines.append("| Approach | k | Recall | Precision | Genericity | Grounding | Primary (F-beta*) |")
    lines.append("|---|---|---|---|---|---|---|")

    def cell(s) -> str:  # noqa: ANN001 - Stat
        return f"{s.mean:.2f} +/- {s.std:.2f}"

    for a in aggregates:
        lines.append(
            f"| {a.approach} | {a.k} | {cell(a.recall)} | {cell(a.precision)} | "
            f"{cell(a.genericity_rate)} | {cell(a.grounding_rate)} | {cell(a.primary_score)} |"
        )
    lines.append("")
    lines.append("> Primary = F-beta (beta>1, prioritizes recall) subject to a genericity ceiling.")
    lines.append("> Genericity: lower is better. Grounding: higher is better.")
    return "\n".join(lines)
