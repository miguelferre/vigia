"""Tests de find_free_port, LockFile e import_with_retry."""

from __future__ import annotations

import socket
import time

import pytest

from vigia.app.preflight import (
    AppControlBlockedError,
    LockFile,
    _pid_is_alive,
    find_free_port,
    import_with_retry,
)


def test_find_free_port_evita_el_ocupado():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        occupied_port = busy.getsockname()[1]

        found = find_free_port(start=occupied_port, host="127.0.0.1")
        assert found != occupied_port
        assert found >= occupied_port


def test_lockfile_escribe_y_libera(data_dir):
    lock = LockFile(data_dir)
    lock.acquire(port=8765)
    lock_path = data_dir / "vigia.lock"
    assert lock_path.exists()
    import json

    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["port"] == 8765
    import os

    assert payload["pid"] == os.getpid()

    lock.release()
    assert not lock_path.exists()


def test_lockfile_obsoleto_se_sobreescribe(data_dir):
    lock_path = data_dir / "vigia.lock"
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path.write_text('{"pid": 999999999, "port": 1, "started_at": "x"}', encoding="utf-8")

    lock = LockFile(data_dir)
    assert lock.is_stale() is True
    lock.acquire(port=8765)
    import json

    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["port"] == 8765
    lock.release()


def test_import_with_retry_clasifica_bloqueo_de_politica_sin_reintento(monkeypatch):
    calls: list[str] = []

    def fake_import(name: str):
        calls.append(name)
        exc = OSError("bloqueado")
        exc.winerror = 4551
        raise exc

    monkeypatch.setattr("vigia.app.preflight.import_module", fake_import)

    with pytest.raises(AppControlBlockedError):
        import_with_retry(["modulo_bloqueado"], attempts=3, wait_s=0)

    assert calls == ["modulo_bloqueado"]  # sin reintento


def test_import_with_retry_reintenta_otros_errores(monkeypatch):
    calls: list[str] = []

    def fake_import(name: str):
        calls.append(name)
        raise ImportError("escaneo asincrono en curso")

    monkeypatch.setattr("vigia.app.preflight.import_module", fake_import)
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    with pytest.raises(ImportError):
        import_with_retry(["modulo_escaneado"], attempts=3, wait_s=0)

    assert calls == ["modulo_escaneado"] * 3


def test_lockfile_guarda_token_para_apagado_externo(data_dir):
    lock = LockFile(data_dir)
    lock.acquire(8765, token="tok-123")
    data = lock.read()
    assert data["token"] == "tok-123"
    assert data["port"] == 8765
    lock.release()
    assert lock.read() is None


def test_pid_de_otro_proceso_vivo_no_se_toma_por_obsoleto(tmp_path):
    """Un proceso que no desciende de este no debe contarse como muerto.

    `os.kill(pid, 0)` falla en Windows con `WinError 87` para un proceso ajeno
    aunque esté vivo: con eso, `is_stale()` daba «obsoleto» con el servidor en
    marcha y `vigia shutdown` devolvía 1. El nieto de abajo es ajeno de verdad:
    lo lanza un proceso intermedio que termina antes de la comprobación.
    """
    import subprocess
    import sys

    codigo = (
        "import subprocess,sys;"
        "q=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],"
        "creationflags=getattr(subprocess,'DETACHED_PROCESS',0)"
        "|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0));"
        "print(q.pid)"
    )
    salida = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, check=False
    )
    ajeno = int(salida.stdout.strip())
    try:
        time.sleep(1.0)
        assert _pid_is_alive(ajeno) is True

        lock = LockFile(tmp_path)
        (tmp_path / "vigia.lock").write_text(
            f'{{"pid": {ajeno}, "port": 8765, "started_at": "x"}}', encoding="utf-8"
        )
        assert lock.is_stale() is False
    finally:
        subprocess.run(["taskkill", "/PID", str(ajeno), "/F"], capture_output=True, check=False)

    assert _pid_is_alive(999999999) is False
