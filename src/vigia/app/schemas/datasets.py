"""Esquemas de subida, mapeo e ingesta de datos.

La subida es multipart (form `file`, `kind`, `role`, `name?`), sin cuerpo JSON:
no hay esquema pydantic para ella, se declara con `Form`/`File` en el router.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from vigia.app.schemas.common import MAX_MOTIVO, MAX_NOMBRE
from vigia.core.schema import ColumnMapping

__all__ = ["IngestBody", "MappingBody"]


class MappingBody(BaseModel):
    """Cuerpo de `PUT /datasets/{id}/mapping`: mapeo definitivo.

    `privacy_decisions` se acepta por compatibilidad y se ignora:
    Vigía no pseudonimiza, no hay decisiones de privacidad que fijar.
    """

    model_config = ConfigDict(extra="forbid")

    mapping: ColumnMapping
    privacy_decisions: dict[str, str] = Field(default_factory=dict)


class IngestBody(BaseModel):
    """Cuerpo de `POST /datasets/{id}/ingest`."""

    model_version_id: int | None = None
    phase_label: str | None = Field(default=None, max_length=MAX_NOMBRE)
    orden_manipulado: bool = False
    motivo_manipulacion: str | None = Field(default=None, max_length=MAX_MOTIVO)
    mode: str | None = None
    evaluate: bool = True
