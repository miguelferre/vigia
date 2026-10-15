"""Reproductor de guiones de demo sobre la BD.

`create_run` monta un proyecto de demo con una versión `sim_logistic` por cada
versión de modelo distinta que aparece en las fases del guion (la primera,
activa); con `project_id` ata la reproducción a un
proyecto que el usuario ya ha creado con el formulario real en vez de crear
uno nuevo (`_attach_project`). `next_phase` materializa una fase (`vigia.sim.scenarios`), la
registra como dataset `source="demo"`/`kind="combined"` con el mapeo
puntuado del harness (`vigia.core.engine._harness_scored_mapping`, privado
pero reutilizado aquí), la ingiere como lote y la
evalúa con `services.evaluate.evaluate_batch`; si `with_human`, simula el
diario de uso de la fase (`vigia.sim.human.simulate_decisions`, mismas
semillas y ventanas temporales que `engine._evaluar_cruzadas`) y dispara la
evaluación de alertas cruzadas del carril C3 (`services.human_layer`); si
`phase.explain_global`, calcula antes `services.explain.explain_global` sobre
el lote de la fase, con el `kind` configurado en el monitor `explain` del
proyecto, y pasa su resultado a `evaluate_batch_service(..., explanation=)`:
es el motor quien la compara contra la referencia de la versión y publica
`explain_stability_ndcg`. `play` encadena
`next_phase` hasta agotar el guion; `reset` reutiliza
`services.projects.reset_project` y recrea el
`demo_run` con el mismo id. `run_lab` materializa una fase con
`source="generate"` y parámetros a la carta sobre el proyecto de una
reproducción sin avanzar su guion (laboratorio).
"""

from __future__ import annotations

import inspect
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from vigia.app.bus import EventBus
from vigia.app.errores import no_encontrado
from vigia.app.events import ACTOR_SISTEMA, Actor, record_event
from vigia.app.jobs import JobContext
from vigia.app.models import (
    Alert,
    Batch,
    Dataset,
    DemoRun,
    ModelVersion,
    Monitor,
    Project,
    Record,
    UsageLog,
    now_iso,
)
from vigia.app.services import explain as explain_service
from vigia.app.services import ingest as ingest_service
from vigia.app.services import projects as projects_service
from vigia.app.services.demo_adoptar import (
    _fechar_lote_y_derivados,
    _fijar_umbral_calidad_demo,
    adoptar_linea_base,
)
from vigia.app.services.evaluate import evaluate_batch as evaluate_batch_service
from vigia.core.engine import _harness_scored_mapping, matches_expected
from vigia.core.schema import State
from vigia.sim import serialize as ser
from vigia.sim.human import HumanParams, simulate_decisions
from vigia.sim.scenarios import (
    _GENERATORS,
    Phase,
    PhaseData,
    Scenario,
    fecha_simulada_fase,
    get_scenario,
    materialize_phase,
)

__all__ = [
    "create_run",
    "lab_params_for_phase",
    "next_phase",
    "play",
    "reset",
    "resolve_lab_phase",
    "run_lab",
    "run_to_dict",
]

_SISTEMA = Actor(kind=ACTOR_SISTEMA[0], id=ACTOR_SISTEMA[1])
_START_DATE = date(2026, 1, 5)
_LABEL_A_INT = {"refer": 1, "no-refer": 0}
_SOURCES_VALIDOS = ("canned", "generate")


