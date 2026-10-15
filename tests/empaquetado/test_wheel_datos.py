"""El wheel lleva dentro los datos enlatados de la demo.

`data/demo` sigue viviendo en la raíz del repositorio; el `force-include` de `pyproject.toml` lo copia a `vigia/data/demo`
dentro del wheel para que el reproductor de demo funcione en el paquete de
Windows, donde no hay raíz de repositorio. Construir el wheel tarda ~1 s, así
que el test corre en la suite normal; si uv no está disponible se salta.
"""

from __future__ import annotations

import importlib.util
import shutil
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "build" / "build.py"

ESPERADOS = (
    "vigia/data/demo/dossier_demo.json",
    "vigia/data/demo/escenario_1/01_baseline_payload.json",
    "vigia/data/demo/escenario_2/02_evento_payload.json",
    "vigia/data/demo/usage_logs_demo.csv",
)


def _cargar_build():
    """Carga build/build.py como módulo aislado (igual que test_build_script.py)."""
    spec = importlib.util.spec_from_file_location("vigia_build_script_wheel", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv no está en el PATH")
def test_el_wheel_incluye_data_demo(tmp_path):
    build = _cargar_build()
    args = build.uv_build_wheel_command(REPO_ROOT, tmp_path)
    build.run_uv(args)

    wheels = sorted(tmp_path.glob("vigia-*.whl"))
    assert wheels, f"uv {' '.join(args)} no dejó ningún wheel en {tmp_path}"

    with zipfile.ZipFile(wheels[0]) as z:
        nombres = set(z.namelist())
    faltan = [n for n in ESPERADOS if n not in nombres]
    assert not faltan, f"el wheel no lleva {faltan}"
