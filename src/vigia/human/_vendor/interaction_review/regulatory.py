"""Mapping of the HAX/PAIR guidelines to a regulatory framework (EU AI Act / NIST AI RMF).

Converts a finding tied to guidelines into its regulatory situation: which
articles of the AI Act and which subcategories of the NIST AI RMF it touches. The goal is for
the report to serve as *evidence of conformity* for the governance buyer,
not just as an academic design critique.

The data lives in guidelines/regulatory_map.yaml. It is an INDICATIVE mapping, not a
legal opinion (see the notice in the YAML itself).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

import yaml

from .guidelines import guidelines_by_id
from .schemas import Finding

_MAP_FILE = Path(__file__).parent / "guidelines" / "regulatory_map.yaml"

# Presentation order of the frameworks.
FRAMEWORKS: tuple[str, ...] = ("eu_ai_act", "nist_ai_rmf", "interaction_risk")


@lru_cache(maxsize=1)
def _raw() -> dict:
    return yaml.safe_load(_MAP_FILE.read_text(encoding="utf-8"))


def framework_names() -> dict[str, str]:
    """framework id -> readable name."""
    fw = _raw()["frameworks"]
    return {k: fw[k]["name"] for k in FRAMEWORKS}


def _ref_sort_key(ref: str) -> tuple[str, int, str]:
    """Sorts refs: by textual prefix and first number (Art. 9 before Art. 13)."""
    m = re.search(r"\d+", ref)
    if m:
        return (ref[: m.start()].strip(), int(m.group()), ref)
    return (ref, 9999, ref)  # features without a number: at the end of their prefix


def refs_for(guideline_ids: Iterable[str]) -> dict[str, list[str]]:
    """Union of regulatory refs by framework for a set of guidelines.

    Returns only the frameworks with at least one ref. Ignores unknown ids.
    """
    m = _raw()["map"]
    acc: dict[str, set[str]] = {fw: set() for fw in FRAMEWORKS}
    for gid in guideline_ids:
        entry = m.get(gid)
        if not entry:
            continue
        for fw in FRAMEWORKS:
            acc[fw].update(entry.get(fw, []))
    return {fw: sorted(acc[fw], key=_ref_sort_key) for fw in FRAMEWORKS if acc[fw]}


def crosswalk(findings: list[Finding]) -> dict[str, list[tuple[str, list[str]]]]:
    """By framework: each ref -> the guidelines (cited by the findings) that imply it.

    It is the 'evidence of conformity' view: which regulatory requirements the
    report's findings touch and through which guideline.
    """
    m = _raw()["map"]
    per_fw: dict[str, dict[str, set[str]]] = {fw: {} for fw in FRAMEWORKS}
    for f in findings:
        for gid in f.guideline_ids:
            entry = m.get(gid)
            if not entry:
                continue
            for fw in FRAMEWORKS:
                for ref in entry.get(fw, []):
                    per_fw[fw].setdefault(ref, set()).add(gid)
    out: dict[str, list[tuple[str, list[str]]]] = {}
    for fw in FRAMEWORKS:
        if not per_fw[fw]:
            continue
        items = [(ref, sorted(gids)) for ref, gids in per_fw[fw].items()]
        items.sort(key=lambda t: _ref_sort_key(t[0]))
        out[fw] = items
    return out


def guideline_notes(guideline_ids: Iterable[str]) -> list[tuple[str, str]]:
    """(guideline_id, rationale note) for the given guidelines that carry a `nota`.

    Surfaces the curated per-guideline map notes (guideline -> why it touches the framework)
    so they reach the report instead of sitting unused in the YAML. Deduped, sorted by id.
    """
    m = _raw()["map"]
    seen: dict[str, str] = {}
    for gid in guideline_ids:
        entry = m.get(gid)
        if entry and entry.get("nota") and gid not in seen:
            seen[gid] = entry["nota"]
    return sorted(seen.items())


def unmapped_guidelines() -> list[str]:
    """Real guidelines that have NO entry in the map (should be empty: all mapped)."""
    mapped = set(_raw()["map"])
    real = set(guidelines_by_id())
    return sorted(real - mapped)


def unknown_map_ids() -> list[str]:
    """Map ids that do not correspond to any real guideline (typos)."""
    mapped = set(_raw()["map"])
    real = set(guidelines_by_id())
    return sorted(mapped - real)


# --------------------------------------------------------------------------- #
# Level 2: transitive inheritance from the Eticas AI Risk Taxonomy.
# A guideline can anchor to Eticas concept ids (map key `eticas`); each concept already carries
# ~18 external framework mappings that a finding then inherits. See interaction_review/eticas.py.
# --------------------------------------------------------------------------- #
def eticas_concepts(guideline_ids: Iterable[str]) -> list[str]:
    """Eticas taxonomy concept ids anchored by the given guidelines (order-preserving, deduped)."""
    m = _raw()["map"]
    out: list[str] = []
    for gid in guideline_ids:
        entry = m.get(gid)
        if not entry:
            continue
        for cid in entry.get("eticas", []) or []:
            if cid not in out:
                out.append(cid)
    return out


def unknown_eticas_ids() -> list[str]:
    """Eticas concept ids cited in the map that do not exist in the taxonomy (typos/drift)."""
    from . import eticas

    cited = {cid for entry in _raw()["map"].values() for cid in (entry.get("eticas") or [])}
    return eticas.unknown_concepts(cited)
