"""Guideline corpora (HAX-18, PAIR and IX) and their loader."""

from .loader import (
    all_guidelines,
    guidelines_by_id,
    load_corpus,
)

# Single source of truth for the default corpus selection. It lives here (not as a
# literal in cli.py / mcp_server.py) because a duplicated "hax,pair" literal is exactly
# what silently dropped the IX corpus from every review once ix.yaml was added.
DEFAULT_CORPUS = "hax,pair,ix"

__all__ = ["DEFAULT_CORPUS", "all_guidelines", "guidelines_by_id", "load_corpus"]
