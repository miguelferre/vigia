"""Respuestas de proyectos, versiones de modelo y monitores.

Serializadores de origen: `services/projects.py` (`project_to_dict`,
`version_to_dict`, `monitor_to_dict`, `_batch_to_dict`, `project_detail`,
`project_state`, `reset_project`) y `services/monitors.py` (`patch_monitor`).
Ningún campo interno del proyecto sale del backend fuera de estos modelos.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, computed_field

# Literales del umbral propuesto, con los mismos valores que
# `core.schema.ThresholdKind` y `core.schema.ThresholdOrigen` (no se importan
# de `core/` para no acoplar la capa de respuestas al motor).
PropuestaKind = Literal["lower_limit", "upper_limit"]
ThresholdOrigenResp = Literal[
    "linea_base", "fabricante", "criterio_clinico", "politica_organizacion", "fabrica"
]

from vigia.app.schemas.respuestas_base import (
    DeploymentStage,
    EstadoMotor,
    MonitorType,
    Respuesta,
    ThresholdKind,
)

__all__ = [
    "AlertasAbiertasPorSeveridad",
    "BatchKpi",
    "BatchResumen",
    "ChecksPorEstado",
    "MetricKpi",
    "ModelVersion",
    "Monitor",
    "MonitorEstado",
    "MonitorPatchResult",
    "MonitorProtocolStep",
    "Project",
    "ProjectCounts",
    "ProjectDetail",
    "ProjectListItem",
    "ProjectResetCounts",
    "ProjectResetResult",
    "ProjectState",
    "ProjectSummary",
    "PropuestaUmbral",
    "StatesByMonitor",
    "ThresholdsProposal",
    "ThresholdsProposalMonitor",
]


class Project(Respuesta):
    """Proyecto vigilado (`GET /projects`)."""

    id: int | None
    name: str
    description: str | None
    domain: str
    task_type: Literal["binary", "multiclass", "regression"]
    # la unión de `ColumnMappingOut`, leída de la plantilla de mapeo
    # (`Project.favorable_label` queda como compatibilidad). Una lista en multiclase.
    # nulo en regresión, que no tiene clase favorable.
    favorable_label: int | str | list[int | str] | None
    # clases declaradas (`classes_json`) o, a falta de ellas, las de la plantilla.
    classes: list[int | str] | None
    # unidad de la salida y rango favorable fijados en el proyecto
    # (regresión); nulos y vacío en clasificación.
    target_unit: str | None = None
    favorable_ranges: list[tuple[float | None, float | None]] = Field(default_factory=list)
    active_version_id: int | None
    calibration_until: str | None
    store_features: bool
    explain_auto: bool
    explain_method: str
    is_demo: bool
    deployment_stage: DeploymentStage
    # plantilla de mapeo (`core.schema.MappingTemplate` en JSON)
    # y si el proyecto recibe feedback.
    mapping_template_json: dict[str, Any] | None
    acepta_feedback: bool
    created_at: str
    updated_at: str


class ModelVersion(Respuesta):
    """Versión de modelo del proyecto (la ventana de equidad se fija aquí)."""

    id: int | None
    project_id: int
    label: str
    is_active: bool
    model_kind: str
    baseline_batch_id: int | None
    fairness_window_n: int
    frozen_at: str | None
    cross_reference_json: dict[str, Any] | None
    # `artifact_path` no sale nunca: solo el tipo y el hash.
    fairness_interval_method: Literal["ventanas", "lote"]
    artifact_kind: Literal["onnx", "pickle"] | None
    artifact_sha256: str | None
    artifact_inputs_json: list[dict[str, Any]] | None
    artifact_uploaded_at: str | None
    created_at: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def aviso_tipos(self) -> str | None:
        """aviso de un pickle subido antes de la corrección de
        tipos. Se deriva de `artifact_kind` y `artifact_uploaded_at`, así que
        `version_to_dict` no cambia."""
        from vigia.app.services.model_registry import aviso_tipos_antiguos

        return aviso_tipos_antiguos(self.artifact_kind, self.artifact_uploaded_at)


class MonitorProtocolStep(Respuesta):
    """Un hito del protocolo de respuesta del monitor: los
    textos que la alerta enseña en `protocol_steps`. `responsable` y
    `plazo_dias` son opcionales; el orden es el de la lista (detección,
    triaje, investigación, decisión, seguimiento, más los hitos extra que
    se pueden intercalar, con clave libre)."""

    key: str
    titulo: str
    descripcion: str
    entregables: list[str]
    responsable: str | None
    plazo_dias: int | None


class Monitor(Respuesta):
    """Monitor configurado. `config` y `thresholds` son JSON libre por tipo de monitor."""

    id: int | None
    project_id: int
    type: MonitorType
    enabled: bool
    config: dict[str, Any] | None
    thresholds: dict[str, Any] | None
    protocolo_md: str
    protocol: list[MonitorProtocolStep]
    group_context: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class ProjectCounts(Respuesta):
    """Recuentos que acompañan a `GET /projects/{id}`."""

    batches: int
    records: int
    evaluations: int
    datasets: int
    alerts_open: int


class ProjectDetail(Project):
    """Proyecto con sus versiones, monitores y recuentos (`GET/POST/PATCH /projects/{id}`)."""

    versions: list[ModelVersion]
    monitors: list[Monitor]
    counts: ProjectCounts
    # Aviso cuando la versión activa no tiene línea base
    # congelada; `None` si la tiene o si el proyecto no tiene versión activa.
    aviso_linea_base: str | None = None


class AlertasAbiertasPorSeveridad(Respuesta):
    """Alertas abiertas del proyecto por severidad: mismo criterio que
    `ProjectCounts.alerts_open` (cualquier estado que no sea `cerrada`).
    `baja` va siempre a 0 hoy: el catálogo solo abre `alta`/`media`, se declara para
    cuando el catálogo la use."""

    alta: int
    media: int
    baja: int


class MetricKpi(Respuesta):
    """Una medida de `BatchKpi.metrics`: la métrica principal de
    cada uno de los cuatro monitores que evaluaron el lote (equidad y deriva,
    la primera con umbral del monitor; calidad, la misma resolución;
    explicabilidad, la estabilidad del ranking), con su umbral ya resuelto
    por `Measurement`."""

    monitor_type: MonitorType
    metric_key: str
    value: float | None
    threshold_kind: ThresholdKind | None
    threshold_value: float | None
    state: EstadoMotor


class StatesByMonitor(Respuesta):
    """Peor estado de cada monitor en un lote (H1b): `None` si ese monitor no
    se evaluó en ese lote.

    Sin `explain` (decisión de producto): ninguna pantalla pinta su
    estado aquí; su métrica sigue en `BatchKpi.metrics`."""

    fairness: EstadoMotor | None
    quality: EstadoMotor | None
    drift: EstadoMotor | None


class ChecksPorEstado(Respuesta):
    """Comprobaciones (filas de `Measurement`, o de las tres cruzadas) de un
    monitor en un lote, por estado del motor: equidad
    cuenta cada grupo como una comprobación; `cross` no tiene lote y siempre
    suma 3 (CX-1, CX-5, CX-6)."""

    ok: int
    aviso: int
    alerta: int
    inestable: int
    sin_datos: int


class BatchKpi(Respuesta):
    """Lote resumido para el delta del cuadro de mando: `last_batch`
    y `previous_batch` de `ProjectSummary`."""

    batch_id: int | None
    seq: int
    phase_label: str | None
    evaluated_at: str | None
    n_rows: int
    monitors_total: int
    monitors_in_alert: int
    states_by_monitor: StatesByMonitor
    alerts_opened: int
    metrics: list[MetricKpi]
    checks_by_state: dict[MonitorType, ChecksPorEstado]


class ProjectSummary(Respuesta):
    """Resumen de un proyecto para la rejilla de `/modelos`."""

    worst_state: EstadoMotor | None
    alerts_open_by_severity: AlertasAbiertasPorSeveridad
    alerts_open_by_monitor: dict[MonitorType, AlertasAbiertasPorSeveridad]
    last_evaluation_at: str | None
    first_batch_at: str | None
    active_version_label: str | None
    last_batch: BatchKpi | None
    previous_batch: BatchKpi | None


class ProjectListItem(Project):
    """Fila de `GET /projects`; `summary` solo viene con `?summary=true`."""

    summary: ProjectSummary | None = None


class BatchResumen(Respuesta):
    """Resumen de lote dentro de `ProjectState.last_batch` (menos campos que `Batch`)."""

    id: int | None
    seq: int
    phase_label: str | None
    n_rows: int
    n_labeled: int
    orden_manipulado: bool
    created_at: str


class MonitorEstado(Respuesta):
    """Monitor visto desde el estado operativo: último veredicto y cuándo."""

    id: int | None
    type: MonitorType
    enabled: bool
    worst_state: EstadoMotor | None
    last_evaluated_at: str | None


class ProjectState(Respuesta):
    """Estado operativo del proyecto (`GET /projects/{id}/state`)."""

    project_id: int | None
    name: str
    active_version_id: int | None
    versions: list[ModelVersion]
    monitors: list[MonitorEstado]
    alerts_open_by_severity: dict[str, int]
    alerts_open_total: int
    last_batch: BatchResumen | None
    # Línea base por `seq` mínimo: así el cuadro no necesita
    # pedir hasta 500 lotes para deducirla en el cliente.
    first_batch: BatchResumen | None
    jobs_running: list[int]
    quality_primary_metric: str


class ProjectResetCounts(Respuesta):
    """Filas borradas por `POST /projects/{id}/reset`, por tabla."""

    datasets: int
    batches: int
    records: int
    evaluations: int
    alerts: int
    explanations: int
    usage_logs: int
    demo_runs: int


class ProjectResetResult(Respuesta):
    """Respuesta de `POST /projects/{id}/reset`."""

    project_id: int | None
    deleted: ProjectResetCounts


class MonitorPatchResult(Respuesta):
    """Respuesta de `PATCH /monitors/{id}`: el monitor y el evento que lo registró."""

    monitor: Monitor
    event_id: int


class PropuestaUmbral(Respuesta):
    """Umbral propuesto por `core.calibration.proponer_umbrales` sobre la línea
    base, junto al umbral que tiene hoy el monitor y su origen.

    `origen_actual` nunca sale `None`: un umbral sin origen guardado se enseña
    como `fabrica` con `aviso`."""

    metric_key: str
    kind: PropuestaKind
    value: float | None
    valor_linea_base: float | None
    motivo: str | None
    umbral_actual: float | None
    origen_actual: ThresholdOrigenResp
    nota_actual: str | None
    aviso: str | None


class ThresholdsProposalMonitor(Respuesta):
    """Propuestas de un monitor (`fairness` o `quality`) de `GET
    /projects/{id}/thresholds/proposal`."""

    monitor_type: MonitorType
    propuestas: list[PropuestaUmbral]


class ThresholdsProposal(Respuesta):
    """Respuesta de `GET /projects/{id}/thresholds/proposal`: la
    propuesta de `core/calibration.py` sobre el lote de línea base de la
    versión activa, para equidad y calidad."""

    baseline_batch_id: int
    tamano_lote: int
    monitors: list[ThresholdsProposalMonitor]
