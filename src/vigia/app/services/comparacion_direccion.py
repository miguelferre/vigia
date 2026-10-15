"""Regla de dirección de la comparación de versiones.

Funciones puras: sin base de datos. `comparacion_versiones` las llama fila a fila.
"""

from __future__ import annotations

from typing import Literal

# Por debajo de esta diferencia, sin intervalos, dos valores cuentan como iguales.
UMBRAL_IGUAL = 0.01

type Direccion = Literal["mejora", "empeora", "igual", "cambia"]

MOTIVO_PROPORCION_DE_CLASE = "una proporción de clase no mejora ni empeora"


def regla_del_umbral(low: float | None, high: float | None) -> str:
    """Texto de la regla que decide qué es mejor con estos umbrales."""
    if low is not None and high is not None:
        return "más cerca del centro del intervalo es mejor"
    if low is not None:
        return "más alto es mejor"
    return "más bajo es mejor"


def _puntuacion(valor: float, low: float | None, high: float | None) -> float:
    """Puntuación en la que más alto siempre es mejor, según el tipo de umbral."""
    if low is not None and high is not None:
        return -abs(valor - (low + high) / 2)
    if low is not None:
        return valor
    return -valor


def _intervalos_solapan(
    ia: tuple[float | None, float | None], ib: tuple[float | None, float | None]
) -> bool:
    if None in ia or None in ib:
        return False
    return ia[0] <= ib[1] and ib[0] <= ia[1]  # type: ignore[operator]


def _motivo_de_igualdad(
    va: float,
    vb: float,
    intervalo_a: tuple[float | None, float | None],
    intervalo_b: tuple[float | None, float | None],
    umbral_igual: float = UMBRAL_IGUAL,
) -> str | None:
    """Motivo por el que dos valores cuentan como iguales, o `None` si no lo son.
    `umbral_igual`: 0,01 salvo en las claves en la unidad de una regresión, donde
    es el 1 % de la desviación del valor real."""
    if _intervalos_solapan(intervalo_a, intervalo_b):
        return "intervalos solapados"
    sin_intervalo = None in intervalo_a or None in intervalo_b
    if sin_intervalo and abs(vb - va) < umbral_igual:
        return f"diferencia menor que {umbral_igual:.4g}".replace(".", ",")
    return None


def decidir_direccion(
    va: float,
    vb: float,
    *,
    low: float | None,
    high: float | None,
    intervalo_a: tuple[float | None, float | None] = (None, None),
    intervalo_b: tuple[float | None, float | None] = (None, None),
    umbral_igual: float = UMBRAL_IGUAL,
) -> tuple[Direccion, str]:
    """Dirección de `b` frente a `a` y el motivo con la regla aplicada.

    `igual` si los intervalos de los dos lados se solapan o, sin intervalo en
    alguno de los lados, si la diferencia es menor que `umbral_igual` (0,01, o el
    1 % de la desviación del valor real en las claves en la unidad de una
    regresión). Si no, la regla del umbral (solo mínimo, solo máximo o los dos).
    """
    motivo_igual = _motivo_de_igualdad(va, vb, intervalo_a, intervalo_b, umbral_igual)
    if motivo_igual is not None:
        return "igual", motivo_igual
    regla = regla_del_umbral(low, high)
    pa, pb = _puntuacion(va, low, high), _puntuacion(vb, low, high)
    if pb > pa:
        return "mejora", regla
    if pb < pa:
        return "empeora", regla
    return "igual", regla


def decidir_direccion_neutra(
    va: float,
    vb: float,
    *,
    intervalo_a: tuple[float | None, float | None] = (None, None),
    intervalo_b: tuple[float | None, float | None] = (None, None),
) -> tuple[Direccion, str]:
    """Dirección de una medida sin sentido de mejora (la proporción de una
    clase, `label_rate` y `prediction_rate` por clase). `igual` con la misma regla
    de igualdad de `decidir_direccion` (intervalos solapados o diferencia menor
    que 0,01); si no, `cambia`, nunca `mejora` ni `empeora`."""
    motivo_igual = _motivo_de_igualdad(va, vb, intervalo_a, intervalo_b)
    if motivo_igual is not None:
        return "igual", motivo_igual
    return "cambia", MOTIVO_PROPORCION_DE_CLASE
