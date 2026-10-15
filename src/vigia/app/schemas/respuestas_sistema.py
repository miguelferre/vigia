"""Respuestas del diario, las colas, la salud, los ajustes y la demo.

Serializadores de origen: `app/events.py` (`event_to_dict`), `routers/jobs.py`
(`job_to_dict`), `routers/health.py`, `services/settings.py` (`get_settings`,
`patch_settings`) y `services/demo_player.py` (`run_to_dict`).
"""

from __future__ import annotations

from typing import Any, Literal

from vigia.app.schemas.respuestas_base import ActorKind, JobQueue, JobStatus, Respuesta
from vigia.app.schemas.respuestas_datos import ColumnMappingOut

__all__ = [
    "DemoRun",
    "DemoScenario",
    "DemoScenarioPhase",
    "Event",
    "Health",
    "Job",
    "JobResumen",
    "QueueCount",
    "SchemaColumn",
    "SchemaForeignKey",
    "SchemaTable",
    "SchemaTables",
    "Settings",
    "SettingsLlm",
    "Shutdown",
]


class Event(Respuesta):
    """Entrada del diario de tres carriles (humano, agente, modelo; más sistema)."""

    id: int | None
    ts: str
    actor_kind: ActorKind
    actor_id: str
    role: str | None
    action: str
    titulo: str
    object_type: str
    object_id: int | None
    project_id: int | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    motivo: str | None
    correlation_id: str | None
    job_id: int | None


class Job(Respuesta):
    """Trabajo de una de las dos colas, tal como lo sirve `routers/jobs.py`."""

    id: int | None
    kind: str
    queue: JobQueue
    status: JobStatus
    progress: float
    message: str
    params: dict[str, Any] | None
    result: dict[str, Any] | None
    error: str | None
    cancel_requested: bool
    project_id: int | None
    correlation_id: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


class JobResumen(Respuesta):
    """Trabajo recién encolado: la forma de `Job` sin `params` ni `cancel_requested`.

    La devuelven los endpoints que encolan (ingesta, evaluación, explicabilidad y
    demo): el cliente ya conoce los parámetros que acaba de enviar.
    """

    id: int | None
    kind: str
    queue: JobQueue
    status: JobStatus
    progress: float
    message: str
    result: dict[str, Any] | None
    error: str | None
    project_id: int | None
    correlation_id: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


class QueueCount(Respuesta):
    """Ocupación de una cola: trabajos pendientes y en curso."""

    pendientes: int
    en_curso: int


class Health(Respuesta):
    """Salud del servicio (`GET /health`)."""

    status: str
    version: str
    python: str
    data_dir: str
    port: int | None
    schema_version: int
    db_path: str
    queues: dict[str, QueueCount]


class Shutdown(Respuesta):
    """Respuesta de `POST /shutdown`."""

    status: str


class SchemaColumn(Respuesta):
    """Columna de una tabla del esquema (resource `schema://tables`)."""

    name: str
    type: str
    nullable: bool
    primary_key: bool


class SchemaForeignKey(Respuesta):
    """Clave ajena de una tabla: columna propia y `tabla.columna` destino."""

    column: str
    references: str


class SchemaTable(Respuesta):
    """Tabla del esquema con sus columnas y claves ajenas."""

    name: str
    columns: list[SchemaColumn]
    foreign_keys: list[SchemaForeignKey]


class SchemaTables(Respuesta):
    """Respuesta de `GET /schema/tables`: introspección en vivo de
    `SQLModel.metadata`, nunca un JSON mantenido a mano."""

    schema_version: int
    tables: list[SchemaTable]


class SettingsLlm(Respuesta):
    """Ajustes del modelo de lenguaje. `api_key` nunca sale en claro (§3.10)."""

    backend: str
    model: str
    base_url: str
    api_key: str


class Settings(Respuesta):
    """Ajustes de la aplicación. `mcp_token` va enmascarado salvo `?reveal=true`."""

    tema: str
    modo_color: str
    rol: str
    idioma: str
    llm: SettingsLlm
    puerto: int
    mcp_token: str
    data_dir: str


class DemoScenarioPhase(Respuesta):
    """Fase de un guion de demo, tal como la sirve `GET /demo/scenarios` (§3.1, §3.4).

    Subconjunto serializable de `vigia.sim.scenarios.Phase`: sin generador,
    parámetros ni enlatado (`app/migrations.py::_fase_a_dict` los omite de
    `phases_json`), más `lab_params`, calculado en el router con la misma
    inspección de firma que valida el laboratorio
    (`services/demo_player.py::lab_params_for_phase`).
    """

    key: str
    title: str
    kind: Literal["baseline", "evento", "recovery"]
    model_version: str
    freeze_baseline: bool
    orden_manipulado: bool
    motivo_manipulacion: str | None
    expected: dict[str, str]
    explain_global: bool
    narrative: str
    lab_params: list[str]


class DemoScenario(Respuesta):
    """Guion de demo sembrado, con sus fases (`GET /demo/scenarios`).

    `upload_mapping`: el mapeo que el formulario de subida debe
    precargar para el CSV combinado de la primera fase (`services/demo_files.py`);
    `None` si esa fase no tiene enlatado.
    """

    key: str
    title: str
    domain: str
    description: str
    phases: list[DemoScenarioPhase] | None
    default_params: dict[str, Any] | None
    upload_mapping: ColumnMappingOut | None


class DemoRun(Respuesta):
    """Reproducción de un guion sobre un proyecto de demo. `result` es un resumen por fase."""

    id: int | None
    scenario_key: str
    project_id: int
    mode: str
    source: str
    with_human: bool
    params: dict[str, Any] | None
    current_phase: int
    status: str
    result: list[dict[str, Any]] | None
    human_seed: int
    created_at: str
    updated_at: str
