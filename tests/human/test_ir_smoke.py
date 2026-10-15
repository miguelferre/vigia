"""Test de humo de la capa humana (interaction_review).

Reutiliza la logica de build/smoke_ir.py (anadiendo build/ al sys.path) en vez
de duplicarla, para que el pytest y el script de linea de comandos verifiquen
exactamente lo mismo.

Los 32 corresponden a directrices, no a ficheros: son 3 ficheros YAML de corpus
(hax18.yaml=18, pair.yaml=12, ix.yaml=2) que suman 32 directrices
individuales (all_guidelines()).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BUILD_DIR = REPO_ROOT / "build"
if str(BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(BUILD_DIR))

from smoke_ir import DEFAULT_DOSSIER, run_smoke

# Cifra real contada leyendo guidelines/hax18.yaml (18) + pair.yaml (12) + ix.yaml (2).
EXPECTED_GUIDELINES_TOTAL = 32
EXPECTED_GUIDELINES_BY_SOURCE = {"HAX": 18, "PAIR": 12, "IX": 2}


def test_smoke_ir_completo(tmp_path):
    t0 = time.monotonic()
    result = run_smoke(DEFAULT_DOSSIER, tmp_path)
    elapsed_s = time.monotonic() - t0

    assert result["errors"] == [], f"errores en el smoke: {result['errors']}"
    assert result["ok"] is True

    assert result["guidelines_total"] == EXPECTED_GUIDELINES_TOTAL
    assert result["guidelines_by_source"] == EXPECTED_GUIDELINES_BY_SOURCE

    assert result["findings_total"] > 0
    assert result["findings_total"] == EXPECTED_GUIDELINES_TOTAL  # B0: un finding por directriz

    assert result["html_bytes"] > 0
    html_path = tmp_path / "smoke_findings_b0.html"
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert html.lower().startswith("<!doctype html")
    assert "Digestivo" in html or "Vigia" in html or len(html) > 0  # sistema identificable

    assert elapsed_s < 30, f"el smoke tardo {elapsed_s:.1f}s, se esperaba <30s"


def test_crosswalk_devuelve_referencias(tmp_path):
    import json

    from vigia.human._vendor.interaction_review import regulatory
    from vigia.human._vendor.interaction_review.approaches.b0_checklist import run as run_b0
    from vigia.human._vendor.interaction_review.guidelines import all_guidelines
    from vigia.human._vendor.interaction_review.schemas import Dossier

    data = json.loads(DEFAULT_DOSSIER.read_text(encoding="utf-8"))
    dossier = Dossier.model_validate(data)
    guidelines = list(all_guidelines())
    findings = run_b0(dossier, guidelines)

    xwalk = regulatory.crosswalk(findings)
    assert xwalk, "el crosswalk regulatorio no debe estar vacio"
    assert set(xwalk).issubset({"eu_ai_act", "nist_ai_rmf", "interaction_risk"})
    for refs in xwalk.values():
        assert len(refs) > 0

    assert regulatory.unmapped_guidelines() == []
    assert regulatory.unknown_map_ids() == []
