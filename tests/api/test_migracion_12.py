"""Migración 12 (ciclo de vida): `project` con `AUTOINCREMENT`, para
que un proyecto nuevo no herede el id (ni el diario) de uno borrado."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel

from vigia.app.db import init_db, make_engine
from vigia.app.migrations import _migracion_12, current_version, migrate, target_version
from vigia.app.models import Batch, Event, ModelVersion, Monitor, Project, now_iso


def _crear_base_version_11(engine) -> None:
    """Esquema tal como lo dejaba la versión 11: `project` sin `AUTOINCREMENT`."""
    tabla = Project.__table__
    previo = tabla.dialect_options["sqlite"]["autoincrement"]
    tabla.dialect_options["sqlite"]["autoincrement"] = False
    try:
        SQLModel.metadata.create_all(engine)
    finally:
        tabla.dialect_options["sqlite"]["autoincrement"] = previo
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER NOT NULL PRIMARY KEY, applied_at VARCHAR NOT NULL)"
            )
        )
        for version in range(1, 12):
            conn.execute(
                text("INSERT INTO schema_version (version, applied_at) VALUES (:v, :ts)"),
                {"v": version, "ts": now_iso()},
            )
    with engine.connect() as conn:
        sql = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='project'")).scalar()
    assert "AUTOINCREMENT" not in sql


def _sembrar(engine) -> None:
    """Tres proyectos con versión, monitor y lote, y el diario de un cuarto proyecto
    (id 5) que ya se borró."""
    with Session(engine) as s:
        for n in range(1, 4):
            s.add(Project(name=f"p12-{n}"))
        s.flush()
        for n in range(1, 4):
            s.add(ModelVersion(project_id=n, label="v1", is_active=True))
            s.add(Monitor(project_id=n, type="quality"))
        s.flush()
        for n in range(1, 4):
            s.add(Batch(project_id=n, model_version_id=n, seq=0, n_rows=2))
        s.add(Event(action="proyecto.borrado", object_type="project", object_id=5, project_id=5))
        s.commit()


@pytest.fixture
def base_v11(tmp_path: Path):
    db_path = tmp_path / "datos" / "vigia.db"
    engine = make_engine(db_path)
    _crear_base_version_11(engine)
    _sembrar(engine)
    assert current_version(engine) == 11
    yield engine, db_path
    engine.dispose()


def test_la_12_recrea_project_y_conserva_datos_e_hijos(base_v11):
    engine, db_path = base_v11
    assert migrate(engine, db_path) == target_version() == 15
    with engine.connect() as conn:
        sql = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='project'")).scalar()
        assert "AUTOINCREMENT" in sql
        nombres = conn.execute(text("SELECT id, name FROM project ORDER BY id")).fetchall()
        assert nombres == [(1, "p12-1"), (2, "p12-2"), (3, "p12-3")]
        for tabla in ("model_version", "monitor", "batch"):
            assert conn.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar() == 3, tabla
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
        indices = {
            r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))
        }
        assert "ix_project_name" in indices


def test_la_12_no_reutiliza_ids_ni_los_de_proyectos_con_diario(base_v11):
    engine, db_path = base_v11
    migrate(engine, db_path)
    with Session(engine) as s:
        # El id 5 quedó en el diario de un proyecto borrado antes de la migración.
        nuevo = Project(name="p12-nuevo")
        s.add(nuevo)
        s.commit()
        assert nuevo.id == 6
        s.delete(nuevo)
        s.commit()
        otro = Project(name="p12-otro")
        s.add(otro)
        s.commit()
        assert otro.id == 7
        # Borrar un proyecto con hijos sigue arrastrándolos en cascada.
        s.delete(s.get(Project, 3))
        s.commit()
        assert s.get(Batch, 3) is None


def test_la_12_es_idempotente(base_v11):
    engine, db_path = base_v11
    migrate(engine, db_path)
    with engine.connect() as conn:
        antes = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='project'")).scalar()
    with engine.connect() as conn:
        _migracion_12(conn)
        despues = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='project'")).scalar()
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM project")).scalar() == 3
    assert antes == despues


def _esquema_project(path: Path):
    import sqlite3

    c = sqlite3.connect(path)
    columnas = {(x[1], x[2], x[3], x[5]) for x in c.execute("PRAGMA table_info(project)")}
    indices = {
        x[1]: tuple(y[2] for y in c.execute(f"PRAGMA index_info({x[1]})"))
        for x in c.execute("PRAGMA index_list(project)")
    }
    sql = c.execute("SELECT sql FROM sqlite_master WHERE name='project'").fetchone()[0]
    c.close()
    return columnas, indices, "AUTOINCREMENT" in sql


def test_base_migrada_y_base_nueva_tienen_el_mismo_esquema_de_project(base_v11):
    engine, db_path = base_v11
    migrate(engine, db_path)
    engine.dispose()
    nueva = Path(tempfile.mkdtemp()) / "nueva.db"
    engine_nueva = make_engine(nueva)
    assert init_db(engine_nueva, nueva) == target_version()
    engine_nueva.dispose()
    assert _esquema_project(db_path) == _esquema_project(nueva)
