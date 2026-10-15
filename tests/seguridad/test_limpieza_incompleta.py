"""El aviso de limpieza incompleta no repite
un fichero ni lo da con la ruta absoluta aunque `data_dir` llegue sin normalizar."""

from __future__ import annotations

from pathlib import Path

import pytest

from vigia.app.services import projects as svc

HUELLAS = {
    "test_la_limpieza_no_repite_un_fichero_con_ruta_sin_normalizar": "incomplete-cleanup-duplicates",
}


def test_la_limpieza_no_repite_un_fichero_con_ruta_sin_normalizar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un fichero que sigue en disco sale una sola vez y relativo a `data_dir`."""
    carpeta = tmp_path / "uploads" / "7"
    carpeta.mkdir(parents=True)
    fichero = carpeta / "datos.csv"
    fichero.write_text("a,b\n1,2\n", encoding="utf-8")
    monkeypatch.setattr(svc.shutil, "rmtree", lambda *a, **k: None)
    sin_normalizar = tmp_path / "otra" / ".." / "uploads" / "7" / "datos.csv"
    data_dir = tmp_path / "otra" / ".."
    quedan = svc._limpiar_ficheros(
        data_dir, 7, [], [], con_artefactos=False, ficheros_dataset=[str(sin_normalizar)]
    )
    assert quedan == ["uploads/7/datos.csv"]
