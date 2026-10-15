"""El wheel lleva la copia vendorizada de `interaction_review` con sus datos.

Las directrices y el mapa regulatorio se cargan por `Path(__file__)`: si el
wheel no lleva los YAML, el fallo aparece en la máquina del usuario y no en
la del desarrollo (fallo silencioso, como `test_wheel_contenido.py`). Construye
el wheel en una carpeta temporal con `uv build --wheel` (sin red, sin tocar
`.venv`), comprueba su lista y lo instala con `--target --no-deps` en otra
carpeta temporal para cargar las directrices desde ahí.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "build" / "build.py"
RAIZ_COPIA = "vigia/human/_vendor/interaction_review"

# Los 9 ficheros de datos del paquete (4 YAML de directrices y mapa regulatorio,
# 5 de Eticas con su licencia y atribución), más la licencia MIT y PROCEDENCIA.md.
DATOS = (
    "guidelines/hax18.yaml",
    "guidelines/pair.yaml",
    "guidelines/ix.yaml",
    "guidelines/regulatory_map.yaml",
    "guidelines/eticas/taxonomy.yaml",
    "guidelines/eticas/mappings.yaml",
    "guidelines/eticas/LICENSE",
    "guidelines/eticas/ATTRIBUTION.md",
    "guidelines/eticas/CITATION.cff",
)
OTROS = ("LICENSE", "PROCEDENCIA.md", "__init__.py", "guidelines/loader.py")

sin_uv = pytest.mark.skipif(shutil.which("uv") is None, reason="uv no está en el PATH")


def _cargar_build():
    spec = importlib.util.spec_from_file_location("vigia_build_script_vendor", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    destino = tmp_path_factory.mktemp("wheel_vendor")
    build = _cargar_build()
    build.run_uv(build.uv_build_wheel_command(REPO_ROOT, destino))
    ruedas = sorted(destino.glob("vigia-*.whl"))
    assert ruedas, f"no quedó ningún wheel en {destino}"
    return ruedas[0]


@sin_uv
def test_el_wheel_lleva_los_nueve_ficheros_de_datos(wheel):
    with zipfile.ZipFile(wheel) as z:
        nombres = set(z.namelist())
    faltan = [f for f in (*DATOS, *OTROS) if f"{RAIZ_COPIA}/{f}" not in nombres]
    assert not faltan, f"el wheel no lleva {faltan}"
    # El cierre de imports completo y ninguna pieza que no es del cierre.
    modulos = [n for n in nombres if n.startswith(RAIZ_COPIA + "/") and n.endswith(".py")]
    assert len(modulos) == 23, sorted(modulos)
    assert f"{RAIZ_COPIA}/cli.py" not in nombres
    assert f"{RAIZ_COPIA}/mcp_server.py" not in nombres
    assert not any(n.startswith("interaction_review/") for n in nombres)


@sin_uv
def test_el_wheel_declara_licencia_y_no_depende_del_paquete_externo(wheel):
    with zipfile.ZipFile(wheel) as z:
        metadata = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
        texto = z.read(metadata).decode("utf-8")
    assert "License-Expression: MIT" in texto
    assert "Requires-Dist: interaction-review" not in texto
    assert "Requires-Dist: interaction_review" not in texto


@sin_uv
def test_directrices_cargan_desde_el_wheel_instalado(wheel, tmp_path):
    """Instala el wheel con `--target` y carga directrices, mapa y taxonomía desde ahí."""
    objetivo = tmp_path / "site"
    uv = shutil.which("uv")
    subprocess.run(
        [uv, "pip", "install", "--python", sys.executable, "--target", str(objetivo),
         "--no-deps", str(wheel)],
        check=True, capture_output=True, text=True,
        env={**os.environ, "UV_PYTHON_DOWNLOADS": "never"},
    )
    assert (objetivo / "vigia" / "human" / "_vendor" / "interaction_review" / "guidelines" / "hax18.yaml").is_file()

    codigo = (
        "import sys\n"
        f"sys.path.insert(0, {str(objetivo)!r})\n"
        "import vigia\n"
        "from vigia.human._vendor.interaction_review import eticas, regulatory\n"
        "from vigia.human._vendor.interaction_review.guidelines import all_guidelines\n"
        "print(vigia.__file__)\n"
        "print(len(all_guidelines()))\n"
        "print(regulatory.unmapped_guidelines(), regulatory.unknown_map_ids(), regulatory.unknown_eticas_ids())\n"
        "print(eticas.unknown_concepts(['no-existe-xyz']))\n"
    )
    entorno = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    salida = subprocess.run(
        [sys.executable, "-c", codigo], check=True, capture_output=True, text=True,
        env=entorno, cwd=tmp_path,
    ).stdout.splitlines()
    assert Path(salida[0]).resolve().is_relative_to(objetivo.resolve()), salida[0]
    assert salida[1] == "32"
    assert salida[2] == "[] [] []"
    assert salida[3] == "['no-existe-xyz']"
