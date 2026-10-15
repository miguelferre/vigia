"""Selección de ventanas sobre el frame canónico: últimas N filas y
ventanas deslizantes dentro de un batch.
"""
from __future__ import annotations

import pandas as pd

from vigia.core.schema import COL_BATCH, COL_SEQ, COL_VERSION, WindowInfo


def _filtrar_version(df: pd.DataFrame, model_version: str | None) -> pd.DataFrame:
    if model_version is None:
        return df
    return df[df[COL_VERSION] == model_version]


def last_n(
    df: pd.DataFrame, n: int, *, model_version: str | None = None
) -> tuple[pd.DataFrame, WindowInfo]:
    filtrado = _filtrar_version(df, model_version).sort_values(COL_SEQ)
    ventana = filtrado.tail(n)
    completa = len(ventana) >= n
    motivo = None
    if not completa:
        motivo = f"solo hay {len(ventana)} filas disponibles, se pedían {n}"
    info = window_info_for(
        ventana,
        kind="ultimos_n",
        requested_n=n,
        model_version=model_version,
        complete=completa,
        motivo=motivo,
    )
    return ventana, info


def interval_windows(
    df_history: pd.DataFrame,
    batch_seq: int,
    n: int,
    step: int,
    *,
    model_version: str | None = None,
    max_windows: int = 200,
) -> list[pd.DataFrame]:
    historia = _filtrar_version(df_history, model_version).sort_values(COL_SEQ)
    batch = historia[historia[COL_BATCH] == batch_seq]
    if len(batch) == 0:
        return []

    ventanas: list[pd.DataFrame] = []
    if len(batch) >= n:
        offset = 0
        max_offset = len(batch) - n
        while offset <= max_offset and len(ventanas) < max_windows:
            ventanas.append(batch.iloc[offset : offset + n])
            offset += step
        return ventanas

    # el batch tiene menos de n filas: ventanas de tamano n que terminan
    # en cada posicion step del batch, tirando de historia anterior de la
    # misma version.
    for pos in range(0, len(batch), step):
        if len(ventanas) >= max_windows:
            break
        fin_seq = batch.iloc[pos][COL_SEQ]
        hasta_aqui = historia[historia[COL_SEQ] <= fin_seq]
        if len(hasta_aqui) >= n:
            ventanas.append(hasta_aqui.tail(n))
    return ventanas


def window_info_for(
    df_window: pd.DataFrame,
    *,
    kind: str,
    requested_n: int | None = None,
    model_version: str | None = None,
    complete: bool = True,
    motivo: str | None = None,
    interval_windows: int | None = None,
) -> WindowInfo:
    n = len(df_window)
    if n:
        start_seq = int(df_window[COL_SEQ].min())
        end_seq = int(df_window[COL_SEQ].max())
        batches = sorted(int(b) for b in df_window[COL_BATCH].unique())
    else:
        start_seq = None
        end_seq = None
        batches = []
    return WindowInfo(
        kind=kind,  # type: ignore[arg-type]
        n=n,
        requested_n=requested_n,
        start_seq=start_seq,
        end_seq=end_seq,
        batches=batches,
        model_version=model_version,
        complete=complete,
        motivo=motivo,
        interval_windows=interval_windows,
    )
