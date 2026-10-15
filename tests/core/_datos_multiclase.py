"""Datos sintéticos multiclase para los tests: un modelo de
`k` clases con ruido, un grupo protegido y dos variables. Sin ficheros."""
from __future__ import annotations

import numpy as np
import pandas as pd

from vigia.core.loaders import concat_history, to_canonical
from vigia.core.schema import ColumnMapping, TaskSpec

CLASES = ["alta", "media", "baja"]
COLS_PROB = ["p_alta", "p_media", "p_baja"]


def crudo(
    n: int = 600,
    *,
    seed: int = 0,
    clases: list[str] | None = None,
    fuerza: float = 2.0,
    pesos: list[float] | None = None,
    desplazar_a: int | None = None,
) -> pd.DataFrame:
    """Fichero crudo: predicción, etiqueta, una probabilidad por clase, dos
    variables y un grupo (0/1). `desplazar_a` empuja la predicción hacia esa
    clase (deriva de predicción sin tocar la etiqueta)."""
    clases = clases or CLASES
    k = len(clases)
    rng = np.random.default_rng(seed)
    p = np.asarray(pesos if pesos is not None else [1.0 / k] * k, dtype=float)
    p = p / p.sum()
    real = rng.choice(k, size=n, p=p)
    logits = rng.normal(0, 1, size=(n, k))
    logits[np.arange(n), real] += fuerza
    if desplazar_a is not None:
        logits[:, desplazar_a] += fuerza * 0.9
    e = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs = e / e.sum(axis=1, keepdims=True)
    pred = probs.argmax(axis=1)
    df = pd.DataFrame(
        {
            "id": [f"r{seed}-{i}" for i in range(n)],
            "pred": [clases[i] for i in pred],
            "real": [clases[i] for i in real],
            "edad": rng.normal(50, 12, size=n).round(1),
            "sexo": rng.choice(["F", "M"], size=n),
            "grupo": rng.integers(0, 2, size=n),
        }
    )
    for i, c in enumerate(clases):
        df[f"p_{c}"] = probs[:, i]
    return df


def mapeo(clases: list[str] | None = None, favorables=("alta",), **extra) -> ColumnMapping:
    clases = clases or CLASES
    base = {
        "prediction_col": "pred",
        "label_col": "real",
        "id_col": "id",
        "classes": list(clases),
        "probability_cols": [f"p_{c}" for c in clases],
        "favorable_label": list(favorables) if favorables is not None else None,
        "feature_cols": ["edad", "sexo"],
        "protected_attr_col": "grupo",
        "unpriv_groups": [[0, 0]],
        "priv_groups": [[1, 1]],
    }
    base.update(extra)
    return ColumnMapping(**base)


def tarea(clases: list[str] | None = None, favorables=("alta",)) -> TaskSpec:
    return TaskSpec(
        task_type="multiclass",
        classes=tuple(clases or CLASES),
        favorables=tuple(favorables or ()),
    )


def canonico(
    n: int = 600,
    *,
    seed: int = 0,
    batch: int = 0,
    seq_start: int = 0,
    favorables=("alta",),
    clases: list[str] | None = None,
    **kw,
) -> pd.DataFrame:
    m = mapeo(clases, favorables)
    t = tarea(clases, favorables)
    return to_canonical(
        crudo(n, seed=seed, clases=clases, **kw),
        m,
        batch_seq=batch,
        seq_start=seq_start,
        task=t,
    )


def historia(*frames: pd.DataFrame) -> pd.DataFrame:
    return concat_history(list(frames))
