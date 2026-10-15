"""Salud del servicio y apagado protegido por token."""

from __future__ import annotations

import hmac
import platform
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlmodel import Session

from vigia.app.db import get_session
from vigia.app.jobs import COLAS
from vigia.app.migrations import current_version
from vigia.app.preflight import (
    DOMINIO_APAGADO,
    DOMINIO_IDENTIDAD,
    VENTANA_RETO_S,
    calcular_prueba,
    prueba_valida,
    reto_reciente,
)
from vigia.app.schemas import respuestas as resp
from vigia.app.settings import Settings

router = APIRouter(tags=["salud"])


def _colas_vacias() -> dict[str, dict[str, int]]:
    return {nombre: {"pendientes": 0, "en_curso": 0} for nombre in COLAS}


@router.get("/health", response_model=resp.Health)
def health(request: Request, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Estado del servicio: versión, carpeta de datos, esquema y ocupación de las colas."""
    s: Settings = request.app.state.settings
    engine = getattr(request.app.state, "engine", None)
    manager = getattr(request.app.state, "jobs", None)
    return {
        "status": "ok",
        "version": s.app_version,
        "python": platform.python_version(),
        "data_dir": str(s.data_dir),
        "port": getattr(request.app.state, "port", None),
        "schema_version": current_version(engine) if engine is not None else 0,
        "db_path": str(s.db_path),
        "queues": manager.queue_counts(session) if manager is not None else _colas_vacias(),
    }


@router.get("/identidad", include_in_schema=False)
def identidad(request: Request, x_vigia_reto: str | None = Header(default=None)) -> dict:
    """Prueba de que este servidor es el dueño del lock: HMAC del reto con su token.

    Los clientes locales la piden antes de enviar el token, un JSON o un fichero.
    """
    token = getattr(request.app.state, "shutdown_token", None)
    if not token or not x_vigia_reto or not reto_reciente(x_vigia_reto):
        raise HTTPException(status_code=404, detail="Sin identidad para ese reto")
    return {"prueba": calcular_prueba(token, x_vigia_reto, DOMINIO_IDENTIDAD)}


def _reto_nuevo(request: Request, reto: str) -> bool:
    """Un reto de apagado solo vale una vez (se guardan los de la última ventana)."""
    usados: dict[str, float] | None = getattr(request.app.state, "retos_apagado", None)
    if usados is None:
        usados = request.app.state.retos_apagado = {}
    ahora = time.time()
    for viejo in [r for r, t in usados.items() if ahora - t > VENTANA_RETO_S]:
        del usados[viejo]
    if reto in usados:
        return False
    usados[reto] = ahora
    return True


def _autorizado(request: Request, token_esperado: str | None, x_vigia_token: str | None, reto: str | None, prueba: str | None) -> bool:
    if not token_esperado:
        return False
    if x_vigia_token and hmac.compare_digest(x_vigia_token.encode("utf-8"), token_esperado.encode("utf-8")):
        return True
    if reto and prueba and reto_reciente(reto) and prueba_valida(token_esperado, reto, DOMINIO_APAGADO, prueba):
        return _reto_nuevo(request, reto)
    return False


@router.post("/shutdown", response_model=resp.Shutdown)
def shutdown(
    request: Request,
    x_vigia_token: str | None = Header(default=None),
    x_vigia_reto: str | None = Header(default=None),
    x_vigia_prueba: str | None = Header(default=None),
) -> dict:
    """Apaga el servidor con el token del lock o con una prueba firmada con él."""
    expected = request.app.state.shutdown_token
    if not _autorizado(request, expected, x_vigia_token, x_vigia_reto, x_vigia_prueba):
        raise HTTPException(status_code=403, detail="Token de apagado inválido")
    event = request.app.state.shutdown_event
    if event is not None:
        event.set()
    return {"status": "shutting_down"}
