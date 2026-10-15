"""Esquemas de explicabilidad global y local."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = ["ExplainGlobalBody", "ExplainLocalBody"]


class ExplainGlobalBody(BaseModel):
    """Cuerpo de `POST /model-versions/{id}/explain/global`."""

    kind: Literal["permutation", "shap"] = "permutation"
    batch_id: int | None = None
    # clase a explicar en un proyecto multiclase. Sin ella, la
    # probabilidad del conjunto favorable (o, sin conjunto, la clase mayoritaria
    # de la línea base). Una clase fuera de las del proyecto da 422.
    clase: int | str | None = Field(default=None)


class ExplainLocalBody(BaseModel):
    """Cuerpo de `POST /model-versions/{id}/explain/local`."""

    batch_id: int
    row_seq: int
    # clase a explicar; sin ella, la clase predicha de la fila.
    clase: int | str | None = Field(default=None)
