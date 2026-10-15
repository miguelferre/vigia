"""Esquemas de diario de eventos."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from vigia.app.schemas.common import ActorBody


class AnotacionBody(ActorBody):
    """Cuerpo de `POST /events`: una anotación humana en el diario.

    `motivo` es el texto de la anotación (toda mutación humana exige actor
    y motivo); `project_id` la cuelga de un proyecto o, si es `None`, del
    sistema.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: int | None = None


class ExportacionBody(BaseModel):
    """Cuerpo de `POST /events/exportaciones`: lo que la
    persona acaba de exportar del diario, para dejar constancia en él. El actor
    sale de las cabeceras; no lleva motivo porque exportar no cambia datos."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["json", "html"]
    since: str | None = None
    until: str | None = None
    project_id: int | None = None
