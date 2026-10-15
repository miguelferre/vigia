"""Outcomes (tope de filas, clave única y migración 15).

Cada test comprueba el control seguro de un apunte; ver `HUELLAS`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from tests.api.conftest import actor_headers
from tests.seguridad import _base_proyecto as _base
from vigia.app.db import make_engine
from vigia.app.events import Actor
from vigia.app.migrations import current_version, migrate, target_version
from vigia.app.models import Outcome, Project, now_iso
from vigia.app.services import outcomes as outcomes_service

# Fixtures compartidas (carpeta de datos temporal y cliente con `base_url` local).
app, client, session, settings = _base.app, _base.client, _base.session, _base.settings

HUELLAS = {
    "test_outcomes_rechaza_mas_filas_que_el_tope_por_lote": (
        "usage-log-upload-sync-work-in-async-handler"
    ),
    "test_outcome_tiene_clave_unica_por_periodo_metrica_y_fuente": "outcome-unique-key",
    "test_la_migracion_15_resuelve_duplicados_y_crea_el_indice": "outcome-unique-key",
    "test_el_upsert_de_outcomes_aguanta_una_fila_concurrente": "outcome-unique-key",
}

CABECERA = b"period,metric_key,value,source\n"


def _csv(n: int) -> bytes:
    return CABECERA + b"".join(f"2026-{i:04d},m,1,s\n".encode() for i in range(n))


def test_outcomes_rechaza_mas_filas_que_el_tope_por_lote(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """La subida de outcomes cuenta las filas antes de procesarlas y rechaza las que
    pasan del máximo por lote, con 422 y sin dejar ninguna fila."""
    proyecto = client.post(
        "/api/projects", json={"name": "s1c-tope", "domain": "reuma"}, headers=actor_headers("miguel")
    ).json()
    monkeypatch.setattr(outcomes_service, "LIMITE_FILAS_LOTE", 3, raising=False)
    resp = client.post(
        f"/api/projects/{proyecto['id']}/outcomes",
        files={"file": ("o.csv", _csv(4), "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422, resp.text
    assert "máximo por lote" in resp.text
    assert client.get(f"/api/projects/{proyecto['id']}/outcomes").json()["rows"] == []
    ok = client.post(
        f"/api/projects/{proyecto['id']}/outcomes",
        files={"file": ("o.csv", _csv(3), "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert ok.status_code == 200, ok.text


def test_outcome_tiene_clave_unica_por_periodo_metrica_y_fuente(client: TestClient, session: Session):
    """La base no admite dos outcomes con la misma clave de proyecto, periodo,
    métrica y fuente."""
    proyecto = client.post(
        "/api/projects", json={"name": "s1c-clave", "domain": "reuma"}, headers=actor_headers("miguel")
    ).json()
    pid = proyecto["id"]
    session.add(Outcome(project_id=pid, period="p", metric_key="m", value=1.0, source="s"))
    session.commit()
    session.add(Outcome(project_id=pid, period="p", metric_key="m", value=2.0, source="s"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def _base_version_14(ruta: Path):
    """Base con el esquema actual pero sin el índice único y en la versión 14."""
    engine = make_engine(ruta)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS uq_outcome_clave"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER NOT NULL PRIMARY KEY, applied_at VARCHAR NOT NULL)"
            )
        )
        for version in range(1, 15):
            conn.execute(
                text("INSERT INTO schema_version (version, applied_at) VALUES (:v, :ts)"),
                {"v": version, "ts": now_iso()},
            )
    return engine


def test_la_migracion_15_resuelve_duplicados_y_crea_el_indice(tmp_path: Path):
    """La migración 15 deja una sola fila por clave (la más reciente), crea el índice
    único y hace antes la copia previa de la base."""
    ruta = tmp_path / "datos" / "vigia.db"
    engine = _base_version_14(ruta)
    with Session(engine) as s:
        s.add(Project(name="p15"))
        s.flush()
        for valor in (1.0, 2.0, 3.0):
            s.add(Outcome(project_id=1, period="p", metric_key="m", value=valor, source="s"))
        s.add(Outcome(project_id=1, period="q", metric_key="m", value=9.0, source="s"))
        s.commit()
    assert current_version(engine) == 14
    assert migrate(engine, ruta) == target_version() == 15
    with Session(engine) as s:
        filas = s.exec(select(Outcome).order_by(Outcome.period)).all()
        assert [(o.period, o.value) for o in filas] == [("p", 3.0), ("q", 9.0)]
    with engine.connect() as conn:
        unicos = [
            f[1] for f in conn.execute(text("PRAGMA index_list(outcome)")).fetchall() if f[2]
        ]
        assert "uq_outcome_clave" in unicos
    assert len(list((ruta.parent / "backups").glob("vigia.db.14.*.bak"))) == 1
    assert migrate(engine, ruta) == 15
    engine.dispose()


class _SesionConCarrera:
    """Sesión que, tras la lectura previa del servicio, deja que otra petición
    inserte la misma clave (la carrera entre la lectura y la escritura)."""

    def __init__(self, real: Session, carrera) -> None:
        self._real, self._carrera, self._hecha = real, carrera, False

    def exec(self, *args, **kwargs):
        resultado = self._real.exec(*args, **kwargs).all()
        if not self._hecha:
            self._hecha = True
            self._carrera()

        class _Filas:
            def all(self_inner):
                return resultado

        return _Filas()

    def __getattr__(self, nombre: str):
        return getattr(self._real, nombre)


def test_el_upsert_de_outcomes_aguanta_una_fila_concurrente(client: TestClient):
    """Si otra subida inserta la misma clave entre la lectura y la escritura, la
    ingesta actualiza esa fila en vez de fallar o duplicarla."""
    proyecto = client.post(
        "/api/projects", json={"name": "s1c-upsert", "domain": "reuma"}, headers=actor_headers("miguel")
    ).json()
    engine = client.app.state.engine

    def carrera() -> None:
        with Session(engine) as otra:
            otra.add(Outcome(project_id=proyecto["id"], period="2026-0000", metric_key="m", value=7.0, source="s"))
            otra.commit()

    with Session(engine) as s:
        proy = s.get(Project, proyecto["id"])
        try:
            outcomes_service.ingest_outcomes(
                _SesionConCarrera(s, carrera),  # type: ignore[arg-type]
                proy,
                file_bytes=_csv(1),
                actor=Actor(kind="humano", id="miguel"),
            )
        except (IntegrityError, HTTPException) as exc:
            pytest.fail(f"la ingesta falla ante una fila concurrente: {exc!r}")
    with Session(engine) as s:
        filas = s.exec(select(Outcome).where(Outcome.project_id == proyecto["id"])).all()
        assert [(o.period, o.value) for o in filas] == [("2026-0000", 1.0)]
