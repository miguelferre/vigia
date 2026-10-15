"""Matriz impacto x probabilidad de la gestión de riesgos.

Tabla explícita de 25 celdas, no una operación aritmética: Severo x Raro es
Medio con producto 5, Menor x Casi seguro también Medio con producto 10.
"""

from __future__ import annotations

__all__ = [
    "IMPACTO_LABELS",
    "MONITOR_LABELS",
    "NIVELES",
    "ORDEN_NIVEL",
    "PROBABILIDAD_LABELS",
    "PROPUESTA_POR_MONITOR",
    "nivel",
]

# Etiquetas de cada eje, de menor a mayor.
IMPACTO_LABELS: dict[int, str] = {
    1: "Insignificante",
    2: "Menor",
    3: "Moderado",
    4: "Mayor",
    5: "Severo",
}

PROBABILIDAD_LABELS: dict[int, str] = {
    1: "Raro",
    2: "Improbable",
    3: "Posible",
    4: "Probable",
    5: "Casi seguro",
}

# Nivel final por celda (impacto, probabilidad) -> bajo|medio|alto|critico.
NIVELES: dict[tuple[int, int], str] = {
    (5, 1): "medio", (5, 2): "alto", (5, 3): "alto", (5, 4): "critico", (5, 5): "critico",
    (4, 1): "bajo", (4, 2): "medio", (4, 3): "alto", (4, 4): "alto", (4, 5): "critico",
    (3, 1): "bajo", (3, 2): "medio", (3, 3): "medio", (3, 4): "alto", (3, 5): "alto",
    (2, 1): "bajo", (2, 2): "bajo", (2, 3): "bajo", (2, 4): "medio", (2, 5): "medio",
    (1, 1): "bajo", (1, 2): "bajo", (1, 3): "bajo", (1, 4): "bajo", (1, 5): "bajo",
}

# Orden de severidad de los cuatro niveles, para saber si un movimiento sube o baja.
ORDEN_NIVEL: dict[str, int] = {"bajo": 0, "medio": 1, "alto": 2, "critico": 3}

# Etiqueta en español de cada monitor (no importar `_ETIQUETA_MONITOR` de
# `events_titulos.py`: es privado a ese módulo).
MONITOR_LABELS: dict[str, str] = {
    "fairness": "equidad",
    "quality": "calidad",
    "drift": "deriva",
    "cross": "cruzadas",
}

# Propuesta de impacto/probabilidad por monitor y severidad de la alerta de
# origen (el backend la aplica al crear desde alerta). `explain` no abre alertas y no está en la tabla.
PROPUESTA_POR_MONITOR: dict[tuple[str, str], tuple[int, int]] = {
    ("fairness", "alta"): (5, 4),
    ("fairness", "media"): (4, 3),
    ("quality", "alta"): (4, 4),
    ("quality", "media"): (3, 3),
    ("drift", "alta"): (3, 4),
    ("drift", "media"): (2, 3),
    ("cross", "alta"): (4, 3),
    ("cross", "media"): (3, 2),
}


def nivel(impacto: int, probabilidad: int) -> str:
    """Nivel final de la celda (impacto, probabilidad), 1 a 5 cada eje.

    `ValueError` fuera de rango: nunca se calcula, se busca en la tabla.
    """
    clave = (impacto, probabilidad)
    if clave not in NIVELES:
        raise ValueError(
            f"impacto y probabilidad deben estar entre 1 y 5; se recibió {clave!r}"
        )
    return NIVELES[clave]