def run_to_dict(run: DemoRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "scenario_key": run.scenario_key,
        "project_id": run.project_id,
        "mode": run.mode,
        "source": run.source,
        "with_human": run.with_human,
        "params": run.params_json,
        "current_phase": run.current_phase,
        "status": run.status,
        "result": run.result_json,
        "human_seed": run.human_seed,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


# ---------------------------------------------------------------------------
# Creación
# ---------------------------------------------------------------------------


def _crear_proyecto_demo(
    session: Session,
    scenario: Scenario,
    *,
    etiquetas_version: list[str],
    fairness_window_n: int,
    project_name: str | None,
    actor: Actor,
    bus: EventBus | None,
) -> tuple[Project, int, None]:
    """Proyecto de demo nuevo, con una versión `sim_logistic` por etiqueta del guion.

    Camino original (sin `project_id`): arranca siempre en la fase 0, `next`
    ingiere la línea base enlatada. si el
    guion declara `umbrales_calidad`, se fijan aquí, antes de que exista
    ninguna fase reproducida (`next`/`play` los usarán ya puestos).
    """
    nombre = project_name or f"demo-{scenario.key}-{uuid4().hex[:8]}"
    project = projects_service.create_project(
        session,
        name=nombre,
        domain=scenario.domain,
        store_features=True,
        model_kind="sim_logistic",
        actor=actor,
        bus=bus,
    )
    project.is_demo = True
    project.deployment_stage = "demo"
    session.add(project)
    session.flush()

    primera_version = session.exec(
        select(ModelVersion).where(ModelVersion.project_id == project.id)
    ).first()
    if primera_version is None:  # pragma: no cover - create_project siempre deja una versión
        raise HTTPException(500, "el proyecto de demo no tiene versión inicial")
    if primera_version.label != etiquetas_version[0]:
        primera_version.label = etiquetas_version[0]
    primera_version.fairness_window_n = fairness_window_n
    session.add(primera_version)
    session.flush()

    for etiqueta in etiquetas_version[1:]:
        projects_service.create_version(
            session,
            project,
            label=etiqueta,
            model_kind="sim_logistic",
            fairness_window_n=fairness_window_n,
            actor=actor,
            motivo=f"guion {scenario.key}: versión {etiqueta}",
            bus=bus,
        )

    if scenario.umbrales_calidad:
        _fijar_umbral_calidad_demo(
            session, project, umbrales=scenario.umbrales_calidad, actor=actor, bus=bus
        )
    return project, 0, None


def _attach_project(
    session: Session,
    project_id: int,
    *,
    fairness_window_n: int,
    scenario: Scenario,
    actor: Actor,
    bus: EventBus | None,
) -> tuple[Project, int, Batch | None]:
    """Proyecto que el usuario ya ha creado, al que atar la reproducción.

    404 si no existe; 409 si ya tiene una reproducción de demo (dos `demo_run`
    sobre el mismo proyecto pisarían `current_phase` y los lotes entre sí);
    422 con el mensaje fijo «la demo necesita un modelo simulado» si su
    versión activa no es `sim_logistic` (lo mira el frontend para guiar al
    usuario). Marca `is_demo`/`deployment_stage` sin tocar los monitores, que
    son los que ya trae el proyecto.

    Sin lotes: arranca en la fase 0, fija `fairness_window_n` al del guion (el
    proyecto no lo tenía configurado todavía) y, si el guion declara
    `umbrales_calidad`, los fija también (`_crear_proyecto_demo` ya
    lo hacía en su rama; aquí faltaba, así que un proyecto atado sin lotes a
    `caso_digestivo` no salía en correcto en calidad). Con un lote de línea
    base (`Dataset.role == "baseline"`, el dataset del lote) y ninguno de
    producción: arranca en la fase 1 (la línea base la subió el usuario, no
    hay que reingerirla) y devuelve ese lote para que quien llama le ponga
    `phase_label="b1"`; `fairness_window_n` no se toca, la versión ya está
    configurada (los umbrales de calidad los fija `adoptar_linea_base` antes
    de evaluar b1). Cualquier otra combinación de lotes arranca en la fase 0
    sin tocar `fairness_window_n` (caso no cubierto por el guion; no bloquea).
    """
    project = session.get(Project, project_id)
    if project is None:
        raise no_encontrado("modelo", project_id, "modelos")

    if session.exec(select(DemoRun).where(DemoRun.project_id == project_id)).first() is not None:
        raise HTTPException(409, "el proyecto ya tiene una reproducción de demo")

    version_activa = (
        session.get(ModelVersion, project.active_version_id)
        if project.active_version_id is not None
        else None
    )
    if version_activa is None or version_activa.model_kind != "sim_logistic":
        raise HTTPException(422, "la demo necesita un modelo simulado")

    project.is_demo = True
    project.deployment_stage = "demo"
    session.add(project)

    lotes = session.exec(select(Batch).where(Batch.project_id == project_id)).all()
    if not lotes:
        version_activa.fairness_window_n = fairness_window_n
        session.add(version_activa)
        session.flush()
        if scenario.umbrales_calidad:
            _fijar_umbral_calidad_demo(
                session, project, umbrales=scenario.umbrales_calidad, actor=actor, bus=bus
            )
        return project, 0, None

    dataset_ids = {b.dataset_id for b in lotes if b.dataset_id is not None}
    datasets: dict[int, Dataset] = {}
    if dataset_ids:
        for dataset in session.exec(select(Dataset).where(Dataset.id.in_(dataset_ids))).all():  # type: ignore[attr-defined]
            datasets[dataset.id] = dataset

    def _role(batch: Batch) -> str | None:
        dataset = datasets.get(batch.dataset_id) if batch.dataset_id is not None else None
        return dataset.role if dataset is not None else None

    baseline = sorted((b for b in lotes if _role(b) == "baseline"), key=lambda b: b.seq)
    produccion = [b for b in lotes if _role(b) == "production"]
    session.flush()
    if baseline and not produccion:
        return project, 1, baseline[0]
    return project, 0, None


def create_run(
    session: Session,
    *,
    scenario_key: str,
    source: str = "canned",
    with_human: bool = False,
    params: dict[str, Any] | None = None,
    project_name: str | None = None,
    project_id: int | None = None,
    data_dir: Path,
    actor: Actor,
    bus: EventBus | None = None,
) -> DemoRun:
    """Valida el guion y crea el `demo_run`.

    Sin `project_id`, crea el proyecto de demo con sus versiones
    (`_crear_proyecto_demo`, comportamiento original). Con `project_id`
, lo ata a un proyecto que el usuario ya ha creado
    con el formulario real (`_attach_project`): la demo no crea nada que el
    usuario pueda crear él mismo. `data_dir` es donde
    `adoptar_linea_base` deja los JSON de `b2..b5` al reproducirlos; mismo
    `data_dir` que usan `next`/`play`.
    """
    try:
        scenario = get_scenario(scenario_key)
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0] if exc.args else exc)) from exc
    if source not in _SOURCES_VALIDOS:
        raise HTTPException(422, f"source debe ser uno de {_SOURCES_VALIDOS}; se recibió {source!r}")

    params = dict(params or {})
    fairness_window_n = int(params.get("min_records", scenario.default_params.get("min_records", 200)))

    etiquetas_version: list[str] = []
    for fase in scenario.phases:
        if fase.model_version not in etiquetas_version:
            etiquetas_version.append(fase.model_version)

    if project_id is not None:
        project, current_phase, lote_baseline = _attach_project(
            session,
            project_id,
            fairness_window_n=fairness_window_n,
            scenario=scenario,
            actor=actor,
            bus=bus,
        )
    else:
        project, current_phase, lote_baseline = _crear_proyecto_demo(
            session,
            scenario,
            etiquetas_version=etiquetas_version,
            fairness_window_n=fairness_window_n,
            project_name=project_name,
            actor=actor,
            bus=bus,
        )

    # Se guarda la clave vigente, nunca la antigua con la que llegó la petición.
    run = DemoRun(
        scenario_key=scenario.key,
        project_id=project.id,
        mode="enlatado" if source == "canned" else "laboratorio",
        source=source,
        with_human=with_human,
        params_json=params,
        current_phase=current_phase,
        status="lista",
        result_json=[],
    )
    session.add(run)
    session.flush()

    if lote_baseline is not None:
        lote_baseline.phase_label = "b1"
        session.add(lote_baseline)
        session.flush()
        # El lote lo ingirió el formulario real; lo que la fase 0 hace
        # después de ingerir (congelar, explicar, evaluar, resumir) se completa
        # aquí para que la reproducción atada sea idéntica a la creada: además fecha b1 y reproduce b2..b5 enlatados.
        adoptar_linea_base(
            session, run, scenario, project, lote_baseline, actor=actor, data_dir=data_dir, bus=bus
        )

    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="demo.run_creada",
        object_type="demo_run",
        object_id=run.id,
        project_id=project.id,
        after={
            "scenario_key": scenario.key,
            "source": source,
            "with_human": with_human,
            "project_id": project.id,
            "attached": project_id is not None,
        },
        bus=bus,
    )
    session.commit()
    session.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Reproducción, fase a fase
