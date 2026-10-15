"""Serie de alertas por lote, día u hora para el panel del cuadro.

`alert_series` agrega alertas y comprobaciones por lote o por tramo temporal en
una zona horaria dada; la semántica es la del gráfico `GraficoAlertasPorLote.tsx`
del frontend: una alerta cuenta en cada lote cuya evaluación aparece en
cualquier entrada de su `history[]`, no solo en la primera. Las cruzadas
(`Evaluation.batch_id` siempre `None`) no tienen lote: en `granularity=batch`
van aparte en `cross_unbatched`; en `day`/`hour` entran por `opened_at` en su
propio tramo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, func, select

from vigia.app.models import Alert, Batch, Dataset, Evaluation, Measurement, Project
from vigia.app.services.alert_series_tramos import items_por_lote, items_por_tramo
from vigia.app.services.alert_series_util import (
    marca_a_zona,
    parse_limite,
    severidad_vacia,
    zona_horaria,
)

__all__ = ["alert_series"]

_GRANULARIDADES = ("batch", "day", "hour")


def _lotes_del_proyecto(session: Session, project_id: int) -> dict[int, Batch]:
    return {b.id: b for b in session.exec(select(Batch).where(Batch.project_id == project_id)).all()}


def _nombres_de_lotes(lotes: dict[int, Batch], session: Session) -> dict[int, str]:
    """`batch_id -> nombre` (el del dataset de origen) de los lotes que lo tienen."""
    ids = {b.dataset_id for b in lotes.values() if b.dataset_id is not None}
    if not ids:
        return {}
    nombres = dict(session.exec(select(Dataset.id, Dataset.name).where(Dataset.id.in_(ids))).all())  # type: ignore[union-attr]
    return {b.id: nombres[b.dataset_id] for b in lotes.values() if b.dataset_id in nombres}


def _utc_iso(momento: datetime | None) -> str | None:
    """`momento` (con tzinfo) a ISO 8601 UTC con microsegundos: mismo formato
    que `models.now_iso()`, así que es comparable como texto con
    `created_at`/`opened_at` directamente en el `WHERE`/`HAVING`."""
    return momento.astimezone(UTC).isoformat(timespec="microseconds") if momento is not None else None


def _marcas_y_medidas(
    session: Session,
    project_id: int,
    *,
    desde_utc: str | None = None,
    hasta_utc: str | None = None,
) -> tuple[dict[int, str], dict[int, int], dict[int, int]]:
    """`batch_id -> marca` (máximo `created_at` de sus evaluaciones) y
    `batch_id -> n_checks` (filas de `Measurement` de esas evaluaciones).

    `desde_utc`/`hasta_utc` acotan por `HAVING` sobre el máximo ya
    agregado, no fila a fila: un lote entra si su ÚLTIMA evaluación (la marca
    que se enseña) cae en el rango, el mismo criterio que antes filtraba en
    Python sobre `marca_por_batch` ya calculado."""
    marca_maxima = func.max(Evaluation.created_at)
    consulta_marca = (
        select(Evaluation.batch_id, marca_maxima)
        .where(Evaluation.project_id == project_id, Evaluation.batch_id.is_not(None))  # type: ignore[attr-defined]
        .group_by(Evaluation.batch_id)
    )
    if desde_utc is not None:
        consulta_marca = consulta_marca.having(marca_maxima >= desde_utc)
    if hasta_utc is not None:
        consulta_marca = consulta_marca.having(marca_maxima <= hasta_utc)
    marca_por_batch: dict[int, str] = dict(session.exec(consulta_marca).all())
    evaluaciones_con_lote = session.exec(
        select(Evaluation.id, Evaluation.batch_id).where(
            Evaluation.project_id == project_id, Evaluation.batch_id.is_not(None)  # type: ignore[attr-defined]
        )
    ).all()
    eval_ids = [e for e, _b in evaluaciones_con_lote]
    conteo_medidas: dict[int, int] = {}
    if eval_ids:
        conteo_medidas = dict(
            session.exec(
                select(Measurement.evaluation_id, func.count())
                .where(Measurement.evaluation_id.in_(eval_ids))  # type: ignore[attr-defined]
                .group_by(Measurement.evaluation_id)
            ).all()
        )
    n_checks_por_batch: dict[int, int] = {}
    for eval_id, batch_id in evaluaciones_con_lote:
        n_checks_por_batch[batch_id] = n_checks_por_batch.get(batch_id, 0) + conteo_medidas.get(eval_id, 0)
    return marca_por_batch, n_checks_por_batch, dict(evaluaciones_con_lote)


def _alertas_por_lote(
    alertas: list[Alert], batch_por_eval: dict[int, int]
) -> dict[int, list[tuple[int, str, str]]]:
    """Para cada lote, las `(id, monitor_type, severity)` de las alertas (no
    cruzadas) cuyo historial toca una evaluación de ese lote; cada par (alerta,
    lote) una vez. El id alimenta `alert_ids` del ítem, con el que la tabla del
    cuadro filtra por el tramo pulsado con la misma semántica que la
    gráfica (`Alert.batch_id` solo diría el último lote)."""
    por_batch: dict[int, list[tuple[int, str, str]]] = {}
    for a in alertas:
        if a.monitor_type == "cross":
            continue
        lotes_tocados: set[int] = set()
        for entrada in a.history_json or []:
            eval_id = entrada.get("evaluation_id") if isinstance(entrada, dict) else None
            batch_id = batch_por_eval.get(eval_id) if eval_id is not None else None
            if batch_id is not None:
                lotes_tocados.add(batch_id)
        for batch_id in lotes_tocados:
            por_batch.setdefault(batch_id, []).append((a.id or 0, a.monitor_type, a.severity))
    return por_batch


def alert_series(
    session: Session,
    project: Project,
    *,
    granularity: str,
    since: str | None,
    until: str | None,
    tz: str,
) -> dict[str, Any]:
    if granularity not in _GRANULARIDADES:
        raise HTTPException(
            422, f"granularity debe ser batch, day u hour; se recibió {granularity!r}"
        )
    zona = zona_horaria(tz)
    desde = parse_limite(since, campo="since", zona=zona, fin_de_dia=False) if since else None
    hasta = parse_limite(until, campo="until", zona=zona, fin_de_dia=True) if until else None
    desde_utc, hasta_utc = _utc_iso(desde), _utc_iso(hasta)

    lotes = _lotes_del_proyecto(session, project.id)
    nombres = _nombres_de_lotes(lotes, session)
    # `since`/`until` al `HAVING` de la marca del lote (abajo) y al
    # `WHERE` de las cruzadas (más abajo), no a un filtro en Python después de
    # traer las filas. `_alertas_por_lote` sigue necesitando TODAS las alertas
    # no cruzadas del proyecto (sin acotar por fecha): un lote entra en rango
    # por su propia marca, no por la fecha de las alertas que lo tocan.
    marca_por_batch, n_checks_por_batch, batch_por_eval = _marcas_y_medidas(
        session, project.id, desde_utc=desde_utc, hasta_utc=hasta_utc
    )
    alertas_no_cross = session.exec(
        select(Alert).where(
            Alert.project_id == project.id,
            Alert.monitor_type != "cross",
            Alert.status != "retirada",
        )
    ).all()
    por_batch = _alertas_por_lote(alertas_no_cross, batch_por_eval)

    batch_ids_en_rango = list(marca_por_batch.keys())

    consulta_cross = select(Alert).where(
        Alert.project_id == project.id,
        Alert.monitor_type == "cross",
        Alert.status != "retirada",
    )
    if desde_utc is not None:
        consulta_cross = consulta_cross.where(Alert.opened_at >= desde_utc)  # type: ignore[attr-defined]
    if hasta_utc is not None:
        consulta_cross = consulta_cross.where(Alert.opened_at <= hasta_utc)  # type: ignore[attr-defined]
    cross_en_rango: list[tuple[datetime, int, str]] = [
        (marca_a_zona(a.opened_at, zona), a.id or 0, a.severity)
        for a in session.exec(consulta_cross).all()
    ]

    if granularity == "batch":
        items = items_por_lote(
            batch_ids_en_rango, lotes, marca_por_batch, zona, por_batch, n_checks_por_batch, nombres
        )
        cross_unbatched = severidad_vacia()
        for _marca, _alert_id, severidad in cross_en_rango:
            if severidad in cross_unbatched:
                cross_unbatched[severidad] += 1
    else:
        items = items_por_tramo(
            granularity,
            batch_ids_en_rango,
            lotes,
            marca_por_batch,
            zona,
            por_batch,
            n_checks_por_batch,
            cross_en_rango,
            nombres,
        )
        # Con día/hora las cruzadas ya entran en su tramo (`by_monitor.cross`):
        # no queda nada "sin lote".
        cross_unbatched = severidad_vacia()

    return {
        "granularity": granularity,
        "since": since,
        "until": until,
        "tz": tz,
        "items": items,
        "total": len(items),
        "cross_unbatched": cross_unbatched,
    }
