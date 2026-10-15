"""Esquemas de outcomes: resultado del sistema combinado por periodo."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["OutcomeRow", "OutcomeSeriePunto", "OutcomeUploadResponse", "OutcomesListResponse"]


class OutcomeUploadResponse(BaseModel):
    """Respuesta de `POST /projects/{id}/outcomes`."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: int | None = None
    n_rows: int
    n_creados: int
    n_actualizados: int


class OutcomeRow(BaseModel):
    """Una fila de la tabla de outcomes."""

    model_config = ConfigDict(extra="forbid")

    period: str
    metric_key: str
    value: float | None
    baseline: float | None
    target: float | None
    source: str


class OutcomeSeriePunto(BaseModel):
    """Un punto de la serie de una métrica, sin `metric_key` (ya agrupa por ella)."""

    model_config = ConfigDict(extra="forbid")

    period: str
    value: float | None
    baseline: float | None
    target: float | None


class OutcomesListResponse(BaseModel):
    """Respuesta de `GET /projects/{id}/outcomes`."""

    model_config = ConfigDict(extra="forbid")

    rows: list[OutcomeRow]
    series: dict[str, list[OutcomeSeriePunto]]
