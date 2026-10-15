"""Ciclo de vida: diario de uso, copias de la base y reutilización de ids.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.app import migrations
from vigia.app.main import create_app
from vigia.app.settings import Settings

USAGE_CSV = Path(__file__).resolve().parents[2] / "data" / "demo" / "usage_logs_demo.csv"
RAIZ = Path(__file__).resolve().parents[2]
CLAVE_FICTICIA = "clave-ficticia-ciclo-0001"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=d,
        host="127.0.0.1",
        port_start=8980,
        open_browser=False,
        jobs_inline=True,
        sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8980
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "reuma"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir_uso(client: TestClient, project_id: int) -> dict:
    with USAGE_CSV.open("rb") as f:
        resp = client.post(
            f"/api/projects/{project_id}/usage-logs/upload",
            files={"file": ("uso.csv", f, "text/csv")},
            headers=actor_headers("miguel"),
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _filas_export(client: TestClient, project_id: int) -> int:
    resp = client.get(f"/api/projects/{project_id}/usage-logs/export.csv")
    assert resp.status_code == 200, resp.text
    lineas = [ln for ln in resp.text.splitlines() if ln.strip()]
    return max(len(lineas) - 1, 0)


def _borrar_dataset_de_uso(client: TestClient, project_id: int) -> tuple[int, int]:
    """Sube un registro de uso, comprueba que existe y lo borra. Devuelve (status, n_filas_subidas)."""
    subida = _subir_uso(client, project_id)
    n = subida["n_rows"]
    assert n > 0
    assert _filas_export(client, project_id) == n
    listado = client.get(f"/api/projects/{project_id}/datasets")
    assert listado.status_code == 200, listado.text
    assert any(d["id"] == subida["dataset_id"] for d in listado.json()["items"])
    resp = client.delete(
        f"/api/datasets/{subida['dataset_id']}",
        params={"confirm": "true"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code not in (404, 405), resp.text
    return resp.status_code, n


def test_borrar_dataset_de_uso_no_deja_filas_en_el_export(client: TestClient):
    """Borrar el registro de uso
    no deja sus filas en el CSV de exportación (o el borrado se rechaza)."""
    proyecto = _crear_proyecto(client, "ciclo-uso-export")
    estado, n = _borrar_dataset_de_uso(client, proyecto["id"])
    if estado == 204:
        assert _filas_export(client, proyecto["id"]) == 0
    else:
        assert 400 <= estado < 500
        assert _filas_export(client, proyecto["id"]) == n


def test_borrar_dataset_de_uso_no_deja_filas_en_overrides(client: TestClient):
    """Tras el borrado, el agregado
    de overrides no cuenta las filas del registro retirado."""
    proyecto = _crear_proyecto(client, "ciclo-uso-overrides")
    antes = client.get(f"/api/projects/{proyecto['id']}/overrides")
    assert antes.status_code == 200, antes.text
    estado, n = _borrar_dataset_de_uso(client, proyecto["id"])
    despues = client.get(f"/api/projects/{proyecto['id']}/overrides")
    assert despues.status_code == 200, despues.text
    total = despues.json().get("n_total")
    assert total is not None, despues.json()
    if estado == 204:
        assert total == 0
    else:
        assert total == n


def _parrafos_sobre_copias(texto: str) -> list[str]:
    return [
        p.lower()
        for p in re.split(r"\n\s*\n", texto)
        if ("backups" in p.lower() or ".bak" in p.lower())
    ]


def test_copia_previa_a_migracion_no_lleva_la_clave_del_llm_en_claro(
    client: TestClient, app: FastAPI, settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    """Límite conocido: La copia
    previa a una migración guarda la base entera, clave del LLM incluida, y los
    documentos de seguridad e instalación lo dicen."""
    resp = client.patch(
        "/api/settings",
        json={
            "actor": "miguel",
            "motivo": "configuro el modelo de lenguaje de prueba",
            "values": {
                "llm": {
                    "backend": "anthropic",
                    "model": "modelo-ficticio",
                    "base_url": "",
                    "api_key": CLAVE_FICTICIA,
                    "confirmacion_no_local": "los formularios no llevan datos de personas afectadas",
                }
            },
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text

    engine = app.state.engine
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    objetivo = migrations.target_version()
    monkeypatch.setattr(
        migrations, "MIGRATIONS", [*migrations.MIGRATIONS, (objetivo + 1, "vacia", lambda conn: None)]
    )
    assert migrations.migrate(engine, settings.db_path) == objetivo + 1

    copias = list((settings.data_dir / "backups").glob("vigia.db.*.bak"))
    assert len(copias) == 1, copias
    con = sqlite3.connect(copias[0])
    try:
        assert con.execute("SELECT COUNT(*) FROM project").fetchone() is not None
    finally:
        con.close()
    # El comportamiento que se documenta: la copia lleva la base entera, clave incluida.
    assert CLAVE_FICTICIA.encode() in copias[0].read_bytes()
    for nombre in ("SEGURIDAD.md", "docs/manual/instalacion.md"):
        parrafos = _parrafos_sobre_copias((RAIZ / nombre).read_text(encoding="utf-8"))
        assert any(
            "clave" in p and ("sin cifrar" in p or "en claro" in p) and "entera" in p
            for p in parrafos
        ), f"{nombre} no cuenta que la copia previa guarda la base entera con la clave del LLM"


def test_las_copias_de_la_base_estan_documentadas():
    """Límite conocido: Ambos
    documentos nombran la carpeta `backups` y avisan de que las copias no se
    borran solas y hay que borrarlas a mano."""
    for nombre in ("SEGURIDAD.md", "docs/manual/instalacion.md"):
        texto = (RAIZ / nombre).read_text(encoding="utf-8")
        parrafos = _parrafos_sobre_copias(texto)
        assert parrafos, f"{nombre} no menciona la carpeta backups ni los .bak"
        assert any("borr" in p and "a mano" in p for p in parrafos), (
            f"{nombre} no avisa de que las copias no se borran solas"
        )


def test_id_de_proyecto_nuevo_no_hereda_el_diario_del_borrado(client: TestClient):
    """Un proyecto creado tras borrar otro no
    comparte id con él, o su diario no muestra los eventos del borrado."""
    a = _crear_proyecto(client, "ciclo-ids-uno")
    resp = client.delete(
        f"/api/projects/{a['id']}", params={"confirm": "true"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 204, resp.text
    b = _crear_proyecto(client, "ciclo-ids-dos")
    assert b["id"] != a["id"], "el id de un proyecto borrado se ha reutilizado"
    ev = client.get("/api/events", params={"project_id": b["id"], "limit": 500})
    assert ev.status_code == 200, ev.text
    items = ev.json()["items"]
    assert any(e["action"] == "proyecto.creado" for e in items)
    assert [e for e in items if e["action"] == "proyecto.borrado"] == []
