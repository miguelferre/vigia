"""Comprueba que vigia.sim no depende de dotenv ni de escenarios/config.

SIM_MODULES se amplía cuando human/scenarios importe estos módulos.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SIM_MODULES: list[str] = [
    "vigia.sim",
    "vigia.sim.model",
    "vigia.sim.generators",
    "vigia.sim.serialize",
    "vigia.sim.human",
    "vigia.sim.scenarios",
]

SIM_SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "vigia" / "sim"


def test_importar_sim_no_carga_dotenv_ni_escenarios():
    imports = "; ".join(f"import {mod}" for mod in SIM_MODULES)
    code = (
        f"{imports}\n"
        "import sys\n"
        "assert 'dotenv' not in sys.modules, 'dotenv cargado'\n"
        "bad = [m for m in sys.modules if m.startswith('escenarios')]\n"
        "assert not bad, f'módulos escenarios cargados: {bad}'\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_ficheros_sim_no_mencionan_dotenv_ni_config_relativo():
    for path in SIM_SRC_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "dotenv" not in text, f"{path.name} menciona dotenv"
        assert "from .config" not in text, f"{path.name} importa .config"
