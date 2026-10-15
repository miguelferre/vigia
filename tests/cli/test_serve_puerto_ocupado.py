"""`vigia serve --port N` con el puerto ocupado avisa y sale con 1."""

from __future__ import annotations

import socket
import webbrowser

from vigia.cli import main


def test_puerto_ocupado_avisa_y_sale_con_1(monkeypatch, capsys, tmp_path):
    abierto: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: abierto.append(url))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ocupado:
        ocupado.bind(("127.0.0.1", 0))
        ocupado.listen(1)
        puerto = ocupado.getsockname()[1]

        codigo = main(["serve", "--port", str(puerto), "--data-dir", str(tmp_path)])

    err = capsys.readouterr().err
    assert codigo == 1
    assert f"el puerto {puerto} está ocupado: prueba con --port {puerto + 1}" in err
    assert abierto == []
    assert not list(tmp_path.iterdir())  # no llegó a crear candado ni datos
