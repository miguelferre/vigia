"""Endurecimiento del build: ruta externa del runtime, versión de uv, formato de --version, ruta de compilación y README.

Sin red, sin uv real y sin compilar nada: `subprocess` y `urlretrieve` se sustituyen.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "build" / "build.py"


def _cargar_build():
    spec = importlib.util.spec_from_file_location("vigia_build_script_end7", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bs = _cargar_build()


# --------------------------------------------------------------------------
# Ninguna ruta externa al runtime en python313._pth
# --------------------------------------------------------------------------


def test_pth_no_lleva_ruta_app_aunque_venga_en_el_original():
    for original in ("python313.zip\n.\n#import site\n", "python313.zip\n.\n..\\app\nimport site\n"):
        lineas = bs.patch_pth_content(original).splitlines()
        assert not any(l.startswith("..") for l in lineas)
        assert "Lib\\site-packages" in lineas
        assert "import site" in lineas


# --------------------------------------------------------------------------
# Versión de uv
# --------------------------------------------------------------------------


def test_aviso_de_uv_solo_si_no_es_la_esperada():
    assert bs.aviso_version_uv(f"uv {bs.UV_ESPERADO} (3c979abda 2026-09-04 x86_64)") is None
    assert bs.aviso_version_uv("uv 0.1.0 (abc 2020-01-01)")
    assert bs.aviso_version_uv("")


def test_comprobar_uv_avisa_por_stderr(monkeypatch, capsys):
    def _uv(cmd, **_k):
        assert cmd == ["uv", "--version"]
        return subprocess.CompletedProcess(cmd, 0, stdout="uv 0.1.0 (x)\n", stderr="")

    monkeypatch.setattr(bs.subprocess, "run", _uv)
    assert bs.comprobar_uv()
    assert "aviso: uv no es la versión verificada" in capsys.readouterr().err

    def _uv_bueno(cmd, **_k):
        return subprocess.CompletedProcess(cmd, 0, stdout=f"uv {bs.UV_ESPERADO} (x)\n", stderr="")

    monkeypatch.setattr(bs.subprocess, "run", _uv_bueno)
    assert bs.comprobar_uv() is None
    assert capsys.readouterr().err == ""


def test_comprobar_uv_avisa_si_uv_no_existe(monkeypatch, capsys):
    def _no_uv(*_a, **_k):
        raise FileNotFoundError("uv")

    monkeypatch.setattr(bs.subprocess, "run", _no_uv)
    assert bs.comprobar_uv()
    assert "aviso:" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Formato de --version
# --------------------------------------------------------------------------


@pytest.mark.parametrize("version", ["3.13.12", "3.13.0", "3.13.99"])
def test_version_con_forma_3_13_n_se_acepta(version):
    assert bs.validar_version_python(version) == version
    assert version in bs.embed_url(version)


@pytest.mark.parametrize(
    "version",
    ["3.13.12/../x", "3.13.12\\..\\x", "3.14.0", "3.13", "3.13.", "3.13.12 ", "3.13.x", "", "3.13.1234"],
)
def test_version_con_otra_forma_se_rechaza(version):
    with pytest.raises(ValueError):
        bs.validar_version_python(version)
    with pytest.raises(ValueError):
        bs.embed_zip_name(version)


def test_cmd_fetch_rechaza_version_mal_formada_sin_descargar(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "EMBED_DIR", tmp_path / "embed")

    def _no_red(*_a, **_k):
        raise AssertionError("no debe haber descarga")

    monkeypatch.setattr(bs.urllib.request, "urlretrieve", _no_red)
    assert bs.cmd_fetch(argparse.Namespace(version="3.13.12/../../x")) == 1
    assert not (tmp_path / "embed").exists()


def test_el_parser_rechaza_version_mal_formada():
    with pytest.raises(SystemExit):
        bs.build_parser().parse_args(["fetch", "--version", "3.13.12/../x"])
    args = bs.build_parser().parse_args(["fetch", "--version", "3.13.12"])
    assert args.version == "3.13.12"


# --------------------------------------------------------------------------
# huella del zip embebido: control positivo y constante fijada
# --------------------------------------------------------------------------


def test_la_huella_fijada_tiene_forma_de_sha256():
    huella = bs.PYTHON_EMBED_SHA256[bs.DEFAULT_VERSION]
    assert len(huella) == 64 and set(huella) <= set("0123456789abcdef")


def test_zip_con_la_huella_fijada_pasa(tmp_path, monkeypatch):
    carpeta = tmp_path / "embed"
    monkeypatch.setattr(bs, "EMBED_DIR", carpeta)
    carpeta.mkdir()
    zip_prueba = carpeta / bs.embed_zip_name("3.13.77")
    with zipfile.ZipFile(zip_prueba, "w") as zf:
        zf.writestr("nota.txt", "x")
    huella = hashlib.sha256(zip_prueba.read_bytes()).hexdigest()
    monkeypatch.setitem(bs.PYTHON_EMBED_SHA256, "3.13.77", huella)

    def _no_red(*_a, **_k):
        raise AssertionError("no debe haber descarga")

    monkeypatch.setattr(bs.urllib.request, "urlretrieve", _no_red)
    assert bs.cmd_fetch(argparse.Namespace(version="3.13.77")) == 0
    assert bs.verificar_embed(zip_prueba, "3.13.77") is None


def test_assemble_rechaza_un_zip_distinto_del_fijado(tmp_path, monkeypatch, capsys):
    carpeta = tmp_path / "embed"
    monkeypatch.setattr(bs, "EMBED_DIR", carpeta)
    carpeta.mkdir()
    with zipfile.ZipFile(carpeta / bs.embed_zip_name(bs.DEFAULT_VERSION), "w") as zf:
        zf.writestr("nota.txt", "no es el oficial")
    args = argparse.Namespace(
        version=bs.DEFAULT_VERSION, with_shap=True, con_parquet=False, out=None, sin_npm=True
    )
    assert bs.cmd_assemble(args) == 1
    assert "sha256" in capsys.readouterr().err


# --------------------------------------------------------------------------
# El paquete no lleva la ruta de la máquina de compilación
# --------------------------------------------------------------------------


def _paquete_de_prueba(out_dir: Path, ruta: str) -> None:
    """Paquete mínimo con las huellas que dejaba uv: lanzadores, direct_url, pyc y comentarios."""
    site = out_dir / "runtime" / "python" / "Lib" / "site-packages"
    (site / "bin").mkdir(parents=True)
    (site / "bin" / "vigia.exe").write_bytes(b"MZ\x00\x00" + ruta.encode() + b"\\python.exe\x00")
    dist = site / f"vigia-{bs.app_version()}.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(f"Name: vigia\nVersion: {bs.app_version()}\n", encoding="utf-8")
    (dist / "direct_url.json").write_text('{"url": "file:///' + ruta.replace("\\", "/") + '"}', encoding="utf-8")
    (dist / "RECORD").write_text(
        "vigia/__init__.py,sha256=x,1\n"
        f"vigia-{bs.app_version()}.dist-info/direct_url.json,sha256=x,1\n"
        "../../bin/vigia.exe,sha256=x,1\n",
        encoding="utf-8",
    )
    (site / "vigia").mkdir()
    (site / "vigia" / "__init__.py").write_text('"""vigia"""\n', encoding="utf-8")
    cache = site / "vigia" / "__pycache__"
    cache.mkdir()
    (cache / "__init__.cpython-313.pyc").write_bytes(b"\x00" + ruta.encode() + b"\\vigia\\__init__.py")
    (out_dir / "requirements.txt").write_text(
        "# This file was autogenerated by uv via the following command:\n"
        f"#    uv export --format requirements-txt -o {ruta}\\requirements.txt\n"
        "numpy==2.3.0 \\\n    --hash=sha256:aa\n",
        encoding="utf-8",
    )
    (out_dir / "Vigia.cmd").write_text("@echo off\n", encoding="utf-8")


def _con_ruta(out_dir: Path, ruta: str) -> list[str]:
    encontrados = []
    for p in out_dir.rglob("*"):
        if p.is_file() and ruta.lower().encode() in p.read_bytes().lower():
            encontrados.append(p.relative_to(out_dir).as_posix())
    return encontrados


def test_paquete_limpio_no_lleva_la_ruta_de_la_maquina(tmp_path):
    out_dir = tmp_path / f"vigia-{bs.app_version()}-win64"
    ruta = str(tmp_path)
    _paquete_de_prueba(out_dir, ruta)
    assert _con_ruta(out_dir, ruta), "el paquete de prueba debe llevar la ruta antes de limpiar"
    assert bs.buscar_rutas_en_paquete(out_dir, [tmp_path])

    quitado = bs.limpiar_paquete(out_dir, [tmp_path])

    assert quitado
    assert _con_ruta(out_dir, ruta) == []
    assert bs.buscar_rutas_en_paquete(out_dir, [tmp_path]) == []
    site = out_dir / "runtime" / "python" / "Lib" / "site-packages"
    assert not (site / "bin").exists()
    assert not (site / f"vigia-{bs.app_version()}.dist-info" / "direct_url.json").exists()
    assert not list(out_dir.rglob("__pycache__"))
    # Lo que no lleva ruta se conserva.
    assert (site / "vigia" / "__init__.py").is_file()
    requirements = (out_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "numpy==2.3.0" in requirements and "--hash=sha256:aa" in requirements
    record = (site / f"vigia-{bs.app_version()}.dist-info" / "RECORD").read_text(encoding="utf-8")
    assert "direct_url.json" not in record and "bin/vigia.exe" not in record
    assert "vigia/__init__.py" in record


def test_la_busqueda_ve_la_ruta_con_otras_barras_y_mayusculas(tmp_path):
    out_dir = tmp_path / "paquete"
    out_dir.mkdir()
    ruta = str(tmp_path)
    (out_dir / "a.txt").write_text(ruta.replace("\\", "/").upper(), encoding="utf-8")
    assert bs.buscar_rutas_en_paquete(out_dir, [tmp_path]) == ["a.txt"]
    (out_dir / "a.txt").write_text("sin rutas", encoding="utf-8")
    assert bs.buscar_rutas_en_paquete(out_dir, [tmp_path]) == []


def test_zip_se_niega_si_el_paquete_lleva_la_ruta(tmp_path, capsys):
    out_dir = tmp_path / f"vigia-{bs.app_version()}-win64"
    _paquete_de_prueba(out_dir, str(out_dir))
    args = argparse.Namespace(out=str(out_dir), dist=str(tmp_path / "dist"), version="3.13.12")
    assert bs.cmd_zip(args) == 1
    assert "ruta de la máquina" in capsys.readouterr().err
    assert not (tmp_path / "dist").exists()


def test_measure_no_deja_bytecode(tmp_path, monkeypatch):
    out_dir = tmp_path / "paquete"
    python_exe = out_dir / "runtime" / "python" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_bytes(b"")
    capturado = {}

    class _Proc:
        stdout = None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    def _popen(cmd, **kwargs):
        capturado["env"] = kwargs["env"]
        return _Proc()

    monkeypatch.setattr(bs.subprocess, "Popen", _popen)
    monkeypatch.setattr(bs, "wait_for_health", lambda *_a, **_k: 10.0)
    monkeypatch.setattr(bs, "OUT_DIR", tmp_path / "out")
    args = argparse.Namespace(
        out=str(out_dir),
        port=8990,
        data_dir=str(tmp_path / "datos"),
        timeout=1.0,
        with_shap_label=True,
    )
    assert bs.cmd_measure(args) == 0
    assert capturado["env"]["PYTHONDONTWRITEBYTECODE"] == "1"


def test_uv_corre_sin_escribir_bytecode(monkeypatch):
    capturado = {}

    def _run(cmd, **kwargs):
        capturado["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(bs, "system_python", lambda: Path("python.exe"))
    monkeypatch.setattr(bs.subprocess, "run", _run)
    bs.run_uv(["--version"])
    assert capturado["env"]["PYTHONDONTWRITEBYTECODE"] == "1"


# --------------------------------------------------------------------------
# El README
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def readme() -> str:
    return (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_usa_uv_sync_locked(readme):
    assert "uv sync --locked --extra dev --extra shap" in readme
    assert "uv sync --extra dev" not in readme


def test_readme_dice_donde_va_el_sha256_y_la_carpeta_anidada(readme):
    assert "va junto al zip, no dentro de él" in readme
    assert f"vigia-{bs.app_version()}-win64\\" in readme
    assert "Get-FileHash" in readme


def test_readme_dice_donde_ver_la_carpeta_de_datos_y_el_fichero_exportado(readme):
    assert "**Ajustes**" in readme and "Carpeta de datos" in readme
    assert "carpeta de descargas" in readme


def test_readme_da_la_variable_de_tema_para_powershell_y_cmd(readme):
    assert '$env:VITE_TEMA="miguel"' in readme
    assert "`set VITE_TEMA=miguel`" in readme
    assert "\nset VITE_TEMA=miguel\n" not in readme
