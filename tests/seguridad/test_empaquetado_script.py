"""Controles del script de empaquetado.

Instalación limpia del frontend, lista de privados exigible y manifiesto ligado al zip;
ver `HUELLAS`. Nada ejecuta npm, uv ni red: `subprocess` se simula.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
from pathlib import Path

import pytest

HUELLAS = {
    "test_el_frontend_se_instala_limpio_y_sin_scripts_antes_de_compilar": "frontend-clean-install",
    "test_la_instalacion_limpia_se_puede_saltar_con_un_argumento": "frontend-clean-install",
    "test_si_la_instalacion_limpia_falla_no_se_compila": "frontend-clean-install",
    "test_el_argumento_para_saltar_la_instalacion_existe": "frontend-clean-install",
    "test_la_lista_de_privados_se_puede_exigir_por_argumento": "private-list-required",
    "test_la_lista_de_privados_se_puede_exigir_por_variable": "private-list-required",
    "test_sin_exigirla_la_lista_de_privados_ausente_no_bloquea": "private-list-required",
    "test_exigida_y_presente_la_lista_se_aplica": "private-list-required",
    "test_el_manifiesto_lleva_el_nombre_del_zip": "manifest-zip-name",
}

REPO_ROOT = Path(__file__).resolve().parents[2]


def _cargar_build():
    spec = importlib.util.spec_from_file_location(
        "vigia_build_script_s2b", REPO_ROOT / "build" / "build.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bs = _cargar_build()


def _simular_subprocess(monkeypatch, codigos=None):
    llamadas: list[list[str]] = []

    def falso(orden, **kwargs):
        llamadas.append(list(orden))
        codigo = (codigos or {}).get(orden[1], 0)
        return subprocess.CompletedProcess(orden, codigo, stdout="", stderr="")

    monkeypatch.setattr(bs.subprocess, "run", falso)
    return llamadas


def test_el_frontend_se_instala_limpio_y_sin_scripts_antes_de_compilar(monkeypatch):
    llamadas = _simular_subprocess(monkeypatch)
    bs.compile_frontend()
    assert [o[1:] for o in llamadas] == [["ci", "--ignore-scripts"], ["run", "build"]]


def test_la_instalacion_limpia_se_puede_saltar_con_un_argumento(monkeypatch):
    llamadas = _simular_subprocess(monkeypatch)
    bs.compile_frontend(instalar=False)
    assert [o[1:] for o in llamadas] == [["run", "build"]]


def test_si_la_instalacion_limpia_falla_no_se_compila(monkeypatch):
    llamadas = _simular_subprocess(monkeypatch, codigos={"ci": 1})
    with pytest.raises(bs.EstaticoError, match="npm ci"):
        bs.compile_frontend()
    assert [o[1] for o in llamadas] == ["ci"]


def test_el_argumento_para_saltar_la_instalacion_existe():
    parser = bs.build_parser()
    assert parser.parse_args(["assemble", "--sin-npm-ci"]).sin_npm_ci is True
    assert parser.parse_args(["assemble"]).sin_npm_ci is False


def test_la_lista_de_privados_se_puede_exigir_por_argumento(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "PRIVADOS_FILE", tmp_path / "renombrado.txt")
    monkeypatch.delenv(bs.ENV_EXIGIR_PRIVADOS, raising=False)
    with pytest.raises(FileNotFoundError, match="privados"):
        bs.comprobar_wheel_sin_privados(tmp_path / "x.whl", exigir=True)


def test_la_lista_de_privados_se_puede_exigir_por_variable(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "PRIVADOS_FILE", tmp_path / "renombrado.txt")
    monkeypatch.setenv(bs.ENV_EXIGIR_PRIVADOS, "1")
    with pytest.raises(FileNotFoundError, match="privados"):
        bs.comprobar_wheel_sin_privados(tmp_path / "x.whl")


def test_sin_exigirla_la_lista_de_privados_ausente_no_bloquea(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "PRIVADOS_FILE", tmp_path / "no-existe.txt")
    monkeypatch.delenv(bs.ENV_EXIGIR_PRIVADOS, raising=False)
    assert bs.comprobar_wheel_sin_privados(tmp_path / "x.whl") == []


def test_exigida_y_presente_la_lista_se_aplica(tmp_path, monkeypatch):
    import zipfile

    lista = tmp_path / "privados.txt"
    lista.write_text("src/vigia/secreto.py\n", encoding="utf-8")
    wheel = tmp_path / "x.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("vigia/secreto.py", "x")
    monkeypatch.setattr(bs, "PRIVADOS_FILE", lista)
    assert bs.comprobar_wheel_sin_privados(wheel, exigir=True) == ["src/vigia/secreto.py"]


def test_el_manifiesto_lleva_el_nombre_del_zip(tmp_path):
    out = tmp_path / "vigia-9.9.9-win64"
    (out / "runtime" / "python").mkdir(parents=True)
    (out / "LEEME.txt").write_text("hola", encoding="utf-8")
    dist = tmp_path / "dist"
    args = argparse.Namespace(out=str(out), dist=str(dist), version="3.13.12")
    assert bs.cmd_zip(args) == 0
    assert (dist / "vigia-9.9.9-win64.zip.MANIFIESTO.txt").is_file()
    assert not (dist / "MANIFIESTO.txt").exists()
