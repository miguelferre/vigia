"""Datos sintéticos de regresión para los tests: un valor real
`y = 50 + 10 x + ruido`, una predicción con error y un recorte opcional en un
grupo protegido, y una variable. Sin ficheros."""
from __future__ import annotations

import numpy as np
import pandas as pd

from vigia.core.engine import History
from vigia.core.loaders import to_canonical
from vigia.core.schema import ColumnMapping, TaskSpec

RANGO_ALTO = [[55, None]]


def crudo(
    n: int = 400,
    *,
    seed: int = 0,
    recorte: float = 0.0,
    desplazamiento: float = 0.0,
    ruido: float = 4.0,
) -> pd.DataFrame:
    """Fichero crudo: predicción (`p`), valor real (`y`), grupo (`g`, `a` es el no
    privilegiado) y una variable (`x`). `recorte` resta a la predicción del grupo
    `a` (un sesgo negativo); `desplazamiento` suma a toda la predicción."""
    rng = np.random.default_rng(seed)
    g = rng.choice(["a", "b"], n)
    x = rng.normal(size=n)
    y = 50 + 10 * x + rng.normal(0, 3, n)
    p = y + rng.normal(0, ruido, n) - np.where(g == "a", recorte, 0.0) + desplazamiento
    return pd.DataFrame({"id": [f"r{seed}-{i}" for i in range(n)], "p": p, "y": y, "g": g, "x": x})


def mapeo(rangos=RANGO_ALTO, unidad: str | None = "horas") -> ColumnMapping:
    return ColumnMapping(
        prediction_col="p",
        label_col="y",
        id_col="id",
        protected_attr_col="g",
        protected_kind="categorical",
        unpriv_groups=["a"],
        priv_groups=["b"],
        feature_cols=["x"],
        target_unit=unidad,
        favorable_ranges=rangos,
    )


def tarea(rangos=RANGO_ALTO, unidad: str | None = "horas") -> TaskSpec:
    return TaskSpec.desde_mapeo("regression", mapeo(rangos, unidad))


def historia(
    lotes: list[pd.DataFrame], rangos=RANGO_ALTO, unidad: str | None = "horas"
) -> tuple[History, TaskSpec]:
    """Historia con `lotes` (el 0 es la línea base congelada) y la tarea."""
    m = mapeo(rangos, unidad)
    t = tarea(rangos, unidad)
    h = History()
    for i, df in enumerate(lotes):
        h.add_batch(to_canonical(df, m, task=t), mapping=m, model_version="v1", batch_seq=i)
    h.freeze_baseline(0, "v1")
    return h, t
