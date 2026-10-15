# Eticas AI Risk Taxonomy (vendored)

`taxonomy.yaml` and `mappings.yaml` are the public distribution of the **Eticas AI Risk Taxonomy**
(v3.0.0), by Eticas, published under **CC BY 4.0**. They are vendored here unmodified to power the
level-2 regulatory inheritance in `interaction_review/eticas.py`: each of our guidelines anchors to
one or more of these concepts (in `../regulatory_map.yaml`, key `eticas`), and a finding inherits the
~18 external framework mappings each concept already carries.

- Source: https://github.com/Eticas-AI/ai-risk-taxonomy-public
- Site: https://taxonomy.eticas.ai
- License: CC BY 4.0 (see `LICENSE`)
- Citation: see `CITATION.cff` — Galdon Clavell, Accuosto & Gohar (2026), arXiv:2607.02201.

We do not modify these files. Our own extension of this taxonomy (the human-AI interaction branch,
`human-ai-interaction`) lives separately in `docs/reference/eticas_extension.yaml`; it is ours, not
Eticas'. The inheritance is indicative, not a legal opinion.
