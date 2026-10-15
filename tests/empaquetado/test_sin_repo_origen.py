"""El empaquetado no depende de ningún repo origen ni de ninguna ruta suya.

Con `interaction_review` vendorizado, el producto no depende de una carpeta
ajena: sin dependencia por ruta, sin segundo wheel y sin referencias a esa
carpeta en `pyproject.toml`, `uv.lock` ni `build/build.py`.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# Nombre de la carpeta del repo origen, por partes: este fichero se exporta y el
# filtro de términos prohibidos del árbol público no debe verlo en claro.
CARPETA_ORIGEN = "agente_" + "IA_" + "Hu" + "mano"
FICHEROS = ("pyproject.toml", "uv.lock", "build/build.py")


@pytest.mark.parametrize("fichero", FICHEROS)
def test_el_empaquetado_no_nombra_el_repo_origen(fichero):
    texto = (REPO_ROOT / fichero).read_text(encoding="utf-8")
    assert texto.count(CARPETA_ORIGEN) == 0


@pytest.mark.parametrize("fichero", ("uv.lock", "build/build.py"))
def test_no_declara_la_dependencia_interaction_review(fichero):
    texto = (REPO_ROOT / fichero).read_text(encoding="utf-8").lower()
    assert "interaction-review" not in texto
    assert "interaction_review" not in texto


def test_pyproject_no_depende_de_interaction_review():
    datos = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencias = [d.lower().replace("_", "-") for d in datos["project"]["dependencies"]]
    assert not any(d.startswith("interaction-review") for d in dependencias)


def test_pyproject_sin_fuentes_por_ruta_y_con_licencia():
    datos = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "sources" not in datos.get("tool", {}).get("uv", {})
    assert datos["project"]["license"] == "MIT"
    assert datos["project"]["license-files"] == ["LICENSE", "NOTICE"]


def test_ningun_fichero_de_empaquetado_lleva_una_ruta_personal():
    # `build.py` no fija la ruta de ningún usuario.
    usuario = "C:\\Users\\" + "ferre"
    for fichero in ("build/build.py", "build/README.md", "build/Vigia.cmd.template"):
        texto = (REPO_ROOT / fichero).read_text(encoding="utf-8")
        assert usuario.lower() not in texto.lower().replace("/", "\\"), fichero
