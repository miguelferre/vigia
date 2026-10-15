"""Tests de la CLI: guardias que no arrancan nada."""

from __future__ import annotations

import pytest

from vigia.cli import LOOPBACK_HOSTS, main


def test_serve_rechaza_host_no_loopback(capsys):
    code = main(["serve", "--host", "0.0.0.0", "--no-browser"])
    assert code == 2
    assert "solo se admite" in capsys.readouterr().err


def test_loopback_hosts_son_127_y_localhost():
    # `::1` queda fuera; Vigía solo escucha en IPv4.
    assert LOOPBACK_HOSTS == {"127.0.0.1", "localhost"}


def test_export_y_eval_exigen_subcomando_y_argumentos():
    """`export` ya no es un stub: exige un subcomando (`events` u `openapi`),
    y `eval` sin sus argumentos obligatorios; ambos fallan con el código 2
    propio de argparse (`SystemExit`).
    """
    with pytest.raises(SystemExit) as exc_info:
        main(["export"])
    assert exc_info.value.code == 2

    with pytest.raises(SystemExit) as exc_info:
        main(["eval"])
    assert exc_info.value.code == 2


def test_redirect_streams_if_headless(tmp_path, monkeypatch):
    from vigia.cli import redirect_streams_if_headless

    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.stderr", None)
    log_path = redirect_streams_if_headless(tmp_path / "datos")
    import sys

    assert log_path == tmp_path / "datos" / "vigia.log"
    assert sys.stdout is not None and sys.stderr is not None
    print("hola desde pythonw")
    sys.stdout.flush()
    assert "hola desde pythonw" in log_path.read_text(encoding="utf-8")
    sys.stdout.close()


def test_redirect_streams_no_hace_nada_con_consola(tmp_path):
    from vigia.cli import redirect_streams_if_headless

    assert redirect_streams_if_headless(tmp_path / "datos") is None
    assert not (tmp_path / "datos" / "vigia.log").exists()
