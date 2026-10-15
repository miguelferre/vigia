"""El wheel lleva dentro los dos JSON de `src/vigia/content/`.

A diferencia de `data/demo` (test_wheel_datos.py), estos JSON viven ya dentro
de `src/vigia/` y no necesitan `force-include`: `pyproject.toml:52` declara
`packages = ["src/vigia"]` y hatchling incluye los ficheros de datos del
paquete solos. Este test comprueba que eso es verdad, porque un contenido que
no llega al paquete de Windows es un fallo silencioso.
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
    "vigia/content/metricas-ayuda.json",
    "vigia/content/glosario.json",
)


def _cargar_build():
    """Carga build/build.py como módulo aislado (igual que test_wheel_datos.py)."""
    spec = importlib.util.spec_from_file_location("vigia_build_script_contenido", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv no está en el PATH")
def test_el_wheel_incluye_content(tmp_path):
    build = _cargar_build()
    args = build.uv_build_wheel_command(REPO_ROOT, tmp_path)
    build.run_uv(args)

    wheels = sorted(tmp_path.glob("vigia-*.whl"))
    assert wheels, f"uv {' '.join(args)} no dejó ningún wheel en {tmp_path}"

    with zipfile.ZipFile(wheels[0]) as z:
        nombres = set(z.namelist())
    faltan = [n for n in ESPERADOS if n not in nombres]
    assert not faltan, f"el wheel no lleva {faltan}"
