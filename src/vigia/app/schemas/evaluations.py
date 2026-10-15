"""Esquemas de evaluaciones, medidas y series temporales."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["EvaluateBody"]


class EvaluateBody(BaseModel):
    """Cuerpo de `POST /batches/{id}/evaluate`."""

    trigger: str = "manual"
