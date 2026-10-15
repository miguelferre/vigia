"""Esquemas de configuración de monitores."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vigia.app.schemas.common import (
    MAX_DESCRIPCION,
    MAX_NOMBRE,
    MAX_TEXTO_LARGO,
    ActorBody,
    TextoDescripcion,
    no_blanco,
)

__all__ = [
    "RANGOS_CONFIG",
    "MonitorPatch",
    "MonitorProtocolStepBody",
    "claves_fuera_de_rango",
    "es_finito",
]

# Cotas de los campos numéricos de la configuración de un monitor: (mínimo,
# máximo, el mínimo es exclusivo). `None` en el máximo: sin tope.
RANGOS_CONFIG: dict[str, tuple[float, float | None, bool]] = {
    "psi_bins": (2, 50, False),
    "confidence_bins": (2, 50, False),
    "window_step": (1, None, False),
    "interval_windows_max": (1, 1000, False),
    "min_group": (1, 100_000, False),
    "min_positives": (0, 100_000, False),
    "min_feedback": (1, 100_000, False),
    "label_min_records": (1, 100_000, False),
    "z_alert": (0, None, True),
}


def es_finito(valor: Any) -> bool:
    """False si `valor`, o algo dentro de una lista o un objeto, es NaN o infinito
    (también escrito como texto, que pydantic acepta como número)."""
    if isinstance(valor, bool):
        return True
    if isinstance(valor, float):
        return math.isfinite(valor)
    if isinstance(valor, str):
        try:
            return math.isfinite(float(valor))
        except ValueError:
            return True
    if isinstance(valor, dict):
        return all(es_finito(v) for v in valor.values())
    if isinstance(valor, list | tuple):
        return all(es_finito(v) for v in valor)
    return True


def claves_fuera_de_rango(config: dict[str, Any]) -> list[str]:
    """Claves de `config` con un valor fuera de `RANGOS_CONFIG` o no finito."""
    malas: list[str] = []
    for clave, valor in config.items():
        if not es_finito(valor):
            malas.append(clave)
            continue
        rango = RANGOS_CONFIG.get(clave)
        if rango is None or isinstance(valor, bool):
            continue
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            continue  # el modelo del monitor rechaza lo que no es número
        minimo, maximo, exclusivo = rango
        por_debajo = numero < minimo or (exclusivo and numero == minimo)
        if por_debajo or (maximo is not None and numero > maximo):
            malas.append(clave)
    return malas


def texto_rango(clave: str) -> str:
    """«psi_bins debe estar entre 2 y 50» (o «mayor que 0», «de 1 en adelante»)."""
    minimo, maximo, exclusivo = RANGOS_CONFIG[clave]
    inicio = f"{minimo:g}"
    if exclusivo:
        return f"{clave} debe ser mayor que {inicio}"
    if maximo is None:
        return f"{clave} debe ser {inicio} o más"
    return f"{clave} debe estar entre {inicio} y {maximo:g}"


class MonitorProtocolStepBody(BaseModel):
    """Un hito del protocolo de respuesta editado en la hoja «Configurar». La forma exacta de los cinco hitos (claves, orden, sin
    huecos ni repeticiones; admite hitos extra intercalados) la
    valida `validar_protocol` en `services/monitors_protocol.py`, no este
    esquema: así el 422 puede explicar qué falta, qué sobra o qué está
    desordenado en vez de un error genérico de literal inválido."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=MAX_NOMBRE)
    titulo: str = Field(min_length=1, max_length=MAX_NOMBRE)
    descripcion: str = Field(default="", max_length=MAX_DESCRIPCION)
    entregables: list[TextoDescripcion] = []
    responsable: str | None = Field(default=None, max_length=MAX_NOMBRE)
    plazo_dias: int | None = Field(default=None, ge=0)

    _titulo_no_blanco = field_validator("titulo")(no_blanco)


class MonitorPatch(ActorBody):
    """Cuerpo del PATCH de un monitor: `actor` y `motivo` exigidos."""

    enabled: bool | None = None
    config: dict[str, Any] | None = None
    thresholds: dict[str, Any] | None = None
    protocolo_md: str | None = Field(default=None, max_length=MAX_TEXTO_LARGO)
    protocol: list[MonitorProtocolStepBody] | None = None
    laboratorio: bool = False

    @field_validator("config")
    @classmethod
    def _config_en_rango(cls, valor: dict[str, Any] | None) -> dict[str, Any] | None:
        # Los valores no finitos los rechaza el servicio (`patch_monitor`): un 422 de
        # esquema devolvería el valor en la respuesta y JSON no admite NaN.
        if valor is None or not es_finito(valor):
            return valor
        malas = claves_fuera_de_rango(valor)
        if malas:
            raise ValueError("; ".join(texto_rango(c) for c in malas))
        return valor
