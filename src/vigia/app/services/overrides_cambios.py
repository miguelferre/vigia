"""Tabla de cambios entre la salida del modelo y la decisión del profesional.

`GET /projects/{id}/overrides/cambios`: una fila por salida del modelo y una celda por decisión
del profesional, con recuentos, en los tres tipos de tarea. Binario: `refer`/`no-refer`.
Multiclase: las clases declaradas. Regresión con rango: «dentro del rango» y «fuera del rango»
(los enteros del diario guardan la pertenencia). Regresión sin rango: tabla vacía con el
motivo de la capa humana sin rango. La fila con menos de `min_n` decisiones da sus tasas en `None` y conserva los
`n`. Lectura sin evento. Vive aparte de `overrides.py` por tamaño.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlmodel import Session, select

from vigia.app.models import Project, UsageLog
from vigia.app.services import tarea as tarea_service
from vigia.app.services.usage_log_clases import MENSAJE_SIN_CLASES
from vigia.core.schema import MOTIVO_CAPA_HUMANA_SIN_RANGO, clave_clase
from vigia.human.ir_adapter import MIN_N

__all__ = [
    "CATEGORIAS_BINARIO",
    "CATEGORIAS_REGRESION",
    "MOTIVO_SIN_FILAS",
    "overrides_cambios",
]

CATEGORIAS_BINARIO = ("refer", "no-refer")
CATEGORIAS_REGRESION = ("dentro del rango", "fuera del rango")
# Mismo texto que `overrides._by_clinician`.
MOTIVO_SIN_FILAS = "sin filas de diario para esta versión"

Par = tuple[str | None, str | None]


def _por_entero(valor: int | None, categorias: Sequence[str]) -> str | None:
    """El entero del diario (1 = favorable, 0 = no) como nombre de categoría."""
    if valor is None:
        return None
    return categorias[0] if int(valor) == 1 else categorias[1]


def _pares(filas: Sequence[UsageLog], tipo: str, categorias: Sequence[str]) -> list[Par]:
    """`(salida del modelo, decisión del profesional)` de cada fila, `None` donde falta."""
    match tipo:
        case "binary" | "regression":
            return [
                (_por_entero(f.model_output, categorias), _por_entero(f.human_decision, categorias))
                for f in filas
            ]
        case "multiclass":
            validas = set(categorias)
            # Una clase fuera de las declaradas no entra en la tabla (suma en `n_sin_decision`).
            return [
                (
                    f.model_class if f.model_class in validas else None,
                    f.human_class if f.human_class in validas else None,
                )
                for f in filas
            ]
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")


def _tabla(categorias: Sequence[str], pares: Sequence[Par], min_n: int) -> tuple[list[dict[str, Any]], int]:
    """Filas de la tabla cuadrada y cuántos pares no entran por falta de una de las dos mitades."""
    cuenta = {(s, d): 0 for s in categorias for d in categorias}
    sin_decision = 0
    for salida, decision in pares:
        if salida is None or decision is None:
            sin_decision += 1
            continue
        cuenta[(salida, decision)] += 1
    filas: list[dict[str, Any]] = []
    for salida in categorias:
        n = sum(cuenta[(salida, d)] for d in categorias)
        con_tasa = n >= min_n
        celdas = [
            {
                "decision_profesional": d,
                "n": cuenta[(salida, d)],
                "tasa": cuenta[(salida, d)] / n if con_tasa else None,
            }
            for d in categorias
        ]
        filas.append(
            {
                "salida_modelo": salida,
                "n": n,
                "tasa_cambio": 1 - cuenta[(salida, salida)] / n if con_tasa else None,
                "celdas": celdas,
            }
        )
    return filas, sin_decision


def overrides_cambios(
    session: Session, project: Project, model_version_id: int, *, min_n: int = MIN_N
) -> dict[str, Any]:
    """Respuesta de `GET /overrides/cambios` para la versión `model_version_id`."""
    tipo = project.task_type
    base: dict[str, Any] = {
        "model_version_id": model_version_id,
        "task_type": tipo,
        "min_n": min_n,
        "unidad": None,
        "rangos_favorables": None,
    }
    match tipo:
        case "binary":
            categorias: list[str] = list(CATEGORIAS_BINARIO)
            motivo_tabla = None
        case "multiclass":
            categorias = [clave_clase(c) for c in tarea_service.clases_del_proyecto(project) or []]
            motivo_tabla = None if categorias else MENSAJE_SIN_CLASES
        case "regression":
            rangos = tarea_service.rangos_capa_humana(project)
            base["unidad"] = project.target_unit
            base["rangos_favorables"] = [list(r) for r in rangos]
            categorias = list(CATEGORIAS_REGRESION) if rangos else []
            motivo_tabla = None if rangos else MOTIVO_CAPA_HUMANA_SIN_RANGO
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    if motivo_tabla is not None:
        return {**base, "categorias": [], "n_total": 0, "n_sin_decision": 0, "filas": [], "motivo": motivo_tabla}

    filas_diario = session.exec(
        select(UsageLog).where(
            UsageLog.project_id == project.id,
            UsageLog.model_version_id == model_version_id,
        )
    ).all()
    filas, sin_decision = _tabla(categorias, _pares(filas_diario, tipo, categorias), min_n)
    return {
        **base,
        "categorias": categorias,
        "n_total": len(filas_diario),
        "n_sin_decision": sin_decision,
        "filas": filas,
        "motivo": None if filas_diario else MOTIVO_SIN_FILAS,
    }
