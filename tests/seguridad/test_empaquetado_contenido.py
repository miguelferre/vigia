"""El zip solo lleva el contenido esperado.

Cada test comprueba el control de la lista blanca del paquete antes de empaquetar;
ver `HUELLAS`. Sin red, sin uv y sin compilar nada: el paquete es sintético.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

HUELLAS = {
    "test_un_paquete_esperado_no_da_problemas": "zip-content-allowlist",
    "test_el_paquete_rechaza_un_fichero_fuera_de_la_lista_blanca": "zip-content-allowlist",
    "test_el_paquete_rechaza_datos_locales_en_el_codigo_de_vigia": "zip-local-data",
    "test_el_paquete_rechaza_la_ruta_del_usuario_de_build": "zip-local-data",
    "test_el_paquete_no_confunde_los_datos_de_prueba_de_terceros": "zip-local-data",
    "test_el_zip_no_se_crea_si_el_paquete_lleva_un_fichero_inesperado": "zip-content-allowlist",
}

REPO_ROOT = Path(__file__).resolve().parents[2]


def _cargar_build():
    spec = importlib.util.spec_from_file_location(
        "vigia_build_script_s2", REPO_ROOT / "build" / "build.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bs = _cargar_build()


def _escribir(base: Path, ruta: str, texto: str = "x") -> Path:
    destino = base / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return destino


def _paquete(base: Path) -> Path:
    """Un paquete como el que deja `assemble`, con lo mínimo de cada zona."""
    out = base / "vigia-9.9.9-win64"
    for nombre in ("Vigia.cmd", "Vigia-consola.cmd", "LEEME.txt", "README.md", "LICENSE"):
        _escribir(out, nombre)
    for nombre in ("NOTICE", "TERCEROS.txt", "requirements.txt"):
        _escribir(out, nombre)
    _escribir(out, "docs/manual/inicio.md")
    _escribir(out, "docs/manual/img/pantalla.png")
    _escribir(out, "runtime/python/python.exe")
    site = "runtime/python/Lib/site-packages"
    _escribir(out, f"{site}/vigia/__init__.py")
    _escribir(out, f"{site}/vigia/static/index.html")
    _escribir(out, f"{site}/vigia/data/demo/usage_logs_demo.csv")
    _escribir(out, f"{site}/numpy/__init__.py")
    return out


def test_un_paquete_esperado_no_da_problemas(tmp_path):
    assert bs.comprobar_contenido_paquete(_paquete(tmp_path), []) == []


@pytest.mark.parametrize(
    "ruta",
    [
        "datos.db",
        "secretos.env",
        ".env",
        "pacientes.privado.csv",
        "modelo.pkl",
        "vigia.log",
        "docs/interno/plan.md",
        "docs/manual/ejecutable.exe",
        "build/out/otro.txt",
    ],
)
def test_el_paquete_rechaza_un_fichero_fuera_de_la_lista_blanca(tmp_path, ruta):
    out = _paquete(tmp_path)
    _escribir(out, ruta)
    problemas = bs.comprobar_contenido_paquete(out, [])
    assert any(ruta in p for p in problemas), problemas


@pytest.mark.parametrize(
    "ruta",
    [
        "vigia/data/caso.db",
        "vigia/data/.env",
        "vigia/m.joblib",
        "vigia/m.pkl",
        "vigia/v.log",
        "vigia/pacientes.privado.csv",
    ],
)
def test_el_paquete_rechaza_datos_locales_en_el_codigo_de_vigia(tmp_path, ruta):
    out = _paquete(tmp_path)
    _escribir(out, f"runtime/python/Lib/site-packages/{ruta}")
    problemas = bs.comprobar_contenido_paquete(out, [])
    assert any(ruta in p for p in problemas), problemas


def test_el_paquete_rechaza_la_ruta_del_usuario_de_build(tmp_path):
    out = _paquete(tmp_path)
    casa = tmp_path / "Users" / "alguien"
    _escribir(out, "LEEME.txt", f"hecho en {casa}\\proyecto")
    problemas = bs.comprobar_contenido_paquete(out, [casa])
    assert any("LEEME.txt" in p for p in problemas), problemas


def test_el_paquete_no_confunde_los_datos_de_prueba_de_terceros(tmp_path):
    out = _paquete(tmp_path)
    _escribir(out, "runtime/python/Lib/site-packages/joblib/test/data/viejo.pkl")
    _escribir(out, "runtime/python/Lib/site-packages/scipy/io/tests/data/x.sav")
    assert bs.comprobar_contenido_paquete(out, []) == []


def test_el_zip_no_se_crea_si_el_paquete_lleva_un_fichero_inesperado(tmp_path, capsys):
    out = _paquete(tmp_path)
    _escribir(out, "pacientes.db")
    dist = tmp_path / "dist"
    args = argparse.Namespace(out=str(out), dist=str(dist), version="3.13.12")
    assert bs.cmd_zip(args) == 1
    assert "pacientes.db" in capsys.readouterr().err
    assert not list(dist.glob("*.zip")) if dist.exists() else True
