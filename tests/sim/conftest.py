"""Fixtures comunes del carril sim: rutas a los datos enlatados del demo."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo"


@pytest.fixture
def e1_dir() -> Path:
    return DEMO_DIR / "escenario_1"


@pytest.fixture
def e2_dir() -> Path:
    return DEMO_DIR / "escenario_2"


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()
