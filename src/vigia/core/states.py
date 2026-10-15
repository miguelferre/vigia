"""Clasificación de un valor frente a sus umbrales y su intervalo de
ventanas deslizantes (si el intervalo cruza un umbral, el estado es
`inestable`, con prioridad sobre `alerta`).
"""
from __future__ import annotations

import math

from vigia.core.schema import State


def _decimales_de(umbral: float) -> int:
    """Decimales significativos de `umbral`, acotados a [2, 3].

    `20.0` (sin parte decimal significativa) usa el mínimo, dos; un umbral con
    más de tres decimales se trunca a tres. El separador sigue siendo el punto:
    el frontend ya lo localiza a coma.
    """
    texto = repr(float(umbral))
    parte_decimal = texto.split(".", 1)[1].rstrip("0") if "." in texto else ""
    return min(3, max(2, len(parte_decimal)))


def decimales_para(*numeros: float | None) -> int | None:
    """Decimales para dibujar un motivo de regresión cuando la unidad es
    pequeña (un MAE de 0,0004 con umbral 0,0003 no puede pintarse «0.000»).
    `None` (los decimales de siempre, `_decimales_de`) si el menor valor no nulo
    es 0,01 o más; si no, los que dejan tres cifras significativas, hasta 10."""
    absolutos = [abs(x) for x in numeros if x is not None and math.isfinite(x) and x != 0]
    if not absolutos or min(absolutos) >= 0.01:
        return None
    return min(10, math.ceil(-math.log10(min(absolutos))) + 2)


def classify_with_motivo(
    value: float | None,
    threshold_low: float | None,
    threshold_high: float | None,
    *,
    interval: tuple[float, float] | None = None,
    aviso_frac: float = 0.10,
    decimales: int | None = None,
) -> tuple[State, str | None]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return State.sin_datos, None

    if interval is not None:
        lo, hi = interval
        for umbral in (threshold_low, threshold_high):
            if umbral is not None and lo <= umbral <= hi:
                dec = decimales if decimales is not None else _decimales_de(umbral)
                return (
                    State.inestable,
                    (
                        f"el intervalo [{lo:.{dec}f}, {hi:.{dec}f}] "
                        f"cruza el umbral {umbral:.{dec}f}"
                    ),
                )

    # Mismo formato que el intervalo: los decimales los marca el umbral.
    def _txt(v: float, umbral: float) -> str:
        return f"{v:.{decimales if decimales is not None else _decimales_de(umbral)}f}"

    if threshold_low is not None and value < threshold_low:
        return State.alerta, (
            f"valor {_txt(value, threshold_low)} por debajo del umbral inferior {_txt(threshold_low, threshold_low)}"
        )
    if threshold_high is not None and value > threshold_high:
        return State.alerta, (
            f"valor {_txt(value, threshold_high)} por encima del umbral superior {_txt(threshold_high, threshold_high)}"
        )

    if threshold_low is not None and threshold_low != 0:
        banda = aviso_frac * abs(threshold_low)
        if value < threshold_low + banda:
            return State.aviso, (
                f"valor {_txt(value, threshold_low)} cerca del umbral inferior {_txt(threshold_low, threshold_low)}"
            )
    if threshold_high is not None and threshold_high != 0:
        banda = aviso_frac * abs(threshold_high)
        if value > threshold_high - banda:
            return State.aviso, (
                f"valor {_txt(value, threshold_high)} cerca del umbral superior {_txt(threshold_high, threshold_high)}"
            )

    return State.ok, None


def classify(
    value: float | None,
    threshold_low: float | None,
    threshold_high: float | None,
    *,
    interval: tuple[float, float] | None = None,
    aviso_frac: float = 0.10,
) -> State:
    estado, _ = classify_with_motivo(
        value, threshold_low, threshold_high, interval=interval, aviso_frac=aviso_frac
    )
    return estado


def classify_point_with_motivo(
    value: float | None,
    threshold_low: float | None,
    threshold_high: float | None,
    *,
    interval: tuple[float, float] | None = None,
    decimales: int | None = None,
    n_filas_lote: int | None = None,
    min_filas_lote: int | None = None,
) -> tuple[State, str | None]:
    """Regla de valor puntual del método `lote` de equidad (
    §3.2; distinta de `classify_with_motivo`, que es la de `ventanas` de
 y no cambia): manda el valor puntual, no el intervalo. `ok` si el
    valor puntual está del lado bueno del umbral; si lo cruza, `alerta`
    cuando todo el intervalo confirma el cruce (se queda del mismo lado) e
    `inestable` cuando el intervalo todavía toca el lado bueno. Sin
    intervalo (una métrica sin fórmula de Katz/Newcombe en `lote`), el
    cruce del valor puntual basta para `alerta`: no hay intervalo con el
    que distinguir inestabilidad.

    Si el lote completo tiene menos de `min_filas_lote`
    filas, el caso `inestable` da `aviso` (con motivo propio). Si falta
    cualquiera de los dos parámetros, no cambia nada. Todo el intervalo del
    lado malo sigue siendo `alerta`, también en un lote pequeño.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return State.sin_datos, None

    cruce: tuple[float, str] | None = None
    if threshold_low is not None and value < threshold_low:
        cruce = (threshold_low, "inferior")
    elif threshold_high is not None and value > threshold_high:
        cruce = (threshold_high, "superior")

    if cruce is None:
        return State.ok, None

    umbral, lado = cruce
    if decimales is None:
        decimales = _decimales_de(umbral)
    valor_txt = f"{value:.{decimales}f}"
    umbral_txt = f"{umbral:.{decimales}f}"

    if interval is None:
        return State.alerta, (
            f"valor {valor_txt} cruza el umbral {lado} {umbral_txt} (lote, sin intervalo)"
        )

    lo, hi = interval
    toca_lado_bueno = (lado == "inferior" and hi >= threshold_low) or (
        lado == "superior" and lo <= threshold_high
    )
    lo_txt, hi_txt = f"{lo:.{decimales}f}", f"{hi:.{decimales}f}"
    if toca_lado_bueno:
        if n_filas_lote is not None and min_filas_lote is not None and n_filas_lote < min_filas_lote:
            return State.aviso, (
                f"lote pequeño ({n_filas_lote} filas, menos de {min_filas_lote}): valor {valor_txt} "
                f"cruza el umbral {lado} {umbral_txt}, pero el intervalo [{lo_txt}, {hi_txt}] "
                "cruza al lado bueno"
            )
        return State.inestable, (
            f"valor {valor_txt} cruza el umbral {lado} {umbral_txt}, pero el intervalo "
            f"[{lo_txt}, {hi_txt}] todavía toca el lado bueno"
        )
    return State.alerta, (
        f"valor {valor_txt} cruza el umbral {lado} {umbral_txt} y todo el intervalo "
        f"[{lo_txt}, {hi_txt}] queda del mismo lado"
    )


def classify_point(
    value: float | None,
    threshold_low: float | None,
    threshold_high: float | None,
    *,
    interval: tuple[float, float] | None = None,
) -> State:
    estado, _ = classify_point_with_motivo(value, threshold_low, threshold_high, interval=interval)
    return estado
