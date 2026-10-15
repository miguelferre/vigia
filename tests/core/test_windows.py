"""Tests de vigia.core.windows: última N y ventanas deslizantes."""
from __future__ import annotations

import pandas as pd

from vigia.core.schema import COL_BATCH, COL_SEQ, COL_VERSION
from vigia.core.windows import interval_windows, last_n, window_info_for


def test_last_n_evento_completo(evento_canonico):
    ventana, info = last_n(evento_canonico, 200)
    assert len(ventana) == 200
    assert info.complete is True
    assert info.n == 200


def test_last_n_con_menos_filas_de_las_pedidas(evento_canonico):
    ventana, info = last_n(evento_canonico.head(50), 200)
    assert len(ventana) == 50
    assert info.complete is False
    assert info.motivo is not None


def test_last_n_filtra_por_version(evento_canonico):
    otra_version = evento_canonico.copy()
    otra_version[COL_VERSION] = "v2"
    ventana, _ = last_n(otra_version, 100, model_version="v1")
    assert len(ventana) == 0


def test_interval_windows_evento_26_ventanas_offsets_0_a_250(evento_canonico):
    ventanas = interval_windows(evento_canonico, batch_seq=evento_canonico[COL_BATCH].iloc[0], n=200, step=10)
    assert len(ventanas) == 26
    assert len(ventanas[0]) == 200
    assert len(ventanas[-1]) == 200


def test_interval_windows_batch_pequeno_tira_de_historia(historia_baseline_evento):
    hist = historia_baseline_evento
    # batch de baseline (batch_seq=0) tiene 450 filas; pedimos ventanas de 500
    # (mas grandes que el propio batch) para forzar que tire de una "historia"
    # anterior vacia: no hay nada antes de baseline, debe devolver lista vacia.
    ventanas = interval_windows(hist, batch_seq=0, n=500, step=10)
    assert ventanas == []


def test_interval_windows_version_distinta_no_entra(evento_canonico):
    otra = evento_canonico.copy()
    otra[COL_VERSION] = "v2"
    ventanas = interval_windows(otra, batch_seq=otra[COL_BATCH].iloc[0], n=200, step=10, model_version="v1")
    assert ventanas == []


def test_interval_windows_historia_vacia():
    vacio = pd.DataFrame(columns=[COL_SEQ, COL_BATCH, COL_VERSION])
    assert interval_windows(vacio, batch_seq=1, n=200, step=10) == []


def test_interval_windows_respeta_max_windows(evento_canonico):
    ventanas = interval_windows(
        evento_canonico, batch_seq=evento_canonico[COL_BATCH].iloc[0], n=200, step=10, max_windows=5
    )
    assert len(ventanas) == 5


def test_window_info_for_batch_vacio():
    vacio = pd.DataFrame(columns=[COL_SEQ, COL_BATCH])
    info = window_info_for(vacio, kind="batch")
    assert info.n == 0
    assert info.start_seq is None
    assert info.batches == []
