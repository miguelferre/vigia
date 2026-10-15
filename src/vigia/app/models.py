"""Tablas SQLModel del esquema versión 1 de Vigía.

Convenciones de este módulo:

- Nombres de tabla en singular, exactamente los de la especificación.
- Las columnas de fecha se guardan como texto ISO 8601 UTC con microsegundos
  (`now_iso()`), de anchura fija: así el orden lexicográfico coincide con el
  cronológico y la serialización a JSON es directa.
- Las enumeraciones son cadenas (`Literal` en los servicios, constantes aquí),
  nunca `Enum` de SQLAlchemy: SQLite no gana nada con ellas y las migraciones
  se complican.
- Las columnas JSON usan `sa_column=Column(JSON)`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

__all__ = [
    "ACCIONES_ALERTA",
    "Alert",
    "AlertAction",
    "Batch",
    "Dataset",
    "DemoRun",
    "DemoScenario",
    "Dossier",
    "DossierReview",
    "Evaluation",
    "Event",
    "Explanation",
    "Job",
    "Measurement",
    "ModelVersion",
    "Monitor",
    "Outcome",
    "Project",
    "Record",
    "Risk",
    "RiskMovement",
    "SchemaVersion",
    "Setting",
    "UsageLog",
    "now_iso",
]


def now_iso() -> str:
    """Marca de tiempo actual en ISO 8601 UTC con microsegundos."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


# Catálogo de acciones de alerta (`seguir_vigilando`,
# la decisión sin medidas) más las dos de flujo.
ACCIONES_ALERTA: tuple[str, ...] = (
    "contener_subgrupo",
    "cambiar_umbral",
    "pedir_reentrenamiento",
    "escalar",
    "retirar_modelo",
    "cribado_retrospectivo",
    "registrar_riesgo",
    "nota",
    "seguir_vigilando",
    "reconocer",
    "cerrar",
)


def _fk(target: str, *, ondelete: str, nullable: bool = False, index: bool = True) -> Column:
    """Columna entera de clave foránea con `ondelete` explícito."""
    return Column(
        Integer,
        ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
        index=index,
    )


def _json_col(*, nullable: bool = True) -> Column:
    return Column(JSON, nullable=nullable)


# ---------------------------------------------------------------------------
# Infraestructura
# ---------------------------------------------------------------------------


class SchemaVersion(SQLModel, table=True):
    """Versiones de esquema ya aplicadas a esta base de datos."""

    __tablename__ = "schema_version"

    version: int = Field(primary_key=True)
    applied_at: str = Field(default_factory=now_iso)


class Setting(SQLModel, table=True):
    """Ajustes de la aplicación, una fila por clave."""

    __tablename__ = "setting"

    key: str = Field(primary_key=True)
    value_json: Any | None = Field(default=None, sa_column=_json_col())
    updated_at: str = Field(default_factory=now_iso)


# ---------------------------------------------------------------------------
# Proyecto, versiones y datos
# ---------------------------------------------------------------------------


