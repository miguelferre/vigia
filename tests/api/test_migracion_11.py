"""Migración 11: ids que no se reutilizan
(`AUTOINCREMENT`) y origen y retirada de las alertas."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel

from vigia.app.db import init_db, make_engine
from vigia.app.migrations import current_version, migrate, target_version
from vigia.app.models import (
    Alert,
    Batch,
    Dataset,
    Evaluation,
    ModelVersion,
    Monitor,
    Project,
    now_iso,
)

_TABLAS = ("dataset", "batch", "evaluation", "alert")
_COLUMNAS_NUEVAS = ("origin_batch_id", "origin_evaluation_id", "retired_reason")


def _crear_base_version_10(engine) -> None:
    """Esquema tal como lo dejaba la versión 10: las cuatro tablas sin
    `AUTOINCREMENT` y `alert` sin las columnas de la 11."""
    tablas = [m.__table__ for m in (Dataset, Batch, Evaluation, Alert)]
    previos = [t.dialect_options["sqlite"]["autoincrement"] for t in tablas]
    for t in tablas:
        t.dialect_options["sqlite"]["autoincrement"] = False
    try:
        SQLModel.metadata.create_all(engine)
    finally:
        for t, previo in zip(tablas, previos, strict=True):
            t.dialect_options["sqlite"]["autoincrement"] = previo
    with engine.begin() as conn:
        for columna in _COLUMNAS_NUEVAS:
            conn.exec_driver_sql(f"ALTER TABLE alert DROP COLUMN {columna}")
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER NOT NULL PRIMARY KEY, applied_at VARCHAR NOT NULL)"
            )
        )
        for version in range(1, 11):
            conn.execute(
                text("INSERT INTO schema_version (version, applied_at) VALUES (:v, :ts)"),
                {"v": version, "ts": now_iso()},
            )
    with engine.connect() as conn:
        sql = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='batch'")).scalar()
    assert "AUTOINCREMENT" not in sql


def _sembrar(engine) -> None:
    """Un proyecto con tres lotes (ids 1 a 3), una evaluación por lote, registros
    y cuatro alertas con historiales de distinta suerte."""
    with Session(engine) as s:
        proyecto = Project(name="p11")
        s.add(proyecto)
        s.flush()
        version = ModelVersion(project_id=proyecto.id, label="v1", is_active=True)
        monitor = Monitor(project_id=proyecto.id, type="quality")
        s.add(version)
        s.add(monitor)
        s.flush()
        for seq in range(3):
            lote = Batch(project_id=proyecto.id, model_version_id=version.id, seq=seq, n_rows=2)
            s.add(lote)
            s.flush()
            s.add(
                Evaluation(
                    monitor_id=monitor.id,
                    project_id=proyecto.id,
                    model_version_id=version.id,
                    batch_id=lote.id,
                )
            )
        s.commit()
    with engine.begin() as conn:
        for lote_id in (1, 2, 3):
            conn.execute(
                text(
                    "INSERT INTO record (batch_id, project_id, seq, prediction, group_code) "
                    "VALUES (:b, 1, 0, 1, 0)"
                ),
                {"b": lote_id},
            )
        historiales = {
            1: [{"evaluation_id": 1}, {"evaluation_id": 2}],
            2: [{"evaluation_id": 99}, {"evaluation_id": 2}],
            3: [{"evaluation_id": 99}],
            4: None,
        }
        for alerta_id, historial in historiales.items():
            conn.execute(
                text(
                    "INSERT INTO alert (id, project_id, monitor_type, metric_key, severity, "
                    "status, title, opened_at, updated_at, observation_count, reopen_count, "
                    "protocolo_md, history_json) VALUES (:id, 1, 'quality', 'm', 'alta', "
                    "'abierta', 't', :ts, :ts, 0, 0, '', :h)"
                ),
                {
                    "id": alerta_id,
                    "ts": now_iso(),
                    "h": json.dumps(historial) if historial is not None else None,
                },
            )


@pytest.fixture
def base_v10(tmp_path: Path):
    db_path = tmp_path / "datos" / "vigia.db"
    engine = make_engine(db_path)
    _crear_base_version_10(engine)
    _sembrar(engine)
    assert current_version(engine) == 10
    yield engine, db_path
    engine.dispose()


def test_la_11_recrea_con_autoincrement_y_no_reutiliza_ids(base_v10):
    engine, db_path = base_v10
    assert migrate(engine, db_path) == target_version() == 15

    with engine.connect() as conn:
        for tabla in _TABLAS:
            sql = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE name=:t"), {"t": tabla}
            ).scalar()
            assert "AUTOINCREMENT" in sql, tabla
        secuencias = dict(conn.execute(text("SELECT name, seq FROM sqlite_sequence")).fetchall())
        assert secuencias["batch"] == 3 and secuencias["evaluation"] == 3
        assert secuencias["alert"] == 4
        # Las FK siguen encendidas en la conexión y nada quedó en cascada.
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM record")).scalar() == 3
        assert conn.execute(text("SELECT COUNT(*) FROM evaluation")).scalar() == 3
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []

    # Se borra el lote 3 (arrastra su evaluación y su registro) y el siguiente
    # lote no hereda el id 3.
    with Session(engine) as s:
        s.delete(s.get(Batch, 3))
        s.commit()
        nuevo = Batch(project_id=1, model_version_id=1, seq=9, n_rows=1)
        s.add(nuevo)
        s.commit()
        assert nuevo.id == 4
        evaluacion = Evaluation(monitor_id=1, project_id=1, model_version_id=1, batch_id=4)
        s.add(evaluacion)
        s.commit()
        assert evaluacion.id == 4


def test_la_11_rellena_el_origen_desde_la_primera_evaluacion_viva(base_v10):
    engine, db_path = base_v10
    migrate(engine, db_path)
    with engine.connect() as conn:
        filas = {
            r[0]: r[1:]
            for r in conn.execute(
                text(
                    "SELECT id, origin_batch_id, origin_evaluation_id, retired_reason "
                    "FROM alert ORDER BY id"
                )
            ).fetchall()
        }
    assert filas[1] == (1, 1, None)  # primera entrada viva: evaluación 1 del lote 1
    assert filas[2] == (2, 2, None)  # la 99 no existe: salta a la 2
    assert filas[3] == (None, None, None)  # solo cita una evaluación borrada
    assert filas[4] == (None, None, None)  # sin historial


def test_la_11_es_idempotente(base_v10):
    from vigia.app.migrations import _migracion_11

    engine, db_path = base_v10
    migrate(engine, db_path)
    with engine.connect() as conn:
        antes = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='alert'")).scalar()
    # Repetirla (fallo entre el COMMIT y el registro de la versión) no cambia nada.
    with engine.connect() as conn:
        _migracion_11(conn)
        despues = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='alert'")).scalar()
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM alert")).scalar() == 4
    assert antes == despues


def _esquema(path: Path) -> dict:
    import sqlite3

    c = sqlite3.connect(path)
    resultado = {}
    for t in _TABLAS:
        columnas = {(x[1], x[2], x[3], x[5]) for x in c.execute(f"PRAGMA table_info({t})")}
        indices = {
            x[1]: tuple(y[2] for y in c.execute(f"PRAGMA index_info({x[1]})"))
            for x in c.execute(f"PRAGMA index_list({t})")
        }
        fks = {(x[2], x[3], x[4], x[6]) for x in c.execute(f"PRAGMA foreign_key_list({t})")}
        sql = c.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,)).fetchone()[0]
        resultado[t] = (columnas, indices, fks, "AUTOINCREMENT" in sql)
    c.close()
    return resultado


def test_base_migrada_y_base_nueva_tienen_el_mismo_esquema(base_v10):
    engine, db_path = base_v10
    migrate(engine, db_path)
    engine.dispose()

    nueva = Path(tempfile.mkdtemp()) / "nueva.db"
    engine_nueva = make_engine(nueva)
    assert init_db(engine_nueva, nueva) == target_version()
    engine_nueva.dispose()

    assert _esquema(db_path) == _esquema(nueva)


def test_base_nueva_no_reutiliza_ids(tmp_path: Path):
    path = tmp_path / "vigia.db"
    engine = make_engine(path)
    init_db(engine, path)
    with Session(engine) as s:
        s.add(Project(name="p"))
        s.commit()
        s.add(ModelVersion(project_id=1, label="v", is_active=True))
        s.commit()
        a = Batch(project_id=1, model_version_id=1, seq=0)
        s.add(a)
        s.commit()
        primero = a.id
        s.delete(a)
        s.commit()
        b = Batch(project_id=1, model_version_id=1, seq=0)
        s.add(b)
        s.commit()
        assert b.id == primero + 1
    engine.dispose()