# ---------------------------------------------------------------------------


def _find_version(session: Session, project: Project, label: str) -> ModelVersion:
    """La versión `label` del proyecto, o 422 si el guion referencia una que no existe."""
    version = session.exec(
        select(ModelVersion).where(ModelVersion.project_id == project.id, ModelVersion.label == label)
    ).first()
    if version is None:
        raise HTTPException(422, f"el proyecto no tiene la versión {label!r} del guion")
    return version


def _kind_monitor_explain(session: Session, project: Project) -> str:
    """`kind` (permutación o SHAP) configurado en el monitor `explain` del proyecto."""
    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == project.id, Monitor.type == "explain")
    ).first()
    configurado = (monitor.config_json or {}).get("kind") if monitor else None
    return "shap" if configurado == "global_shap" else "permutation"


def _registrar_dataset_fase(
    session: Session,
    project: Project,
    phase: Any,
    phase_data: PhaseData,
    *,
    data_dir: Path,
    job: JobContext | None,
    correlation_id: str | None,
    bus: EventBus | None,
) -> Dataset:
    """Registra el frame puntuado de la fase como dataset `combined`/`demo` ya mapeado.

    No hay multipart que envolver (`register_upload` acepta bytes en crudo): se
    reutiliza tal cual, sin duplicar la lógica de privacidad. Las decisiones de
    privacidad son `hashear` para las columnas que marque el informe (aquí
    siempre `Patient_Id` y `Episode_Id`, los dos identificadores del harness).
    """
    contenido = phase_data.df_scored.to_json(orient="records").encode("utf-8")
    role = "baseline" if phase.freeze_baseline else "production"
    job_id = job.job_id if job else None
    dataset, _preview = ingest_service.register_upload(
        session,
        project,
        file_bytes=contenido,
        filename=f"{phase.key}_combined.json",
        kind="combined",
        role=role,
        name=f"{phase.key} (guion, combinado)",
        source="demo",
        data_dir=data_dir,
        actor=_SISTEMA,
        correlation_id=correlation_id,
        job_id=job_id,
        bus=bus,
    )
    mapping = _harness_scored_mapping()
    return ingest_service.set_mapping(
        session,
        dataset,
        mapping,
        actor=_SISTEMA,
        correlation_id=correlation_id,
        job_id=job_id,
        bus=bus,
    )