class Project(SQLModel, table=True):
    """Proyecto vigilado: un modelo, sus datos, sus monitores y sus alertas."""

    __tablename__ = "project"
    # Migración 12: el id de un proyecto borrado no se reutiliza (el diario no tiene FK).
    __table_args__ = {"sqlite_autoincrement": True}

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String, nullable=False, unique=True, index=True))
    description: str | None = Field(default=None)
    domain: str = Field(default="libre")
    task_type: str = Field(default="binary")
    favorable_label: int = Field(default=1)
    # Sin ForeignKey declarada: project <-> model_version es un ciclo y SQLite no
    # admite ALTER TABLE ADD CONSTRAINT. La integridad la mantienen los servicios.
    active_version_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True, index=True),
    )
    calibration_until: str | None = Field(default=None)
    # `hmac_salt` (sin uso) la retira la migración 7.
    store_features: bool = Field(default=True)
    explain_auto: bool = Field(default=True)
    explain_method: str = Field(default="permutation")
    is_demo: bool = Field(default=False)
    # Estado de despliegue: "desarrollo" | "produccion" | "demo".
    deployment_stage: str = Field(default="desarrollo")
    # Plantilla de mapeo del proyecto: claves
    # `favorable_label`, `positive_label`, `id_col`, `timestamp_col`, `feature_cols`,
    # `protected_attr_col`, `protected_kind`, `unpriv_groups`, `priv_groups`.
    # Cada dataset la hereda y puede apartarse de ella con evento en el diario.
    mapping_template_json: Any | None = Field(default=None, sa_column=_json_col())
    # Clases declaradas, en el orden de las
    # probabilidades; se fijan al crear y se confirman al congelar la línea base.
    classes_json: Any | None = Field(default=None, sa_column=_json_col())
    # Unidad de la salida y rango favorable de
    # una regresión (lista de `[min, max]` con extremo nulo abierto). Se fijan en
    # el alta o al congelar la línea base y después no cambian.
    target_unit: str | None = Field(default=None)
    favorable_ranges_json: Any | None = Field(default=None, sa_column=_json_col())
    # Sin feedback el `id_col` deja de ser obligatorio.
    acepta_feedback: bool = Field(default=True)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class ModelVersion(SQLModel, table=True):
    """Versión de modelo dentro de un proyecto (ventana de equidad fijada aquí)."""

    __tablename__ = "model_version"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(sa_column=_fk("project.id", ondelete="CASCADE"))
    label: str
    is_active: bool = Field(default=False)
    model_kind: str = Field(default="external_files")
    # Sin ForeignKey declarada por el mismo ciclo que `Project.active_version_id`.
    baseline_batch_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True, index=True),
    )
    fairness_window_n: int = Field(default=200)
    frozen_at: str | None = Field(default=None)
    cross_reference_json: Any | None = Field(default=None, sa_column=_json_col())
    # Método del intervalo de equidad:
    # "ventanas" (la demo y los proyectos antiguos) o "lote"
    # (Katz y Newcombe sobre el lote completo con la regla de valor puntual),
    # el de los proyectos nuevos. La columna nace con "ventanas" para no
    # cambiar ningún proyecto existente; el alta pone "lote".
    fairness_interval_method: str = Field(default="ventanas")
    # Artefacto del modelo ejecutable. El
    # fichero vive en la carpeta de datos del proyecto, fuera del repo.
    # `artifact_kind`: "onnx" o "pickle" (este, solo con confirmación).
    # `artifact_inputs_json`: lista de {"name", "type", "kind"} por entrada,
    # con `kind` "numerica" o "categorica".
    artifact_path: str | None = Field(default=None)
    artifact_kind: str | None = Field(default=None)
    artifact_sha256: str | None = Field(default=None)
    artifact_inputs_json: Any | None = Field(default=None, sa_column=_json_col())
    artifact_uploaded_at: str | None = Field(default=None)
    created_at: str = Field(default_factory=now_iso)


class Dataset(SQLModel, table=True):
    """Fichero subido o generado, con su informe de privacidad y su mapeo de columnas."""

    __tablename__ = "dataset"
    # Migración 11: los ids no se reutilizan tras borrar.
    __table_args__ = {"sqlite_autoincrement": True}

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(sa_column=_fk("project.id", ondelete="CASCADE"))
    name: str
    source: str = Field(default="upload")
    kind: str = Field(default="combined")
    role: str = Field(default="production")
    format: str = Field(default="csv")
    file_path: str = Field(default="")
    sha256: str = Field(default="")
    sha256_privado: str | None = Field(default=None)
    raw_purged: bool = Field(default=False)
    n_rows: int = Field(default=0)
    columns_json: Any | None = Field(default=None, sa_column=_json_col())
    mapping_json: Any | None = Field(default=None, sa_column=_json_col())
    privacy_report_json: Any | None = Field(default=None, sa_column=_json_col())
    privacy_decisions_json: Any | None = Field(default=None, sa_column=_json_col())
    suggested_mapping_json: Any | None = Field(default=None, sa_column=_json_col())
    # Dialecto del CSV detectado al subir:
    # codificación, separador y decimal. Nulo en JSON y en datasets anteriores.
    dialect_json: Any | None = Field(default=None, sa_column=_json_col())
    status: str = Field(default="subido")
    created_at: str = Field(default_factory=now_iso)


