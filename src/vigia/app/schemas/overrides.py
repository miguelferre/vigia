"""Esquemas de overrides: vista de gestor agregada y vista propia."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class OverridesGroupRow(BaseModel):
    """Una fila de `GET /overrides?by=subgroup|phase`."""

    model_config = ConfigDict(extra="forbid")

    group: str
    n: int
    # `None` si la celda tiene menos de `min_n` decisiones (con su
    # `n`). `tasa` es el único nombre de esta tasa; `override_rate` se
    # retiró de la fila de grupo (los de `/overrides/me` y las cruzadas siguen).
    tasa: float | None
    p25: float | None
    median: float | None
    p75: float | None
    # solo en regresión, media de |cifra del profesional - cifra del modelo| en la
    # unidad del proyecto; `None` con menos de `min_n` filas con las dos cifras y en
    # clasificación. Informativa: sin umbral ni alerta.
    diferencia_media: float | None = None


class OverridesByGroupResponse(BaseModel):
    """Respuesta de `GET /overrides?by=subgroup|phase`."""

    model_config = ConfigDict(extra="forbid")

    by: str
    model_version_id: int
    n_total: int
    # Celda mínima: por debajo, la tasa de la celda va a `None` con su `n`.
    min_n: int
    groups: list[OverridesGroupRow]
    # por qué no hay datos (regresión sin rango favorable). Nulo en otro caso.
    motivo: str | None = None
    # unidad de `diferencia_media`; solo en regresión.
    unidad: str | None = None


class ClinicianDistribution(BaseModel):
    """Distribución del `override_rate` entre profesionales cualificados:
    nunca una fila por pseudónimo."""

    model_config = ConfigDict(extra="forbid")

    p25: float
    median: float
    p75: float
    bin_edges: list[float]
    bin_counts: list[int]


class OverridesByClinicianResponse(BaseModel):
    """Respuesta de `GET /overrides?by=clinician`: agregada, nunca nombra."""

    model_config = ConfigDict(extra="forbid")

    by: str
    model_version_id: int
    n_total: int
    n_clinicians: int
    n_qualified: int
    distribution: ClinicianDistribution | None
    motivo: str | None = None


class OverridesClinicianList(BaseModel):
    """Respuesta de `GET /overrides/clinicians`: fuente del selector de profesional."""

    model_config = ConfigDict(extra="forbid")

    clinicians: list[str]
    # en una regresión, por qué la lista va vacía.
    motivo: str | None = None


class OverridesMeWindowStats(BaseModel):
    """Tasa del propio profesional en una ventana."""

    model_config = ConfigDict(extra="forbid")

    n: int
    override_rate: float | None


class OverridesMeServiceStats(BaseModel):
    """Media y p25-p75 de todos los profesionales de la ventana."""

    model_config = ConfigDict(extra="forbid")

    n: int
    override_rate: float | None
    p25: float | None
    p75: float | None


class OverridesMeWindow(BaseModel):
    """Una ventana de calendario de `GET /overrides/me`."""

    model_config = ConfigDict(extra="forbid")

    start: str
    end: str
    mine: OverridesMeWindowStats
    service: OverridesMeServiceStats


class OverridesMeResponse(BaseModel):
    """Respuesta de `GET /overrides/me`: curvas propias frente al servicio."""

    model_config = ConfigDict(extra="forbid")

    clinician: str
    model_version_id: int
    n_windows: int
    windows: list[OverridesMeWindow]
    # en una regresión, por qué no hay ventanas.
    motivo: str | None = None


class OverridesCambiosCelda(BaseModel):
    """Una celda de la tabla de cambios: cuántas decisiones del profesional
    cayeron en `decision_profesional` ante la salida del modelo de su fila."""

    model_config = ConfigDict(extra="forbid")

    decision_profesional: str
    n: int
    # `n` de la celda entre `n` de la fila, en tanto por uno; `None` si la fila tiene menos
    # de `min_n` decisiones.
    tasa: float | None


class OverridesCambiosFila(BaseModel):
    """Una fila de la tabla de cambios: las decisiones con esa salida del modelo."""

    model_config = ConfigDict(extra="forbid")

    salida_modelo: str
    n: int
    # 1 menos la tasa de la diagonal (el profesional decidió otra cosa que el modelo); `None`
    # si la fila tiene menos de `min_n` decisiones.
    tasa_cambio: float | None
    celdas: list[OverridesCambiosCelda]


class OverridesCambiosResponse(BaseModel):
    """Respuesta de `GET /overrides/cambios`: salida del modelo frente a
    decisión del profesional, con recuentos, en los tres tipos de tarea."""

    model_config = ConfigDict(extra="forbid")

    model_version_id: int
    task_type: Literal["binary", "multiclass", "regression"]
    # Orden de las filas y de las celdas: tabla cuadrada.
    categorias: list[str]
    n_total: int
    # Filas del diario sin decisión del profesional o sin salida del modelo (en multiclase,
    # también las de una clase fuera de las declaradas): no entran en la tabla.
    n_sin_decision: int
    min_n: int
    filas: list[OverridesCambiosFila]
    # Solo regresión: la unidad y los intervalos del rango favorable.
    unidad: str | None = None
    rangos_favorables: list[tuple[float | None, float | None]] | None = None
    motivo: str | None = None
