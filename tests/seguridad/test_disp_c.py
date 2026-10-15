"""Disponibilidad, parte C: subidas de ficheros y de outcomes.

Cada test comprueba el control seguro de una huella (ver `HUELLAS`) contra el código actual.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session

from tests.api.conftest import actor_headers
from vigia.app.main import create_app
from vigia.app.settings import Settings

HUELLAS = {
    "test_dataset_rechazado_no_deja_fichero": "upload-orphan-files-before-validation-no-size-cap",
    "test_diario_rechazado_no_deja_fichero": "upload-orphan-files-before-validation-no-size-cap",
    "test_borrar_proyecto_limpia_su_carpeta_de_subidas": "upload-orphan-files-before-validation-no-size-cap",
    "test_outcomes_no_hace_una_consulta_por_fila": "usage-log-upload-sync-work-in-async-handler",
}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=d, host="127.0.0.1", port_start=8973, open_browser=False,
        jobs_inline=True, sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8973
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


@pytest.fixture
def session(client: TestClient) -> Iterator[Session]:
    with Session(client.app.state.engine) as s:
        yield s


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post(
        "/api/projects", json={"name": name, "domain": "reuma"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ficheros(settings: Settings, pid: int) -> list[Path]:
    carpeta = settings.data_dir / "uploads" / str(pid)
    return [p for p in carpeta.rglob("*") if p.is_file()] if carpeta.exists() else []


def _subir_dataset(client: TestClient, pid: int, nombre: str, contenido: bytes):
    return client.post(
        f"/api/projects/{pid}/datasets/upload",
        files={"file": (nombre, contenido, "text/csv")},
        data={"kind": "combined", "role": "baseline"},
        headers=actor_headers("miguel"),
    )


def test_dataset_rechazado_no_deja_fichero(client: TestClient, settings: Settings):
    """Control: una subida de dataset rechazada (422) no deja ficheros en uploads/."""
    pid = _crear_proyecto(client, "disp-huerfano")["id"]
    bueno = _subir_dataset(client, pid, "ok.csv", b"a,b\n1,2\n3,4\n")
    assert bueno.status_code == 200, bueno.text  # control positivo
    antes = len(_ficheros(settings, pid))
    assert antes == 1
    for n in ("a.csv", "b.csv", "c.csv"):
        malo = _subir_dataset(client, pid, n, b"a,b\n1,2\x00")
        assert malo.status_code == 422, malo.text  # el rechazo se ejerce
    assert len(_ficheros(settings, pid)) == antes


def test_diario_rechazado_no_deja_fichero(client: TestClient, settings: Settings):
    """Control: una subida del diario de uso rechazada (422) no deja ficheros en uploads/."""
    pid = _crear_proyecto(client, "disp-huerfano-uso")["id"]
    base = "date,human_decision,model_output,ground_truth\n"
    bueno = client.post(
        f"/api/projects/{pid}/usage-logs/upload",
        files={"file": ("ok.csv", (base + "2026-01-05,refer,refer,refer\n").encode(), "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert bueno.status_code == 200, bueno.text  # control positivo
    antes = len(_ficheros(settings, pid))
    for n in ("a.csv", "b.csv", "c.csv"):
        malo = client.post(
            f"/api/projects/{pid}/usage-logs/upload",
            files={"file": (n, (base + "xx,refer,refer,refer\n").encode(), "text/csv")},
            headers=actor_headers("miguel"),
        )
        assert malo.status_code == 422, malo.text
    assert len(_ficheros(settings, pid)) == antes


def test_borrar_proyecto_limpia_su_carpeta_de_subidas(client: TestClient, settings: Settings):
    """Control: borrar un proyecto elimina la carpeta uploads/<id> aunque queden ficheros sueltos."""
    pid = _crear_proyecto(client, "disp-borrado")["id"]
    assert _subir_dataset(client, pid, "ok.csv", b"a,b\n1,2\n").status_code == 200
    carpeta = settings.data_dir / "uploads" / str(pid)
    (carpeta / "99_suelto.csv").write_bytes(b"x,y\n1,2\n")
    resp = client.delete(f"/api/projects/{pid}?confirm=true", headers=actor_headers("miguel"))
    assert resp.status_code == 204, resp.text
    assert [p for p in carpeta.rglob("*") if p.is_file()] == []


def test_outcomes_no_hace_una_consulta_por_fila(client: TestClient, session: Session):
    """Control: la subida de outcomes no lanza una SELECT sobre outcome por cada fila."""
    pid = _crear_proyecto(client, "disp-outcomes")["id"]
    filas = ["period,metric_key,value,source"]
    filas += [f"2026-{m:02d},metrica_{k:02d},0.5,manual" for m in range(1, 13) for k in range(20)]
    selects: list[str] = []

    def _contar(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith("SELECT") and "FROM outcome" in statement:
            selects.append(statement)

    engine = client.app.state.engine
    event.listen(engine, "before_cursor_execute", _contar)
    try:
        resp = client.post(
            f"/api/projects/{pid}/outcomes",
            files={"file": ("o.csv", "\n".join(filas).encode(), "text/csv")},
            headers=actor_headers("miguel"),
        )
    finally:
        event.remove(engine, "before_cursor_execute", _contar)
    assert resp.status_code == 200, resp.text
    assert resp.json()["n_rows"] == 240
    assert len(selects) < 30, f"{len(selects)} consultas sobre outcome para 240 filas"


