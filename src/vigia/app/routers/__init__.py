"""Routers de la API de Vigía. `ALL_ROUTERS` fija el orden de registro.

El catch-all del SPA se monta después de todos ellos, en `main.create_app`.
"""

from __future__ import annotations

from vigia.app.routers import (
    alerts,
    content,
    cross,
    datasets,
    demo,
    dossiers,
    evaluations,
    events,
    explain,
    health,
    human,
    jobs,
    model_artifacts,
    monitors,
    outcomes,
    overrides,
    projects,
    risks,
    schema,
    settings,
    versiones,
)

__all__ = ["ALL_ROUTERS"]

ALL_ROUTERS = [
    health,
    settings,
    projects,
    versiones,
    datasets,
    monitors,
    evaluations,
    alerts,
    explain,
    model_artifacts,
    demo,
    human,
    overrides,
    outcomes,
    cross,
    dossiers,
    risks,
    events,
    jobs,
    content,
    schema,
]
