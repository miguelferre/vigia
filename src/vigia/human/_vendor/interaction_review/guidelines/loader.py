"""Loads and validates the guideline corpora (HAX-18 and PAIR) from YAML."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ..schemas import Guideline, GuidelineCorpus

_HERE = Path(__file__).parent
_FILES = {
    GuidelineCorpus.HAX: _HERE / "hax18.yaml",
    GuidelineCorpus.PAIR: _HERE / "pair.yaml",
    GuidelineCorpus.IX: _HERE / "ix.yaml",
}


def load_corpus(corpus: GuidelineCorpus) -> list[Guideline]:
    """Loads a specific corpus from its YAML and validates it with pydantic."""
    path = _FILES[corpus]
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    declared = GuidelineCorpus(raw["corpus"])
    if declared != corpus:
        raise ValueError(f"{path.name} declara corpus {declared}, se esperaba {corpus}.")
    return [Guideline(corpus=declared, **item) for item in raw["guidelines"]]


@lru_cache(maxsize=1)
def all_guidelines() -> tuple[Guideline, ...]:
    """All guidelines from all corpora (cached)."""
    out: list[Guideline] = []
    for corpus in GuidelineCorpus:
        out.extend(load_corpus(corpus))
    ids = [g.id for g in out]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"Ids de guideline duplicados entre corpus: {dupes}")
    return tuple(out)


def guidelines_by_id() -> dict[str, Guideline]:
    """Index id -> Guideline over all corpora."""
    return {g.id: g for g in all_guidelines()}
