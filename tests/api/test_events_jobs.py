"""Diario de eventos (filtros, export) y trabajos (lista, stream, cancel)."""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api.conftest import actor_headers
from vigia.app.bus import EventBus
from vigia.app.db import session_scope
from vigia.app.jobs import JobContext, JobManager
from vigia.app.settings import Settings


def _puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def _servidor_real(app: FastAPI) -> Iterator[str]:
    """Sirve `app` (ya inicializada por el `lifespan` de `TestClient`) en un socket real.

    El `TestClient` de Starlette ejecuta la app entera con `portal.call(...)` y no
    devuelve nada hasta que la corrutina termina: un generador SSE infinito
    (`GET /events/stream`) nunca acaba por sí solo, así que `client.stream(...)`
    se bloquea para siempre. Con un servidor real (socket TCP) el flujo sí llega
    de forma incremental. `lifespan="off"` porque el estado (motor, bus, colas)
    ya lo puso `TestClient` al entrar en su `with`.
    """
    puerto = _puerto_libre()
    config = uvicorn.Config(app, host="127.0.0.1", port=puerto, lifespan="off", log_level="warning")
    server = uvicorn.Server(config)
    hilo = threading.Thread(target=server.run, daemon=True)
    hilo.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.02)
        yield f"http://127.0.0.1:{puerto}"
    finally:
        server.should_exit = True
        hilo.join(timeout=5)


def _crear_proyecto(client: TestClient, name: str = "p-diario") -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "libre"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- eventos -----------------------------------------------------------


