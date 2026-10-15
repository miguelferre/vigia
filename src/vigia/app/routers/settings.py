"""Ajustes de la aplicación."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from vigia.app.db import get_session
from vigia.app.events import Actor, get_actor
from vigia.app.schemas import respuestas as resp
from vigia.app.schemas.settings import SettingsPatchBody
from vigia.app.services import settings as settings_service

router = APIRouter(tags=["ajustes"])


@router.get("/settings", response_model=resp.Settings)
def read_settings(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    reveal: bool = False,
) -> dict:
    """Ajustes actuales de la aplicación."""
    s = request.app.state.settings
    return settings_service.get_settings(
        session, port_default=s.port_start, data_dir=str(s.data_dir), reveal=reveal
    )


@router.patch("/settings", response_model=resp.Settings)
def patch_settings(
    body: SettingsPatchBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> dict:
    """Cambia uno o varios ajustes; exige `actor` y `motivo`."""
    s = request.app.state.settings
    actor_final = Actor(kind=actor.kind, id=body.actor, role=body.role or actor.role)
    return settings_service.patch_settings(
        session,
        actor=actor_final,
        motivo=body.motivo,
        values=body.values,
        port_default=s.port_start,
        data_dir=str(s.data_dir),
        bus=request.app.state.bus,
    )