def _reproducir_uso(
    session: Session,
    project: Project,
    version: ModelVersion,
    *,
    phase: Any,
    phase_data: PhaseData,
    batch: Batch,
    index: int,
    n_fases: int,
    human_seed: int,
    params_override: dict[str, Any] | None,
    scenario_human: dict[str, Any] | None = None,
    job: JobContext | None,
    bus: EventBus | None,
) -> list[dict[str, Any]]:
    """Simula el diario de uso de la fase e inserta las alertas cruzadas.

    Los parámetros humanos salen del guion (`Scenario.human_params`) y
    quien reproduce puede pisarlos con `params_override["human"]`.
    """
    from vigia.app.services.human_layer import evaluate_cross_for_project

    primer_seq = session.exec(
        select(Record.seq).where(Record.batch_id == batch.id).order_by(Record.seq).limit(1)  # type: ignore[arg-type]
    ).first()
    record_seq_start = int(primer_seq) if primer_seq is not None else 0

    human_kwargs = {**(scenario_human or {}), **((params_override or {}).get("human") or {})}
    human_params = HumanParams(**human_kwargs)
    t_start = index / n_fases
    t_end = (index + 1) / n_fases
    fecha_inicio = _START_DATE + timedelta(days=7 * index)

    df_uso = simulate_decisions(
        phase_data.df_scored,
        seed=human_seed + index,
        params=human_params,
        t_start=t_start,
        t_end=t_end,
        start_date=fecha_inicio,
        model_version=phase.model_version,
        record_seq_start=record_seq_start,
    )

    filas = [
        UsageLog(
            project_id=project.id,
            batch_id=batch.id,
            model_version_id=version.id,
            record_seq=int(fila["record_seq"]),
            date=str(fila["date"]),
            clinician_pseudonym=fila["clinician_pseudonym"],
            subgroup=fila["subgroup"],
            human_decision=_LABEL_A_INT.get(fila["human_decision"]),
            model_output=_LABEL_A_INT.get(fila["model_output"]),
            ground_truth=_LABEL_A_INT.get(fila["ground_truth"]),
        )
        for fila in df_uso.to_dict(orient="records")
    ]
    session.add_all(filas)
    session.flush()

    record_event(
        session,
        actor_kind=ACTOR_SISTEMA[0],
        actor_id=ACTOR_SISTEMA[1],
        action="usage_log.ingerido",
        object_type="batch",
        object_id=batch.id,
        project_id=project.id,
        after={"n_rows": len(filas), "phase": phase.key},
        job_id=job.job_id if job else None,
        correlation_id=job.correlation_id if job else None,
        bus=bus,
    )

    evaluacion_cross = evaluate_cross_for_project(
        session, project, version=version, trigger="demo", job=job, bus=bus
    )
    if evaluacion_cross is None:
        return []
    resultado = evaluacion_cross.result_json or {}
    return list(resultado.get("alerts") or [])


