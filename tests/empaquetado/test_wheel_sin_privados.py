"""El wheel de Vigía no lleva datos de pruebas, trabajo interno ni términos prohibidos.

Construye el wheel (`uv build --wheel`) y busca en cada nombre y en cada fichero los
términos de `build/publico/terminos-prohibidos.txt`, como subcadena y sin distinguir
mayúsculas. Ese fichero no se exporta al árbol público: allí el test de términos se
salta con su motivo. El resto (versión, carpetas internas, estética privada) corre
siempre que haya `uv`.
"""

from __future__ import annotations

import importlib.util
import shutil
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "build" / "build.py"
TERMINOS = REPO_ROOT / "build" / "publico" / "terminos-prohibidos.txt"
PRIVADOS = REPO_ROOT / "build" / "publico" / "privados.txt"

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv no está en el PATH")


def _cargar_build():
    spec = importlib.util.spec_from_file_location("vigia_build_script_wheel", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bs = _cargar_build()


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    destino = tmp_path_factory.mktemp("wheel")
    bs.run_uv(bs.uv_build_wheel_command(REPO_ROOT, destino))
    wheels = sorted(destino.glob("vigia-*.whl"))
    assert len(wheels) == 1, f"se esperaba un wheel y hay {wheels}"
    return wheels[0]


@pytest.fixture(scope="module")
def contenido(wheel) -> dict[str, str]:
    """Nombre -> texto en minúsculas de cada fichero del wheel.

    De `RECORD` solo cuentan las rutas: sus huellas base64 forman subcadenas al azar
    (una huella casaba por azar con un término prohibido de tres letras).
    """
    with zipfile.ZipFile(wheel) as zf:
        salida = {
            n: zf.read(n).decode("utf-8", errors="replace").lower()
            for n in zf.namelist()
            if not n.endswith("/")
        }
    for n in [n for n in salida if n.endswith(".dist-info/RECORD")]:
        salida[n] = "\n".join(linea.split(",")[0] for linea in salida[n].splitlines())
    return salida


def _terminos() -> list[str]:
    return [
        linea.strip()
        for linea in TERMINOS.read_text(encoding="utf-8").splitlines()
        if linea.strip() and not linea.lstrip().startswith("#")
    ]


def test_el_wheel_lleva_la_version_de_vigia(wheel):
    import vigia

    assert wheel.name.startswith(f"vigia-{vigia.__version__}-")
    assert vigia.__version__ == bs.app_version()  # una sola fuente


def test_el_wheel_solo_lleva_el_paquete_y_sus_metadatos(contenido):
    raices = {n.split("/")[0] for n in contenido}
    assert raices == {"vigia", f"vigia-{bs.app_version()}.dist-info"}


@pytest.mark.parametrize("prohibido", ["_wip", "vigia-" + "pruebas", "docs/", "research/", "casos/"])
def test_el_wheel_no_lleva_trabajo_interno_ni_datos_de_pruebas(contenido, prohibido):
    # `docs/` solo como carpeta propia: `vigia/data/demo` y `vigia/content` sí viajan.
    assert not [n for n in contenido if prohibido in n.lower().split("dist-info")[0]], prohibido


def test_el_wheel_no_lleva_la_estetica_privada(wheel):
    if not PRIVADOS.is_file():
        pytest.skip("build/publico/privados.txt no está (árbol público): no hay lista que comprobar")
    assert bs.comprobar_wheel_sin_privados(wheel) == []


def test_el_wheel_no_contiene_terminos_prohibidos(contenido):
    if not TERMINOS.is_file():
        pytest.skip(
            "build/publico/terminos-prohibidos.txt no está (el árbol público no exporta "
            "build/publico/): la lista de términos solo vive en el árbol de trabajo"
        )
    hallazgos = []
    for termino in _terminos():
        t = termino.lower()
        hallazgos += [f"{n}: {termino}" for n, texto in contenido.items() if t in texto or t in n.lower()]
    assert hallazgos == []


# --------------------------------------------------------------------------
# funciones puras: la comprobación de rutas privadas
# --------------------------------------------------------------------------


def test_rutas_privadas_en_wheel_encuentra_solo_las_de_src():
    privados = (
        "# comentario\n"
        "frontend/src/themes/tokens-x.css\n"
        "src/vigia/app/services/temas_privados.py\n"
        "src/vigia/otra/cosa.py\n"
        "\n"
    )
    nombres = ["vigia/app/services/temas_privados.py", "vigia/app/main.py"]
    assert bs.rutas_privadas_en_wheel(nombres, privados) == [
        "src/vigia/app/services/temas_privados.py"
    ]
    assert bs.rutas_privadas_en_wheel(["vigia/app/main.py"], privados) == []


def test_rutas_privadas_acepta_barras_invertidas():
    assert bs.rutas_privadas_en_wheel(
        ["vigia\\app\\x.py"], "src\\vigia\\app\\x.py\n"
    ) == ["src/vigia/app/x.py"]


def test_sin_lista_de_privados_no_hay_nada_que_comprobar(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "PRIVADOS_FILE", tmp_path / "no-existe.txt")
    assert bs.comprobar_wheel_sin_privados(tmp_path / "x.whl") == []
