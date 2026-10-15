"""Motor SQLite y sesiones de Vigía.

`make_engine` fija los PRAGMA en cada conexión nueva (WAL, `busy_timeout`,
`foreign_keys`); `get_session` es la dependencia de FastAPI y `session_scope`
el contexto que usan los trabajos de las colas, que corren fuera de una
petición.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi import Request
from sqlalchemy import event as sa_event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from vigia.app import models as _models  # noqa: F401  (registra las tablas en la metadata)

__all__ = ["get_session", "init_db", "make_engine", "session_scope"]

BUSY_TIMEOUT_MS = 5000
CONNECT_TIMEOUT_S = 5


def make_engine(db_path: Path | str) -> Engine:
    """Crea el motor SQLite de la aplicación con los PRAGMA del proyecto."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": CONNECT_TIMEOUT_S},
        future=True,
    )

    @sa_event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA foreign_keys=ON")
            # Las filas borradas se sobrescriben en las páginas libres.
            cursor.execute("PRAGMA secure_delete=ON")
        finally:
            cursor.close()

    return engine


def init_db(engine: Engine, db_path: Path | str | None = None) -> int:
    """Crea las tablas y aplica las migraciones pendientes. Devuelve la versión final."""
    from vigia.app.migrations import migrate

    SQLModel.metadata.create_all(engine)
    if db_path is None:
        db_path = engine.url.database or ""
    return migrate(engine, Path(db_path))


def get_session(request: Request) -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición sobre `app.state.engine`."""
    engine: Engine = request.app.state.engine
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Sesión para código fuera de una petición (colas): commit al salir, rollback si falla."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
