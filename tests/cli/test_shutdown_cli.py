"""Tests de `vigia shutdown`.

En vez de levantar `uvicorn` en un hilo, se hace
`monkeypatch` de `httpx.post`. Cubre los
tres códigos del contrato: `1` sin lock/obsoleto, `0` apagado aceptado, `2`
conexión fallida o rechazo del servidor.
"""

from __future__ import annotations

import httpx

from vigia.app.preflight import LockFile, prueba_valida
from vigia.cli import main


def test_shutdown_sin_lock_devuelve_1(tmp_path, capsys):
    codigo = main(["shutdown", "--data-dir", str(tmp_path)])

    assert codigo == 1
    assert "no hay Vigía en marcha" in capsys.readouterr().err


def test_shutdown_con_lock_obsoleto_devuelve_1(tmp_path, capsys):
    lock = LockFile(tmp_path)
    lock.acquire(port=1, token="tok")
    lock.release()
    # Lock obsoleto: PID inexistente escrito a mano.
    (tmp_path / "vigia.lock").write_text(
        '{"pid": 999999999, "port": 12345, "token": "tok"}', encoding="utf-8"
    )

    codigo = main(["shutdown", "--data-dir", str(tmp_path)])

    assert codigo == 1
    assert "no hay Vigía en marcha" in capsys.readouterr().err


def test_shutdown_ok_llama_a_post_shutdown_con_el_token_y_devuelve_0(tmp_path, monkeypatch, capsys):
    lock = LockFile(tmp_path)
    lock.acquire(port=8842, token="tok-bueno")

    capturado = {}

    def falso_post(url, headers=None, timeout=None, trust_env=True):
        capturado["url"] = url
        capturado["headers"] = headers
        capturado["trust_env"] = trust_env
        return httpx.Response(200, json={"status": "shutting_down"})

    monkeypatch.setattr(httpx, "post", falso_post)

    codigo = main(["shutdown", "--data-dir", str(tmp_path)])

    assert codigo == 0
    assert capturado["url"] == "http://127.0.0.1:8842/api/shutdown"
    # El token no viaja: va una prueba firmada con él sobre un reto nuevo.
    cabeceras = capturado["headers"]
    assert "X-Vigia-Token" not in cabeceras
    assert prueba_valida("tok-bueno", cabeceras["X-Vigia-Reto"], "apagado", cabeceras["X-Vigia-Prueba"])
    assert capturado["trust_env"] is False
    assert "apagado solicitado" in capsys.readouterr().out


def test_shutdown_token_incorrecto_devuelve_2(tmp_path, monkeypatch, capsys):
    lock = LockFile(tmp_path)
    lock.acquire(port=8842, token="tok-caducado")

    def falso_post(url, headers=None, timeout=None, trust_env=True):
        return httpx.Response(403, json={"detail": "Token de apagado inválido"})

    monkeypatch.setattr(httpx, "post", falso_post)

    codigo = main(["shutdown", "--data-dir", str(tmp_path)])

    assert codigo == 2
    assert "rechazado" in capsys.readouterr().err


def test_shutdown_servidor_caido_devuelve_2(tmp_path, monkeypatch, capsys):
    lock = LockFile(tmp_path)
    lock.acquire(port=8842, token="tok")

    def falso_post(url, headers=None, timeout=None, trust_env=True):
        raise httpx.ConnectError("conexión rechazada")

    monkeypatch.setattr(httpx, "post", falso_post)

    codigo = main(["shutdown", "--data-dir", str(tmp_path)])

    assert codigo == 2
    assert "no se pudo contactar" in capsys.readouterr().err
