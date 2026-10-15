"""Equidad de regresión (E1).

Dos partes que `fairness.py` combina:

- Las medidas de error por grupo, que se publican siempre: `mean_absolute_error` y `mean_error` de cada grupo (sin umbral) y
  sus tres comparaciones (`mean_absolute_error_difference`,
  `mean_absolute_error_ratio` y `mean_error_difference`, con umbral de la línea
  base). No privilegiado menos privilegiado; razón no privilegiado entre
  privilegiado; el sesgo conserva el signo (predicción menos real).
- La distribución de la predicción por grupo, para el violín.

El intervalo de las diferencias es el de Welch sobre la media de `|e|` y de
`e` en el método `lote`. Este módulo no importa `fairness.py`:
`fairness.py` lo importa.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sps

from vigia.core.quality_multiclase import MOTIVO_UMBRAL_PENDIENTE
from vigia.core.schema import (
    CLAVES_ERROR_POR_GRUPO,
    COL_GROUP,
    COL_LABEL_VALUE,
    COL_PREDICTION_VALUE,
    Measurement,
    MonitorThresholds,
    State,
)
from vigia.core.states import classify_point_with_motivo, classify_with_motivo, decimales_para

_CUANTILES = {"p5": 0.05, "p25": 0.25, "p50": 0.50, "p75": 0.75, "p95": 0.95}
_Z95 = 1.959963984540054
N_CAJAS = 20
GRUPOS = (("unpriv", 0), ("priv", 1))


def _motivo_grupo(n: int, n_otro: int, min_group: int) -> str:
    # Sin atributo protegido ningún grupo tiene filas.
    if n == 0 and n_otro == 0:
        return (
            "no hay atributo protegido configurado: defínelo en el modelo para vigilar la equidad"
        )
    return f"grupo insuficiente: n={n}, min_group={min_group}"


def _errores(g: pd.DataFrame) -> np.ndarray:
    """Residuos (predicho menos real) de las filas con los dos valores finitos."""
    y = g[COL_LABEL_VALUE].to_numpy(dtype=float)
    yhat = g[COL_PREDICTION_VALUE].to_numpy(dtype=float)
    valida = np.isfinite(y) & np.isfinite(yhat)
    return yhat[valida] - y[valida]


def _welch(a: np.ndarray, b: np.ndarray) -> tuple[float, float] | None:
    """Intervalo de Welch del 95 % de `media(a) - media(b)`. `None` si no se
    puede (algún grupo con menos de dos filas)."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    va, vb = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    se2 = va / na + vb / nb
    diferencia = float(a.mean() - b.mean())
    if se2 <= 0:
        return diferencia, diferencia
    se = math.sqrt(se2)
    gl_den = (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    gl = se2**2 / gl_den if gl_den > 0 else float("inf")
    t = float(sps.t.ppf(0.975, gl)) if math.isfinite(gl) else _Z95
    return diferencia - t * se, diferencia + t * se


def _intervalo_cociente(a: np.ndarray, b: np.ndarray) -> tuple[float, float] | None:
    """Intervalo del 95 % de `media(a) / media(b)` por el método delta en la
    escala logarítmica. `None` si alguna media no es positiva o falta una fila."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    ma, mb = float(a.mean()), float(b.mean())
    if ma <= 0 or mb <= 0:
        return None
    se = math.sqrt(
        float(np.var(a, ddof=1)) / (na * ma * ma) + float(np.var(b, ddof=1)) / (nb * mb * mb)
    )
    razon = ma / mb
    return razon * math.exp(-_Z95 * se), razon * math.exp(_Z95 * se)


def _medida_comparacion(
    clave: str,
    valor: float | None,
    intervalo: tuple[float, float] | None,
    thresholds: MonitorThresholds,
    *,
    interval_method: str,
    kind_label: str,
    n: int,
    motivo_nulo: str | None,
    n_filas_lote: int | None = None,
    min_filas_lote: int | None = None,
) -> Measurement:
    """Una comparación entre grupos. Sin umbral todavía, espera a la
    línea base: `sin_datos` con `umbral_pendiente` y el valor calculado en
    `extra`. Con umbral, el estado lo decide la regla del método."""
    low, high = thresholds.limits(clave)
    extra: dict[str, Any] = {"window": kind_label, "n": n}
    if valor is None:
        return Measurement(
            metric_key=clave,
            value=None,
            threshold_low=low,
            threshold_high=high,
            state=State.sin_datos,
            motivo=motivo_nulo,
            extra=extra,
        )
    if low is None and high is None:
        return Measurement(
            metric_key=clave,
            value=None,
            state=State.sin_datos,
            motivo=MOTIVO_UMBRAL_PENDIENTE,
            extra={**extra, "umbral_pendiente": True, "valor_calculado": valor},
        )
    if interval_method == "lote":
        estado, motivo = classify_point_with_motivo(
            valor,
            low,
            high,
            interval=intervalo,
            decimales=decimales_para(valor, low, high),
            n_filas_lote=n_filas_lote,
            min_filas_lote=min_filas_lote,
        )
    else:
        # Sin banda de aviso: el umbral de la línea base ya incluye su margen.
        estado, motivo = classify_with_motivo(
            valor, low, high, aviso_frac=0.0, decimales=decimales_para(valor, low, high)
        )
    return Measurement(
        metric_key=clave,
        value=valor,
        interval_low=intervalo[0] if intervalo else None,
        interval_high=intervalo[1] if intervalo else None,
        threshold_low=low,
        threshold_high=high,
        state=estado,
        motivo=motivo,
        extra=extra,
    )


def medidas_error_por_grupo(
    ventana_label: pd.DataFrame,
    *,
    thresholds: MonitorThresholds,
    min_group: int,
    interval_method: str,
    kind_label: str,
    n_filas_lote: int | None = None,
    min_filas_lote: int | None = None,
) -> tuple[list[Measurement], dict[str, Any]]:
    """Las medidas de error por grupo de una ventana con etiqueta, y el
    bloque `details.error_por_grupo`. Un grupo con menos de `min_group` filas con
    etiqueta da `sin_datos` con motivo, nunca una alerta.

    A2: en el método `lote`, `n_filas_lote` (filas del lote completo, no
    solo las con etiqueta) y `min_filas_lote` (`min_records`) activan el aviso de
    un lote pequeño en las comparaciones entre grupos."""
    errores: dict[str, np.ndarray] = {}
    for nombre, codigo in GRUPOS:
        g = ventana_label[ventana_label[COL_GROUP] == codigo] if len(ventana_label) else ventana_label
        errores[nombre] = _errores(g) if len(g) else np.array([], dtype=float)
    n = {k: len(v) for k, v in errores.items()}

    por_grupo: dict[str, dict[str, Any]] = {}
    for nombre, _codigo in GRUPOS:
        otro = "priv" if nombre == "unpriv" else "unpriv"
        e = errores[nombre]
        if n[nombre] >= min_group:
            por_grupo[nombre] = {
                "n": n[nombre],
                "mae": float(np.abs(e).mean()),
                "sesgo": float(e.mean()),
                "motivo": None,
            }
        else:
            por_grupo[nombre] = {
                "n": n[nombre],
                "mae": None,
                "sesgo": None,
                "motivo": _motivo_grupo(n[nombre], n[otro], min_group),
            }

    medidas: list[Measurement] = []
    for clave in CLAVES_ERROR_POR_GRUPO:
        campo = "mae" if clave == "mean_absolute_error" else "sesgo"
        for nombre, _codigo in GRUPOS:
            datos = por_grupo[nombre]
            valor = datos[campo]
            medidas.append(
                Measurement(
                    metric_key=clave,
                    value=valor,
                    state=State.ok if valor is not None else State.sin_datos,
                    group_code=nombre,
                    motivo=None if valor is not None else datos["motivo"],
                    extra={"window": kind_label, "n": datos["n"]},
                )
            )
    for nombre, _codigo in GRUPOS:
        medidas.append(
            Measurement(
                metric_key="n",
                value=float(n[nombre]),
                state=State.ok,
                group_code=nombre,
                extra={"window": kind_label},
            )
        )

    u, p = por_grupo["unpriv"], por_grupo["priv"]
    suficientes = u["mae"] is not None and p["mae"] is not None
    motivo_cmp = None if suficientes else "grupo insuficiente en alguno de los dos"
    lote = interval_method == "lote"
    abs_u, abs_p = np.abs(errores["unpriv"]), np.abs(errores["priv"])
    dif_mae = (u["mae"] - p["mae"]) if suficientes else None
    razon_mae: float | None = None
    motivo_razon = motivo_cmp
    if suficientes:
        if p["mae"] > 0:
            razon_mae = u["mae"] / p["mae"]
        else:
            motivo_razon = "el error del grupo de referencia es 0: la razón no está definida"
    dif_sesgo = (u["sesgo"] - p["sesgo"]) if suficientes else None
    n_total = n["unpriv"] + n["priv"]
    comparaciones = (
        (
            "mean_absolute_error_difference",
            dif_mae,
            _welch(abs_u, abs_p) if lote and suficientes else None,
            motivo_cmp,
        ),
        (
            "mean_absolute_error_ratio",
            razon_mae,
            _intervalo_cociente(abs_u, abs_p) if lote and suficientes else None,
            motivo_razon,
        ),
        (
            "mean_error_difference",
            dif_sesgo,
            _welch(errores["unpriv"], errores["priv"]) if lote and suficientes else None,
            motivo_cmp,
        ),
    )
    for clave, valor, intervalo, motivo in comparaciones:
        medidas.append(
            _medida_comparacion(
                clave,
                valor,
                intervalo,
                thresholds,
                interval_method=interval_method,
                kind_label=kind_label,
                n=n_total,
                motivo_nulo=motivo,
                n_filas_lote=n_filas_lote,
                min_filas_lote=min_filas_lote,
            )
        )
    detalle = {**por_grupo, "metodo_intervalo": "welch" if lote else None}
    return medidas, detalle


def prediccion_por_grupo(ventana: pd.DataFrame, *, min_group: int) -> dict[str, Any]:
    """Distribución de `prediction_value` por grupo para el violín:
    cuantiles, media, `n` e histograma con los mismos cortes en los dos grupos. Un
    grupo con menos de `min_group` filas lleva solo `n` y `motivo`."""
    valores: dict[str, np.ndarray] = {}
    for nombre, codigo in GRUPOS:
        g = ventana[ventana[COL_GROUP] == codigo] if len(ventana) else ventana
        v = g[COL_PREDICTION_VALUE].to_numpy(dtype=float) if len(g) else np.array([], dtype=float)
        valores[nombre] = v[np.isfinite(v)]
    suficientes = [v for v in valores.values() if len(v) >= min_group]
    bordes = (
        np.histogram_bin_edges(np.concatenate(suficientes), bins=N_CAJAS) if suficientes else None
    )
    salida: dict[str, Any] = {}
    for nombre, _codigo in GRUPOS:
        otro = "priv" if nombre == "unpriv" else "unpriv"
        v = valores[nombre]
        if len(v) < min_group or bordes is None:
            salida[nombre] = {
                "n": len(v),
                "motivo": _motivo_grupo(len(v), len(valores[otro]), min_group),
            }
            continue
        cuentas, _ = np.histogram(v, bins=bordes)
        salida[nombre] = {
            "cuantiles": {k: float(np.quantile(v, q)) for k, q in _CUANTILES.items()},
            "media": float(v.mean()),
            "n": len(v),
            "histograma": {
                "bin_edges": [float(b) for b in bordes],
                "counts": [int(c) for c in cuentas],
            },
        }
    return salida
