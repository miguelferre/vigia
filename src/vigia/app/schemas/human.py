"""Esquemas de capa humana: diario de uso, alertas cruzadas y deskilling
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ComprobacionCodificacion",
    "DeskillingResponse",
    "DeskillingSignalOut",
    "DeskillingTrendsOut",
    "DeskillingWindowOut",
    "JobAccepted",
    "UsageLogUploadResponse",
    "ValorFavorable",
]

# Qué valor del fichero es la decisión favorable para la persona.
# `refer` es el valor por defecto ; con `no-refer` o `0`
# la subida recodifica `human_decision`, `model_output` y `ground_truth`.
type ValorFavorable = Literal["refer", "no-refer", "1", "0"]


class ComprobacionCodificacion(BaseModel):
    """Coherencia entre la tasa favorable del diario ya recodificado
    (`r`) y la de las predicciones de producción de la misma versión (`p`).
    Es un aviso, nunca un rechazo."""

    model_config = ConfigDict(extra="forbid")

    estado: Literal["coherente", "posible_inversion", "inconcluso"]
    r: float | None
    p: float | None
    n: int
    motivo: str | None = None


class UsageLogUploadResponse(BaseModel):
    """Respuesta de `POST /projects/{id}/usage-logs/upload`.

    La frase de la decisión favorable va en una sola línea
    sin cortar, a propósito, porque el test la busca byte a byte en
    /openapi.json; con triple comillas normales el ajuste de línea mete un
    "\\n" en medio de la frase y rompe la comparación.

    refer (o 1) es la decisión favorable para la persona afectada, en el mismo sentido que la etiqueta favorable del modelo.
    """

    dataset_id: int
    n_rows: int
        # Nulo en una regresión: el registro trae cifras y no se recodifica.
    valor_favorable: ValorFavorable | None = "refer"
    comprobacion_codificacion: ComprobacionCodificacion | None = None
    # Avisos que no rechazan la subida, p. ej. filas de fechas sin lote.
    avisos: list[str] = Field(default_factory=list)


class JobAccepted(BaseModel):
    """Trabajo encolado (o ya terminado si `Settings.jobs_inline`), forma mínima común."""

    id: int
    kind: str
    queue: str
    status: str
    progress: float
    message: str
    result: dict[str, Any] | None = None
    error: str | None = None


class DeskillingWindowOut(BaseModel):
    """Una ventana de `interaction_review.telemetry.WindowMetrics`."""

    model_config = ConfigDict(extra="forbid")

    start: str
    end: str
    n: int
    n_with_gt: int
    agreement_rate: float | None
    human_accuracy: float | None
    model_accuracy: float | None
    rescue_rate: float | None
    # `True` si la ventana tiene `n < min_n` y no aporta punto a
    # la pendiente. La ventana sigue en `windows`, con su `n`.
    excluida_de_pendiente: bool = False


class DeskillingTrendsOut(BaseModel):
    """`interaction_review.telemetry.Trends`: pendiente OLS por ventana."""

    model_config = ConfigDict(extra="forbid")

    agreement_slope: float | None
    human_accuracy_slope: float | None
    model_accuracy_slope: float | None
    rescue_slope: float | None


class DeskillingSignalOut(BaseModel):
    """`interaction_review.telemetry.DeskillingSignal` con `reason` en español
    (`deskilling_texto.motivo_es`). El núcleo sigue en inglés
    porque CX-4 lo lee."""

    model_config = ConfigDict(extra="forbid")

    fired: bool
    reason: str


class DeskillingResponse(BaseModel):
    """Respuesta de `GET /projects/{id}/deskilling`."""

    model_config = ConfigDict(extra="forbid")

    sin_datos: bool
    motivo: str | None
    model_version_id: int
    model_version_label: str
    clinician: str | None
    subgroup: str | None
    n_windows: int
    windows: list[DeskillingWindowOut]
    trends: DeskillingTrendsOut | None
    signal: DeskillingSignalOut | None
    summary_md: str | None
    min_n: int
    # Cuántas ventanas de `windows` salen de la pendiente por tener
    # menos de `min_n` decisiones.
    ventanas_excluidas: int = 0
    eps: float
    package_version: str
    # Filas de `usage_log` excluidas por fecha no ISO (defensa
    # en profundidad de `ir_adapter.records_from_db`; 0 en el camino normal,
    # porque `POST /usage-logs/upload` ya normaliza la fecha a ISO).
    filas_excluidas_fecha: int
