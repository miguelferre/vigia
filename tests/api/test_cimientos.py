"""Esquema, migraciones, diario append-only, bus, colas y /health."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlmodel import Session, select

from vigia.app.bus import EventBus
from vigia.app.content_loader import protocolo_hitos_plantilla
from vigia.app.db import make_engine, session_scope
from vigia.app.events import record_event
from vigia.app.jobs import JobCancelled, JobContext, JobManager
from vigia.app.migrations import current_version, migrate, target_version
from vigia.app.models import DemoScenario, Event, Job, Monitor, now_iso
from vigia.app.settings import Settings

TABLAS_ESPERADAS = {
    "alert",
    "alert_action",
    "batch",
    "dataset",
    "demo_run",
    "demo_scenario",
    "evaluation",
    "event",
    "explanation",
    "job",
    "measurement",
    "model_version",
    "monitor",
    "outcome",
    "project",
    "record",
    "schema_version",
    "setting",
    "usage_log",
}


@pytest.fixture
def engine_tmp(tmp_path: Path):
    """Motor sobre una base de datos temporal ya migrada."""
    db_path = tmp_path / "datos" / "vigia.db"
    engine = make_engine(db_path)
    migrate(engine, db_path)
    yield engine, db_path
    engine.dispose()


# --- esquema y migraciones -------------------------------------------------


def test_migrate_crea_las_tablas_y_deja_la_version_objetivo(engine_tmp):
    engine, _db_path = engine_tmp
    tablas = set(inspect(engine).get_table_names())
    assert TABLAS_ESPERADAS <= tablas
    assert current_version(engine) == target_version()


def test_pragmas_de_la_conexion(engine_tmp):
    engine, _db_path = engine_tmp
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_migrate_es_idempotente_y_no_hace_copia(engine_tmp):
    engine, db_path = engine_tmp
    objetivo = target_version()
    assert migrate(engine, db_path) == objetivo
    assert migrate(engine, db_path) == objetivo
    with engine.connect() as conn:
        filas = conn.execute(text("SELECT version FROM schema_version")).fetchall()
    assert [f[0] for f in filas] == list(range(1, objetivo + 1))
    assert not (db_path.parent / "backups").exists()


def test_siembra_de_guiones_idempotente(engine_tmp):
    engine, db_path = engine_tmp
    with Session(engine) as session:
        guiones = session.exec(select(DemoScenario)).all()
    claves = {g.key for g in guiones}
    assert "timeline_completo" in claves
    timeline = next(g for g in guiones if g.key == "timeline_completo")
    assert len(timeline.phases_json) == 9
    assert timeline.phases_json[0]["key"]
    assert "expected" in timeline.phases_json[0]

    migrate(engine, db_path)
    with Session(engine) as session:
        assert len(session.exec(select(DemoScenario)).all()) == len(guiones)


def test_migracion_2_anade_description_a_una_tabla_project_anterior(tmp_path: Path):
    """Una tabla `project` creada por una versión del código anterior a
    `description` (`create_all` no toca tablas que ya existen: hace falta el
    `ALTER TABLE` de la migración 2) gana la columna sin perder datos."""
    db_path = tmp_path / "datos" / "vigia.db"
    engine = make_engine(db_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE project ("
                "id INTEGER PRIMARY KEY, name VARCHAR NOT NULL UNIQUE, "
                "domain VARCHAR NOT NULL DEFAULT 'libre', "
                "task_type VARCHAR NOT NULL DEFAULT 'binary', "
                "favorable_label INTEGER NOT NULL DEFAULT 1, "
                "active_version_id INTEGER, calibration_until VARCHAR, "
                "hmac_salt VARCHAR NOT NULL DEFAULT '', "
                "store_features BOOLEAN NOT NULL DEFAULT 1, "
                "is_demo BOOLEAN NOT NULL DEFAULT 0, "
                "created_at VARCHAR NOT NULL, updated_at VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO project (name, hmac_salt, created_at, updated_at) "
                "VALUES ('previo', 'x', :ts, :ts)"
            ),
            {"ts": now_iso()},
        )
    assert current_version(engine) == 0  # sin schema_version: se ve como base nueva

    assert migrate(engine, db_path) == target_version()
    with engine.connect() as conn:
        columnas = {f[1] for f in conn.execute(text("PRAGMA table_info(project)")).fetchall()}
        assert "description" in columnas
        fila = conn.execute(text("SELECT name, description FROM project")).fetchone()
    assert fila == ("previo", None)
    engine.dispose()


def test_migracion_4_quita_deidentified_de_una_tabla_project_anterior(tmp_path: Path):
    """Una tabla `project` de una versión con `deidentified`
    (migración 3) pierde la columna sin perder el resto de los datos."""
    db_path = tmp_path / "datos" / "vigia.db"
    engine = make_engine(db_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE project ("
                "id INTEGER PRIMARY KEY, name VARCHAR NOT NULL UNIQUE, "
                "description VARCHAR, "
                "domain VARCHAR NOT NULL DEFAULT 'libre', "
                "task_type VARCHAR NOT NULL DEFAULT 'binary', "
                "favorable_label INTEGER NOT NULL DEFAULT 1, "
                "active_version_id INTEGER, calibration_until VARCHAR, "
                "hmac_salt VARCHAR NOT NULL DEFAULT '', "
                "store_features BOOLEAN NOT NULL DEFAULT 1, "
                "deidentified BOOLEAN NOT NULL DEFAULT 0, "
                "explain_auto BOOLEAN NOT NULL DEFAULT 1, "
                "explain_method VARCHAR NOT NULL DEFAULT 'permutation', "
                "is_demo BOOLEAN NOT NULL DEFAULT 0, "
                "created_at VARCHAR NOT NULL, updated_at VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO project (name, hmac_salt, deidentified, created_at, updated_at) "
                "VALUES ('previo', 'x', 1, :ts, :ts)"
            ),
            {"ts": now_iso()},
        )
    assert current_version(engine) == 0  # sin schema_version: se ve como base nueva

    assert migrate(engine, db_path) == target_version()
    with engine.connect() as conn:
        columnas = {f[1] for f in conn.execute(text("PRAGMA table_info(project)")).fetchall()}
        assert "deidentified" not in columnas
        fila = conn.execute(text("SELECT name FROM project")).fetchone()
    assert fila == ("previo",)
    engine.dispose()


def test_migracion_5_anade_deployment_stage_y_marca_los_proyectos_demo(tmp_path: Path):
    """Una tabla `project` sin `deployment_stage` (versión 4)
    gana la columna; un proyecto con `is_demo=1` queda en `demo`, el resto en
    `desarrollo`."""
    db_path = tmp_path / "datos" / "vigia.db"
    engine = make_engine(db_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE project ("
                "id INTEGER PRIMARY KEY, name VARCHAR NOT NULL UNIQUE, "
                "domain VARCHAR NOT NULL DEFAULT 'libre', "
                "task_type VARCHAR NOT NULL DEFAULT 'binary', "
                "favorable_label INTEGER NOT NULL DEFAULT 1, "
                "active_version_id INTEGER, calibration_until VARCHAR, "
                "hmac_salt VARCHAR NOT NULL DEFAULT '', "
                "store_features BOOLEAN NOT NULL DEFAULT 1, "
                "explain_auto BOOLEAN NOT NULL DEFAULT 1, "
                "explain_method VARCHAR NOT NULL DEFAULT 'permutation', "
                "is_demo BOOLEAN NOT NULL DEFAULT 0, "
                "created_at VARCHAR NOT NULL, updated_at VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO project (name, hmac_salt, is_demo, created_at, updated_at) "
                "VALUES ('demo-previo', 'x', 1, :ts, :ts)"
            ),
            {"ts": now_iso()},
        )
        conn.execute(
            text(
                "INSERT INTO project (name, hmac_salt, is_demo, created_at, updated_at) "
                "VALUES ('normal-previo', 'x', 0, :ts, :ts)"
            ),
            {"ts": now_iso()},
        )
    assert current_version(engine) == 0  # sin schema_version: se ve como base nueva

    assert migrate(engine, db_path) == target_version()
    with engine.connect() as conn:
        columnas = {f[1] for f in conn.execute(text("PRAGMA table_info(project)")).fetchall()}
        assert "deployment_stage" in columnas
        filas = dict(
            conn.execute(text("SELECT name, deployment_stage FROM project")).fetchall()
        )
    assert filas == {"demo-previo": "demo", "normal-previo": "desarrollo"}
    engine.dispose()


def test_migracion_6_anade_protocol_json_y_rellena_la_plantilla(tmp_path: Path):
    """Una tabla `monitor` sin `protocol_json` (versión 5)
    gana la columna; todo monitor existente (sin protocolo propio) recibe la
    plantilla de `content/protocolo-hitos.json`, sin perder el resto de sus
    datos."""
    db_path = tmp_path / "datos" / "vigia.db"
    engine = make_engine(db_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE monitor ("
                "id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, "
                "type VARCHAR NOT NULL, enabled BOOLEAN NOT NULL DEFAULT 1, "
                "config_json JSON, thresholds_json JSON, "
                "protocolo_md TEXT NOT NULL DEFAULT '', "
                "created_at VARCHAR NOT NULL, updated_at VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO monitor "
                "(project_id, type, protocolo_md, created_at, updated_at) "
                "VALUES (1, 'fairness', 'protocolo previo', :ts, :ts)"
            ),
            {"ts": now_iso()},
        )
    assert current_version(engine) == 0  # sin schema_version: se ve como base nueva

    assert migrate(engine, db_path) == target_version() == 15
    assert current_version(engine) == target_version() == 15
    with engine.connect() as conn:
        columnas = {f[1] for f in conn.execute(text("PRAGMA table_info(monitor)")).fetchall()}
        assert "protocol_json" in columnas

    with Session(engine) as session:
        monitor = session.exec(select(Monitor).where(Monitor.type == "fairness")).first()
    assert monitor is not None
    assert monitor.protocolo_md == "protocolo previo"
    assert monitor.protocol_json == protocolo_hitos_plantilla()
    engine.dispose()


def test_migracion_7_anade_baseline_y_target_y_retira_hmac_salt(tmp_path: Path):
    """Una base de la versión 6, con `outcome`
    sin `baseline`/`target` y `project` con `hmac_salt`, gana las dos columnas
    nulas y pierde `hmac_salt` sin perder el resto de sus filas."""
    db_path = tmp_path / "datos" / "vigia.db"
    engine = make_engine(db_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE outcome ("
                "id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, "
                "period VARCHAR NOT NULL, metric_key VARCHAR NOT NULL, "
                "value FLOAT, source VARCHAR NOT NULL, created_at VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO outcome (project_id, period, metric_key, value, source, created_at) "
                "VALUES (1, '2026-S1', 'reingresos', 0.12, 'manual', :ts)"
            ),
            {"ts": now_iso()},
        )
        conn.execute(
            text(
                "CREATE TABLE project ("
                "id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, "
                "hmac_salt VARCHAR NOT NULL DEFAULT '', is_demo BOOLEAN NOT NULL DEFAULT 0, "
                "created_at VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            text("INSERT INTO project (name, hmac_salt, created_at) VALUES ('previo', 'abc', :ts)"),
            {"ts": now_iso()},
        )

    assert migrate(engine, db_path) == target_version() == 15
    with engine.connect() as conn:
        outcome = {f[1] for f in conn.execute(text("PRAGMA table_info(outcome)")).fetchall()}
        project = {f[1] for f in conn.execute(text("PRAGMA table_info(project)")).fetchall()}
        fila = conn.execute(
            text("SELECT period, metric_key, value, baseline, target FROM outcome")
        ).fetchone()
        nombres = conn.execute(text("SELECT name FROM project")).fetchall()
    assert {"baseline", "target"} <= outcome
    assert "hmac_salt" not in project
    assert fila == ("2026-S1", "reingresos", 0.12, None, None)
    assert nombres == [("previo",)]
    engine.dispose()


def test_migraciones_8_y_9_crean_las_tablas_del_dossier_y_de_la_matriz(tmp_path: Path):
    """Una base de la versión 7 (sin `dossier`,
    `dossier_review`, `risk` ni `risk_movement`) gana las cuatro tablas sin
    perder las filas de las que ya tenía; una base nueva las trae por
    `create_all` y las migraciones 8 y 9 no fallan sobre ellas."""
    db_path = tmp_path / "datos" / "vigia.db"
    engine = make_engine(db_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE project ("
                "id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, "
                "is_demo BOOLEAN NOT NULL DEFAULT 0, created_at VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            text("INSERT INTO project (name, created_at) VALUES ('previo', :ts)"),
            {"ts": now_iso()},
        )
        conn.execute(text(_CREA_SCHEMA_VERSION_TEST))
        for version in range(1, 8):
            conn.execute(
                text("INSERT INTO schema_version (version, applied_at) VALUES (:v, :ts)"),
                {"v": version, "ts": now_iso()},
            )
    assert current_version(engine) == 7

    assert migrate(engine, db_path) == target_version() == 15
    tablas = set(inspect(engine).get_table_names())
    assert {"dossier", "dossier_review", "risk", "risk_movement"} <= tablas
    with engine.connect() as conn:
        nombres = conn.execute(text("SELECT name FROM project")).fetchall()
        risk = {f[1] for f in conn.execute(text("PRAGMA table_info(risk)")).fetchall()}
        review = {f[1] for f in conn.execute(text("PRAGMA table_info(dossier_review)")).fetchall()}
    assert nombres == [("previo",)]
    assert {"code", "impact_level", "probability_level", "level", "origin_alert_id"} <= risk
    assert {"approach", "status", "report_html", "corpus_hash", "prompt_sha256"} <= review
    # Copia previa: había versión registrada, así que `migrate` la hizo.
    assert list((db_path.parent / "backups").glob("vigia.db.7.*.bak"))
    engine.dispose()


_CREA_SCHEMA_VERSION_TEST = (
    "CREATE TABLE IF NOT EXISTS schema_version ("
    "version INTEGER NOT NULL PRIMARY KEY, applied_at VARCHAR NOT NULL)"
)


def test_migrate_copia_la_base_de_datos_si_habia_version_anterior(tmp_path: Path):
    db_path = tmp_path / "datos" / "vigia.db"
    engine = make_engine(db_path)
    # Base de datos "de la versión 0": tablas creadas y versión 0 registrada.
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER NOT NULL PRIMARY KEY, applied_at VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            text("INSERT INTO schema_version (version, applied_at) VALUES (0, :ts)"),
            {"ts": now_iso()},
        )
    assert current_version(engine) == 0

    assert migrate(engine, db_path) == target_version()
    copias = list((db_path.parent / "backups").glob("vigia.db.0.*.bak"))
    assert len(copias) == 1
    engine.dispose()


# --- diario append-only ----------------------------------------------------


def test_event_rechaza_update_y_delete(engine_tmp):
    engine, _db_path = engine_tmp
    with session_scope(engine) as session:
        record_event(
            session,
            actor_kind="humano",
            actor_id="miguel",
            action="proyecto.creado",
            object_type="project",
            object_id=1,
        )
    with engine.begin() as conn, pytest.raises(Exception, match="append-only"):
        conn.execute(text("UPDATE event SET motivo = 'trampa'"))
    with engine.begin() as conn, pytest.raises(Exception, match="append-only"):
        conn.execute(text("DELETE FROM event"))
    with Session(engine) as session:
        assert len(session.exec(select(Event)).all()) == 1


def test_record_event_publica_en_el_bus(engine_tmp):
    engine, _db_path = engine_tmp
    bus = EventBus()
    sub = bus.subscribe()
    with session_scope(engine) as session:
        record_event(
            session,
            actor_kind="agente",
            actor_id="claude",
            action="monitor.configurado",
            object_type="monitor",
            object_id=7,
            project_id=3,
            motivo="umbral revisado",
            bus=bus,
        )
    msg = sub.get(timeout=1)
    assert msg is not None
    assert msg["type"] == "event"
    assert msg["event"]["action"] == "monitor.configurado"
    assert msg["event"]["actor_kind"] == "agente"
    assert msg["event"]["id"] is not None
    sub.close()
    assert bus.n_subscribers == 0


# --- colas con hilos reales ------------------------------------------------


def _trabajo_con_progreso(ctx: JobContext, session: Session, *, pasos: int = 4) -> dict:
    for i in range(pasos):
        ctx.progress((i + 1) / pasos, f"paso {i + 1}")
    return {"pasos": pasos}


def _trabajo_con_escritura_sin_commit_y_progreso(ctx: JobContext, session: Session) -> dict:
    """Reproduce el patrón de §3.3 (ingesta por bloques): escribir y avisar progreso
    antes de que la sesión del trabajo haga commit. No debe bloquear ni fallar con
    `database is locked`."""
    evento = Event(
        actor_kind="agente",
        actor_id="prueba",
        action="evento.prueba",
        object_type="job",
        object_id=None,
        motivo="regresión: progress() con escritura sin commit",
        before_json=None,
        after_json=None,
    )
    session.add(evento)
    session.flush()
    ctx.progress(0.5, "a mitad de bloque")
    return {"evento_id": evento.id}


def _trabajo_cancelable(ctx: JobContext, session: Session, *, listo: threading.Event) -> dict:
    listo.set()
    for _ in range(200):
        ctx.raise_if_cancelled()
        time.sleep(0.01)
    return {"terminado": True}


def _espera_estado(manager: JobManager, job_id: int, estados: tuple[str, ...]) -> Job:
    for _ in range(500):
        job = manager.get(job_id)
        if job.status in estados:
            return job
        time.sleep(0.01)
    raise AssertionError(f"el trabajo {job_id} no llegó a {estados}")


def test_cola_ejecuta_el_trabajo_y_registra_progreso(engine_tmp):
    engine, _db_path = engine_tmp
    settings = Settings(data_dir=_db_path.parent, jobs_inline=False)
    bus = EventBus()
    sub = bus.subscribe()
    manager = JobManager(engine, settings, bus)
    try:
        job = manager.enqueue(
            "prueba", "rapida", _trabajo_con_progreso, params={"pasos": 3}, correlation_id="c-1"
        )
        final = _espera_estado(manager, int(job.id or 0), ("terminado", "error", "cancelado"))
        assert final.status == "terminado"
        assert final.progress == 1.0
        assert final.result_json == {"pasos": 3}
        assert final.correlation_id == "c-1"
        mensajes = []
        while (msg := sub.get(timeout=0.2)) is not None:
            mensajes.append(msg)
        assert any(m["message"] == "paso 2" for m in mensajes if m["type"] == "job")
        assert mensajes[-1]["status"] == "terminado"
    finally:
        manager.shutdown(timeout=5)


def test_progress_no_bloquea_con_escritura_sin_commit_inline(engine_tmp):
    engine, db_path = engine_tmp
    settings = Settings(data_dir=db_path.parent, jobs_inline=True)
    manager = JobManager(engine, settings, EventBus())
    job = manager.enqueue("prueba", "rapida", _trabajo_con_escritura_sin_commit_y_progreso, params={})
    assert job.status == "terminado"
    assert job.progress == 1.0
    assert job.result_json["evento_id"] is not None


def test_progress_no_bloquea_con_escritura_sin_commit_en_hilo(engine_tmp):
    engine, db_path = engine_tmp
    settings = Settings(data_dir=db_path.parent, jobs_inline=False)
    manager = JobManager(engine, settings, EventBus())
    try:
        job = manager.enqueue(
            "prueba", "rapida", _trabajo_con_escritura_sin_commit_y_progreso, params={}
        )
        final = _espera_estado(manager, int(job.id or 0), ("terminado", "error", "cancelado"))
        assert final.status == "terminado"
        assert final.error is None
    finally:
        manager.shutdown(timeout=5)


def test_cola_cancela_de_forma_cooperativa(engine_tmp):
    engine, db_path = engine_tmp
    settings = Settings(data_dir=db_path.parent, jobs_inline=False)
    manager = JobManager(engine, settings, EventBus())
    listo = threading.Event()
    try:
        job = manager.enqueue(
            "prueba", "llm", _trabajo_cancelable, params={"listo": listo}, project_id=1
        )
        job_id = int(job.id or 0)
        assert listo.wait(timeout=5)
        manager.cancel(job_id)
        final = _espera_estado(manager, job_id, ("terminado", "error", "cancelado"))
        assert final.status == "cancelado"
        assert final.error is None
    finally:
        manager.shutdown(timeout=5)


def test_cancelar_un_trabajo_pendiente_lo_deja_cancelado(engine_tmp):
    engine, db_path = engine_tmp
    settings = Settings(data_dir=db_path.parent, jobs_inline=False)
    manager = JobManager(engine, settings, EventBus())
    manager.shutdown(timeout=5)  # sin workers: el trabajo se queda pendiente
    job = manager.enqueue("prueba", "rapida", _trabajo_con_progreso, params={})
    job_id = int(job.id or 0)
    assert manager.get(job_id).status == "pendiente"
    assert manager.cancel(job_id).status == "cancelado"


def test_jobs_inline_ejecuta_en_el_hilo_de_la_peticion(engine_tmp):
    engine, db_path = engine_tmp
    settings = Settings(data_dir=db_path.parent, jobs_inline=True)
    manager = JobManager(engine, settings, EventBus())
    job = manager.enqueue("prueba", "rapida", _trabajo_con_progreso, params={"pasos": 2})
    assert job.status == "terminado"
    assert job.result_json == {"pasos": 2}


def test_trabajo_que_lanza_job_cancelled_queda_cancelado(engine_tmp):
    engine, db_path = engine_tmp
    settings = Settings(data_dir=db_path.parent, jobs_inline=True)
    manager = JobManager(engine, settings, EventBus())

    def _aborta(ctx: JobContext, session: Session) -> None:
        raise JobCancelled("abortado a propósito")

    job = manager.enqueue("prueba", "rapida", _aborta, params={})
    assert job.status == "cancelado"


def test_trabajo_con_error_guarda_el_mensaje(engine_tmp):
    engine, db_path = engine_tmp
    settings = Settings(data_dir=db_path.parent, jobs_inline=True)
    manager = JobManager(engine, settings, EventBus())

    def _falla(ctx: JobContext, session: Session) -> None:
        raise ValueError("algo va mal")

    job = manager.enqueue("prueba", "rapida", _falla, params={})
    assert job.status == "error"
    # Sin texto de librería; el detalle queda en el registro del servidor
    assert job.error == "error interno al ejecutar el trabajo: el registro del servidor tiene el detalle"


# --- salud -----------------------------------------------------------------


def test_health_expone_schema_version_db_path_y_colas(client: TestClient):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["schema_version"] == target_version()
    assert body["db_path"].endswith("vigia.db")
    assert body["queues"]["rapida"] == {"pendientes": 0, "en_curso": 0}
    assert body["queues"]["llm"] == {"pendientes": 0, "en_curso": 0}


def test_el_arranque_deja_evento_de_sistema(client: TestClient, session: Session):
    acciones = [e.action for e in session.exec(select(Event)).all()]
    assert "sistema.arranque" in acciones
    assert "sistema.migracion" in acciones


def test_migracion_10_anade_plantilla_intervalo_y_artefacto(tmp_path: Path):
    """Una base de la versión 9 gana en
    `project` la plantilla de mapeo (nula) y `acepta_feedback` (verdadero), en
    `dataset` el dialecto (nulo), y
    en `model_version` el método del intervalo (`ventanas`, el de antes) y los
    cinco campos del artefacto (nulos), sin perder filas."""
    db_path = tmp_path / "datos" / "vigia.db"
    engine = make_engine(db_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE project ("
                "id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, "
                "is_demo BOOLEAN NOT NULL DEFAULT 0, created_at VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE model_version ("
                "id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, label VARCHAR NOT NULL, "
                "model_kind VARCHAR NOT NULL DEFAULT 'external_files', "
                "created_at VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            text("CREATE TABLE dataset (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL)")
        )
        conn.execute(text("INSERT INTO dataset (name) VALUES ('fichero')"))
        conn.execute(
            text("INSERT INTO project (name, created_at) VALUES ('previo', :ts)"),
            {"ts": now_iso()},
        )
        conn.execute(
            text("INSERT INTO model_version (project_id, label, created_at) VALUES (1, 'v1', :ts)"),
            {"ts": now_iso()},
        )
        conn.execute(text(_CREA_SCHEMA_VERSION_TEST))
        for version in range(1, 10):
            conn.execute(
                text("INSERT INTO schema_version (version, applied_at) VALUES (:v, :ts)"),
                {"v": version, "ts": now_iso()},
            )
    assert current_version(engine) == 9

    assert migrate(engine, db_path) == target_version() == 15
    with engine.connect() as conn:
        proyecto = conn.execute(
            text("SELECT name, mapping_template_json, acepta_feedback FROM project")
        ).fetchone()
        version = conn.execute(
            text(
                "SELECT label, fairness_interval_method, artifact_path, artifact_kind, "
                "artifact_sha256, artifact_inputs_json, artifact_uploaded_at FROM model_version"
            )
        ).fetchone()
        dataset = conn.execute(text("SELECT name, dialect_json FROM dataset")).fetchone()
    assert proyecto == ("previo", None, 1)
    assert dataset == ("fichero", None)
    assert version == ("v1", "ventanas", None, None, None, None, None)
    engine.dispose()
