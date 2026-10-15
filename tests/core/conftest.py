"""Fixtures del carril CORE-A: rutas y frames canónicos del escenario 1."""
from __future__ import annotations

from pathlib import Path

import pytest

from vigia.core.loaders import concat_history, load_feedback, to_canonical
from vigia.core.schema import HARNESS_FEEDBACK_MAPPING

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_E1 = REPO_ROOT / "data" / "demo" / "escenario_1"
DATA_E2 = REPO_ROOT / "data" / "demo" / "escenario_2"


@pytest.fixture
def e1_baseline_feedback_path() -> Path:
    return DATA_E1 / "01_baseline_feedback.json"


@pytest.fixture
def e1_baseline_payload_path() -> Path:
    return DATA_E1 / "01_baseline_payload.json"


@pytest.fixture
def e1_evento_feedback_path() -> Path:
    return DATA_E1 / "02_evento_feedback.json"


@pytest.fixture
def e1_evento_payload_path() -> Path:
    return DATA_E1 / "02_evento_payload.json"


@pytest.fixture
def e2_evento_feedback_path() -> Path:
    return DATA_E2 / "02_evento_feedback.json"


@pytest.fixture
def e2_recovery_feedback_path() -> Path:
    return DATA_E2 / "03_recovery_feedback.json"


@pytest.fixture
def baseline_canonico(e1_baseline_feedback_path: Path):
    fb = load_feedback(e1_baseline_feedback_path)
    return to_canonical(fb, HARNESS_FEEDBACK_MAPPING, batch_seq=0, model_version="v1")


@pytest.fixture
def evento_canonico(e1_evento_feedback_path: Path):
    fb = load_feedback(e1_evento_feedback_path)
    return to_canonical(
        fb, HARNESS_FEEDBACK_MAPPING, batch_seq=1, model_version="v1", seq_start=450
    )


@pytest.fixture
def historia_baseline_evento(baseline_canonico, evento_canonico):
    return concat_history([baseline_canonico, evento_canonico])
