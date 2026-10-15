"""Dependencias declaradas frente al lock.

`vigia.core.predict_onnx` y `app.services.onnx_entradas_double` importan `onnx` directamente, y
llegaba solo como dependencia indirecta de `skl2onnx`. Estos
tests fijan que `pyproject.toml` lo declara con la versión del lock. `uv lock --check`
(con `UV_PYTHON_DOWNLOADS=never`) es la comprobación completa y la corre el cierre.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
LOCK = REPO_ROOT / "uv.lock"


def _dependencias() -> list[str]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["dependencies"]


def _lock() -> dict:
    return tomllib.loads(LOCK.read_text(encoding="utf-8"))


def _paquete(nombre: str) -> dict:
    return next(p for p in _lock()["package"] if p["name"] == nombre)


def test_onnx_esta_declarado_con_la_version_exacta_del_lock():
    declaradas = [d for d in _dependencias() if re.match(r"onnx(?![\w-])", d)]
    assert len(declaradas) == 1, declaradas
    version = _paquete("onnx")["version"]
    assert declaradas[0].replace(" ", "") == f"onnx=={version}"


def test_el_lock_lista_onnx_entre_las_dependencias_directas_de_vigia():
    vigia = _paquete("vigia")
    assert "onnx" in [d["name"] for d in vigia["dependencies"]]
    requeridas = {d["name"]: d for d in vigia["metadata"]["requires-dist"]}
    assert requeridas["onnx"]["specifier"] == f"=={_paquete('onnx')['version']}"


def test_todo_lo_que_se_importa_de_onnx_esta_declarado():
    """Si algún módulo de `src/vigia` importa `onnx`, la dependencia directa es obligatoria."""
    importan = [
        p
        for p in (REPO_ROOT / "src" / "vigia").rglob("*.py")
        if re.search(r"^\s*(?:import|from)\s+onnx(?![\w])", p.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    declarada = any(re.match(r"onnx(?![\w-])", d) for d in _dependencias())
    assert declarada or not importan, [str(p.relative_to(REPO_ROOT)) for p in importan]
