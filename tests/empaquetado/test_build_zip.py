"""Tests en seco del zip: funciones puras de `build/build.py`.

Cubren la fuente única de versión, el LEEME, el estático,
TERCEROS, la huella y el manifiesto y la elección del Python del sistema y del
wheel. Sin red, sin uv y sin compilar nada.
"""

from __future__ import annotations

import importlib.util
import re
import tomllib
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "build" / "build.py"


def _cargar_build():
    spec = importlib.util.spec_from_file_location("vigia_build_script_zip", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bs = _cargar_build()


# --------------------------------------------------------------------------
# Una sola fuente de versión
# --------------------------------------------------------------------------


def test_la_version_sale_de_init_y_pyproject_la_lee_como_dinamica():
    datos = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in datos["project"]
    assert "version" in datos["project"]["dynamic"]
    assert datos["tool"]["hatch"]["version"]["path"] == "src/vigia/__init__.py"


def test_la_version_vale_1_0_0_en_todas_las_fuentes():
    import vigia

    assert vigia.__version__ == "1.0.0"
    assert bs.app_version() == vigia.__version__
    assert bs.out_dir_for(vigia.__version__, None).name == "vigia-1.0.0-win64"


def test_ningun_fichero_fija_la_version_vieja():
    viejo = "0.0" + ".1"
    for fichero in ("src/vigia/__init__.py", "pyproject.toml", "build/build.py"):
        texto = (REPO_ROOT / fichero).read_text(encoding="utf-8")
        assert not re.search(rf"(?<![\d.]){re.escape(viejo)}(?![\d.])", texto), fichero


def test_uv_lock_lleva_vigia_como_dinamica():
    texto = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    bloque = texto[texto.index('name = "vigia"') :].split("[[package]]")[0]
    assert "version =" not in bloque.split("source =")[0]


# --------------------------------------------------------------------------
# Python del sistema (sin ruta personal)
# --------------------------------------------------------------------------


def test_candidato_la_variable_de_entorno_manda():
    ruta = bs.candidate_system_python({bs.ENV_PYTHON_SISTEMA: r"D:\py313\python.exe"}, "X:/base")
    assert ruta == Path(r"D:\py313\python.exe")


def test_candidato_sin_variable_usa_el_prefijo_base():
    ruta = bs.candidate_system_python({}, "X:/base")
    assert ruta == Path("X:/base") / "python.exe"
    assert bs.candidate_system_python({bs.ENV_PYTHON_SISTEMA: "  "}, "X:/base") == ruta


def test_parse_python_version():
    assert bs.parse_python_version("3.13\n") == (3, 13)
    assert bs.parse_python_version("3.13.12") == (3, 13)
    assert bs.parse_python_version("Python 3.13") is None
    assert bs.parse_python_version("") is None


def test_validate_acepta_el_3_13():
    bs.validate_system_python(Path(r"C:\Python313\python.exe"), (3, 13))


@pytest.mark.parametrize("version", [(3, 12), (3, 14), (2, 7)])
def test_validate_rechaza_otra_version_con_mensaje_claro(version):
    with pytest.raises(bs.SystemPythonError) as exc:
        bs.validate_system_python(Path(r"C:\Python\python.exe"), version)
    mensaje = str(exc.value)
    assert "3.13" in mensaje and bs.ENV_PYTHON_SISTEMA in mensaje


def test_validate_rechaza_version_ilegible():
    with pytest.raises(bs.SystemPythonError):
        bs.validate_system_python(Path(r"C:\Python\python.exe"), None)


def test_validate_rechaza_los_interpretes_que_descarga_uv():
    ruta = Path(r"C:\Users\alguien\AppData\Roaming\uv\python\cpython-3.13.1\python.exe")
    assert bs.is_uv_managed(ruta)
    with pytest.raises(bs.SystemPythonError, match="uv"):
        bs.validate_system_python(ruta, (3, 13))
    assert not bs.is_uv_managed(Path(r"C:\Python313\python.exe"))


def test_system_python_falla_claro_si_la_ruta_no_existe(monkeypatch, tmp_path):
    monkeypatch.setattr(bs, "_SYSTEM_PYTHON_CACHE", None)
    monkeypatch.setenv(bs.ENV_PYTHON_SISTEMA, str(tmp_path / "no-existe" / "python.exe"))
    with pytest.raises(bs.SystemPythonError, match="No existe"):
        bs.system_python()


def test_system_python_resuelve_el_3_13_del_sistema_desde_el_venv(monkeypatch):
    # El venv del proyecto o el Python del sistema: en ambos casos `sys.base_prefix`
    # da el 3.13 que no está en un venv ni lo bajó uv.
    monkeypatch.setattr(bs, "_SYSTEM_PYTHON_CACHE", None)
    monkeypatch.delenv(bs.ENV_PYTHON_SISTEMA, raising=False)
    ruta = bs.system_python()
    assert ruta.is_file()
    assert ruta.parent == Path(__import__("sys").base_prefix)


# --------------------------------------------------------------------------
# wheel de Vigía: uno solo
# --------------------------------------------------------------------------


def test_select_vigia_wheel_acepta_uno_de_la_version():
    w = bs.select_vigia_wheel([Path("w/vigia-0.9.0-py3-none-any.whl")], "0.9.0")
    assert w.name == "vigia-0.9.0-py3-none-any.whl"


def test_select_vigia_wheel_rechaza_varios_o_ninguno():
    with pytest.raises(RuntimeError, match="un solo wheel"):
        bs.select_vigia_wheel([], "0.9.0")
    with pytest.raises(RuntimeError, match="interaction"):
        bs.select_vigia_wheel(
            [Path("vigia-0.9.0-py3-none-any.whl"), Path("interaction_review-0.1.0-py3-none-any.whl")],
            "0.9.0",
        )


def test_select_vigia_wheel_rechaza_una_version_vieja():
    with pytest.raises(RuntimeError, match="no es de vigia 0.9.0"):
        bs.select_vigia_wheel([Path("vigia-0.0.1-py3-none-any.whl")], "0.9.0")


def test_cada_paquete_tiene_su_carpeta_de_wheels():
    a = bs.wheels_dir_for(Path("build/out/vigia-0.9.0-win64"))
    b = bs.wheels_dir_for(Path("trabajo/x/out/vigia-0.9.0-win64-sin-shap"))
    assert a.parent == bs.WHEELS_DIR and a != b


# --------------------------------------------------------------------------
# El estático
# --------------------------------------------------------------------------

INDEX_OK = '<!doctype html><head><meta name="vigia-tema" content="miguel"></head>'


def test_tema_del_estatico_lee_la_marca_en_cualquier_orden():
    assert bs.tema_del_estatico(INDEX_OK) == "miguel"
    assert bs.tema_del_estatico('<meta content="todos" name="vigia-tema">') == "todos"
    assert bs.tema_del_estatico('<meta name="viewport" content="width=device-width">') is None
    assert bs.tema_del_estatico("<head></head>") is None


def test_estatico_valido_no_da_problemas():
    assert bs.verificar_estatico(INDEX_OK, 2000, 1000) == []
    assert bs.verificar_estatico(INDEX_OK, 1000, 1000) == []  # mismo segundo: no es más viejo


def test_estatico_que_falta():
    problemas = bs.verificar_estatico(None, None, 1000)
    assert len(problemas) == 1 and "index.html" in problemas[0]


def test_estatico_sin_la_marca_del_tema():
    problemas = bs.verificar_estatico("<head></head>", 2000, 1000)
    assert any("vigia-tema" in p for p in problemas)


def test_estatico_de_otro_tema():
    problemas = bs.verificar_estatico('<meta name="vigia-tema" content="todos">', 2000, 1000)
    assert any("'todos'" in p and "'miguel'" in p for p in problemas)


def test_estatico_mas_viejo_que_el_ultimo_commit_de_frontend():
    problemas = bs.verificar_estatico(INDEX_OK, 999, 1000)
    assert any("más viejo" in p for p in problemas)


def test_estatico_sin_git_no_comprueba_la_edad():
    assert bs.verificar_estatico(INDEX_OK, 1, None) == []


def test_comprobar_estatico_sobre_carpetas_sinteticas(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "ultimo_commit_frontend", lambda *a, **k: 1000)
    assert bs.comprobar_estatico(tmp_path)[0].startswith("falta")
    (tmp_path / "index.html").write_text(INDEX_OK, encoding="utf-8")
    assert bs.comprobar_estatico(tmp_path) == []  # mtime de ahora, mayor que 1000
    monkeypatch.setattr(bs, "ultimo_commit_frontend", lambda *a, **k: 4_000_000_000)
    assert any("más viejo" in p for p in bs.comprobar_estatico(tmp_path))


def test_preparar_estatico_sin_npm_falla_con_el_motivo(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "STATIC_DIR", tmp_path)
    monkeypatch.setattr(bs, "compile_frontend", lambda: pytest.fail("no debe compilar"))
    with pytest.raises(bs.EstaticoError, match="index.html"):
        bs.preparar_estatico(sin_npm=True)


def test_preparar_estatico_con_npm_compila_antes_de_comprobar(tmp_path, monkeypatch):
    llamadas: list[str] = []
    monkeypatch.setattr(bs, "STATIC_DIR", tmp_path)
    monkeypatch.setattr(bs, "ultimo_commit_frontend", lambda *a, **k: 1000)

    def compilar(*args, **kwargs):
        llamadas.append("npm")
        (tmp_path / "index.html").write_text(INDEX_OK, encoding="utf-8")

    monkeypatch.setattr(bs, "compile_frontend", compilar)
    bs.preparar_estatico(sin_npm=False)
    assert llamadas == ["npm"]


def test_npm_se_lanza_con_npm_cmd_en_windows():
    orden = bs.npm_command()
    assert orden[1:] == ["run", "build"]
    assert orden[0] == ("npm.cmd" if __import__("os").name == "nt" else "npm")


# --------------------------------------------------------------------------
# TERCEROS, huella y manifiesto
# --------------------------------------------------------------------------


def _meta(**campos) -> str:
    lineas = ["Metadata-Version: 2.4"]
    for clave, valor in campos.items():
        valores = valor if isinstance(valor, list) else [valor]
        lineas += [f"{clave.replace('_', '-')}: {v}" for v in valores]
    return "\n".join(lineas) + "\n\nDescripción larga\n"


def test_licencia_con_expresion_spdx():
    n, v, lic, fich = bs.licencia_de_metadatos(
        _meta(Name="numpy", Version="2.5.3", License_Expression="BSD-3-Clause AND 0BSD",
              License_File=["LICENSE.txt", "libdivide/LICENSE.txt"])
    )
    assert (n, v, lic) == ("numpy", "2.5.3", "BSD-3-Clause AND 0BSD")
    assert fich == ["LICENSE.txt", "libdivide/LICENSE.txt"]


def test_licencia_corta_en_el_campo_license():
    _, _, lic, _ = bs.licencia_de_metadatos(_meta(Name="six", Version="1.17.0", License="MIT"))
    assert lic == "MIT"


def test_licencia_larga_cae_a_los_clasificadores():
    texto = (
        "Metadata-Version: 2.1\nName: scipy\nVersion: 1.18.1\n"
        "License: Copyright (c) 2001-2002 Enthought, Inc.\n 2003, SciPy Developers.\n"
        " All rights reserved.\n"
        "Classifier: License :: OSI Approved :: BSD License\n\nx\n"
    )
    _, _, lic, _ = bs.licencia_de_metadatos(texto)
    assert lic == "BSD License"


def test_licencia_solo_texto_largo_se_cita_sin_inventar():
    texto = "Name: x\nVersion: 1\nLicense: " + "Licencia propia " * 20 + "\n\n"
    _, _, lic, _ = bs.licencia_de_metadatos(texto)
    assert lic.startswith("texto de licencia en los metadatos, empieza: «Licencia propia")


def test_licencia_no_declarada():
    _, _, lic, fich = bs.licencia_de_metadatos("Name: x\nVersion: 1\n\nsin licencia\n")
    assert lic == bs.NO_DECLARADA == "no declarada en los metadatos"
    assert fich == []


def test_leer_distribuciones_y_terceros(tmp_path):
    sp = tmp_path / "site-packages"
    for carpeta, meta, licencias in (
        ("six-1.17.0.dist-info", _meta(Name="six", Version="1.17.0", License="MIT"), None),
        ("raro-2.0.dist-info", _meta(Name="raro", Version="2.0"), ["LICENCIA"]),
        ("numpy-2.5.3.dist-info", _meta(Name="numpy", Version="2.5.3",
                                          License_Expression="BSD-3-Clause"), None),
    ):
        d = sp / carpeta
        d.mkdir(parents=True)
        (d / "METADATA").write_text(meta, encoding="utf-8")
        for lic in licencias or []:
            (d / "licenses").mkdir(exist_ok=True)
            (d / "licenses" / lic).write_text("texto", encoding="utf-8")
    (sp / "paquete").mkdir()  # una carpeta que no es dist-info no cuenta
    (sp / "x-1.whl").mkdir()

    dists = bs.leer_distribuciones(sp)
    assert [d["nombre"] for d in dists] == ["numpy", "raro", "six"]
    assert dists[1]["licencia"] == bs.NO_DECLARADA and dists[1]["ficheros"] == ["LICENCIA"]

    texto = bs.generar_terceros(dists, "3.13.12", "PSF LICENSE AGREEMENT\ntexto", "0.9.0")
    assert "Vigía 0.9.0" in texto
    assert "Distribuciones: 3. Sin licencia declarada: 1." in texto
    assert "numpy | 2.5.3 | BSD-3-Clause" in texto
    assert "raro | 2.0 | no declarada en los metadatos | LICENCIA" in texto
    assert "six | 1.17.0 | MIT | (ninguno nombrado)" in texto
    assert "Python embebido 3.13.12" in texto and "PSF LICENSE AGREEMENT" in texto


def test_terceros_sin_licencia_de_python_lo_dice():
    texto = bs.generar_terceros([], "3.13.12", None, "0.9.0")
    assert "no trae LICENSE.txt" in texto


def test_leer_distribuciones_en_carpeta_inexistente(tmp_path):
    assert bs.leer_distribuciones(tmp_path / "nada") == []


def test_sha256_y_manifiesto(tmp_path):
    z = tmp_path / "vigia-0.9.0-win64.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("vigia-0.9.0-win64/LEEME.txt", "hola")
        zf.writestr("vigia-0.9.0-win64/LICENSE", "MIT" * 10)
        zf.writestr("vigia-0.9.0-win64/docs/", "")
    entradas = bs.entradas_del_zip(z)
    assert entradas == [
        ("vigia-0.9.0-win64/LEEME.txt", 4),
        ("vigia-0.9.0-win64/LICENSE", 30),
    ]
    digest = bs.sha256_of(z)
    linea = bs.sha256_file_text(digest, z.name)
    assert linea == f"{digest} *vigia-0.9.0-win64.zip\n"

    texto = bs.manifiesto_texto(
        z.name, digest, entradas,
        [{"nombre": "numpy", "version": "2.5.3", "licencia": "x", "ficheros": []}],
        "0.9.0", "3.13.12",
    )
    assert "Vigía 0.9.0; Python embebido 3.13.12" in texto
    assert f"sha256 del zip: {digest}" in texto
    assert "Ficheros: 2; tamaño descomprimido: 34 bytes" in texto
    assert "numpy 2.5.3" in texto
    assert "vigia-0.9.0-win64/LICENSE; 30" in texto


# --------------------------------------------------------------------------
# LEEME y documentación dentro del paquete
# --------------------------------------------------------------------------


def test_leeme_separa_la_version_de_vigia_y_la_de_python():
    texto = bs.leeme_text("0.9.0", "3.13.12")
    assert texto.startswith("Vigía 0.9.0 - paquete para Windows")
    assert "Python embebido: 3.13.12" in texto
    assert "Vigía 3.13.12" not in texto  # el fallo de antes: la versión de Python como la de Vigía


def test_leeme_explica_el_apagado_y_la_clave_de_api():
    texto = bs.leeme_text("0.9.0", "3.13.12")
    assert "no tiene botón de apagado" in texto
    assert "runtime\\python\\python.exe -m vigia shutdown" in texto
    assert "Vigia-consola.cmd" in texto and "Ctrl+C" in texto
    assert "clave de API" in texto and "funciona entero" in texto


def test_el_apagado_del_leeme_existe_en_la_cli():
    cli = (REPO_ROOT / "src" / "vigia" / "cli.py").read_text(encoding="utf-8")
    assert 'sub.add_parser("shutdown"' in cli
    assert '"--data-dir"' in cli


def test_copiar_documentacion_copia_todo(tmp_path):
    repo, out = tmp_path / "repo", tmp_path / "out"
    (repo / "docs" / "manual" / "img").mkdir(parents=True)
    out.mkdir()
    for nombre in ("README.md", "SEGURIDAD.md", "LICENSE", "NOTICE"):
        (repo / nombre).write_text(nombre, encoding="utf-8")
    (repo / "docs" / "manual" / "uso.md").write_text("uso", encoding="utf-8")
    (repo / "docs" / "manual" / "img" / "cuadro.png").write_bytes(b"png")
    for rel in bs.DOCS_SUELTOS:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(rel, encoding="utf-8")
    copiados = bs.copiar_documentacion(repo, out)
    assert copiados == [
        "README.md", "SEGURIDAD.md", "LICENSE", "NOTICE", "docs/manual/", *bs.DOCS_SUELTOS
    ]
    for rel in bs.DOCS_SUELTOS:
        assert (out / rel).read_text(encoding="utf-8") == rel
    assert (out / "docs" / "manual" / "img" / "cuadro.png").read_bytes() == b"png"
    # Repetir no falla ni deja restos de una copia vieja.
    (out / "docs" / "manual" / "viejo.md").write_text("x", encoding="utf-8")
    bs.copiar_documentacion(repo, out)
    assert not (out / "docs" / "manual" / "viejo.md").exists()


@pytest.mark.parametrize("falta", ["README.md", "SEGURIDAD.md", "LICENSE", "NOTICE"])
def test_copiar_documentacion_falla_si_falta_un_fichero(tmp_path, falta):
    repo, out = tmp_path / "repo", tmp_path / "out"
    (repo / "docs" / "manual").mkdir(parents=True)
    out.mkdir()
    for nombre in ("README.md", "SEGURIDAD.md", "LICENSE", "NOTICE"):
        if nombre != falta:
            (repo / nombre).write_text(nombre, encoding="utf-8")
    with pytest.raises(FileNotFoundError, match=falta):
        bs.copiar_documentacion(repo, out)


def test_copiar_documentacion_falla_sin_manual(tmp_path):
    repo, out = tmp_path / "repo", tmp_path / "out"
    repo.mkdir()
    out.mkdir()
    for nombre in ("README.md", "SEGURIDAD.md", "LICENSE", "NOTICE"):
        (repo / nombre).write_text(nombre, encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="manual"):
        bs.copiar_documentacion(repo, out)


def test_el_repo_tiene_lo_que_el_paquete_copia():
    for nombre in bs.DOCS_EN_PAQUETE:
        assert (REPO_ROOT / nombre).is_file(), nombre
    assert (REPO_ROOT / "docs" / "manual").is_dir()


def test_vigia_version_da_la_de_init(capsys):
    import vigia
    from vigia.cli import _build_parser

    with pytest.raises(SystemExit) as salida:
        _build_parser().parse_args(["--version"])
    assert salida.value.code == 0
    assert vigia.__version__ in capsys.readouterr().out