def test_list_events_filtra_por_actor_kind_y_object_type(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-eventos-1")
    resp = client.get("/api/events", params={"actor_kind": "sistema", "object_type": "sistema"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert all(e["actor_kind"] == "sistema" for e in body["items"])
    assert all(e["object_type"] == "sistema" for e in body["items"])

    resp = client.get(
        "/api/events", params={"actor_kind": "humano", "object_type": "project"}
    )
    body = resp.json()
    assert any(e["action"] == "proyecto.creado" for e in body["items"])
    assert body["items"][0]["object_id"] == proyecto["id"]


def test_list_events_filtra_por_since(client: TestClient):
    _crear_proyecto(client, name="p-eventos-since")
    resp_todos = client.get("/api/events")
    ultimo_ts = resp_todos.json()["items"][0]["ts"]
    resp = client.get("/api/events", params={"since": ultimo_ts})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


# --- `until` en `GET /events`, inclusivo, igual que `/events/export` --


def test_list_events_filtra_por_until_inclusivo(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-eventos-until")

    resp_todos = client.get(
        "/api/events", params={"object_type": "project", "object_id": proyecto["id"]}
    )
    assert resp_todos.status_code == 200
    eventos = resp_todos.json()["items"]
    assert len(eventos) == 1
    ts_creacion = eventos[0]["ts"]

    # `until` = justo el `ts` del evento: inclusivo, así que se queda dentro
    # (mismo criterio que `select_events` de `services/evidence.py`).
    resp_incluye_igual = client.get(
        "/api/events",
        params={"object_type": "project", "object_id": proyecto["id"], "until": ts_creacion},
    )
    assert resp_incluye_igual.status_code == 200
    assert resp_incluye_igual.json()["total"] == 1

    # un instante anterior lo deja fuera.
    resp_excluye = client.get(
        "/api/events",
        params={"object_type": "project", "object_id": proyecto["id"], "until": "2000-01-01T00:00:00"},
    )
    assert resp_excluye.status_code == 200
    assert resp_excluye.json()["total"] == 0

    # cualquier instante posterior sí lo incluye.
    resp_incluye = client.get(
        "/api/events",
        params={"object_type": "project", "object_id": proyecto["id"], "until": "2099-01-01T00:00:00"},
    )
    assert resp_incluye.status_code == 200
    assert resp_incluye.json()["total"] == 1


def test_list_events_since_y_until_a_la_vez(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-eventos-since-until")
    resp = client.get(
        "/api/events", params={"object_type": "project", "object_id": proyecto["id"]}
    )
    ts_creacion = resp.json()["items"][0]["ts"]

    # since <= ts <= until: el evento cae dentro del rango.
    resp_dentro = client.get(
        "/api/events",
        params={
            "object_type": "project",
            "object_id": proyecto["id"],
            "since": ts_creacion,
            "until": "2099-01-01T00:00:00",
        },
    )
    assert resp_dentro.json()["total"] == 1

    # since posterior al evento: fuera de rango aunque `until` sea amplio.
    resp_fuera = client.get(
        "/api/events",
        params={
            "object_type": "project",
            "object_id": proyecto["id"],
            "since": "2099-01-01T00:00:00",
            "until": "2100-01-01T00:00:00",
        },
    )
    assert resp_fuera.json()["total"] == 0


def test_list_events_filtra_por_correlation_id(client: TestClient):
    correlacion = "corr-monitor-1"
    proyecto = _crear_proyecto(client, name="p-eventos-corr")
    quality = next(m for m in proyecto["monitors"] if m["type"] == "quality")
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={"actor": "miguel", "motivo": "prueba de correlación", "enabled": False},
        headers=actor_headers("miguel", correlation=correlacion),
    )
    assert resp.status_code == 200, resp.text

    resp = client.get("/api/events", params={"correlation_id": correlacion})
    body = resp.json()
    assert body["total"] >= 1
    assert all(e["correlation_id"] == correlacion for e in body["items"])


# --- Eventos globales (`project_id` nulo) con "Solo proyecto" ----


def test_list_events_con_project_id_incluye_los_eventos_globales(client: TestClient):
    """Con `project_id` puesto (equivalente a "Solo proyecto" activo en el
    diario) los eventos sin proyecto (`ajuste.cambiado`, `ajuste.llm_confirmado`,
    o aquí una anotación de sistema) no se pierden: antes la igualdad estricta
    los dejaba fuera."""
    proyecto = _crear_proyecto(client, name="p-eventos-globales")
    otro_proyecto = _crear_proyecto(client, name="p-eventos-globales-otro")

    resp = client.post(
        "/api/events",
        json={"actor": "ana", "role": "gestor", "motivo": "anotación de sistema"},
        headers=actor_headers("ana"),
    )
    assert resp.status_code == 200, resp.text
    evento_global = resp.json()
    assert evento_global["project_id"] is None

    listado = client.get("/api/events", params={"project_id": proyecto["id"]}).json()
    assert any(e["id"] == evento_global["id"] for e in listado["items"])

    # el evento global también aparece filtrando por el otro proyecto: no es
    # que "pertenezca" a ninguno, se enseña siempre que hay alcance de proyecto.
    listado_otro = client.get("/api/events", params={"project_id": otro_proyecto["id"]}).json()
    assert any(e["id"] == evento_global["id"] for e in listado_otro["items"])

    # y el evento propio del proyecto (su creación) no se cuela en el otro.
    creacion_proyecto = next(
        e for e in listado["items"] if e["action"] == "proyecto.creado" and e["object_id"] == proyecto["id"]
    )
    assert not any(
        e["id"] == creacion_proyecto["id"] for e in listado_otro["items"]
    )


def test_eventos_de_un_job_comparten_correlation_id(client: TestClient):
    manager = client.app.state.jobs
    bus = client.app.state.bus

    def _trabajo_con_eventos(ctx: JobContext, session: Session) -> dict:
        from vigia.app.events import ACTOR_SISTEMA, record_event

        record_event(
            session,
            actor_kind=ACTOR_SISTEMA[0],
            actor_id=ACTOR_SISTEMA[1],
            action="sistema.migracion",
            object_type="sistema",
            correlation_id=ctx.correlation_id,
            job_id=ctx.job_id,
            bus=None,
        )
        return {"ok": True}

    correlacion = "corr-job-1"
    job = manager.enqueue(
        "prueba", "rapida", _trabajo_con_eventos, params={}, correlation_id=correlacion
    )
    assert job.status == "terminado"

    resp = client.get("/api/events", params={"correlation_id": correlacion})
    body = resp.json()
    assert body["total"] >= 1
    assert all(e["correlation_id"] == correlacion for e in body["items"])
    _ = bus


def test_post_events_registra_anotacion_humana(client: TestClient):
    """El botón de anotación de la línea de tiempo escribe en el
    carril humano con título en español y motivo obligatorio."""
    proyecto = _crear_proyecto(client, name="p-anotacion")
    cuerpo = {"actor": "ana", "role": "gestor", "motivo": "Revisado con el clínico", "project_id": proyecto["id"]}
    resp = client.post("/api/events", json=cuerpo)
    assert resp.status_code == 200, resp.text
    evento = resp.json()
    assert evento["action"] == "anotacion.manual"
    assert evento["actor_kind"] == "humano"
    assert evento["actor_id"] == "ana"
    assert evento["titulo"] == "Anotación humana"
    assert evento["motivo"] == "Revisado con el clínico"
    assert evento["project_id"] == proyecto["id"]

    listado = client.get("/api/events", params={"project_id": proyecto["id"], "actor_kind": "humano"}).json()
    assert any(e["id"] == evento["id"] for e in listado["items"])

    # Sin proyecto cuelga del sistema; sin motivo es 422; proyecto inexistente es 404.
    assert client.post("/api/events", json={"actor": "ana", "motivo": "nota"}).json()["object_type"] == "sistema"
    assert client.post("/api/events", json={"actor": "ana", "motivo": "  "}).status_code == 422
    assert client.post("/api/events", json={"actor": "ana", "motivo": "x", "project_id": 999999}).status_code == 404


def test_export_events_html(client: TestClient):
    _crear_proyecto(client, name="p-export-html")
    resp = client.get("/api/events/export", params={"format": "html"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Content-Disposition" in resp.headers
    assert "Evidencias Vigía" in resp.text


def test_export_events_json(client: TestClient):
    _crear_proyecto(client, name="p-export-json")
    resp = client.get("/api/events/export", params={"format": "json"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    datos = json.loads(resp.text)
    assert isinstance(datos, list)
    assert len(datos) >= 1


def test_export_events_json_filtra_por_project_id(client: TestClient):
    """`GET /events/export` con `project_id` se acota a ese
    proyecto MÁS los eventos globales (`project_id` nulo), igual que
    `GET /events`; sin él exporta el diario entero, como antes. El prompt
    `informe_semanal` del MCP (`mcp/prompts.py`) es quien lo necesitaba."""
    proyecto = _crear_proyecto(client, name="p-export-filtrado")
    otro_proyecto = _crear_proyecto(client, name="p-export-filtrado-otro")

    resp = client.post(
        "/api/events",
        json={"actor": "ana", "role": "gestor", "motivo": "anotación de sistema"},
        headers=actor_headers("ana"),
    )
    assert resp.status_code == 200, resp.text
    evento_global = resp.json()

    resp = client.get(
        "/api/events/export", params={"format": "json", "project_id": proyecto["id"]}
    )
    assert resp.status_code == 200, resp.text
    datos = json.loads(resp.text)
    ids = {e["id"] for e in datos}
    project_ids = {e["project_id"] for e in datos}

    assert evento_global["id"] in ids  # el evento global entra siempre
    assert otro_proyecto["id"] not in project_ids  # el otro proyecto, no
    assert proyecto["id"] in project_ids


def test_export_events_formato_no_soportado_422(client: TestClient):
    """§9.5: `format` distinto de `json`/`html` es un 422, no un `json` por defecto silencioso."""
    _crear_proyecto(client, name="p-export-formato-malo")
    resp = client.get("/api/events/export", params={"format": "csv"})
    assert resp.status_code == 422


def test_events_stream_emite_evento_y_heartbeat(client: TestClient):
    # `TestClient` no sirve para un generador SSE infinito (ver `_servidor_real`):
    # aquí se levanta un socket real sobre la misma app ya inicializada.
    with (
        _servidor_real(client.app) as base_url,
        httpx.Client(base_url=base_url, timeout=10) as http,
        http.stream("GET", "/api/events/stream") as resp,
    ):
        assert resp.status_code == 200
        lineas = resp.iter_lines()

        def _publica():
            time.sleep(0.05)
            with session_scope(client.app.state.engine) as session:
                from vigia.app.events import record_event

                record_event(
                    session,
                    actor_kind="humano",
                    actor_id="miguel",
                    action="proyecto.creado",
                    object_type="project",
                    object_id=1,
                    motivo=None,
                    bus=client.app.state.bus,
                )

        hilo = threading.Thread(target=_publica)
        hilo.start()

        vistos_evento = False
        vistos_heartbeat = False
        for linea in lineas:
            if linea.startswith("event: event"):
                vistos_evento = True
            if linea.startswith("event: heartbeat"):
                vistos_heartbeat = True
            if vistos_evento and vistos_heartbeat:
                break
        hilo.join(timeout=5)
        assert vistos_evento
        assert vistos_heartbeat


def test_events_stream_deja_pasar_mensajes_job(client: TestClient):
    """Los avisos `{"type": "job"}` del bus llegan al flujo global."""
    with (
        _servidor_real(client.app) as base_url,
        httpx.Client(base_url=base_url, timeout=10) as http,
        http.stream("GET", "/api/events/stream") as resp,
    ):
        assert resp.status_code == 200
        lineas = resp.iter_lines()

        def _publica():
            time.sleep(0.05)
            client.app.state.bus.publish(
                {"type": "job", "job_id": 1, "status": "en_curso", "progress": 0.5, "message": "x"}
            )

        hilo = threading.Thread(target=_publica)
        hilo.start()
        visto_job = False
        for linea in lineas:
            if linea.startswith("event: job"):
                visto_job = True
                break
            if linea.startswith("event: heartbeat"):
                break
        hilo.join(timeout=5)
        assert visto_job


# --- jobs ----------------------------------------------------------------


def _espera_estado(manager: JobManager, job_id: int, estados: tuple[str, ...]):
    for _ in range(500):
        job = manager.get(job_id)
        if job.status in estados:
            return job
        time.sleep(0.01)
    raise AssertionError(f"el trabajo {job_id} no llegó a {estados}")


def test_list_jobs_y_get_job(client: TestClient):
    manager = client.app.state.jobs

    def _trabajo(ctx: JobContext, session: Session) -> dict:
        return {"ok": True}

    job = manager.enqueue("prueba", "rapida", _trabajo, params={})
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert any(j["id"] == job.id for j in body["items"])

    resp = client.get(f"/api/jobs/{job.id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "terminado"


def test_list_jobs_filtra_por_status(client: TestClient):
    manager = client.app.state.jobs

    def _trabajo(ctx: JobContext, session: Session) -> dict:
        return {"ok": True}

    manager.enqueue("prueba", "rapida", _trabajo, params={})
    resp = client.get("/api/jobs", params={"status": "terminado"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert all(j["status"] == "terminado" for j in body["items"])


def test_get_job_404(client: TestClient):
    resp = client.get("/api/jobs/999999")
    assert resp.status_code == 404


def test_job_stream_termina_con_estado_final(client: TestClient):
    manager = client.app.state.jobs

    def _trabajo(ctx: JobContext, session: Session) -> dict:
        return {"ok": True}

    job = manager.enqueue("prueba", "rapida", _trabajo, params={})
    with client.stream("GET", f"/api/jobs/{job.id}/stream") as resp:
        assert resp.status_code == 200
        eventos = []
        for linea in resp.iter_lines():
            if linea.startswith("data:"):
                eventos.append(json.loads(linea[len("data:") :].strip()))
            if eventos and eventos[-1].get("status") in ("terminado", "error", "cancelado"):
                break
    assert eventos[-1]["status"] == "terminado"


def test_job_terminado_trae_result_y_message_final(client: TestClient):
    """`_publish_job` manda `result` y `error`, y el último `message` que
    puso el trabajo (no uno intermedio) queda, tanto en `GET /jobs/{id}` como en
    el último evento del stream."""
    manager = client.app.state.jobs

    def _trabajo(ctx: JobContext, session: Session) -> dict:
        ctx.progress(0.5, "a medias")
        ctx.progress(1.0, "terminando el trabajo")
        return {"ok": True, "n": 3}

    job = manager.enqueue("prueba", "rapida", _trabajo, params={})
    assert job.status == "terminado"

    resp = client.get(f"/api/jobs/{job.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] == {"ok": True, "n": 3}
    assert body["message"] == "terminando el trabajo"
    assert body["error"] is None

    with client.stream("GET", f"/api/jobs/{job.id}/stream") as resp_stream:
        eventos = [
            json.loads(linea[len("data:") :].strip())
            for linea in resp_stream.iter_lines()
            if linea.startswith("data:")
        ]
    assert eventos[-1]["result"] == {"ok": True, "n": 3}
    assert eventos[-1]["message"] == "terminando el trabajo"


def test_cancelar_job_en_curso_lo_deja_cancelado(data_dir):
    """Job real (jobs_inline=False) que se cancela mientras corre: el manager queda `cancelado`.

    Prueba solo la cancelación cooperativa de `JobManager` (esto es su carril).
    No ejercita un batch a medias: si el trabajo escribe en su propia sesión
    (`session.add(...); session.flush()`, sin `commit`) y la mantiene abierta
    mientras sondea `ctx.raise_if_cancelled()`, esa escritura retiene el único
    escritor de SQLite y bloquea la escritura de `cancel()` hasta que el
    trabajo termina por sí solo (ver el aviso en `JobContext`, jobs.py); con
    eso, `cancel()` nunca llega a tiempo y el test sería inestable. La
    verificación end-to-end de que un batch a medias no queda en la base tras
    cancelar pertenece al carril de ingesta, como test de integración sobre
    `ingest_dataset`.
    """
    settings = Settings(data_dir=data_dir, jobs_inline=False)
    from vigia.app.db import init_db, make_engine

    engine = make_engine(settings.db_path)
    init_db(engine, settings.db_path)
    bus = EventBus()
    manager = JobManager(engine, settings, bus)
    listo = threading.Event()

    def _trabajo_cancelable(ctx: JobContext, session: Session) -> dict:
        listo.set()
        for _ in range(200):
            ctx.raise_if_cancelled()
            time.sleep(0.01)
        return {"terminado": True}

    try:
        job = manager.enqueue("prueba", "llm", _trabajo_cancelable, params={})
        job_id = int(job.id or 0)
        assert listo.wait(timeout=5)
        cancelado = manager.cancel(job_id)
        assert cancelado.cancel_requested is True
        final = _espera_estado(manager, job_id, ("terminado", "error", "cancelado"))
        assert final.status == "cancelado"
    finally:
        manager.shutdown(timeout=5)
        engine.dispose()


def test_cancel_job_endpoint_registra_evento(client: TestClient, session: Session):
    manager = client.app.state.jobs

    def _trabajo(ctx: JobContext, sesion: Session) -> dict:
        return {"ok": True}

    job = manager.enqueue("prueba", "rapida", _trabajo, params={})
    resp = client.post(f"/api/jobs/{job.id}/cancel")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job.id

    resp = client.get("/api/events", params={"object_type": "job", "object_id": job.id})
    acciones = [e["action"] for e in resp.json()["items"]]
    assert "job.cancelado" in acciones