def next_phase(
    session: Session,
    run: DemoRun,
    *,
    data_dir: Path,
    job: JobContext | None = None,
    bus: EventBus | None = None,
) -> dict[str, Any]:
    """Reproduce la siguiente fase pendiente del guion y devuelve su resumen."""
    scenario = get_scenario(run.scenario_key)
    if run.current_phase >= len(scenario.phases):
        raise HTTPException(409, "el guion ya se ha reproducido por completo")

    project = session.get(Project, run.project_id)
    if project is None:
        raise no_encontrado("modelo", run.project_id, "modelos")

    return _reproducir_fase(
        session, run, scenario, project, run.current_phase, data_dir=data_dir, job=job, bus=bus
    )


def _reproducir_fase(
    session: Session,
    run: DemoRun,
    scenario: Scenario,
    project: Project,
    index: int,
    *,
    data_dir: Path,
    job: JobContext | None = None,
    bus: EventBus | None = None,
) -> dict[str, Any]:
    """Reproduce la fase `index` del guion y devuelve su resumen.

    Cuerpo de `next_phase`, compartido con `demo_adoptar.adoptar_linea_base`
    para reproducir `b2..b5` sin usuario ni job: la
    llaman `next_phase` (con `index=run.current_phase`, tal cual antes) y la
    adopción, en un bucle síncrono, tras adoptar `b1`.
    """
    n_fases = len(scenario.phases)
    phase = scenario.phases[index]

    params_override = dict(run.params_json or {}) or None
    phase_data = materialize_phase(
        phase, source=run.source, params_override=params_override, data_dir=None
    )

    carpeta = Path(data_dir) / "demo" / str(run.id)
    carpeta.mkdir(parents=True, exist_ok=True)
    ser.dump_json(phase_data.payload, carpeta / f"{phase.key}_payload.json", indent=2)
    ser.dump_json(phase_data.feedback, carpeta / f"{phase.key}_feedback.json", indent=2)

    correlation_id = job.correlation_id if job else None

    version = _find_version(session, project, phase.model_version)
    if not version.is_active:
        version = projects_service.activate_version(
            session,
            version,
            actor=_SISTEMA,
            motivo=f"guion {run.scenario_key}, fase {phase.key}",
            correlation_id=correlation_id,
            job_id=job.job_id if job else None,
            bus=bus,
        )

    dataset = _registrar_dataset_fase(
        session,
        project,
        phase,
        phase_data,
        data_dir=data_dir,
        job=job,
        correlation_id=correlation_id,
        bus=bus,
    )

    resultado_ingesta = ingest_service.ingest_dataset(
        session,
        dataset,
        model_version=version,
        phase_label=phase.key,
        orden_manipulado=phase.orden_manipulado,
        motivo_manipulacion=phase.motivo_manipulacion,
        demo_run_id=run.id,
        congelar_automatico=False,  # la fase congela con su motivo de guion
        job=job,
        correlation_id=correlation_id,
        bus=bus,
    )
    batch = session.get(Batch, resultado_ingesta.batch_id)
    if batch is None:  # pragma: no cover - ingest_dataset siempre deja un lote en modo crear
        raise HTTPException(500, "la ingesta de la fase de demo no ha producido un lote")

    # Fecha simulada de la fase (`None` en los guiones antiguos, que
    # siguen con `now_iso()` real). El lote se fecha nada más ingerir; sus
    # evaluaciones y las alertas que abra se fechan igual más abajo, cuando
    # se conocen (`alert_ids_antes` se captura antes de evaluar para saber
    # cuáles son nuevas).
    fecha_simulada = fecha_simulada_fase(phase)
    if fecha_simulada is not None:
        batch.created_at = fecha_simulada
        session.add(batch)
        session.flush()

    if phase.freeze_baseline:
        projects_service.freeze_baseline(
            session,
            version,
            batch,
            actor=_SISTEMA,
            motivo=f"guion {run.scenario_key}, fase {phase.key}",
            correlation_id=correlation_id,
            job_id=job.job_id if job else None,
            bus=bus,
        )

    # Si la fase declara explicabilidad global, se calcula
    # ANTES de evaluar el lote y su resultado viaja a evaluate_batch_service
    # como explanation=, no solo se guarda: es el motor quien compara contra
    # la referencia de la versión y publica explain_stability_ndcg.
    # Si la fase no declara explicabilidad global pero el
    # proyecto tiene `explain_auto`, se calcula la explicación automática
    # aquí, también ANTES de evaluar (nunca dos explicaciones para el mismo
    # lote: una fase con explain_global manda siempre sobre la automática).
    explicacion = None
    explain_calculado = False
    if phase.explain_global:
        explicacion = explain_service.explain_global(
            session,
            version,
            kind=_kind_monitor_explain(session, project),
            batch=batch,
            job=job,
            correlation_id=correlation_id,
            bus=bus,
        )
        explain_calculado = True
    elif project.explain_auto:
        explicacion = explain_service.maybe_auto_explain(
            session,
            batch,
            version,
            project,
            job=job,
            correlation_id=correlation_id,
            bus=bus,
        )
        explain_calculado = explicacion is not None

    alert_ids_antes = (
        set(session.exec(select(Alert.id).where(Alert.project_id == project.id)).all())
        if fecha_simulada is not None
        else set()
    )

    evaluaciones = evaluate_batch_service(
        session,
        batch,
        trigger="demo",
        job=job,
        correlation_id=correlation_id,
        bus=bus,
        with_cross=not run.with_human,
        explanation=explicacion,
    )

    if fecha_simulada is not None:
        _fechar_lote_y_derivados(
            session,
            project,
            fecha=fecha_simulada,
            evaluaciones=evaluaciones.values(),
            alert_ids_antes=alert_ids_antes,
        )

    states = {tipo: ev.worst_state for tipo, ev in evaluaciones.items()}
    coincide = {
        tipo: matches_expected(tipo, State(states[tipo]), esperado)
        for tipo, esperado in phase.expected.items()
        if tipo in states
    }

    cross_alerts: list[dict[str, Any]] = []
    if run.with_human:
        cross_alerts = _reproducir_uso(
            session,
            project,
            version,
            phase=phase,
            phase_data=phase_data,
            batch=batch,
            index=index,
            n_fases=n_fases,
            human_seed=run.human_seed,
            params_override=params_override,
            scenario_human=scenario.human_params,
            job=job,
            bus=bus,
        )

    resumen = {
        "phase_key": phase.key,
        "batch_id": batch.id,
        "states": states,
        "expected": phase.expected,
        "matches_expected": coincide,
        "cross_alerts": cross_alerts,
        "explain_calculado": explain_calculado,
    }
    resultados = list(run.result_json or [])
    resultados.append(resumen)
    run.result_json = resultados
    run.current_phase = index + 1
    run.status = "terminada" if run.current_phase >= n_fases else "en_curso"
    run.updated_at = now_iso()
    session.add(run)
    session.flush()

    record_event(
        session,
        actor_kind=ACTOR_SISTEMA[0],
        actor_id=ACTOR_SISTEMA[1],
        action="demo.fase_reproducida",
        object_type="demo_run",
        object_id=run.id,
        project_id=project.id,
        after=resumen,
        job_id=job.job_id if job else None,
        correlation_id=correlation_id,
        bus=bus,
    )
    session.commit()
    session.refresh(run)
    return resumen


