"""Diario de eventos y su exportación."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlmodel import Session, or_, select
from sse_starlette.sse import EventSourceResponse

from vigia.app.db import get_session
from vigia.app.errores import no_encontrado
from vigia.app.events import Actor, event_to_dict, get_actor, get_correlation_id, record_event
from vigia.app.models import Event, Project
from vigia.app.schemas import respuestas as resp
from vigia.app.schemas.events import AnotacionBody, ExportacionBody
from vigia.app.services.evidence import render_events_html, select_events
from vigia.app.sse import comprobar_cupo, sse_stream, suscribir

router = APIRouter(tags=["diario"])


def _filtros(
    session: Session,
    *,
    actor_kind: str | None,
    object_type: str | None,
    object_id: int | None,
    project_id: int | None,
    since: str | None,
    until: str | None,
    correlation_id: str | None,
):
    consulta = select(Event)
    if actor_kind is not None:
        consulta = consulta.where(Event.actor_kind == actor_kind)
    if object_type is not None:
        consulta = consulta.where(Event.object_type == object_type)
    if object_id is not None:
        consulta = consulta.where(Event.object_id == object_id)
    if project_id is not None:
        # con "Solo proyecto" activo, los eventos globales
        # (`project_id` nulo: `ajuste.cambiado`, `ajuste.llm_confirmado`) se
        # quedaban fuera. Se incluyen siempre, con un OR, en vez de exigir
        # una igualdad estricta.
        consulta = consulta.where(
            or_(Event.project_id == project_id, Event.project_id.is_(None))  # type: ignore[attr-defined]
        )
    if since is not None:
        consulta = consulta.where(Event.ts >= since)
    if until is not None:
        # Inclusivo, igual que `since` por abajo y que `select_events`
        # de `services/evidence.py` (usado por `GET /events/export` y por
        # `vigia export events`): el mismo instante pasado como `until` cuenta
        # como límite incluido en los dos sitios. Antes era exclusivo aquí
        # (pensado para la navegación de mes del diario, ya retirada): se unifica porque ya no queda ningún llamador que dependa
        # de la asimetría.
        consulta = consulta.where(Event.ts <= until)
    if correlation_id is not None:
        consulta = consulta.where(Event.correlation_id == correlation_id)
    return consulta


@router.get("/events", response_model=resp.ListResponse[resp.Event])
def list_events(
    session: Annotated[Session, Depends(get_session)],
    actor_kind: str | None = None,
    object_type: str | None = None,
    object_id: int | None = None,
    project_id: int | None = None,
    since: str | None = None,
    until: str | None = None,
    correlation_id: str | None = None,
    offset: int = 0,
    limit: Annotated[int, Query(le=500)] = 50,
) -> dict:
    """Eventos filtrados, del más reciente al más antiguo.

    `until` acota por arriba, igual que `since` por abajo, y es inclusivo:
    el mismo criterio que `select_events` de `services/evidence.py`."""
    consulta = _filtros(
        session,
        actor_kind=actor_kind,
        object_type=object_type,
        object_id=object_id,
        project_id=project_id,
        since=since,
        until=until,
        correlation_id=correlation_id,
    )
    total = len(session.exec(consulta).all())
    filas = session.exec(
        consulta.order_by(Event.ts.desc()).offset(offset).limit(limit)  # type: ignore[attr-defined]
    ).all()
    return {"items": [event_to_dict(e) for e in filas], "total": total}


@router.post("/events", response_model=resp.Event)
def create_annotation(
    body: AnotacionBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> dict:
    """Anotación humana en el diario: el botón redondo de la línea
    de tiempo. Solo el carril humano escribe por aquí; el motor y la aplicación
    registran sus eventos desde los servicios. Con `project_id`, el proyecto
    tiene que existir (404 si no)."""
    if actor.kind != "humano":
        raise HTTPException(
            422, "solo una persona puede escribir notas en el diario: entra como persona, no como agente"
        )
    if body.project_id is not None and session.get(Project, body.project_id) is None:
        raise no_encontrado("modelo", body.project_id, "modelos")
    evento = record_event(
        session,
        actor_kind="humano",
        actor_id=body.actor,
        role=body.role,
        action="anotacion.manual",
        object_type="project" if body.project_id is not None else "sistema",
        object_id=body.project_id,
        project_id=body.project_id,
        motivo=body.motivo,
        correlation_id=correlation_id,
        bus=request.app.state.bus,
    )
    session.commit()
    session.refresh(evento)
    return event_to_dict(evento)


@router.get("/events/stream")
async def stream_events(request: Request):
    """SSE con los eventos del diario y los avisos de trabajos del bus, más el latido.

    Los mensajes `job` pasan siempre para que la interfaz refresque los trabajos
    en curso sin sondear.
    """
    heartbeat_s = getattr(request.app.state.settings, "sse_heartbeat_s", 15.0)
    comprobar_cupo(request)

    async def _generador():
        # La suscripción nace dentro del generador: si el flujo no llega a abrirse
        # no queda ninguna viva, y se libera siempre en el `finally`.
        subscription = suscribir(request)
        if subscription is None:
            return
        try:
            async for evento in sse_stream(
                request,
                subscription,
                heartbeat_s=heartbeat_s,
                filtro=lambda msg: msg.get("type") in ("event", "job"),
            ):
                yield evento
        finally:
            subscription.close()

    return EventSourceResponse(_generador())


def _fecha_local(instante: str | None) -> str | None:
    """El instante del filtro en la hora local de la máquina, para leerlo en el diario.

    `desde` guarda el instante tal cual llegó (UTC, el que filtra); este texto es
    el mismo instante como lo ve la persona: `dd/mm/aaaa`, con la hora si no es medianoche.
    Un texto que no es una fecha ISO devuelve `None`."""
    if not instante:
        return None
    try:
        momento = datetime.fromisoformat(instante)
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    local = momento.astimezone()
    formato = "%d/%m/%Y" if (local.hour, local.minute) == (0, 0) else "%d/%m/%Y %H:%M"
    return local.strftime(formato)


@router.post("/events/exportaciones", response_model=resp.Event)
def registrar_exportacion(
    body: ExportacionBody,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    filtro_actor_kind: Annotated[str | None, Query(alias="actor_kind")] = None,
    filtro_object_type: Annotated[str | None, Query(alias="object_type")] = None,
    filtro_correlacion: Annotated[str | None, Query(alias="filter_correlation_id")] = None,
) -> dict:
    """Deja en el diario que alguien ha exportado las evidencias:
    quién, en qué formato, qué periodo y cuántos eventos llevaba. La descarga en
    sí es `GET /events/export`; la interfaz llama a esta ruta cuando termina.
    El recuento usa el mismo filtro que la exportación (también el
    carril, el tipo de objeto y la correlación, que llegan como parámetros de
    consulta; la correlación de este POST es la de la petición, no la filtrada)."""
    if body.project_id is not None and session.get(Project, body.project_id) is None:
        raise no_encontrado("modelo", body.project_id, "modelos")
    n_eventos = len(
        select_events(
            session,
            project_id=body.project_id,
            since=body.since,
            until=body.until,
            actor_kind=filtro_actor_kind,
            object_type=filtro_object_type,
            correlation_id=filtro_correlacion,
        )
    )
    filtros = {
        k: v
        for k, v in (
            ("carril", filtro_actor_kind),
            ("tipo_objeto", filtro_object_type),
            ("correlacion", filtro_correlacion),
        )
        if v is not None
    }
    evento = record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="diario.exportado",
        object_type="sistema",
        project_id=body.project_id,
        after={
            "formato": body.format,
            "desde": body.since,
            "desde_local": _fecha_local(body.since),
            "hasta": body.until,
            "n_eventos": n_eventos,
            **({"filtros": filtros} if filtros else {}),
        },
        correlation_id=correlation_id,
        bus=request.app.state.bus,
    )
    session.commit()
    session.refresh(evento)
    return event_to_dict(evento)


@router.get("/events/export")
def export_events(
    session: Annotated[Session, Depends(get_session)],
    project_id: int | None = None,
    since: str | None = None,
    until: str | None = None,
    format: str = "json",
    actor_kind: str | None = None,
    object_type: str | None = None,
    correlation_id: str | None = None,
) -> Response:
    """Exporta el diario a JSON o HTML (§9.4/§9.5), con cabecera `Content-Disposition`.

    `project_id` (opcional) acota al proyecto, con los eventos
    globales incluidos siempre (mismo criterio que `GET /events`); el prompt
    `informe_semanal` del MCP (`mcp/prompts.py`) lo usa para que el HTML de
    evidencias no traiga el diario entero de proyectos ajenos.

    `actor_kind`, `object_type` y `correlation_id` (opcionales)
    acotan igual que en `GET /events`: la pantalla del diario exporta lo que
    enseña."""
    if format not in ("json", "html"):
        raise HTTPException(422, f"el formato {format!r} no está disponible: elige json o html")

    filas = select_events(
        session,
        project_id=project_id,
        since=since,
        until=until,
        actor_kind=actor_kind,
        object_type=object_type,
        correlation_id=correlation_id,
    )

    if format == "html":
        contenido = render_events_html(filas)
        return Response(
            content=contenido,
            media_type="text/html",
            headers={"Content-Disposition": 'attachment; filename="evidencias-vigia.html"'},
        )

    contenido = json.dumps([event_to_dict(e) for e in filas], ensure_ascii=False, default=str)
    return Response(
        content=contenido,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="evidencias-vigia.json"'},
    )
