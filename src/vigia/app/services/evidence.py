"""Render único de evidencias del diario: usado por `routers/events.py`
(`GET /events/export`) y por `vigia export events`, para que el HTML producido
por la API y por la CLI sea idéntico ante los mismos eventos.
"""

from __future__ import annotations

import html

from sqlmodel import Session, or_, select

from vigia.app.models import Event

__all__ = ["render_events_html", "select_events"]

TITULO_EVIDENCIAS = "Evidencias Vigía"

_ENCABEZADOS = ("id", "ts", "actor_kind", "actor_id", "action", "object_type", "object_id", "motivo")


# Claves de los eventos `sistema.*` que llevan una ruta del equipo del usuario.
_CLAVES_CON_RUTA = ("data_dir",)


def _sin_ruta_local(evento: Event) -> Event:
    """El evento tal cual, o una copia sin la ruta local si es de `sistema.*`: el fichero
    de evidencias que se entrega a un tercero no revela la carpeta de datos del usuario.
    La copia no pertenece a la sesión: el diario guardado no cambia."""
    despues = evento.after_json
    if not (
        evento.action.startswith("sistema.")
        and isinstance(despues, dict)
        and any(k in despues for k in _CLAVES_CON_RUTA)
    ):
        return evento
    copia = Event(**{campo: getattr(evento, campo) for campo in Event.model_fields})
    copia.after_json = {k: v for k, v in despues.items() if k not in _CLAVES_CON_RUTA}
    return copia


def select_events(
    session: Session,
    *,
    project_id: int | None = None,
    since: str | None = None,
    until: str | None = None,
    actor_kind: str | None = None,
    object_type: str | None = None,
    correlation_id: str | None = None,
) -> list[Event]:
    """Eventos del diario entre `since` y `until` (ISO 8601), en orden cronológico.

    Orden ascendente (más antiguo primero): la exportación es un informe de
    evidencias que se lee como línea de tiempo, a diferencia de `GET /events`
    (consulta interactiva, más reciente primero).

    `until` es inclusivo: el mismo criterio que `_filtros` de
    `routers/events.py` (`GET /events`), que antes era exclusivo y se unificó
    a este.

    `project_id` (opcional) acota al proyecto, incluidos los
    eventos globales (`project_id` nulo: `ajuste.cambiado`,
    `ajuste.llm_confirmado`), con el mismo criterio OR que `_filtros` de
    `routers/events.py`. Sin él, exporta el diario entero, como hasta ahora.

    `actor_kind`, `object_type` y `correlation_id` (opcionales)
    son los otros filtros de la pantalla del diario, con la misma igualdad
    que `GET /events`: así la exportación trae lo que la pantalla enseña.
    """
    consulta = select(Event).order_by(Event.ts.asc(), Event.id.asc())  # type: ignore[attr-defined]
    if project_id is not None:
        consulta = consulta.where(
            or_(Event.project_id == project_id, Event.project_id.is_(None))  # type: ignore[attr-defined]
        )
    if since is not None:
        consulta = consulta.where(Event.ts >= since)
    if until is not None:
        consulta = consulta.where(Event.ts <= until)
    if actor_kind is not None:
        consulta = consulta.where(Event.actor_kind == actor_kind)
    if object_type is not None:
        consulta = consulta.where(Event.object_type == object_type)
    if correlation_id is not None:
        consulta = consulta.where(Event.correlation_id == correlation_id)
    return [_sin_ruta_local(e) for e in session.exec(consulta)]


def render_events_html(eventos: list[Event], *, titulo: str = TITULO_EVIDENCIAS) -> str:
    """HTML autocontenido con la tabla de eventos, para adjuntar como evidencia."""

    def _fila(evento: Event) -> str:
        valores = (
            evento.id,
            evento.ts,
            evento.actor_kind,
            evento.actor_id,
            evento.action,
            evento.object_type,
            evento.object_id if evento.object_id is not None else "",
            evento.motivo or "",
        )
        celdas = "".join(f"<td>{html.escape(str(v))}</td>" for v in valores)
        return f"<tr>{celdas}</tr>"

    filas_html = "\n".join(_fila(e) for e in eventos)
    cabecera_html = "".join(f"<th>{html.escape(h)}</th>" for h in _ENCABEZADOS)
    titulo_html = html.escape(titulo)
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{titulo_html}</title>
<style>
body {{ font-family: "Segoe UI", sans-serif; margin: 2rem; color: #222; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 4px 8px; font-size: 0.85rem; text-align: left; vertical-align: top; }}
th {{ background: #f0f0f0; }}
</style>
</head>
<body>
<h1>{titulo_html}</h1>
<p>{len(eventos)} eventos.</p>
<table>
<thead>
<tr>{cabecera_html}</tr>
</thead>
<tbody>
{filas_html}
</tbody>
</table>
</body>
</html>
"""