def play(
    session: Session,
    run: DemoRun,
    *,
    data_dir: Path,
    job: JobContext | None = None,
    bus: EventBus | None = None,
) -> DemoRun:
    """Encadena `next_phase` hasta agotar el guion; se detiene si `job.cancelled`."""
    scenario = get_scenario(run.scenario_key)
    n_fases = len(scenario.phases)
    while run.current_phase < n_fases:
        if job is not None:
            job.raise_if_cancelled()
        fase = scenario.phases[run.current_phase]
        next_phase(session, run, data_dir=data_dir, job=job, bus=bus)
        if job is not None:
            job.progress(run.current_phase / n_fases, fase.title)
    return run


def reset(
    session: Session,
    run: DemoRun,
    *,
    actor: Actor,
    motivo: str,
    bus: EventBus | None = None,
    data_dir: Path | str | None = None,
) -> DemoRun:
    """Deja el proyecto virgen (`reset_project`) y recrea el `demo_run` con el mismo id.

    `reset_project` borra los `demo_run` del proyecto (incluido este): se
    capturan sus datos antes y se reinserta con el mismo id para que la URL
    del run siga siendo válida tras el reinicio.
    """
    project = session.get(Project, run.project_id)
    if project is None:
        raise no_encontrado("modelo", run.project_id, "modelos")

    datos = {
        "scenario_key": run.scenario_key,
        "project_id": run.project_id,
        "mode": run.mode,
        "source": run.source,
        "with_human": run.with_human,
        "params_json": run.params_json,
        "human_seed": run.human_seed,
    }
    run_id = run.id

    projects_service.reset_project(
        session, project, actor=actor, motivo=motivo, bus=bus, data_dir=data_dir
    )

    nuevo = DemoRun(id=run_id, current_phase=0, status="lista", result_json=[], **datos)
    session.add(nuevo)
    session.flush()

    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="demo.reiniciada",
        object_type="demo_run",
        object_id=nuevo.id,
        project_id=project.id,
        motivo=motivo,
        bus=bus,
    )
    session.commit()
    session.refresh(nuevo)
    return nuevo


