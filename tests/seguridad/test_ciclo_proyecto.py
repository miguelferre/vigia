"""Ciclo de vida del proyecto.

Cada test comprueba el control seguro de un apunte; ver `HUELLAS`.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlmodel import Session, SQLModel, select

from tests.api.conftest import actor_headers
from tests.seguridad import _base_proyecto as _base
from vigia.app.models import Dossier, Event, Job, Outcome

# Fixtures compartidas (carpeta de datos temporal y cliente con `base_url` local).
app, client, session, settings = _base.app, _base.client, _base.session, _base.settings

HUELLAS = {
    "test_borrar_proyecto_registra_el_fichero_que_no_pudo_retirar": (
        "lifecycle/project-cleanup-failures-swallowed-leave-clinical-files-unrecorded"
    ),
    "test_reiniciar_proyecto_registra_el_fichero_que_no_pudo_retirar": (
        "lifecycle/project-cleanup-failures-swallowed-leave-clinical-files-unrecorded"
    ),
    "test_reiniciar_proyecto_retira_outcomes_jobs_y_telemetria": (
        "lifecycle/project-reset-keeps-outcome-dossier-telemetry-and-job-rows"
    ),
    "test_borrar_proyecto_retira_sus_jobs": (
        "lifecycle/project-reset-keeps-outcome-dossier-telemetry-and-job-rows"
    ),
    "test_tablas_con_project_id_sin_clave_estan_cubiertas_por_el_reinicio": (
        "lifecycle/project-reset-keeps-outcome-dossier-telemetry-and-job-rows"
    ),
    "test_las_conexiones_borran_con_secure_delete": "connections-secure-delete",
}

# Tablas con `project_id` que no cuelgan de `project` por clave foránea. Si aparece
# otra, el reinicio y el borrado deben decidir qué hacen con ella.
SIN_CLAVE = {"measurement", "explanation", "outcome", "event", "job"}
CUBIERTAS = {
    "measurement": "cae con su evaluación (CASCADE)",
    "explanation": "la borra el reinicio",
    "outcome": "la borra el reinicio y el borrado",
    "job": "la borra el reinicio y el borrado (los terminados)",
    "event": "el diario es de solo añadir",
}


@pytest.fixture
def proyecto(client: TestClient) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": "s1c-ciclo", "domain": "reuma"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class _Bloqueo:
    """Mantiene un fichero abierto sin permitir su borrado (Windows)."""

    def __init__(self, ruta: Path) -> None:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]  # fmt: skip
        self._k32 = k32
        self._h = k32.CreateFileW(str(ruta), 0x80000000, 1, None, 3, 0x80, None)
        assert self._h not in (None, -1), "no se pudo abrir el fichero de la prueba"

    def cerrar(self) -> None:
        self._k32.CloseHandle(self._h)


@pytest.fixture
def fichero_retenido(client: TestClient, proyecto: dict) -> Iterator[Path]:
    carpeta = Path(client.app.state.settings.data_dir) / "uploads" / str(proyecto["id"])
    carpeta.mkdir(parents=True)
    ruta = carpeta / "1_x.privado.csv"
    ruta.write_text("dato\n", encoding="utf-8")
    bloqueo = _Bloqueo(ruta)
    try:
        yield ruta
    finally:
        bloqueo.cerrar()


def _eventos(client: TestClient, project_id: int) -> list[dict]:
    resp = client.get("/api/events", params={"project_id": project_id, "limit": 500})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _comprobar_aviso(client: TestClient, proyecto: dict, ruta: Path, caplog) -> None:
    avisos = [e for e in _eventos(client, proyecto["id"]) if e["action"].endswith("limpieza_incompleta")]
    assert len(avisos) == 1, [e["action"] for e in _eventos(client, proyecto["id"])]
    asunto = str(avisos[0])
    assert ruta.name in asunto
    assert str(client.app.state.settings.data_dir) not in asunto
    assert any(ruta.name in r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)


@pytest.mark.skipif(sys.platform != "win32", reason="el bloqueo sin borrado es de Windows")
def test_borrar_proyecto_registra_el_fichero_que_no_pudo_retirar(
    client: TestClient, proyecto: dict, fichero_retenido: Path, caplog
):
    """Si un fichero del proyecto no se puede retirar, el borrado deja constancia
    en el diario y en el log, sin la ruta absoluta de la carpeta de datos."""
    with caplog.at_level(logging.WARNING):
        resp = client.delete(
            f"/api/projects/{proyecto['id']}", params={"confirm": "true"}, headers=actor_headers("miguel")
        )
    assert resp.status_code == 204, resp.text
    assert fichero_retenido.exists()
    _comprobar_aviso(client, proyecto, fichero_retenido, caplog)


@pytest.mark.skipif(sys.platform != "win32", reason="el bloqueo sin borrado es de Windows")
def test_reiniciar_proyecto_registra_el_fichero_que_no_pudo_retirar(
    client: TestClient, proyecto: dict, fichero_retenido: Path, caplog
):
    """Igual que el borrado: el reinicio no da por completa una limpieza que no lo fue."""
    with caplog.at_level(logging.WARNING):
        resp = client.post(
            f"/api/projects/{proyecto['id']}/reset",
            json={"actor": "miguel", "motivo": "prueba del control", "confirm": True},
            headers=actor_headers("miguel"),
        )
    assert resp.status_code == 200, resp.text
    assert fichero_retenido.exists()
    _comprobar_aviso(client, proyecto, fichero_retenido, caplog)


def _sembrar(session: Session, project_id: int) -> None:
    session.add(Outcome(project_id=project_id, period="2026-01", metric_key="m", value=1.0, source="s"))
    session.add(Job(kind="x", status="terminado", project_id=project_id))
    session.add(Job(kind="x", status="en_curso", project_id=project_id))
    session.add(
        Dossier(project_id=project_id, system_name="s", telemetry_included=True, telemetry_text="resumen")
    )
    session.commit()


def _cuenta(session: Session, modelo, project_id: int) -> int:
    return session.exec(
        select(func.count()).select_from(modelo).where(modelo.project_id == project_id)
    ).one()


def test_reiniciar_proyecto_retira_outcomes_jobs_y_telemetria(
    client: TestClient, proyecto: dict, session: Session
):
    """El reinicio deja el proyecto sin outcomes, sin trabajos terminados y sin el
    resumen de uso copiado en los dossiers; la tabla de recuentos lo cuenta."""
    pid = proyecto["id"]
    _sembrar(session, pid)
    resp = client.post(
        f"/api/projects/{pid}/reset",
        json={"actor": "miguel", "motivo": "prueba del control", "confirm": True},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert client.get(f"/api/projects/{pid}/outcomes").json()["rows"] == []
    session.expire_all()
    assert _cuenta(session, Outcome, pid) == 0
    assert [j.status for j in session.exec(select(Job).where(Job.project_id == pid)).all()] == ["en_curso"]
    dossier = session.exec(select(Dossier).where(Dossier.project_id == pid)).one()
    assert dossier.telemetry_text is None and dossier.telemetry_included is False
    evento = session.exec(select(Event).where(Event.action == "proyecto.reiniciado")).one()
    assert evento.before_json["outcomes"] == 1


def test_borrar_proyecto_retira_sus_jobs(client: TestClient, proyecto: dict, session: Session):
    """Borrar un proyecto no deja filas de trabajos terminados con su id."""
    pid = proyecto["id"]
    _sembrar(session, pid)
    resp = client.delete(f"/api/projects/{pid}", params={"confirm": "true"}, headers=actor_headers("miguel"))
    assert resp.status_code == 204, resp.text
    session.expire_all()
    assert _cuenta(session, Outcome, pid) == 0
    assert [j.status for j in session.exec(select(Job).where(Job.project_id == pid)).all()] == ["en_curso"]


def test_tablas_con_project_id_sin_clave_estan_cubiertas_por_el_reinicio():
    """Cada tabla con `project_id` sin clave foránea a `project` tiene decisión
    explícita: una tabla nueva obliga a decidir qué hace el reinicio con ella."""
    encontradas = {
        t.name
        for t in SQLModel.metadata.tables.values()
        if "project_id" in t.c
        and not any(fk.column.table.name == "project" for fk in t.c.project_id.foreign_keys)
    }
    assert encontradas == SIN_CLAVE, encontradas ^ SIN_CLAVE
    assert set(CUBIERTAS) == SIN_CLAVE


def test_las_conexiones_borran_con_secure_delete(client: TestClient):
    """Las filas borradas se sobrescriben en las páginas libres de la base."""
    with client.app.state.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA secure_delete").scalar() == 1
