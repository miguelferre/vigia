"""Servicio de outcomes: resultado del sistema combinado por periodo.

Sin `Dataset` ni fichero en disco (a diferencia del diario de uso): un outcome
es una fila de tabla, no un fichero versionado. Sin alertas: ningún monitor
evalúa `Outcome`.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, select

from vigia.app.bus import EventBus
from vigia.app.events import Actor, record_event
from vigia.app.models import Outcome, Project, now_iso
from vigia.core.loaders import (
    LIMITE_FILAS_LOTE,
    contar_filas_csv,
    mensaje_limite_filas,
    read_csv_smart,
)
from vigia.core.schema import DatosNoValidos

__all__ = ["OUTCOME_COLUMNS", "ingest_outcomes", "list_outcomes"]

OUTCOME_COLUMNS = ("period", "metric_key", "value", "source")
_TROZO_UPSERT = 5000


def _read_outcomes_csv(file_bytes: bytes) -> pd.DataFrame:
    try:
        df, _dialecto = read_csv_smart(file_bytes, como_texto=True)
    except DatosNoValidos as exc:
        raise HTTPException(422, str(exc)) from exc
    faltantes = [c for c in OUTCOME_COLUMNS if c not in df.columns]
    if faltantes:
        raise HTTPException(
            422,
            f"faltan columnas obligatorias en el fichero de outcomes: {', '.join(faltantes)}; "
            f"la cabecera necesita al menos {', '.join(OUTCOME_COLUMNS)}",
        )
    return df


def _parse_value(valor: Any, *, fila_n: int) -> float | None:
    texto = str(valor).strip()
    if not texto:
        return None
    # Coma decimal («0,8»): solo si no hay punto, para no tocar «1,234.5».
    if "," in texto and "." not in texto:
        texto = texto.replace(",", ".")
    try:
        numero = float(texto)
    except ValueError as exc:
        raise HTTPException(
            422, f"el valor de la fila {fila_n} no es un número ({valor!r}): corrígelo y sube el fichero otra vez"
        ) from exc
    if not math.isfinite(numero):
        raise HTTPException(
            422, f"el valor de la fila {fila_n} no es un número finito ({valor!r}): corrígelo y sube el fichero otra vez"
        )
    return numero


def ingest_outcomes(
    session: Session,
    project: Project,
    *,
    file_bytes: bytes,
    actor: Actor,
    bus: EventBus | None = None,
    correlation_id: str | None = None,
) -> tuple[int, int, int]:
    """Ingiere el CSV de outcomes con upsert por `(project_id, period, metric_key, source)`.

    Devuelve `(n_rows, n_creados, n_actualizados)`. Deja el evento `outcome.ingerido`.
    """
    # el tope de filas por lote vale también aquí; se cuenta antes de leer.
    n_filas = contar_filas_csv(file_bytes)
    if n_filas > LIMITE_FILAS_LOTE:
        raise HTTPException(422, mensaje_limite_filas(n_filas))
    df = _read_outcomes_csv(file_bytes)

    vistas_en_fichero: set[tuple[str, str, str]] = set()
    filas_a_upsertar: list[tuple[str, str, str, float | None]] = []
    for posicion, fila in enumerate(df.itertuples(index=False), start=1):
        period = str(getattr(fila, "period", "")).strip()
        metric_key = str(getattr(fila, "metric_key", "")).strip()
        source = str(getattr(fila, "source", "")).strip()
        value = _parse_value(getattr(fila, "value", ""), fila_n=posicion)
        clave = (period, metric_key, source)
        if clave in vistas_en_fichero:
            raise HTTPException(
                422,
                "hay una fila repetida en el fichero: "
                f"periodo {period}, métrica {metric_key}, fuente {source}; deja solo una",
            )
        vistas_en_fichero.add(clave)
        filas_a_upsertar.append((period, metric_key, source, value))

    n_creados = 0
    n_actualizados = 0
    # Una sola consulta con lo que ya hay en el proyecto, no una por fila.
    existentes: set[tuple[str, str, str]] = set(
        session.exec(
            select(Outcome.period, Outcome.metric_key, Outcome.source).where(
                Outcome.project_id == project.id
            )
        ).all()
    )
    nuevas: list[dict[str, Any]] = []
    for period, metric_key, source, value in filas_a_upsertar:
        if (period, metric_key, source) in existentes:
            n_actualizados += 1
        else:
            n_creados += 1
        nuevas.append(
            {
                "project_id": project.id,
                "period": period,
                "metric_key": metric_key,
                "source": source,
                "value": value,
                "created_at": now_iso(),
            }
        )
    # upsert atómico sobre la clave única; una subida concurrente de la
    # misma clave actualiza la fila en vez de duplicarla o fallar.
    if nuevas:
        tabla = Outcome.__table__  # type: ignore[attr-defined]
        insercion = sqlite_insert(tabla)
        upsert = insercion.on_conflict_do_update(
            index_elements=["project_id", "period", "metric_key", "source"],
            set_={"value": insercion.excluded.value},
        )
        for inicio in range(0, len(nuevas), _TROZO_UPSERT):
            session.connection().execute(upsert, nuevas[inicio : inicio + _TROZO_UPSERT])

    session.flush()
    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="outcome.ingerido",
        object_type="project",
        object_id=project.id,
        project_id=project.id,
        after={"n_creados": n_creados, "n_actualizados": n_actualizados},
        correlation_id=correlation_id,
        bus=bus,
    )
    session.commit()
    return len(filas_a_upsertar), n_creados, n_actualizados


def list_outcomes(
    session: Session,
    project: Project,
    *,
    metric_key: str | None = None,
) -> tuple[list[Outcome], dict[str, list[Outcome]]]:
    """Devuelve `(rows, series)`: `rows` ordenadas por `period` y `metric_key`,
    `series` agrupadas por `metric_key` en listas ordenadas por `period`."""
    consulta = select(Outcome).where(Outcome.project_id == project.id)
    if metric_key:
        consulta = consulta.where(Outcome.metric_key == metric_key)
    filas = session.exec(consulta).all()
    filas = sorted(filas, key=lambda o: (o.period, o.metric_key))

    series: dict[str, list[Outcome]] = {}
    for fila in sorted(filas, key=lambda o: (o.metric_key, o.period)):
        series.setdefault(fila.metric_key, []).append(fila)
    return filas, series
