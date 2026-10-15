"""Endurecimiento de las colas de trabajos, bus de eventos, flujos SSE y diario de uso.

Un test por arreglo: deduplicación de trabajos, tope de suscripciones, cupo 503 del flujo,
paginación de trabajos, tope de la subida del diario, evento de cruzadas y fecha local.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.app.bus import BusLleno, EventBus
from vigia.app.main import create_app
from vigia.app.routers.events import _fecha_local
from vigia.app.services import subidas
from vigia.app.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=d, host="127.0.0.1", port_start=8976, open_browser=False,
        jobs_inline=True, sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8976
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post(
        "/api/projects", json={"name": name, "domain": "reuma"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_enqueue_con_clave_devuelve_el_trabajo_vigente_y_la_suelta_al_acabar(client: TestClient):
    """Una clave de deduplicación devuelve el trabajo pendiente; al terminar, deja encolar otro."""
    jobs = client.app.state.jobs
    jobs.settings.jobs_inline = False
    bloqueo = threading.Event()
    try:
        jobs._start_workers()

        def _trabajo(ctx, sesion) -> dict:
            bloqueo.wait(20)
            return {"ok": True}

        a = jobs.enqueue("prueba", "rapida", _trabajo, clave_dedup="k:1")
        b = jobs.enqueue("prueba", "rapida", _trabajo, clave_dedup="k:1")
        otro = jobs.enqueue("prueba", "rapida", _trabajo, clave_dedup="k:2")
        sin_clave = jobs.enqueue("prueba", "rapida", _trabajo)
        assert a.id == b.id
        assert len({a.id, otro.id, sin_clave.id}) == 3
        bloqueo.set()
        for _ in range(100):
            if jobs.get(a.id).status == "terminado":
                break
            threading.Event().wait(0.1)
        assert jobs.get(a.id).status == "terminado"
        c = jobs.enqueue("prueba", "rapida", _trabajo, clave_dedup="k:1")
        assert c.id != a.id
    finally:
        bloqueo.set()


def test_bus_con_tope_de_suscripciones_lanza_bus_lleno():
    """El bus no admite más suscripciones que su tope y las libera al cerrar."""
    bus = EventBus(max_subscribers=2)
    a = bus.subscribe()
    bus.subscribe()
    assert bus.lleno
    with pytest.raises(BusLleno):
        bus.subscribe()
    a.close()
    assert not bus.lleno
    bus.subscribe()


def test_flujo_con_el_bus_lleno_responde_503_en_espanol(client: TestClient):
    """Con el bus lleno, abrir un flujo SSE da 503 con un texto claro y no deja suscripción."""
    bus = client.app.state.bus
    bus._max_subscribers = bus.n_subscribers
    r = client.get("/api/events/stream")
    assert r.status_code == 503, r.text
    assert "demasiadas conexiones" in r.json()["detail"]
    assert bus.n_subscribers == bus._max_subscribers


def test_listado_de_trabajos_rechaza_paginacion_no_valida(client: TestClient):
    """`limit` 0 o negativo y `offset` negativo dan 422 en el listado de trabajos."""
    for params in ({"limit": 0}, {"limit": -1}, {"offset": -1}):
        r = client.get("/api/jobs", params=params)
        assert r.status_code == 422, (params, r.text)
    assert client.get("/api/jobs", params={"limit": 1, "offset": 0}).status_code == 200


def test_subida_del_diario_por_encima_del_tope_da_413(client: TestClient, monkeypatch):
    """Un diario de uso mayor que el tope se rechaza con 413 y no deja fichero en uploads/."""
    proyecto = _crear_proyecto(client, "end4-tope")
    monkeypatch.setattr(subidas, "LIMITE_BYTES_SUBIDA", 64)
    contenido = b"date,human_decision,model_output,ground_truth\n" + b"2026-01-05,refer,refer,refer\n" * 5
    r = client.post(
        f"/api/projects/{proyecto['id']}/usage-logs/upload",
        files={"file": ("uso.csv", contenido, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert r.status_code == 413, r.text
    assert "máximo" in r.json()["detail"]
    carpeta = Path(client.app.state.settings.data_dir) / "uploads" / str(proyecto["id"])
    assert not carpeta.exists() or [p for p in carpeta.rglob("*") if p.is_file()] == []


def test_pedir_cruzadas_deja_un_evento_con_el_solicitante(client: TestClient):
    """`POST cross/evaluate` anota `cruzadas.solicitadas` con el actor de las cabeceras y su título."""
    proyecto = _crear_proyecto(client, "end4-cruzadas")
    r = client.post(
        f"/api/projects/{proyecto['id']}/cross/evaluate",
        headers=actor_headers("ana", correlation="corr-end4"),
    )
    assert r.status_code == 200, r.text
    eventos = client.get("/api/events", params={"correlation_id": "corr-end4"}).json()["items"]
    solicitud = [e for e in eventos if e["action"] == "cruzadas.solicitadas"]
    assert len(solicitud) == 1, [e["action"] for e in eventos]
    assert solicitud[0]["actor_id"] == "ana" and solicitud[0]["actor_kind"] == "humano"
    assert solicitud[0]["job_id"] == r.json()["id"]
    assert solicitud[0]["titulo"] == "Ha pedido evaluar las alertas cruzadas"


def test_diario_exportado_escribe_el_desde_en_hora_local(client: TestClient):
    """`after.desde_local` es el instante en la hora de la máquina; `desde` sigue siendo el instante."""
    instante = "2026-10-05T22:00:00Z"
    r = client.post(
        "/api/events/exportaciones",
        json={"format": "json", "since": instante},
        headers=actor_headers("ana"),
    )
    assert r.status_code == 200, r.text
    after = r.json()["after"]
    esperado = datetime(2026, 10, 5, 22, 0, tzinfo=UTC).astimezone()
    formato = "%d/%m/%Y" if (esperado.hour, esperado.minute) == (0, 0) else "%d/%m/%Y %H:%M"
    assert after["desde"] == instante
    assert after["desde_local"] == esperado.strftime(formato)
    assert after["desde_local"] in r.json()["titulo"]
    assert "Z" not in r.json()["titulo"]


def test_fecha_local_sin_fecha_o_con_texto_no_valido_es_none():
    assert _fecha_local(None) is None
    assert _fecha_local("no es una fecha") is None


def test_config_de_cruzadas_descarta_valores_fuera_de_rango():
    """Una fila antigua con z_alert, min_group o min_positives fuera de rango vuelve al valor de fábrica."""
    from vigia.app.services.human_layer import _config_cruzadas_sana
    from vigia.human.cross_alerts import CrossConfig

    mala = {"z_alert": -1, "min_group": 0, "min_positives": -5, "min_clinician": 12}
    sana = _config_cruzadas_sana(mala)
    assert sana == {"min_clinician": 12}
    config = CrossConfig(**sana)
    fabrica = CrossConfig()
    assert (config.z_alert, config.min_group, config.min_positives) == (
        fabrica.z_alert, fabrica.min_group, fabrica.min_positives,
    )
    assert _config_cruzadas_sana({"z_alert": float("inf")}) == {}
    assert _config_cruzadas_sana({"z_alert": 2.5, "min_group": 10}) == {"z_alert": 2.5, "min_group": 10}
    assert _config_cruzadas_sana(None) == {}
