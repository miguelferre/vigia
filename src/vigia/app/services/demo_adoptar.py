"""Adopción de la línea base que subió el usuario al atar una reproducción.

`create_run` con `project_id` arranca en la fase 1 cuando el proyecto ya tiene
un lote de línea base y ninguno de producción (`_attach_project`). Ese lote
lo ingirió el formulario real, no `next_phase`, así que le falta lo que la
fase 0 del guion hace después de ingerir: congelar la línea base en la
versión activa (sin ella el monitor de deriva no tiene con qué comparar),
calcular la explicación global si la fase la declara y evaluar el lote. Aquí
se completa eso y se deja el resumen de la fase en `result_json`, con el
mismo formato que `next_phase`, para que el frontend lea `result[0]` como
la fase `b1` tanto si la reproducción se ató como si la creó la demo. Un
lote sin registros (no debería darse por API; sí en tests de la semántica
del atado) solo se etiqueta y se congela: no hay nada que evaluar.

Si el lote ya tiene evaluaciones (el usuario dejó marcado «evaluar al
terminar»), no se vuelve a evaluar: el resumen se construye con la última
evaluación de cada monitor; la deriva puede quedar `sin_datos` porque se
evaluó antes de congelar. La demo guiada precarga esa casilla apagada.

Antes de evaluar, el atado fija los umbrales de calidad de
`scenario.umbrales_calidad` en el proyecto (`_fijar_umbral_calidad_demo`)
para que el monitor de calidad salga en correcto en todas las fases del
guion; `_crear_proyecto_demo` (`demo_player.py`) hace lo mismo para el
camino sin `project_id`, antes de que se reproduzca ninguna fase. Al
terminar con `b1`, fecha el lote y sus evaluaciones con la fecha simulada de
la fase (`_fechar_lote_y_derivados`, seis semanas atrás para `b1` aunque se
haya subido hoy: es un proyecto de demo) y reproduce `b2` a `b5` enlatados
con el mismo camino que `next_phase` (`demo_player._reproducir_fase`, import
local más abajo para no crear un ciclo), dejando sus resúmenes detrás del de
`b1` en `run.result_json`.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from vigia.app.bus import EventBus
from vigia.app.events import ACTOR_SISTEMA, Actor, record_event
from vigia.app.models import (
    Alert,
    Batch,
    DemoRun,
    Evaluation,
    Explanation,
    ModelVersion,
    Monitor,
    Project,
    Record,
    now_iso,
)
from vigia.app.services import explain as explain_service
from vigia.app.services import monitors as monitors_service
from vigia.app.services import projects as projects_service
from vigia.app.services.evaluate import evaluate_batch as evaluate_batch_service
from vigia.core.engine import matches_expected
from vigia.core.schema import MonitorThresholds, State, Threshold, ThresholdKind
from vigia.sim.scenarios import Phase, Scenario, fecha_simulada_fase

__all__ = ["adoptar_linea_base"]

_MOTIVO_UMBRALES_DEMO = "demo guiada: calidad en correcto en todas las fases"


def _fijar_umbral_calidad_demo(
    session: Session,
    project: Project,
    *,
    umbrales: dict[str, float],
    actor: Actor,
    bus: EventBus | None,
) -> None:
    """Fija los umbrales
    inferiores de calidad de `umbrales` (`Scenario.umbrales_calidad` del
    guion) en el proyecto de la demo, con motivo y evento en el diario.
    No hace nada si `umbrales` está vacío (guiones antiguos, sin umbrales).

    Con la banda de aviso del 10 % (`core/states.py::classify_with_motivo`),
    cada métrica necesita `valor >= umbral × 1,1` para leer `ok`; los valores
    de `caso_digestivo` (`scenarios.py`) están elegidos así para sus siete
    fases, verificado con `core.engine.run_scenario`. Solo toca el proyecto
    de la demo (siempre `is_demo` aquí); el motor y los demás
    proyectos no cambian.
    """
    if not umbrales:
        return
    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == project.id, Monitor.type == "quality")
    ).first()
    if monitor is None:  # pragma: no cover - create_project siempre deja un monitor quality
        return
    actuales = MonitorThresholds(**(monitor.thresholds_json or {"thresholds": []}))
    nuevos = [
        t.model_copy(update={"value": umbrales[t.metric_key]})
        if t.metric_key in umbrales and t.kind == ThresholdKind.lower_limit
        else t
        for t in actuales.thresholds
    ]
    ya_cubiertas = {t.metric_key for t in nuevos if t.kind == ThresholdKind.lower_limit}
    for metric_key in sorted(set(umbrales) - ya_cubiertas):
        nuevos.append(
            Threshold(metric_key=metric_key, kind=ThresholdKind.lower_limit, value=umbrales[metric_key])
        )
    monitors_service.patch_monitor(
        session,
        monitor,
        actor=actor,
        role=actor.role,
        motivo=_MOTIVO_UMBRALES_DEMO,
        thresholds={"thresholds": [t.model_dump(mode="json") for t in nuevos]},
        bus=bus,
    )


def _fechar_lote_y_derivados(
    session: Session,
    project: Project,
    *,
    fecha: str,
    evaluaciones: Iterable[Evaluation],
    alert_ids_antes: set[int],
) -> None:
    """Backdata `Evaluation.created_at` de `evaluaciones` (todas las del
    lote, se hayan creado ahora o antes de atar) y `Alert.opened_at` de las
    alertas del proyecto que no estaban en `alert_ids_antes`: las que abre
    esta evaluación, no las que ya existían y se reabren, que conservan su
    fecha real de apertura. Usada tanto para `b1` (aquí) como para `b2..b5`
    y el resto de fases (`demo_player._reproducir_fase`).
    """
    for ev in evaluaciones:
        ev.created_at = fecha
        session.add(ev)
    alertas_nuevas = [
        a
        for a in session.exec(select(Alert).where(Alert.project_id == project.id)).all()
        if a.id not in alert_ids_antes
    ]
    for alerta in alertas_nuevas:
        alerta.opened_at = fecha
        session.add(alerta)
    session.flush()


def _kind_monitor_explain(session: Session, project: Project) -> str:
    """Mismo criterio que `demo_player._kind_monitor_explain` (sin importarlo: ciclo)."""
    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == project.id, Monitor.type == "explain")
    ).first()
    configurado = (monitor.config_json or {}).get("kind") if monitor else None
    return "shap" if configurado == "global_shap" else "permutation"


def _estados_ya_evaluados(session: Session, lote: Batch) -> dict[str, str]:
    """`worst_state` de la última evaluación de cada monitor del lote."""
    evaluaciones = session.exec(
        select(Evaluation, Monitor.type)
        .join(Monitor, Monitor.id == Evaluation.monitor_id)  # type: ignore[arg-type]
        .where(Evaluation.batch_id == lote.id)
        .order_by(Evaluation.created_at)  # type: ignore[arg-type]
    ).all()
    estados: dict[str, str] = {}
    for evaluacion, tipo in evaluaciones:
        if evaluacion.worst_state is not None:
            estados[tipo] = evaluacion.worst_state
    return estados


def adoptar_linea_base(
    session: Session,
    run: DemoRun,
    scenario: Scenario,
    project: Project,
    lote: Batch,
    *,
    actor: Actor,
    data_dir: Path,
    bus: EventBus | None = None,
) -> dict[str, Any]:
    """Completa la fase 0 sobre el lote del usuario, reproduce `b2..b5` y
    devuelve el resumen de `b1` (ver docstring del módulo).
    `data_dir` es donde `_reproducir_fase` deja los JSON de cada fase
    (mismo `data_dir` que usa `next`).
    """
    phase: Phase = scenario.phases[0]
    version = session.get(ModelVersion, lote.model_version_id)
    if version is None:  # pragma: no cover - el lote siempre apunta a una versión del proyecto
        version = session.get(ModelVersion, project.active_version_id)
    assert version is not None

    # Para saber qué alertas abre esta adopción (y no las que ya
    # hubiera, si el usuario evaluó el lote antes de atar). Antes de
    # evaluar, para que b1 (y luego b2..e1_recovery) salgan en correcto.
    alert_ids_antes = set(session.exec(select(Alert.id).where(Alert.project_id == project.id)).all())
    if scenario.umbrales_calidad:
        _fijar_umbral_calidad_demo(
            session, project, umbrales=scenario.umbrales_calidad, actor=actor, bus=bus
        )

    motivo_adopcion = f"guion {run.scenario_key}, línea base subida por el usuario"
    ya_congelada = version.frozen_at is not None
    if not ya_congelada:
        version = projects_service.freeze_baseline(
            session,
            version,
            lote,
            actor=actor,
            motivo=motivo_adopcion,
            bus=bus,
        )

    estados = _estados_ya_evaluados(session, lote)
    explain_calculado = (
        session.exec(select(Explanation).where(Explanation.batch_id == lote.id)).first() is not None
    )
    hay_registros = session.exec(select(Record).where(Record.batch_id == lote.id)).first() is not None
    if not estados and hay_registros:
        explicacion = None
        if phase.explain_global:
            explicacion = explain_service.explain_global(
                session,
                version,
                kind=_kind_monitor_explain(session, project),
                batch=lote,
                bus=bus,
            )
            explain_calculado = True
        elif project.explain_auto:
            explicacion = explain_service.maybe_auto_explain(session, lote, version, project, bus=bus)
            explain_calculado = explicacion is not None
        evaluaciones = evaluate_batch_service(
            session,
            lote,
            trigger="demo",
            bus=bus,
            with_cross=not run.with_human,
            explanation=explicacion,
        )
        estados = {tipo: ev.worst_state for tipo, ev in evaluaciones.items() if ev.worst_state}

    coincide = {
        tipo: matches_expected(tipo, State(estados[tipo]), esperado)
        for tipo, esperado in phase.expected.items()
        if tipo in estados
    }
    resumen: dict[str, Any] = {
        "phase_key": phase.key,
        "batch_id": lote.id,
        "states": estados,
        "expected": phase.expected,
        "matches_expected": coincide,
        "cross_alerts": [],
        "explain_calculado": explain_calculado,
        "adoptado": True,
    }

    # Fecha simulada de b1 (seis semanas atrás), también en sus
    # evaluaciones (nuevas o de antes de atar: todas las del lote).
    fecha_simulada = fecha_simulada_fase(phase)
    if fecha_simulada is not None:
        lote.created_at = fecha_simulada
        session.add(lote)
        evaluaciones_lote = session.exec(
            select(Evaluation).where(Evaluation.batch_id == lote.id)
        ).all()
        _fechar_lote_y_derivados(
            session,
            project,
            fecha=fecha_simulada,
            evaluaciones=evaluaciones_lote,
            alert_ids_antes=alert_ids_antes,
        )

    run.result_json = [resumen]
    run.status = "en_curso"
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
        # Con la versión ya congelada al ingerir (motivo «congelado
        # automático»), el motivo del guion se conserva aquí, en el evento de
        # la fase 0, en vez de perderse.
        motivo=f"{motivo_adopcion}; la versión ya llegó congelada al ingerirla" if ya_congelada else None,
        after=resumen,
        bus=bus,
    )

    # B2 a b5 enlatados, mismo camino que `next_phase`. Import local:
    # `demo_player` importa este módulo a nivel de módulo (`create_run`
    # llama a `adoptar_linea_base`); importar `_reproducir_fase` aquí arriba
    # crearía un ciclo. En tiempo de ejecución el módulo ya está cargado del
    # todo cuando esta función se invoca de verdad.
    from vigia.app.services.demo_player import _reproducir_fase

    # Solo las semanas de línea base que siguen a la del usuario (fases
    # `kind="baseline"` consecutivas, sin congelar): con `caso_digestivo` son
    # b2 a b5; un guion con una sola línea base, o atado por `project_id` con
    # otro guion, no reproduce nada más aquí (eso lo hace `next`).
    while run.current_phase < len(scenario.phases):
        siguiente = scenario.phases[run.current_phase]
        if siguiente.kind != "baseline" or siguiente.freeze_baseline:
            break
        _reproducir_fase(
            session,
            run,
            scenario,
            project,
            run.current_phase,
            data_dir=data_dir,
            job=None,
            bus=bus,
        )

    return resumen
