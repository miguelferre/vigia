"""Base de los modelos de respuesta: cierre estricto y enumerados compartidos.

Todos los modelos de `respuestas_*.py` heredan de `Respuesta`, que prohíbe las
claves extra: si un serializador de `services/` devuelve una clave que el modelo
no declara, FastAPI falla al validar la respuesta. Ese fallo es el contrato:
obliga a declarar el campo aquí antes de que llegue al frontend.

Los enumerados son `Literal` con los mismos valores que las uniones de
`frontend/src/api/types-base.ts`, para que `openapi-typescript` genere allí las
mismas uniones de cadenas.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ActorKind",
    "AlertSeverity",
    "AlertStage",
    "AlertStatus",
    "DatasetKind",
    "DatasetRole",
    "DatasetStatus",
    "DeploymentStage",
    "EstadoMotor",
    "ExplanationKind",
    "JobQueue",
    "JobStatus",
    "MonitorType",
    "ProtocolStepKey",
    "ProtocolStepStatus",
    "Respuesta",
    "SeriesGranularity",
    "ThresholdKind",
]


class Respuesta(BaseModel):
    """Modelo de respuesta cerrado: cualquier clave no declarada es un error."""

    model_config = ConfigDict(extra="forbid")


# Los cinco estados del motor (`core/schema.py`).
type EstadoMotor = Literal["ok", "aviso", "alerta", "inestable", "sin_datos"]
type MonitorType = Literal["fairness", "quality", "drift", "explain", "cross"]
type AlertStatus = Literal["abierta", "en_observacion", "reconocida", "cerrada", "retirada"]
# Severidades que abre el catálogo: `alerta` a `alta`, `inestable` a `media`.
type AlertSeverity = Literal["alta", "media"]
# Etiqueta de estado de la alerta: el último hito hecho del protocolo,
# no el `status` interno del motor.
type AlertStage = Literal["detectada", "en_observacion", "en_investigacion", "en_seguimiento", "cerrada"]
type JobStatus = Literal["pendiente", "en_curso", "terminado", "error", "cancelado"]
type JobQueue = Literal["rapida", "llm"]
type ActorKind = Literal["humano", "agente", "modelo", "sistema"]
type DatasetKind = Literal["combined", "payload", "feedback", "usage_log", "outcome"]
type DatasetRole = Literal["baseline", "production"]
# `error` lo añade el estado de error: ingesta fallida, fichero en bruto borrado.
type DatasetStatus = Literal["subido", "mapeado", "ingerido", "error"]
type ExplanationKind = Literal["global_permutation", "global_shap", "local_lime"]
# Umbral de una medida: `lower`/`upper` según `threshold_low`/`threshold_high`.
type ThresholdKind = Literal["lower", "upper"]
# Los cinco hitos estándar del protocolo por alerta. El
# protocolo admite hitos extra con clave libre: `key` de los
# pasos es `str` y estas cinco son las únicas que mueven la etapa.
type ProtocolStepKey = Literal["deteccion", "triaje", "investigacion", "decision", "seguimiento"]
# `informativo`: hito extra del protocolo del monitor, sin evento propio
# ni barra de progreso; no participa en la etapa de la alerta.
type ProtocolStepStatus = Literal["done", "current", "pending", "informativo"]
# Estado de despliegue del proyecto. `validacion` lo añade el alta;
# `demo` solo lo pone el reproductor de la demo.
type DeploymentStage = Literal["desarrollo", "validacion", "produccion", "demo"]
# Granularidad del panel «Alertas por lote».
type SeriesGranularity = Literal["batch", "day", "hour"]
