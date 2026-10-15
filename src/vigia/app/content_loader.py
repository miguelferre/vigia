"""Lectura del contenido estático de `vigia.content` para uso interno del backend.

Complementa a `routers/content.py` (que sirve el JSON tal cual): este
módulo es para servicios que necesitan una sola etiqueta, no el fichero
completo. Mismo mecanismo de lectura (recurso del paquete,
cacheado): así funciona igual en el repositorio y en el paquete instalado.

No se toca `content.py` ni los JSON de `src/vigia/content/`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

__all__ = ["fase_label", "metric_label", "protocolo_hitos_plantilla"]


@lru_cache(maxsize=1)
def _metricas_ayuda() -> dict[str, Any]:
    ref = resources.files("vigia.content").joinpath("metricas-ayuda.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def metric_label(metric_key: str) -> str | None:
    """Etiqueta en español de `metric_key` (`content/metricas-ayuda.json`), o `None`."""
    entrada = _metricas_ayuda().get(metric_key)
    if entrada is None:
        return None
    etiqueta = entrada.get("etiqueta")
    return etiqueta if isinstance(etiqueta, str) and etiqueta else None


@lru_cache(maxsize=1)
def _fases_demo() -> dict[str, Any]:
    ref = resources.files("vigia.content").joinpath("demo-digestivo.json")
    contenido = json.loads(ref.read_text(encoding="utf-8"))
    fases = contenido.get("fases")
    return fases if isinstance(fases, dict) else {}


def fase_label(phase_key: str) -> str | None:
    """Etiqueta en español de una fase del guion de la demo (`fases` de
    `content/demo-digestivo.json`): «Línea base», «Casos nuevos»,
    «Tras las medidas»; la clave `lab:*` da «Laboratorio». `None` si la fase
    no está en el contenido (guiones antiguos: `b2`, `e2_evento`...)."""
    entrada = _fases_demo().get(phase_key)
    if entrada is None:
        return None
    etiqueta = entrada.get("etiqueta")
    return etiqueta if isinstance(etiqueta, str) and etiqueta else None


# Campos de un hito del protocolo por monitor: la plantilla de
# `content/protocolo-hitos.json` trae `key`, `titulo`, `descripcion` y
# `entregables`; `responsable` y `plazo_dias` nacen vacíos y se rellenan en
# la hoja «Configurar». `orden` no se guarda: es la posición en la lista.
CAMPOS_HITO_PROTOCOLO: tuple[str, ...] = (
    "key",
    "titulo",
    "descripcion",
    "entregables",
    "responsable",
    "plazo_dias",
)


@lru_cache(maxsize=1)
def _protocolo_hitos() -> tuple[dict[str, Any], ...]:
    ref = resources.files("vigia.content").joinpath("protocolo-hitos.json")
    hitos = json.loads(ref.read_text(encoding="utf-8"))
    return tuple(
        {
            "key": h["key"],
            "titulo": h["titulo"],
            "descripcion": h["descripcion"],
            "entregables": list(h.get("entregables") or []),
            "responsable": None,
            "plazo_dias": None,
        }
        for h in sorted(hitos, key=lambda h: h["orden"])
    )


def protocolo_hitos_plantilla() -> list[dict[str, Any]]:
    """Los cinco hitos de `content/protocolo-hitos.json` en la forma de
    `Monitor.protocol_json`: copia nueva en cada llamada, para que
    quien la guarde en un monitor no comparta listas con la caché."""
    return [
        {**h, "entregables": list(h["entregables"])} for h in _protocolo_hitos()
    ]
