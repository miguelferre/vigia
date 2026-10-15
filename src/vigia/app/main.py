"""Aplicación FastAPI de Vigía: base de datos, colas, routers de /api y servido del SPA."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from vigia.app.bus import EventBus
from vigia.app.db import make_engine, session_scope
from vigia.app.errores import TEXTO_404_RUTA, registrar_manejadores
from vigia.app.events import ACTOR_SISTEMA, record_event
from vigia.app.jobs import JobManager
from vigia.app.migrations import current_version, migrate
from vigia.app.routers import ALL_ROUTERS
from vigia.app.seguridad_http import FronteraLocal
from vigia.app.settings import Settings

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
ASSETS_DIR = STATIC_DIR / "assets"
INDEX_FILE = STATIC_DIR / "index.html"

_log = logging.getLogger("vigia.app")

_FRONTEND_NO_COMPILADO = """\
<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><title>Vigía</title></head>
<body>
<h1>Vigía: frontend no compilado</h1>
<p>No se encontró <code>static/index.html</code>. El servidor funciona: prueba
<a href="/api/health">/api/health</a>.</p>
</body>
</html>
"""


def create_app(settings: Settings) -> FastAPI:
    """Construye la app FastAPI: lifespan (BD, migraciones, colas), /api y el SPA."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Abre la base de datos y las colas al arrancar y las cierra al terminar."""
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = make_engine(settings.db_path)
        app.state.engine = engine

        version_previa = current_version(engine)
        version = migrate(engine, settings.db_path)
        app.state.schema_version = version

        bus = EventBus()
        app.state.bus = bus
        app.state.jobs = JobManager(engine, settings, bus)
        # lo que quedó vivo en un cierre anterior no lo ejecutará nadie.
        app.state.jobs.reconciliar_huerfanos()

        with session_scope(engine) as session:
            if version != version_previa:
                record_event(
                    session,
                    actor_kind=ACTOR_SISTEMA[0],
                    actor_id=ACTOR_SISTEMA[1],
                    action="sistema.migracion",
                    object_type="sistema",
                    before={"schema_version": version_previa},
                    after={"schema_version": version},
                    motivo="migración del esquema al arrancar",
                    bus=bus,
                )
            record_event(
                session,
                actor_kind=ACTOR_SISTEMA[0],
                actor_id=ACTOR_SISTEMA[1],
                action="sistema.arranque",
                object_type="sistema",
                after={
                    "version": settings.app_version,
                    "schema_version": version,
                    "data_dir": str(settings.data_dir),
                },
                bus=bus,
            )
        try:
            yield
        finally:
            app.state.jobs.shutdown()
            with session_scope(engine) as session:
                record_event(
                    session,
                    actor_kind=ACTOR_SISTEMA[0],
                    actor_id=ACTOR_SISTEMA[1],
                    action="sistema.apagado",
                    object_type="sistema",
                    after={"version": settings.app_version},
                    bus=bus,
                )
            engine.dispose()

    # Sin /docs ni /redoc: cargan scripts de un CDN. El esquema sigue en /openapi.json.
    # `strict_content_type` explícito: un cuerpo JSON exige `Content-Type: application/json`.
    app = FastAPI(
        title="Vigía",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        strict_content_type=True,
    )
    app.state.settings = settings
    app.state.shutdown_token = None
    app.state.shutdown_event = None
    app.state.engine = None
    app.state.bus = None
    app.state.jobs = None
    app.add_middleware(FronteraLocal)
    registrar_manejadores(app)

    for modulo in ALL_ROUTERS:
        app.include_router(modulo.router, prefix="/api")

    if ASSETS_DIR.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(ASSETS_DIR)),
            name="assets",
        )

    @app.get("/{full_path:path}")
    def spa_catch_all(full_path: str) -> Response:
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": TEXTO_404_RUTA})
        if INDEX_FILE.is_file():
            response = FileResponse(str(INDEX_FILE), media_type="text/html")
            response.headers["Cache-Control"] = "no-store"
            return response
        return HTMLResponse(
            content=_FRONTEND_NO_COMPILADO,
            headers={"Cache-Control": "no-store"},
        )

    return app