# ---------------------------------------------------------------------------
# Laboratorio: fase generada a la carta, sin avanzar el guion
# ---------------------------------------------------------------------------


def _phase_for_key(scenario: Scenario, phase_key: str) -> Phase:
    for fase in scenario.phases:
        if fase.key == phase_key:
            return fase
    claves = ", ".join(p.key for p in scenario.phases)
    raise HTTPException(
        404, f"la fase {phase_key} no existe en el guion {scenario.key}; las fases del guion son: {claves}"
    )


def lab_params_for_phase(phase: Phase) -> list[str]:
    """Claves que el generador de laboratorio de `phase` acepta.

    Misma inspección de firma que `_validate_lab_params` usa para el 422:
    `GET /demo/scenarios` la reutiliza para anunciar, por fase, qué parámetros
    puede mover el laboratorio (`DemoScenarioPhase.lab_params`), así el
    frontend solo pinta los que de verdad existen. Fase sin generador
    conocido (no debería darse: todo el guion referencia uno): lista vacía.
    """
    generador = _GENERATORS.get(phase.generator)
    if generador is None:
        return []
    return sorted(inspect.signature(generador).parameters)


def _validate_lab_params(phase: Phase, params: dict[str, Any]) -> None:
    """422 con el nombre de la clave si `params` trae algo que el generador no acepta."""
    if phase.generator not in _GENERATORS:
        raise HTTPException(422, f"la fase {phase.key!r} no tiene generador de laboratorio")
    aceptados = set(lab_params_for_phase(phase))
    desconocidos = sorted(set(params) - aceptados)
    if desconocidos:
        raise HTTPException(
            422,
            f"el generador de la fase {phase.key!r} no acepta {', '.join(desconocidos)}; "
            f"acepta {', '.join(sorted(aceptados))}",
        )


