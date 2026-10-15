"""Esquemas del monitor cruzado: `GET /projects/{id}/cross/latest`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = ["CrossLatestOut", "CrossRuleOut"]


class CrossRuleOut(BaseModel):
    """Una regla (CX-1 a CX-6) tal como quedó en la última evaluación `cross`.

    `value` es el número que resume la regla: `z` de override en CX-1/CX-2/CX-6,
    `p` del chi-cuadrado en CX-5, `z` de rescate en CX-3 (el que decide si dispara). `group` es `None` en las reglas globales (CX-2 a CX-5).

    `motivo` es la frase que deja la señal (p. ej. «ningún profesional
    ha corregido al modelo en N decisiones») y `n` las decisiones de la ventana
    que la sostienen; `None` cuando el motor no los da.
    """

    model_config = ConfigDict(extra="forbid")

    rule: str
    group: str | None
    state: str
    value: float | None
    motivo: str | None
    n: int | None
    # Si `value` cruza el umbral de la regla en el sentido en que
    # alerta (CX-1 y CX-3 hacia abajo, CX-2 hacia arriba, CX-6 en las dos colas).
    # `None` en las reglas cuyo valor no es una desviación (CX-4, CX-5, la señal de
    # revisión humana) y cuando no hay valor.
    supera_umbral: bool | None = None


class CrossLatestOut(BaseModel):
    """Respuesta de `GET /projects/{id}/cross/latest`.

    Mismo patrón que `GET /projects/{id}/explanations/summary`: la tarjeta de
    cruzadas del cuadro lo consume en vez de `StatesByMonitor`, que es un estado
    por lote y `cross` no tiene lote (`Evaluation.batch_id=None`).
    """

    model_config = ConfigDict(extra="forbid")

    # Sin monitor cruzado o sin ninguna evaluación (proyecto sin diario
    # de uso) la respuesta es 200 con `estado="sin_datos"`, `evaluation_id`,
    # `model_version_id`, `evaluated_at` y `mode` a `None` y `rules` vacío.
    estado: Literal["con_datos", "sin_datos"]
    evaluation_id: int | None
    mode: str | None
    worst_state: str
    model_version_id: int | None
    evaluated_at: str | None
    rules: list[CrossRuleOut]
    calibration_until: str | None
    # Por qué no hay datos de capa humana (regresión sin rango favorable o
    # aún sin capa humana). Nulo en clasificación.
    motivo: str | None = None
