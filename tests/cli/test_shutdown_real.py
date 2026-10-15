"""`vigia shutdown` contra un servidor real.

`test_shutdown_cli.py` cubre los cuatro códigos con `monkeypatch` de
`httpx.post` (decisión documentada en su cabecera); aquí se arranca un
`vigia serve` de verdad, mismo patrón de `subprocess.Popen` + espera de
salud que `build/demo_local.py:28-110`, para comprobar el código 2 (token
rechazado) contra la respuesta real del servidor, no una simulada, y de
paso el código 0 de un apagado real. Puerto 8807 propio y `--data-dir` en
el scratchpad de pytest (`tmp_path`); nunca el puerto del servidor habitual del usuario.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from vigia.cli import main

REPO = Path(__file__).resolve().parents[2]
PUERTO = 8807


def _salud(base: str, timeout_s: float = 60.0) -> bool:
    limite = time.monotonic() + timeout_s
    while time.monotonic() < limite:
        try:
            if httpx.get(f"{base}/api/health", timeout=1.0).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    return False


def _puerto_libre(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", puerto)) != 0


def test_shutdown_codigo_2_y_0_contra_servidor_real(tmp_path: Path):
    if not _puerto_libre(PUERTO):
        pytest.skip(f"puerto {PUERTO} ocupado, no se toca")

    data_dir = tmp_path / "vigia-datos"
    data_dir.mkdir()
    lock_path = data_dir / "vigia.lock"
    base = f"http://127.0.0.1:{PUERTO}"
    log = open(data_dir / "serve.log", "ab")  # noqa: SIM115

    proceso = subprocess.Popen(
        [sys.executable, "-m", "vigia", "serve", "--no-browser", "--port", str(PUERTO), "--data-dir", str(data_dir)],
        cwd=str(REPO),
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        assert _salud(base), f"el servidor real no respondió a tiempo; mira {log.name}"

        lock_real = json.loads(lock_path.read_text(encoding="utf-8"))
        assert lock_real["port"] == PUERTO
        assert lock_real.get("token"), "el servidor real debe escribir un token de apagado en el lock"

        # Código 2: mismo PID (no obsoleto), token que el servidor real rechaza.
        lock_path.write_text(
            json.dumps({**lock_real, "token": lock_real["token"] + "-no-es-este"}), encoding="utf-8"
        )
        assert main(["shutdown", "--data-dir", str(data_dir)]) == 2
        assert lock_path.exists(), "un rechazo no debe borrar el lock"

        # Código 0: con el token real, el mismo servidor sí se apaga.
        lock_path.write_text(json.dumps(lock_real), encoding="utf-8")
        assert main(["shutdown", "--data-dir", str(data_dir)]) == 0

        for _ in range(60):
            if not lock_path.exists():
                break
            time.sleep(0.5)
        assert not lock_path.exists(), "el servidor real no ha borrado su lock al apagarse"
    finally:
        log.close()
        if proceso.poll() is None:
            proceso.terminate()
            try:
                proceso.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proceso.kill()
