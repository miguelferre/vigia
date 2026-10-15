"""Esquemas de ajustes de la aplicación."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from vigia.app.schemas.common import MAX_ACTOR, NombreActor, TextoMotivo, no_blanco

__all__ = ["SettingsOut", "SettingsPatchBody"]


class SettingsPatchBody(BaseModel):
    """Cuerpo del PATCH de ajustes: actor, motivo y el diccionario de valores a cambiar."""

    actor: NombreActor
    role: str | None = Field(default=None, max_length=MAX_ACTOR)
    motivo: TextoMotivo
    values: dict[str, Any] = Field(min_length=1)

    _actor_no_blanco = field_validator("actor")(no_blanco)
    _motivo_no_blanco = field_validator("motivo")(no_blanco)


class SettingsOut(BaseModel):
    """Forma de salida de GET /settings.

    `mcp_token` sale enmascarado salvo `?reveal=true`; `llm.api_key` nunca sale
    en claro (ni aquí ni en el evento `ajuste.cambiado`).
    """

    tema: str
    modo_color: str
    rol: str
    idioma: str
    llm: dict[str, Any]
    puerto: int
    mcp_token: str
    data_dir: str
