"""Esquemas de guiones y reproducciones de demo."""

from __future__ import annotations

import math
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

from vigia.app.schemas.common import ActorBody

__all__ = ["CreateRunBody", "LabRunBody", "ResetRunBody", "exigir_parametros_finitos"]

# Cotas de los parámetros que fijan cuántas filas genera una fase o la capa
# humana: (mínimo, máximo, entero). Una clave ausente no se comprueba.
_COTAS_GENERADOR: dict[str, tuple[float, float, bool]] = {
    "n_total": (1, 10_000, True),
    "frac_young": (0, 1, False),
    "n_clinicians": (1, 500, True),
    # La edad media y su dispersión fijan si el muestreo de edades termina.
    # Cubren todo lo que ofrece el laboratorio (media 30 a 80, dispersión 5 a 30);
    # el generador además corta con un error claro si una combinación no llega a 36.
    "age_mean": (18, 100, False),
    "age_std": (1, 50, False),
}


def _no_finitos(params: dict[str, Any]) -> bool:
    return any(isinstance(v, float) and not math.isfinite(v) for v in params.values())


def exigir_parametros_finitos(params: dict[str, Any] | None) -> None:
    """422 si algún parámetro (o uno de `human`) es NaN o infinito. Va en la ruta y no
    en el esquema: un 422 de esquema devolvería el valor en la respuesta y JSON no
    admite NaN."""
    if params is None:
        return
    humano = params.get("human")
    if _no_finitos(params) or (isinstance(humano, dict) and _no_finitos(humano)):
        raise HTTPException(422, "los parámetros solo admiten números finitos")


def _comprobar_cotas(params: dict[str, Any]) -> None:
    if _no_finitos(params):
        return  # lo rechaza `exigir_parametros_finitos`
    for clave, (minimo, maximo, entero) in _COTAS_GENERADOR.items():
        if clave not in params:
            continue
        valor = params[clave]
        if isinstance(valor, bool) or not isinstance(valor, int | float):
            raise ValueError(f"{clave} debe ser un número")  # noqa: TRY004
        if not minimo <= valor <= maximo:
            raise ValueError(f"{clave} debe estar entre {minimo:g} y {maximo:g}")
        if entero and valor != int(valor):
            raise ValueError(f"{clave} debe ser un número entero")


def _validar_parametros(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if params is None:
        return params
    _comprobar_cotas(params)
    humano = params.get("human")
    if isinstance(humano, dict):
        _comprobar_cotas(humano)
    return params


class CreateRunBody(BaseModel):
    """Cuerpo de `POST /demo/runs`.

    Con `project_id`, la reproducción se ata a un
    proyecto que el usuario ya ha creado con el formulario real, en vez de
    crear uno nuevo: `project_name` no se usa en ese caso.
    """

    scenario_key: str = Field(min_length=1)
    source: str = "canned"
    with_human: bool = False
    params: dict[str, Any] | None = None
    project_name: str | None = None
    project_id: int | None = None

    _params_en_rango = field_validator("params")(_validar_parametros)


class ResetRunBody(ActorBody):
    """Cuerpo de `POST /demo/runs/{id}/reset`: actor, motivo y confirmación explícita."""

    confirm: bool = False


class LabRunBody(ActorBody):
    """Cuerpo de `POST /demo/runs/{id}/lab`: fase generada a la carta.

    `params` se valida contra los parámetros que acepta el generador de esa
    fase (`sim/generators.py`); una clave desconocida es 422, no un silencio.
    """

    phase_key: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    seed: int | None = None

    _params_en_rango = field_validator("params")(_validar_parametros)