class Batch(SQLModel, table=True):
    """Lote ingerido: unidad de evaluación y de orden dentro del proyecto."""

    __tablename__ = "batch"
    __table_args__ = {"sqlite_autoincrement": True}

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(sa_column=_fk("project.id", ondelete="CASCADE"))
    dataset_id: int | None = Field(
        default=None,
        sa_column=_fk("dataset.id", ondelete="SET NULL", nullable=True),
    )
    model_version_id: int = Field(sa_column=_fk("model_version.id", ondelete="CASCADE"))
    seq: int = Field(default=0, index=True)
    phase_label: str | None = Field(default=None)
    n_rows: int = Field(default=0)
    n_labeled: int = Field(default=0)
    orden_manipulado: bool = Field(default=False)
    motivo_manipulacion: str | None = Field(default=None)
    demo_run_id: int | None = Field(default=None, index=True)
    sha256: str | None = Field(default=None)
    created_at: str = Field(default_factory=now_iso)


class Record(SQLModel, table=True):
    """Fila canónica de un lote. `external_id` se guarda sin codificar."""

    __tablename__ = "record"
    __table_args__ = (
        Index("ix_record_project_seq", "project_id", "seq"),
        Index("ix_record_project_external", "project_id", "external_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    batch_id: int = Field(sa_column=_fk("batch.id", ondelete="CASCADE"))
    project_id: int = Field(sa_column=_fk("project.id", ondelete="CASCADE", index=False))
    seq: int = Field(default=0)
    external_id: str | None = Field(default=None)
    timestamp: str | None = Field(default=None)
    prediction: int = Field(default=0)
    prob_favorable: float | None = Field(default=None)
    label: float | None = Field(default=None)
    protected_value: str | None = Field(default=None)
    group_code: int = Field(default=-1)
    clinician_pseudonym: str | None = Field(default=None)
    subgroup: str | None = Field(default=None)
    features_json: Any | None = Field(default=None, sa_column=_json_col())
    # Clase predicha y clase real (texto
    # normalizado) y las `k` probabilidades en el orden de `classes`. Nulos en
    # las filas de antes y en binario sin clases declaradas.
    prediction_class: str | None = Field(default=None)
    label_class: str | None = Field(default=None)
    probabilities_json: Any | None = Field(default=None, sa_column=_json_col())
    # Valor continuo de la predicción y de la
    # etiqueta en una regresión. `prediction` y `label` guardan el 0/1 de
    # pertenencia al rango favorable. Nulos en las filas de antes y en clasificación.
    prediction_value: float | None = Field(default=None)
    label_value: float | None = Field(default=None)


# ---------------------------------------------------------------------------
# Monitores, evaluaciones y alertas
# ---------------------------------------------------------------------------


class Monitor(SQLModel, table=True):
    """Monitor configurado de un proyecto (uno por tipo)."""

    __tablename__ = "monitor"
    __table_args__ = (UniqueConstraint("project_id", "type", name="uq_monitor_project_type"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(sa_column=_fk("project.id", ondelete="CASCADE"))
    type: str
    enabled: bool = Field(default=True)
    config_json: Any | None = Field(default=None, sa_column=_json_col())
    thresholds_json: Any | None = Field(default=None, sa_column=_json_col())
    protocolo_md: str = Field(default="", sa_column=Column(Text, nullable=False, default=""))
    # Los cinco hitos del protocolo de respuesta,
    # editables por monitor (`key`, `titulo`, `descripcion`, `entregables`,
    # `responsable`, `plazo_dias`); se rellena con la plantilla de
    # `content/protocolo-hitos.json` al crear el monitor y al migrar.
    protocol_json: Any | None = Field(default=None, sa_column=_json_col())
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class Evaluation(SQLModel, table=True):
    """Ejecución de un monitor sobre un lote: `result_json` es el `EvaluationResult` completo."""

    __tablename__ = "evaluation"
    __table_args__ = {"sqlite_autoincrement": True}

    id: int | None = Field(default=None, primary_key=True)
    monitor_id: int = Field(sa_column=_fk("monitor.id", ondelete="CASCADE"))
    project_id: int = Field(sa_column=_fk("project.id", ondelete="CASCADE"))
    model_version_id: int = Field(sa_column=_fk("model_version.id", ondelete="CASCADE"))
    batch_id: int | None = Field(
        default=None,
        sa_column=_fk("batch.id", ondelete="CASCADE", nullable=True),
    )
    trigger: str = Field(default="manual")
    window_json: Any | None = Field(default=None, sa_column=_json_col())
    config_snapshot_json: Any | None = Field(default=None, sa_column=_json_col())
    app_version: str = Field(default="")
    core_version: str = Field(default="")
    status: str = Field(default="ok")
    worst_state: str | None = Field(default=None)
    result_json: Any | None = Field(default=None, sa_column=_json_col())
    job_id: int | None = Field(default=None, index=True)
    created_at: str = Field(default_factory=now_iso, index=True)


class Measurement(SQLModel, table=True):
    """Medida individual de una evaluación (fila de `EvaluationResult.measurements`)."""

    __tablename__ = "measurement"
    __table_args__ = (
        Index("ix_measurement_project_monitor_metric", "project_id", "monitor_type", "metric_key"),
    )

    id: int | None = Field(default=None, primary_key=True)
    evaluation_id: int = Field(sa_column=_fk("evaluation.id", ondelete="CASCADE"))
    project_id: int = Field(default=0)
    monitor_type: str = Field(default="")
    metric_key: str = Field(default="")
    value: float | None = Field(default=None)
    interval_low: float | None = Field(default=None)
    interval_high: float | None = Field(default=None)
    threshold_low: float | None = Field(default=None)
    threshold_high: float | None = Field(default=None)
    state: str = Field(default="sin_datos")
    group_code: str | None = Field(default=None)
    motivo: str | None = Field(default=None)
    extra_json: Any | None = Field(default=None, sa_column=_json_col())
    created_at: str = Field(default_factory=now_iso)


class Alert(SQLModel, table=True):
    """Alerta abierta por el motor. Nunca se cierra sola."""

    __tablename__ = "alert"
    __table_args__ = (
        Index("ix_alert_clave", "project_id", "monitor_type", "metric_key", "group_code"),
        {"sqlite_autoincrement": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(sa_column=_fk("project.id", ondelete="CASCADE", index=False))
    monitor_type: str = Field(default="")
    metric_key: str = Field(default="")
    group_code: str | None = Field(default=None)
    severity: str = Field(default="media")
    status: str = Field(default="abierta", index=True)
    title: str = Field(default="")
    opened_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    closed_at: str | None = Field(default=None)
    last_evaluation_id: int | None = Field(default=None)
    last_value: float | None = Field(default=None)
    observation_count: int = Field(default=0)
    reopen_count: int = Field(default=0)
    protocolo_md: str = Field(default="", sa_column=Column(Text, nullable=False, default=""))
    history_json: Any | None = Field(default=None, sa_column=_json_col())
    # Migración 11: lote y evaluación con los que se abrió
    # (sin clave foránea: el lote puede borrarse y la alerta queda `retirada`)
    # y motivo de la retirada. Nulos en filas anteriores sin origen vivo.
    origin_batch_id: int | None = Field(default=None)
    origin_evaluation_id: int | None = Field(default=None)
    retired_reason: str | None = Field(default=None)


class AlertAction(SQLModel, table=True):
    """Acción humana sobre una alerta: siempre con actor y motivo."""

    __tablename__ = "alert_action"

    id: int | None = Field(default=None, primary_key=True)
    alert_id: int = Field(sa_column=_fk("alert.id", ondelete="CASCADE"))
    action: str
    actor: str
    role: str | None = Field(default=None)
    motivo: str = Field(default="")
    attachment_path: str | None = Field(default=None)
    ts: str = Field(default_factory=now_iso)


class Explanation(SQLModel, table=True):
    """Resultado de explicabilidad global o local. `available=False` si no se pudo calcular."""

    __tablename__ = "explanation"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(default=0, index=True)
    model_version_id: int = Field(sa_column=_fk("model_version.id", ondelete="CASCADE"))
    batch_id: int | None = Field(
        default=None,
        sa_column=_fk("batch.id", ondelete="SET NULL", nullable=True),
    )
    kind: str = Field(default="global_permutation")
    row_seq: int | None = Field(default=None)
    params_json: Any | None = Field(default=None, sa_column=_json_col())
    result_json: Any | None = Field(default=None, sa_column=_json_col())
    available: bool = Field(default=True)
    motivo: str | None = Field(default=None)
    job_id: int | None = Field(default=None, index=True)
    created_at: str = Field(default_factory=now_iso)


# ---------------------------------------------------------------------------
# Capa humana y resultados clínicos
# ---------------------------------------------------------------------------


class UsageLog(SQLModel, table=True):
    """Fila del diario de uso: decisión humana frente a salida del modelo."""

    __tablename__ = "usage_log"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(sa_column=_fk("project.id", ondelete="CASCADE"))
    dataset_id: int | None = Field(
        default=None,
        sa_column=_fk("dataset.id", ondelete="SET NULL", nullable=True),
    )
    batch_id: int | None = Field(
        default=None,
        sa_column=_fk("batch.id", ondelete="SET NULL", nullable=True),
    )
    model_version_id: int = Field(sa_column=_fk("model_version.id", ondelete="CASCADE"))
    record_seq: int | None = Field(default=None)
    date: str = Field(default="")
    clinician_pseudonym: str | None = Field(default=None)
    subgroup: str | None = Field(default=None)
    human_decision: int | None = Field(default=None)
    model_output: int | None = Field(default=None)
    ground_truth: int | None = Field(default=None)
    # Nombres de clase.
    human_class: str | None = Field(default=None)
    model_class: str | None = Field(default=None)
    truth_class: str | None = Field(default=None)
    # Cifras de una regresión con rango; los
    # enteros guardan el 0/1 de pertenencia.
    human_value: float | None = Field(default=None)
    model_value: float | None = Field(default=None)
    truth_value: float | None = Field(default=None)
    created_at: str = Field(default_factory=now_iso)


class Outcome(SQLModel, table=True):
    """Resultado agregado por periodo: el resultado del sistema
    combinado, ingerido a mano por periodo y métrica. `baseline` y `target` los
    reserva la capa de valor y por ahora van siempre nulos."""

    __tablename__ = "outcome"
    # Una fila por clave; habilita el upsert atómico.
    __table_args__ = (
        Index("uq_outcome_clave", "project_id", "period", "metric_key", "source", unique=True),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(default=0, index=True)
    period: str = Field(default="")
    metric_key: str = Field(default="")
    value: float | None = Field(default=None)
    source: str = Field(default="")
    baseline: float | None = Field(default=None)
    target: float | None = Field(default=None)
    created_at: str = Field(default_factory=now_iso)


# ---------------------------------------------------------------------------
# Auditoría de la interacción y matriz de riesgos
# ---------------------------------------------------------------------------


class Dossier(SQLModel, table=True):
    """Dossier de auditoría de la interacción: las
    respuestas de los tres formularios de `interaction_review` (perfil del
    sistema, experiencia de uso, inventario de documentos), como
    `{pregunta: respuesta}`, más el resumen determinista de deskilling
    si se adjuntó. Las respuestas solo viven aquí: los eventos del diario
    llevan `system_name`, `domain` y `telemetry_included`, nunca el texto
    (privacidad de `interaction_review`)."""

    __tablename__ = "dossier"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(sa_column=_fk("project.id", ondelete="CASCADE"))
    system_name: str = Field(default="")
    domain: str = Field(default="")
    profile_json: Any | None = Field(default=None, sa_column=_json_col())
    experience_json: Any | None = Field(default=None, sa_column=_json_col())
    inventory_json: Any | None = Field(default=None, sa_column=_json_col())
    telemetry_included: bool = Field(default=False)
    telemetry_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    summary: str = Field(default="", sa_column=Column(Text, nullable=False, default=""))
    sha256: str = Field(default="")
    actor: str = Field(default="")
    role: str | None = Field(default=None)
    motivo: str = Field(default="")
    created_at: str = Field(default_factory=now_iso)


class DossierReview(SQLModel, table=True):
    """Revisión de un dossier: `b0` sin LLM en la cola `rapida`;
    `p3` y `auto` en la cola `llm`. Guarda hallazgos, crosswalk e informe HTML
    con su bloque de reproducibilidad (versión del paquete, hash del corpus,
    sha256 del dossier y del prompt). `error` es el mensaje legible cuando
    `status="error"` (LLM sin configurar, por ejemplo), nunca un 500."""

    __tablename__ = "dossier_review"

    id: int | None = Field(default=None, primary_key=True)
    dossier_id: int = Field(sa_column=_fk("dossier.id", ondelete="CASCADE"))
    approach: str = Field(default="b0")
    status: str = Field(default="pendiente", index=True)
    findings_json: Any | None = Field(default=None, sa_column=_json_col())
    crosswalk_json: Any | None = Field(default=None, sa_column=_json_col())
    report_html: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    package_version: str = Field(default="")
    corpus_hash: str = Field(default="")
    dossier_sha256: str = Field(default="")
    prompt_sha256: str | None = Field(default=None)
    llm_backend: str | None = Field(default=None)
    model: str | None = Field(default=None)
    job_id: int | None = Field(default=None, index=True)
    error: str | None = Field(default=None)
    actor: str = Field(default="")
    role: str | None = Field(default=None)
    motivo: str = Field(default="")
    created_at: str = Field(default_factory=now_iso)
    finished_at: str | None = Field(default=None)


class Risk(SQLModel, table=True):
    """Riesgo del registro por proyecto: una celda de la
    matriz impacto x probabilidad (niveles 1 a 5) con `level` derivado de la
    tabla explícita de `human/risk_levels.py`, nunca de un producto. `code`
    es `R-nnn`, correlativo por proyecto y nunca reutilizado. Nace de una
    alerta (`origin_alert_id`) o a mano. Cerrar es terminal en v1."""

    __tablename__ = "risk"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_risk_project_code"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(sa_column=_fk("project.id", ondelete="CASCADE"))
    code: str = Field(default="")
    impact_level: int = Field(default=1)
    probability_level: int = Field(default=1)
    level: str = Field(default="bajo")
    title: str = Field(default="")
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    origin_alert_id: int | None = Field(
        default=None, sa_column=_fk("alert.id", ondelete="SET NULL", nullable=True)
    )
    monitor_type: str | None = Field(default=None)
    status: str = Field(default="abierto", index=True)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class RiskMovement(SQLModel, table=True):
    """Movimiento de un riesgo: una fila cambia de celda
    (`from_*`/`to_*` de impacto y probabilidad, estado nulo) o de estado
    (`from_status`/`to_status`, celda sin cambio), nunca las dos cosas. El
    alta también deja una fila (todo `from_*` nulo). Con motivo obligatorio,
    como toda acción humana del repo."""

    __tablename__ = "risk_movement"

    id: int | None = Field(default=None, primary_key=True)
    risk_id: int = Field(sa_column=_fk("risk.id", ondelete="CASCADE"))
    from_impact: int | None = Field(default=None)
    from_probability: int | None = Field(default=None)
    to_impact: int | None = Field(default=None)
    to_probability: int | None = Field(default=None)
    from_status: str | None = Field(default=None)
    to_status: str | None = Field(default=None)
    actor: str = Field(default="")
    role: str | None = Field(default=None)
    motivo: str = Field(default="", sa_column=Column(Text, nullable=False, default=""))
    correlation_id: str | None = Field(default=None)
    created_at: str = Field(default_factory=now_iso, index=True)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


class DemoScenario(SQLModel, table=True):
    """Guion de demo sembrado desde `vigia.sim.scenarios.SCENARIOS`."""

    __tablename__ = "demo_scenario"

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(sa_column=Column(String, nullable=False, unique=True, index=True))
    title: str = Field(default="")
    domain: str = Field(default="")
    description: str = Field(default="", sa_column=Column(Text, nullable=False, default=""))
    phases_json: Any | None = Field(default=None, sa_column=_json_col())
    default_params_json: Any | None = Field(default=None, sa_column=_json_col())


class DemoRun(SQLModel, table=True):
    """Reproducción de un guion sobre un proyecto de demo."""

    __tablename__ = "demo_run"

    id: int | None = Field(default=None, primary_key=True)
    scenario_key: str = Field(default="", index=True)
    project_id: int = Field(sa_column=_fk("project.id", ondelete="CASCADE"))
    mode: str = Field(default="enlatado")
    source: str = Field(default="canned")
    with_human: bool = Field(default=False)
    params_json: Any | None = Field(default=None, sa_column=_json_col())
    current_phase: int = Field(default=0)
    status: str = Field(default="lista")
    result_json: Any | None = Field(default=None, sa_column=_json_col())
    human_seed: int = Field(default=0)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


# ---------------------------------------------------------------------------
# Diario y colas
# ---------------------------------------------------------------------------


class Event(SQLModel, table=True):
    """Diario de tres carriles (humano, agente, modelo; más sistema). Append-only por triggers."""

    __tablename__ = "event"
    __table_args__ = (Index("ix_event_object", "object_type", "object_id"),)

    id: int | None = Field(default=None, primary_key=True)
    ts: str = Field(default_factory=now_iso, index=True)
    actor_kind: str = Field(default="sistema", index=True)
    actor_id: str = Field(default="")
    role: str | None = Field(default=None)
    action: str = Field(default="")
    object_type: str = Field(default="")
    object_id: int | None = Field(default=None)
    project_id: int | None = Field(default=None, index=True)
    before_json: Any | None = Field(default=None, sa_column=_json_col())
    after_json: Any | None = Field(default=None, sa_column=_json_col())
    motivo: str | None = Field(default=None)
    correlation_id: str | None = Field(default=None, index=True)
    job_id: int | None = Field(default=None, index=True)


class Job(SQLModel, table=True):
    """Trabajo de una de las dos colas en proceso."""

    __tablename__ = "job"

    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(default="")
    queue: str = Field(default="rapida", index=True)
    status: str = Field(default="pendiente", index=True)
    progress: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    message: str = Field(default="")
    params_json: Any | None = Field(default=None, sa_column=_json_col())
    result_json: Any | None = Field(default=None, sa_column=_json_col())
    error: str | None = Field(default=None)
    cancel_requested: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, default=False),
    )
    project_id: int | None = Field(default=None, index=True)
    correlation_id: str | None = Field(default=None, index=True)
    created_at: str = Field(default_factory=now_iso, index=True)
    started_at: str | None = Field(default=None)
    finished_at: str | None = Field(default=None)
