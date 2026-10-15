"""Los lanzadores validan la carpeta de datos del argumento.

Cada test comprueba que `Vigia.cmd` y `Vigia-consola.cmd` rechazan una carpeta con
caracteres que `cmd` interpreta; ver `HUELLAS`. Las pruebas con `cmd /c` corren dentro
de `tmp_path`, sin paquete instalado: lo único que se ejecuta es el lanzador.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

HUELLAS = {
    "test_el_lanzador_no_pasa_el_argumento_sin_validar_a_set": "launcher-data-dir-argument",
    "test_el_lanzador_rechaza_una_carpeta_con_caracteres_de_cmd": "launcher-data-dir-argument",
    "test_el_lanzador_acepta_una_carpeta_normal": "launcher-data-dir-argument",
    "test_el_lanzador_sin_argumento_sigue_su_camino": "launcher-data-dir-argument",
}

BUILD = Path(__file__).resolve().parents[2] / "build"
PLANTILLAS = ["Vigia.cmd.template", "Vigia-consola.cmd.template"]
solo_windows = pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe solo existe en Windows")


@pytest.mark.parametrize("plantilla", PLANTILLAS)
def test_el_lanzador_no_pasa_el_argumento_sin_validar_a_set(plantilla):
    texto = (BUILD / plantilla).read_text(encoding="utf-8")
    assert 'set "VIGIA_HOME=%~1"' not in texto
    assert "validar_carpeta" in texto
    assert "DisableDelayedExpansion" in texto


def _lanzar(tmp_path: Path, plantilla: str, crudo: str) -> subprocess.CompletedProcess:
    """Copia la plantilla a `tmp_path` (con CRLF, como la escribe `build.py`) y la lanza."""
    texto = (BUILD / plantilla).read_text(encoding="utf-8")
    lanzador = tmp_path / "Vigia.cmd"
    lanzador.write_bytes(texto.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
    orden = f'cmd /d /c ""{lanzador}" {crudo}"'
    return subprocess.run(
        orden, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False
    )


@solo_windows
@pytest.mark.parametrize("plantilla", PLANTILLAS)
@pytest.mark.parametrize(
    "crudo",
    [
        '"datos&carpeta"',
        '"datos|carpeta"',
        '"datos^carpeta"',
        '"datos%carpeta"',
        '"datos<carpeta"',
        '"datos>carpeta"',
        '"da"tos"x"',
        'a" & b "c',
    ],
)
def test_el_lanzador_rechaza_una_carpeta_con_caracteres_de_cmd(tmp_path, plantilla, crudo):
    proceso = _lanzar(tmp_path, plantilla, crudo)
    assert proceso.returncode == 2, (proceso.stdout, proceso.stderr)
    assert "carpeta de datos" in proceso.stdout


@solo_windows
@pytest.mark.parametrize("plantilla", PLANTILLAS)
@pytest.mark.parametrize("crudo", ['"C:\\Datos de Vigia\\caso 1"', "C:\\datos\\vigia"])
def test_el_lanzador_acepta_una_carpeta_normal(tmp_path, plantilla, crudo):
    proceso = _lanzar(tmp_path, plantilla, crudo)
    # No hay runtime en tmp_path: llega a la comprobación del paquete (código 1), no al rechazo (2).
    assert proceso.returncode == 1, (proceso.stdout, proceso.stderr)
    assert "No se encuentra" in proceso.stdout


@solo_windows
@pytest.mark.parametrize("plantilla", PLANTILLAS)
def test_el_lanzador_sin_argumento_sigue_su_camino(tmp_path, plantilla):
    proceso = _lanzar(tmp_path, plantilla, "")
    assert proceso.returncode == 1
    assert "No se encuentra" in proceso.stdout
