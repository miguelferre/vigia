"""Tests en seco de build/build.py: solo funciones puras, sin red ni descarga.

Ejecutar con el venv del proyecto una vez exista .venv/SYNC_OK:
    .venv\\Scripts\\python.exe -m pytest tests/build -q
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BUILD_SCRIPT = REPO_ROOT / "build" / "build.py"


def _load_build_module():
    """Carga build/build.py como modulo aislado (nombre distinto del paquete 'build' de PyPI)."""
    spec = importlib.util.spec_from_file_location("vigia_build_script", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bs = _load_build_module()


# --------------------------------------------------------------------------
# patch_pth_content
# --------------------------------------------------------------------------


def test_patch_pth_adds_site_packages_sin_ruta_externa():
    original = "python313.zip\n.\n\n#import site\n"
    patched = bs.patch_pth_content(original)
    lines = patched.splitlines()
    assert r"Lib\site-packages" in lines
    assert r"..\app" not in lines
    assert "import site" in lines
    assert "#import site" not in lines


def test_patch_pth_idempotent():
    original = "python313.zip\n.\nLib\\site-packages\n..\\app\nimport site\n"
    once = bs.patch_pth_content(original)
    twice = bs.patch_pth_content(once)
    assert once == twice
    assert once.count(r"Lib\site-packages") == 1
    assert r"..\app" not in once


def test_patch_pth_preserves_other_lines():
    original = "python313.zip\n.\n#import site\n"
    patched = bs.patch_pth_content(original)
    assert "python313.zip" in patched
    assert patched.splitlines()[0] == "python313.zip"


# --------------------------------------------------------------------------
# uv_export_command
# --------------------------------------------------------------------------


def _extras(args):
    return [args[i + 1] for i, a in enumerate(args) if a == "--extra"]


def test_uv_export_command_sin_parquet_por_defecto():
    out = Path("build/out/vigia-0.9.0-win64/requirements.txt")
    args = bs.uv_export_command(out, with_shap=True)
    assert args[:2] == ["export", "--format"]
    assert "requirements-txt" in args
    assert "--no-dev" in args
    assert "--no-emit-project" in args
    assert "--no-editable" in args
    assert args[-2:] == ["-o", str(out)]
    # SHAP entra y Parquet no.
    assert _extras(args) == ["shap"]


def test_uv_export_command_sin_shap():
    out = Path("build/out/vigia-0.9.0-win64-sin-shap/requirements.txt")
    assert _extras(bs.uv_export_command(out, with_shap=False)) == []


def test_uv_export_command_con_parquet_lo_anade():
    out = Path("requirements.txt")
    assert _extras(bs.uv_export_command(out, with_shap=True, con_parquet=True)) == [
        "shap",
        "parquet",
    ]
    assert _extras(bs.uv_export_command(out, with_shap=False, con_parquet=True)) == ["parquet"]


def test_extras_del_paquete_nunca_incluye_parquet_sin_pedirlo():
    assert bs.extras_del_paquete(True, False) == ["shap"]
    assert "parquet" not in bs.extras_del_paquete(True, False)


def test_los_extras_que_nombra_build_existen_en_pyproject():
    import tomllib

    datos = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declarados = set(datos["project"]["optional-dependencies"])
    assert set(bs.extras_del_paquete(True, True)) <= declarados


# --------------------------------------------------------------------------
# uv_build_wheel_command / uv_pip_install_command
# --------------------------------------------------------------------------


def test_uv_build_wheel_command():
    project_dir = Path("C:/repo/vigia")
    out_dir = Path("build/wheels")
    args = bs.uv_build_wheel_command(project_dir, out_dir)
    assert args == ["build", "--wheel", "--out-dir", str(out_dir), str(project_dir)]


def test_uv_pip_install_command_lists_wheels_individually():
    args = bs.uv_pip_install_command(
        Path("out/runtime/python/python.exe"),
        Path("out/runtime/python/Lib/site-packages"),
        Path("out/requirements.txt"),
        [
            "build/wheels/vigia-0.9.0-py3-none-any.whl",
        ],
    )
    assert "--python" in args
    assert "--target" in args
    assert "-r" in args
    assert args[-1:] == ["build/wheels/vigia-0.9.0-py3-none-any.whl"]


# --------------------------------------------------------------------------
# out_dir_for / dist_zip_name / embed_zip_name / embed_url
# --------------------------------------------------------------------------


def test_out_dir_for_default():
    d = bs.out_dir_for("0.9.0", None)
    assert d.name == "vigia-0.9.0-win64"


def test_out_dir_for_override():
    d = bs.out_dir_for("0.9.0", "C:/custom/out")
    assert str(d) == str(Path("C:/custom/out"))


def test_dist_zip_name():
    assert bs.dist_zip_name(Path("build/out/vigia-0.9.0-win64")) == "vigia-0.9.0-win64.zip"


def test_un_solo_zip_sin_sufijo_shap():
    # El zip de siempre lleva SHAP y no lleva sufijo.
    assert bs.out_dir_for("0.9.0", None).name == "vigia-0.9.0-win64"
    assert bs.out_dir_for("0.9.0", None, with_shap=True).name == "vigia-0.9.0-win64"
    assert "-shap" not in bs.out_dir_for("0.9.0", None).name


def test_las_variantes_llevan_sufijo_propio():
    assert bs.out_dir_for("0.9.0", None, with_shap=False).name == "vigia-0.9.0-win64-sin-shap"
    assert (
        bs.out_dir_for("0.9.0", None, with_shap=True, con_parquet=True).name
        == "vigia-0.9.0-win64-con-parquet"
    )


def test_app_version_es_la_de_vigia():
    v = bs.app_version()
    assert v.count(".") == 2 and not v.startswith("3.13")


def test_embed_zip_name_and_url():
    assert bs.embed_zip_name("3.13.12") == "python-3.13.12-embed-amd64.zip"
    url = bs.embed_url("3.13.12")
    assert url == "https://www.python.org/ftp/python/3.13.12/python-3.13.12-embed-amd64.zip"


# --------------------------------------------------------------------------
# is_policy_block
# --------------------------------------------------------------------------


def test_is_policy_block_detects_4551():
    msg = "OSError: [WinError 4551] Una directiva de Control de aplicaciones bloqueó este archivo"
    assert bs.is_policy_block(msg) is True


def test_is_policy_block_ignores_unrelated_errors():
    msg = "ConnectionError: no se pudo conectar a pypi.org"
    assert bs.is_policy_block(msg) is False


# --------------------------------------------------------------------------
# measure: parseo del JSON, sin arrancar servidor real
# --------------------------------------------------------------------------


def test_measure_json_roundtrip(tmp_path):
    payload = {
        "paquete": str(tmp_path),
        "con_shap": False,
        "tamano_total_mb": 250.4,
        "top10_site_packages_mb": [{"name": "pandas", "mb": 40.0}],
        "arranque_ms": 1234.5,
        "arranque_ok": True,
    }
    p = tmp_path / "measure-sin-shap.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded["arranque_ok"] is True
    assert loaded["tamano_total_mb"] == 250.4


def test_top_site_packages_sorts_and_limits(tmp_path):
    site_packages = tmp_path / "site-packages"
    site_packages.mkdir()
    for name, size_kb in (("numpy", 500), ("pandas", 900), ("tiny", 1)):
        pkg = site_packages / name
        pkg.mkdir()
        (pkg / "data.bin").write_bytes(b"0" * (size_kb * 1024))
    (site_packages / "foo.dist-info").mkdir()

    top = bs.top_site_packages(site_packages, n=2)
    assert len(top) == 2
    assert top[0]["name"] == "pandas"
    assert top[1]["name"] == "numpy"
    assert all(entry["name"] != "foo.dist-info" for entry in top)


# --------------------------------------------------------------------------
# filter_local_requirements / instalacion en dos pasos
# --------------------------------------------------------------------------


def test_filter_local_requirements_descarta_rutas_locales():
    text = (
        "# generado por uv export\n"
        "anthropic==0.125.0 ; sys_platform == 'win32' \\\n"
        "    --hash=sha256:abc\n"
        '../proyecto-hermano ; sys_platform == "win32"  # via vigia\n'
        "-e ../otro\n"
        "C:\\ruta\\local\n"
        "numpy==2.5.3 ; sys_platform == 'win32'\n"
    )
    kept, dropped = bs.filter_local_requirements(text)
    assert "../proyecto-hermano" not in kept
    assert "-e ../otro" not in kept
    assert "C:\\ruta" not in kept
    assert "anthropic==0.125.0" in kept and "numpy==2.5.3" in kept
    assert "--hash=sha256:abc" in kept
    assert len(dropped) == 3


def test_uv_pip_install_command_wheels_sin_dependencias():
    args = bs.uv_pip_install_command(
        Path("py.exe"), Path("sp"), wheel_paths=["a.whl", "b.whl"], no_deps=True
    )
    assert "--no-deps" in args
    assert "-r" not in args
    assert args[-2:] == ["a.whl", "b.whl"]


def test_shap_por_defecto_y_no_shap():
    parser = bs.build_parser()
    assert parser.parse_args(["assemble"]).with_shap is True
    assert parser.parse_args(["assemble"]).con_parquet is False
    assert parser.parse_args(["assemble", "--con-parquet"]).con_parquet is True
    assert parser.parse_args(["assemble"]).sin_npm is False
    assert parser.parse_args(["assemble", "--sin-npm"]).sin_npm is True
    assert parser.parse_args(["assemble", "--no-shap"]).with_shap is False
    assert parser.parse_args(["all", "--no-shap"]).with_shap is False
    assert parser.parse_args(["all", "--with-shap"]).with_shap is True
