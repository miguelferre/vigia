"""Calidad de regresión (E5).

Hermano de `quality_multiclase.py`: las métricas de una ventana ya filtrada a
filas con etiqueta y el bloque `details` para las pantallas de residuos y de
«predicho frente a real». Este módulo no importa `quality.py`: `quality.py` lo
importa.

El signo del sesgo es el de Evidently: `mean_error = media(predicción - real)`.
Un valor negativo es infraestimar.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    median_absolute_error,
)

from vigia.core.schema import (
    COL_LABEL_VALUE,
    COL_PREDICTION_VALUE,
    DatosNoValidos,
)

MOTIVO_R2_SIN_VARIANZA = "el valor real no varía en la ventana: R² no está definido"
MOTIVO_SIN_PARES = "ninguna fila de la ventana tiene a la vez valor real y predicción numéricos"
# Tolerancia relativa de «el valor real no varía»: un valor constante que no es
# exacto en coma flotante (3,3) deja un residuo de redondeo en la suma de
# cuadrados que, sin esta tolerancia, daría un R² de -1e30.
_TOL_VARIANZA_NULA = 1e-12


def varianza_nula(y: np.ndarray) -> bool:
    """`True` si el valor real no varía: el recorrido es cero o menor que
    `1e-12` veces el mayor valor absoluto. Un criterio compartido por la calidad
    y por la línea base para que decidan igual cuándo `r2` no está definido."""
    if y.size == 0:
        return True
    return bool(np.ptp(y) <= _TOL_VARIANZA_NULA * float(np.max(np.abs(y))))
N_CAJAS_HISTOGRAMA = 20
N_DECILES = 10


def exigir_columnas_valor(df: pd.DataFrame) -> None:
    """422 (`DatosNoValidos`) en español si a los datos de un proyecto de
    regresión les falta el valor de la predicción o de la etiqueta, en vez de
    un `KeyError` (500)."""
    faltan = [c for c in (COL_PREDICTION_VALUE, COL_LABEL_VALUE) if c not in df.columns]
    if faltan:
        raise DatosNoValidos(
            "a los datos del proyecto les falta el valor de la predicción o de la etiqueta "
            f"({', '.join(faltan)}): vuelve a subir el fichero con las columnas de predicción "
            "y de etiqueta del mapeo"
        )


def _desviacion(x: np.ndarray) -> float:
    return float(np.std(x, ddof=1)) if len(x) > 1 else 0.0


def residuos_de(df_labeled: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(real, predicho, residuo)` de las filas con ambos valores finitos;
    residuo = predicho - real."""
    exigir_columnas_valor(df_labeled)
    y = df_labeled[COL_LABEL_VALUE].to_numpy(dtype=float)
    yhat = df_labeled[COL_PREDICTION_VALUE].to_numpy(dtype=float)
    valida = np.isfinite(y) & np.isfinite(yhat)
    y, yhat = y[valida], yhat[valida]
    return y, yhat, yhat - y


def metricas_regresion(df_labeled: pd.DataFrame) -> dict[str, Any]:
    """Métricas de calidad de una ventana con etiqueta. Claves:
    `n`, `mean_absolute_error`, `root_mean_squared_error`, `r2`, `mean_error`
    (sesgo medio), `mean_squared_error`, `median_absolute_error` y
    `motivo_r2` (texto si `r2` no está definido, `None` si lo está).

    `r2` es `None` con varianza nula del valor real, nunca `-inf`. Con
    ninguna fila, todas las métricas son `None`."""
    y, yhat, e = residuos_de(df_labeled)
    n = len(y)
    if n == 0:
        return {
            "n": 0,
            "mean_absolute_error": None,
            "root_mean_squared_error": None,
            "r2": None,
            "mean_error": None,
            "mean_squared_error": None,
            "median_absolute_error": None,
            "motivo_r2": MOTIVO_SIN_PARES,
        }
    mse = float(mean_squared_error(y, yhat))
    if varianza_nula(y):
        r2: float | None = None
        motivo_r2 = MOTIVO_R2_SIN_VARIANZA
    else:
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = float(1.0 - np.sum(e**2) / ss_tot)
        motivo_r2 = None
    return {
        "n": n,
        "mean_absolute_error": float(mean_absolute_error(y, yhat)),
        "root_mean_squared_error": float(math.sqrt(mse)),
        "r2": r2,
        "mean_error": float(e.mean()),
        "mean_squared_error": mse,
        "median_absolute_error": float(median_absolute_error(y, yhat)),
        "motivo_r2": motivo_r2,
    }


def _histograma(x: np.ndarray) -> dict[str, Any]:
    bordes = np.histogram_bin_edges(x, bins=N_CAJAS_HISTOGRAMA)
    cuentas, _ = np.histogram(x, bins=bordes)
    return {
        "bin_edges": [float(b) for b in bordes],
        "counts": [int(c) for c in cuentas],
    }


def pred_vs_real(y: np.ndarray, yhat: np.ndarray) -> list[dict[str, Any]]:
    """Por decil de la predicción, la media de la predicción, la media, el
    percentil 10 y el percentil 90 del valor real, y `n`. Los cortes repetidos
    (una predicción en escalones) se unen: salen menos de diez grupos."""
    if len(yhat) == 0:
        return []
    cortes = np.unique(np.quantile(yhat, np.linspace(0.0, 1.0, N_DECILES + 1)))
    if len(cortes) < 2:
        indice = np.zeros(len(yhat), dtype=int)
    else:
        indice = np.searchsorted(cortes[1:-1], yhat, side="right")
    filas: list[dict[str, Any]] = []
    for d in np.unique(indice):
        mascara = indice == d
        real = y[mascara]
        filas.append(
            {
                "decil": int(d) + 1,
                "pred_media": float(yhat[mascara].mean()),
                "real_media": float(real.mean()),
                "real_p10": float(np.quantile(real, 0.10)),
                "real_p90": float(np.quantile(real, 0.90)),
                "n": int(mascara.sum()),
            }
        )
    return filas


def detalles_regresion(df_labeled: pd.DataFrame, unidad: str | None) -> dict[str, Any]:
    """`details` de calidad en regresión: `residuos` (histograma de
    predicción menos real, 20 cajas), `pred_vs_real` (por decil de la predicción)
    y `etiqueta` (media, desviación e histograma del valor real)."""
    y, yhat, e = residuos_de(df_labeled)
    if len(y) == 0:
        return {"task_type": "regression", "unidad": unidad}
    return {
        "task_type": "regression",
        "unidad": unidad,
        "residuos": {
            **_histograma(e),
            "media": float(e.mean()),
            "desviacion": _desviacion(e),
            "n": len(e),
        },
        "pred_vs_real": pred_vs_real(y, yhat),
        "etiqueta": {
            "media": float(y.mean()),
            "desviacion": _desviacion(y),
            "histograma": _histograma(y),
        },
    }
