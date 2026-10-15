"""La copia vendorizada de `interaction_review`.

`src/vigia/human/_vendor/interaction_review/` sustituye a la dependencia por
ruta. Estos tests fijan lo que la hace segura: imports solo relativos,
versión como constante, datos que cargan por `Path(__file__)` (en
`tests/empaquetado/test_vendor_wheel.py`), `PROCEDENCIA.md` presente y
`ruff` fuera de la copia. El proveedor de la revisión va en `test_revision_proveedor.py`.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
VENDOR = RAIZ / "src" / "vigia" / "human" / "_vendor" / "interaction_review"
CIERRE = 23  # módulos .py del cierre medido el 2026-10-06, sin `report_html.py`


def _modulos() -> list[Path]:
    return sorted(VENDOR.rglob("*.py"))


def test_cierre_de_modulos_completo():
    assert len(_modulos()) == CIERRE
    for sin_copiar in ("cli.py", "mcp_server.py", "runner.py", "smart_ingest.py", "judge.py", "report_html.py"):
        assert not (VENDOR / sin_copiar).exists(), f"{sin_copiar} no es del cierre de imports"


def test_ningun_import_de_primer_nivel_de_interaction_review():
    """La copia no importa `interaction_review` como paquete de primer nivel,
    ni arriba ni dentro de una función, y no toca `sys.path`."""
    ofensores: list[str] = []
    for ruta in _modulos():
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom):
                if nodo.level == 0 and (nodo.module or "").split(".")[0] == "interaction_review":
                    ofensores.append(f"{ruta.relative_to(VENDOR)}:{nodo.lineno} from {nodo.module}")
            elif isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    if alias.name.split(".")[0] == "interaction_review":
                        ofensores.append(f"{ruta.relative_to(VENDOR)}:{nodo.lineno} import {alias.name}")
            elif (
                isinstance(nodo, ast.Attribute)
                and nodo.attr == "path"
                and isinstance(nodo.value, ast.Name)
                and nodo.value.id == "sys"
            ):
                ofensores.append(f"{ruta.relative_to(VENDOR)}:{nodo.lineno} sys.path")
    assert not ofensores, ofensores


def test_versiones_salen_de_la_constante():
    """La versión no se lee de los metadatos de una distribución."""
    from vigia.human import dossier_adapter, ir_adapter
    from vigia.human._vendor import interaction_review

    assert interaction_review.__version__ == "0.1.0"
    assert ir_adapter.PACKAGE_VERSION == "0.1.0"
    assert dossier_adapter.PACKAGE_VERSION == "0.1.0"
    for modulo in (ir_adapter, dossier_adapter):
        fuente = Path(modulo.__file__).read_text(encoding="utf-8")
        assert "importlib.metadata" not in fuente


def test_directrices_cargan_desde_la_copia():
    from vigia.human._vendor.interaction_review import eticas, regulatory
    from vigia.human._vendor.interaction_review.guidelines import all_guidelines

    assert len(all_guidelines()) == 32
    assert regulatory.unmapped_guidelines() == []
    assert regulatory.unknown_map_ids() == []
    assert regulatory.unknown_eticas_ids() == []
    assert eticas.unknown_concepts(["no-existe-xyz"]) == ["no-existe-xyz"]


def test_tildes_en_las_directrices_sin_tocar_identificadores():
    """Las directrices salen con tildes; los identificadores no cambian."""
    from vigia.human._vendor.interaction_review.guidelines import all_guidelines

    por_id = {g.id: g for g in all_guidelines()}
    assert "qué puede hacer" in por_id["HAX-G1"].title
    assert por_id["IX-1"].group == "Supervisión humana y agencia"
    assert {"HAX-G1", "HAX-G18", "PAIR-UN-1", "IX-1", "IX-2"} <= set(por_id)


def test_procedencia_y_licencias_intactas():
    """PROCEDENCIA.md con el commit de origen, licencias presentes
    y ruff excluye la copia."""
    procedencia = (VENDOR / "PROCEDENCIA.md").read_text(encoding="utf-8")
    assert "dcb0ca8363195fe7803793f0fa59cddaf869402d" in procedencia
    assert "extend-exclude" in procedencia
    assert (VENDOR / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")
    eticas = VENDOR / "guidelines" / "eticas"
    for nombre in ("LICENSE", "ATTRIBUTION.md", "CITATION.cff"):
        assert (eticas / nombre).is_file(), nombre

    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["tool"]["ruff"]["extend-exclude"] == ["src/vigia/human/_vendor"]
