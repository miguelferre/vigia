"""El lock de arranque no se queda atascado con un PID reutilizado.

Cada test comprueba el control del lock; ver `HUELLAS`. Sin servidor: solo el fichero de lock.
"""

from __future__ import annotations

import json
import os
import sys
import time

import pytest

from vigia.app import preflight
from vigia.app.preflight import LockFile

HUELLAS = {
    "test_el_lock_guarda_la_hora_de_creacion_del_proceso": "stale-startup-lock",
    "test_un_pid_reutilizado_por_otro_proceso_deja_el_lock_obsoleto": "stale-startup-lock",
    "test_el_mismo_proceso_con_su_hora_no_deja_el_lock_obsoleto": "stale-startup-lock",
    "test_un_lock_viejo_sin_la_hora_sigue_funcionando": "stale-startup-lock",
    "test_un_pid_reutilizado_no_bloquea_el_arranque": "stale-startup-lock",
    "test_la_hora_del_proceso_propio_es_creible": "stale-startup-lock",
}


def _escribir_lock(data_dir, **campos):
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "vigia.lock").write_text(json.dumps(campos), encoding="utf-8")


def test_el_lock_guarda_la_hora_de_creacion_del_proceso(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "_process_start_time", lambda pid: 1234.5, raising=False)
    LockFile(tmp_path).acquire(port=8905)
    datos = json.loads((tmp_path / "vigia.lock").read_text(encoding="utf-8"))
    assert datos["process_started"] == 1234.5


def test_un_pid_reutilizado_por_otro_proceso_deja_el_lock_obsoleto(tmp_path, monkeypatch):
    # El PID del lock vive (es el de este proceso), pero el proceso actual con ese PID
    # se creó mucho después de la hora guardada: es otro proceso que reutilizó el PID.
    _escribir_lock(
        tmp_path, pid=os.getpid(), port=8905, started_at="x", process_started=1_000_000.0
    )
    monkeypatch.setattr(preflight, "_process_start_time", lambda pid: 1_005_000.0, raising=False)
    assert LockFile(tmp_path).is_stale() is True


def test_el_mismo_proceso_con_su_hora_no_deja_el_lock_obsoleto(tmp_path, monkeypatch):
    _escribir_lock(
        tmp_path, pid=os.getpid(), port=8905, started_at="x", process_started=1_000_000.0
    )
    monkeypatch.setattr(preflight, "_process_start_time", lambda pid: 1_000_000.4, raising=False)
    assert LockFile(tmp_path).is_stale() is False


def test_un_lock_viejo_sin_la_hora_sigue_funcionando(tmp_path, monkeypatch):
    _escribir_lock(tmp_path, pid=os.getpid(), port=8905, started_at="x")
    monkeypatch.setattr(preflight, "_process_start_time", lambda pid: 1_005_000.0, raising=False)
    assert LockFile(tmp_path).is_stale() is False
    _escribir_lock(tmp_path, pid=999_999_999, port=8905, started_at="x")
    assert LockFile(tmp_path).is_stale() is True


def test_un_pid_reutilizado_no_bloquea_el_arranque(tmp_path, monkeypatch):
    _escribir_lock(
        tmp_path, pid=os.getpid(), port=8905, started_at="x", process_started=1_000_000.0
    )
    monkeypatch.setattr(preflight, "_process_start_time", lambda pid: 1_005_000.0, raising=False)
    lock = LockFile(tmp_path)
    lock.acquire(port=8906)
    assert json.loads((tmp_path / "vigia.lock").read_text(encoding="utf-8"))["port"] == 8906
    lock.release()


@pytest.mark.skipif(
    sys.platform != "win32", reason="la hora de creación se lee con la API de Windows"
)
def test_la_hora_del_proceso_propio_es_creible():
    inicio = preflight._process_start_time(os.getpid())
    assert inicio is not None
    ahora = time.time()
    assert ahora - 7 * 24 * 3600 < inicio <= ahora + 2
