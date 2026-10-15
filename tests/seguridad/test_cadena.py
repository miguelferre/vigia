"""Cadena de suministro del build : controles de build/build.py.

Sin red, sin uv real y sin compilar nada: se comprueba el comportamiento de
`cmd_fetch` con `urlretrieve` sustituido y la composicion de los argumentos de uv.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "build" / "build.py"


def _cargar_build():
    spec = importlib.util.spec_from_file_location("vigia_build_script_cadena", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bs = _cargar_build()


def _zip_inocuo(path: Path) -> None:
    """Zip valido y distinto del oficial: un unico fichero de texto."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("nota.txt", "contenido de prueba")


@pytest.fixture
def embed_tmp(tmp_path, monkeypatch):
    carpeta = tmp_path / "embed"
    monkeypatch.setattr(bs, "EMBED_DIR", carpeta)
    return carpeta


def _sin_red(monkeypatch):
    def _no_red(*_a, **_k):
        raise AssertionError("no debe haber descarga en este caso")

    monkeypatch.setattr(bs.urllib.request, "urlretrieve", _no_red)


def test_embed_control_positivo_fichero_no_zip_da_1(embed_tmp, monkeypatch):
    """Control positivo: cmd_fetch llega a su validacion y rechaza un fichero que no es zip."""
    _sin_red(monkeypatch)
    embed_tmp.mkdir(parents=True)
    destino = embed_tmp / bs.embed_zip_name(bs.DEFAULT_VERSION)
    destino.write_bytes(b"no es un zip")
    assert bs.cmd_fetch(argparse.Namespace(version=bs.DEFAULT_VERSION)) == 1


def test_embed_zip_distinto_se_rechaza(embed_tmp, monkeypatch):
    """Un zip descargado distinto del oficial no pasa."""
    llamadas = []

    def _descarga(_url, dest):
        llamadas.append(dest)
        _zip_inocuo(Path(dest))

    monkeypatch.setattr(bs.urllib.request, "urlretrieve", _descarga)
    codigo = bs.cmd_fetch(argparse.Namespace(version=bs.DEFAULT_VERSION))
    assert llamadas, "la descarga sustituida debe ejercerse"
    assert Path(llamadas[0]).exists()
    assert codigo != 0


def test_embed_version_no_fijada_se_rechaza(embed_tmp, monkeypatch):
    """Una version sin huella fijada no se acepta."""

    def _descarga(_url, dest):
        _zip_inocuo(Path(dest))

    monkeypatch.setattr(bs.urllib.request, "urlretrieve", _descarga)
    codigo = bs.cmd_fetch(argparse.Namespace(version="3.13.99"))
    assert (embed_tmp / bs.embed_zip_name("3.13.99")).exists()
    assert codigo != 0


def test_embed_zip_ya_presente_se_verifica(embed_tmp, monkeypatch):
    """Un zip ya presente en build/embed tambien se comprueba."""
    _sin_red(monkeypatch)
    embed_tmp.mkdir(parents=True)
    destino = embed_tmp / bs.embed_zip_name(bs.DEFAULT_VERSION)
    _zip_inocuo(destino)
    codigo = bs.cmd_fetch(argparse.Namespace(version=bs.DEFAULT_VERSION))
    assert destino.exists()
    assert codigo != 0


def test_uv_export_fija_el_lock(tmp_path, monkeypatch):
    """El export respeta el lock (--locked, --frozen o UV_*)."""
    capturado = {}

    def _falso_run(cmd, **kwargs):
        capturado["cmd"] = list(cmd)
        capturado["env"] = kwargs.get("env") or {}
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(bs, "system_python", lambda: Path("python.exe"))
    monkeypatch.setattr(bs.subprocess, "run", _falso_run)
    for var in ("UV_LOCKED", "UV_FROZEN"):
        monkeypatch.delenv(var, raising=False)

    args = bs.uv_export_command(tmp_path / "requirements.txt", with_shap=True)
    bs.run_uv(args)

    assert capturado["cmd"][:2] == ["uv", "export"], "el comando compuesto debe llegar a uv"
    env = capturado["env"]
    por_indicador = "--locked" in capturado["cmd"] or "--frozen" in capturado["cmd"]
    por_entorno = env.get("UV_LOCKED") in {"1", "true"} or env.get("UV_FROZEN") in {"1", "true"}
    assert por_indicador or por_entorno
