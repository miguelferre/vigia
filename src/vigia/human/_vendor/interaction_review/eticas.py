"""Level 2: inherit ~18 framework mappings transitively from the Eticas AI Risk Taxonomy.

Each guideline can anchor to Eticas taxonomy concept ids (in `guidelines/regulatory_map.yaml`,
under the key `eticas`). Each Eticas concept already carries mappings to ~18 frameworks
(ISO/IEC 42001, MIT AI Risk Repository, OWASP Agentic, DPV, IBM Atlas, ...). This module resolves
guideline -> concept -> those frameworks, so a finding "speaks" them without us maintaining the
mappings by hand.

Data: `guidelines/eticas/{taxonomy,mappings}.yaml` (Eticas AI Risk Taxonomy v3.0.0, CC BY 4.0;
see the ATTRIBUTION and LICENSE in that folder). The inheritance is INDICATIVE, not a legal opinion;
it is only as strong as the guideline->concept anchor and Eticas' own mappings, many
of which are broad/related matches.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

import yaml

_DIR = Path(__file__).parent / "guidelines" / "eticas"
_TAXONOMY = _DIR / "taxonomy.yaml"
_FRAMEWORKS = _DIR / "mappings.yaml"

# Frameworks already surfaced at level 1 by our own regulatory_map: do not repeat them in the
# inherited view (would duplicate the AI Act / NIST RMF sections). nist_600 (GenAI profile) is a
# DIFFERENT framework and is kept.
_ALREADY_SHOWN = frozenset({"eu_ai_act", "nist_rmf"})


@lru_cache(maxsize=1)
def _concepts() -> dict[str, dict]:
    raw = yaml.safe_load(_TAXONOMY.read_text(encoding="utf-8"))
    return {c["id"]: c for c in raw["concepts"]}


@lru_cache(maxsize=1)
def _framework_meta() -> dict[str, dict]:
    raw = yaml.safe_load(_FRAMEWORKS.read_text(encoding="utf-8"))
    return raw["frameworks"]


def concept_label(concept_id: str) -> str:
    """Readable label of an Eticas concept id (falls back to the id)."""
    c = _concepts().get(concept_id)
    return c.get("label", concept_id) if c else concept_id


def framework_name(framework_id: str) -> str:
    """Readable name of an Eticas external framework id (falls back to the id)."""
    m = _framework_meta().get(framework_id)
    return m.get("name", framework_id) if m else framework_id


def unknown_concepts(concept_ids: Iterable[str]) -> list[str]:
    """Concept ids that do NOT exist in the taxonomy (integrity check, mirrors unknown_map_ids)."""
    return sorted(set(concept_ids) - set(_concepts()))


def inherited(concept_ids: Iterable[str]) -> dict[str, list[str]]:
    """framework_id -> sorted unique target labels, for the given Eticas concepts.

    The transitive inheritance: each concept's own mappings become the finding's inherited
    coverage. Excludes the frameworks already shown at level 1 (EU AI Act, NIST RMF).
    """
    acc: dict[str, set[str]] = {}
    concepts = _concepts()
    for cid in concept_ids:
        c = concepts.get(cid)
        if not c:
            continue
        for m in c.get("mappings", []) or []:
            fw = m.get("framework")
            if not fw or fw in _ALREADY_SHOWN:
                continue
            label = m.get("target_label") or m.get("target_id")
            if label:
                acc.setdefault(fw, set()).add(str(label))
    return {fw: sorted(labels) for fw, labels in acc.items()}
