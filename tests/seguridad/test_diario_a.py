"""Area diario (a): solicitante en el diario y avisos de atribucion autodeclarada.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from tests.api.test_alerts import DEMO_DIR, _crear_proyecto
from tests.api.test_human import _subir_usage_log
from vigia.app.jobs import JobContext
from vigia.app.main import create_app
from vigia.app.settings import Settings

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        data_dir=data_dir,
        host="127.0.0.1",
        port_start=8975,
        open_browser=False,
        jobs_inline=True,
        sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8975
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _cabeceras_agente(client: TestClient, correlation: str) -> dict[str, str]:
    token = client.get("/api/settings", params={"reveal": "true"}).json()["mcp_token"]
    return actor_headers("agente-prueba", kind="agente", correlation=correlation, token=token)


def _eventos(client: TestClient, **filtros) -> list[dict]:
    resp = client.get("/api/events", params={**filtros, "limit": 500})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def test_cross_evaluate_deja_al_solicitante_en_su_carril(client: TestClient):
    """El agente que evalua cruzadas consta en el diario."""
    proyecto = _crear_proyecto(client, name="diario-cross")
    _subir_usage_log(client, proyecto["id"])
    corr = "corr-diario-cross"
    resp = client.post(
        f"/api/projects/{proyecto['id']}/cross/evaluate", headers=_cabeceras_agente(client, corr)
    )
    assert resp.status_code == 200, resp.text
    eventos = _eventos(client, correlation_id=corr)
    assert eventos, "control positivo: el trabajo debe dejar eventos con esa correlacion"
    assert any(e["actor_kind"] == "agente" for e in eventos), [
        (e["action"], e["actor_kind"]) for e in eventos
    ]


def test_ingesta_deja_al_solicitante_mas_alla_de_subida_y_mapeo(client: TestClient):
    """El paso de ingerir tambien consta con el carril del solicitante."""
    proyecto = _crear_proyecto(client, name="diario-ingesta")
    corr = "corr-diario-ingesta"
    cab = _cabeceras_agente(client, corr)
    contenido = (DEMO_DIR / "01_baseline_feedback.json").read_bytes()
    resp = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("01_baseline_feedback.json", contenido, "application/json")},
        data={"kind": "combined", "role": "baseline"},
        headers=cab,
    )
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    dataset_id = cuerpo["dataset"]["id"]
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": cuerpo["suggested_mapping"]},
        headers=cab,
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/api/datasets/{dataset_id}/ingest", json={"evaluate": False}, headers=cab)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.json()
    eventos = _eventos(client, correlation_id=corr)
    acciones = {e["action"] for e in eventos}
    assert {"dataset.subido", "dataset.mapeado"} <= acciones, "control positivo"
    assert "batch.ingerido" in acciones, "control positivo: la ingesta debe dejar su evento"
    previos = {"dataset.subido", "dataset.mapeado"}
    assert any(e["actor_kind"] == "agente" for e in eventos if e["action"] not in previos), [
        (e["action"], e["actor_kind"]) for e in eventos
    ]


def test_cancelar_trabajo_deja_al_solicitante_en_su_carril(client: TestClient):
    """Cancelar un trabajo nombra a quien lo pide."""

    def _trabajo(ctx: JobContext, sesion) -> dict:
        return {"ok": True}

    job = client.app.state.jobs.enqueue("prueba", "rapida", _trabajo, params={})
    resp = client.post(f"/api/jobs/{job.id}/cancel", headers=_cabeceras_agente(client, "corr-cancel"))
    assert resp.status_code == 200, resp.text
    eventos = _eventos(client, object_type="job", object_id=job.id)
    assert any(e["action"] == "job.cancelado" for e in eventos), "control positivo"
    assert any(e["actor_kind"] == "agente" for e in eventos), [
        (e["action"], e["actor_kind"]) for e in eventos
    ]


def _seccion(texto: str, titulo: str) -> str:
    patron = rf"^## {re.escape(titulo)}\s*$(.*?)(?=^## |\Z)"
    m = re.search(patron, texto, flags=re.MULTILINE | re.DOTALL)
    assert m, f"falta la seccion {titulo!r}"
    return m.group(1)


def test_limites_conocidos_declara_atribucion_autodeclarada():
    """SEGURIDAD.md avisa de que nombre y carril del diario no prueban autoria."""
    texto = (RAIZ / "SEGURIDAD.md").read_text(encoding="utf-8")
    assert "## Qué no hace" in texto, "control positivo: el documento tiene su estructura"
    limites = _seccion(texto, "Qué no protege y qué hacer").lower()
    assert "diario" in limites
    assert re.search(r"autodeclar|declara el (llamador|cliente)|no (prueba|prueban|acredita|garantiza)", limites)


@pytest.mark.parametrize(
    "ruta",
    [
        "frontend/src/pages/modelos/alta-textos.ts",
        "docs/manual/uso.md",
        "src/vigia/content/guia-uso.json",
    ],
)
def test_textos_no_hablan_de_firma_en_el_diario(ruta: str):
    """La interfaz y el manual no presentan el diario como firma."""
    texto = (RAIZ / ruta).read_text(encoding="utf-8")
    assert len(texto) > 100, "control positivo: el fichero existe y tiene contenido"
    assert not re.search(r"firmad[oa]s? en el diario", texto, flags=re.IGNORECASE)


def test_agente_sin_token_recibe_401_control_acotado(client: TestClient):
    """El unico control real, token para el carril agente, actua."""
    resp = client.post(
        "/api/projects",
        json={"name": "diario-sin-token", "domain": "reuma"},
        headers=actor_headers("agente-prueba", kind="agente"),
    )
    assert resp.status_code == 401, resp.text
    resp = client.post(
        "/api/projects",
        json={"name": "diario-con-token", "domain": "reuma"},
        headers=_cabeceras_agente(client, "corr-token"),
    )
    assert resp.status_code == 200, resp.text