def resolve_lab_phase(run: DemoRun, phase_key: str, params: dict[str, Any]) -> Phase:
    """Fase de `run.scenario_key` para el laboratorio, validada contra `params`.

    Se llama antes de encolar el job (desde el router) para que una fase
    desconocida o una clave de `params` que el generador no acepta lleguen
    como 404/422 reales, no como un job terminado en `error`.
    """
    scenario = get_scenario(run.scenario_key)
    phase = _phase_for_key(scenario, phase_key)
    _validate_lab_params(phase, params)
    return phase


def run_lab(
    session: Session,
    run: DemoRun,
    *,
    phase_key: str,
    params: dict[str, Any],
    seed: int | None,
    actor: Actor,
    motivo: str,
    data_dir: Path,
    job: JobContext | None = None,
    bus: EventBus | None = None,
) -> dict[str, Any]:
    """Materializa `phase_key` con `params` sobre el proyecto de `run` y la evalúa.

    Siempre `source="generate"`: los enlatados ignorarían los parámetros y
    darían un resultado que no depende de lo que ha movido quien opera el
    laboratorio. No avanza el guion (no toca `current_phase` ni `status`) y su
    resultado no se mezcla con `run.result_json`: viaja solo en el `result`
    del job, como el resto de acciones encoladas del reproductor.
    """
    phase = resolve_lab_phase(run, phase_key, params)

    project = session.get(Project, run.project_id)
    if project is None:
        raise no_encontrado("modelo", run.project_id, "modelos")

    params_generador = dict(params)
    if seed is not None:
        params_generador["seed"] = seed

    phase_data = materialize_phase(
        phase, source="generate", params_override=params_generador, data_dir=None
    )

    carpeta = Path(data_dir) / "demo" / str(run.id) / "lab"
    carpeta.mkdir(parents=True, exist_ok=True)
    sufijo = uuid4().hex[:8]
    ser.dump_json(phase_data.payload, carpeta / f"{phase.key}_{sufijo}_payload.json", indent=2)
    ser.dump_json(phase_data.feedback, carpeta / f"{phase.key}_{sufijo}_feedback.json", indent=2)

    correlation_id = job.correlation_id if job else None
    version = _find_version(session, project, phase.model_version)

    dataset = _registrar_dataset_fase(
        session,
        project,
        phase,
        phase_data,
        data_dir=data_dir,
        job=job,
        correlation_id=correlation_id,
        bus=bus,
    )
    resultado_ingesta = ingest_service.ingest_dataset(
        session,
        dataset,
        model_version=version,
        phase_label=f"lab:{phase.key}",
        orden_manipulado=phase.orden_manipulado,
        motivo_manipulacion=phase.motivo_manipulacion,
        demo_run_id=run.id,
        congelar_automatico=False,  # el laboratorio nunca congela
        job=job,
        correlation_id=correlation_id,
        bus=bus,
    )
    batch = session.get(Batch, resultado_ingesta.batch_id)
    if batch is None:  # pragma: no cover - ingest_dataset siempre deja un lote en modo crear
        raise HTTPException(500, "la ingesta del laboratorio no ha producido un lote")

    evaluaciones = evaluate_batch_service(
        session,
        batch,
        trigger="demo_lab",
        job=job,
        correlation_id=correlation_id,
        bus=bus,
        with_cross=False,
    )
    states = {tipo: ev.worst_state for tipo, ev in evaluaciones.items()}

    resumen = {
        "phase_key": phase.key,
        "batch_id": batch.id,
        "params": params_generador,
        "states": states,
    }

    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="demo.lab_ejecutada",
        object_type="demo_run",
        object_id=run.id,
        project_id=project.id,
        after=resumen,
        motivo=motivo,
        job_id=job.job_id if job else None,
        correlation_id=correlation_id,
        bus=bus,
    )
    session.commit()
    return resumen
