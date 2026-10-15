"""Composición por grupo de un lote y etiquetado de `group_code`.

Extraído de `services/ingest.py` (que ya pasaba de 9 KB) porque solo sirve a
`GET /batches/{id}/composition` y a `GET /batches/{id}/records`: nada de esto
depende de la ingesta en sí. `ingest.py` reexporta `batch_composition` y
`group_labeller` para no mover su uso en `routers/datasets.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlmodel import Session, select

from vigia.app.models import Batch, Dataset, Project, Record
from vigia.app.services import alerting
from vigia.app.services import tarea as tarea_service
from vigia.core.schema import MOTIVO_SIN_RANGO, ColumnMapping

__all__ = ["batch_composition", "group_labeller"]


def _mapping_del_lote(session: Session, batch: Batch) -> ColumnMapping | None:
    """Mapeo del dataset origen del lote, o `None` si no hay dataset o no tiene mapeo.

    A diferencia de `services/evaluate._mapping_for_batch`, aquí no vale el
    respaldo `HARNESS_FEEDBACK_MAPPING`: sin mapeo, la etiqueta de grupo es
    `null` y la UI enseña el código.
    """
    if batch.dataset_id is None:
        return None
    dataset = session.get(Dataset, batch.dataset_id)
    if dataset is None or not dataset.mapping_json:
        return None
    return ColumnMapping(**dataset.mapping_json)


def group_labeller(session: Session, batch: Batch) -> Callable[[int], str | None]:
    """Traductor de `group_code` a etiqueta legible para un lote.

    Resuelve el mapeo del dataset origen una sola vez por petición y cachea la
    etiqueta por código: ni una consulta por registro. Sin mapeo, `None`.
    """
    mapping = _mapping_del_lote(session, batch)
    cache: dict[int, str | None] = {}

    def etiqueta(group_code: int) -> str | None:
        if mapping is None:
            return None
        if group_code not in cache:
            cache[group_code] = alerting.label_for_group_code(mapping, group_code)
        return cache[group_code]

    return etiqueta


def batch_composition(session: Session, batch: Batch) -> dict[str, Any]:
    """Composición por grupo del lote: n, recuentos y tasas de favorable.

    `pred_favorable_n`/`label_favorable_n` son los recuentos de los que salen
    las tasas ya existentes; `label_favorable_n` es `None` si el grupo no
    tiene ningún registro etiquetado, igual que su tasa.
    """
    etiqueta = group_labeller(session, batch)
    registros = session.exec(select(Record).where(Record.batch_id == batch.id)).all()
    # en una regresión sin rango la pertenencia no se calcula, así que las
    # tasas favorables no existen (nunca un 0 inventado).
    proyecto = session.get(Project, batch.project_id)
    sin_pertenencia = False
    if proyecto is not None:
        match proyecto.task_type:
            case "binary" | "multiclass":
                pass
            case "regression":
                sin_pertenencia = not tarea_service._rango_efectivo(proyecto)
            case _:
                raise ValueError(f"tipo de tarea no reconocido: {proyecto.task_type!r}")
    grupos: dict[int, dict[str, int]] = {}
    for r in registros:
        g = grupos.setdefault(
            r.group_code, {"n": 0, "n_pred_favorable": 0, "n_label": 0, "n_label_favorable": 0}
        )
        g["n"] += 1
        if r.prediction == 1:
            g["n_pred_favorable"] += 1
        if r.label is not None:
            g["n_label"] += 1
            if r.label == 1.0:
                g["n_label_favorable"] += 1

    # Supervisado (0) y referencia (1) primero; «otros» (-1) al final, como en la
    # tabla de composición de la pantalla.
    por_grupo = []
    for group_code, g in sorted(grupos.items(), key=lambda kv: (kv[0] not in (0, 1), kv[0])):
        por_grupo.append(
            {
                "group_code": group_code,
                "group_label": etiqueta(group_code),
                "n": g["n"],
                "pred_favorable_n": None if sin_pertenencia else g["n_pred_favorable"],
                "pred_favorable_rate": None
                if sin_pertenencia
                else ((g["n_pred_favorable"] / g["n"]) if g["n"] else None),
                "label_favorable_n": None
                if sin_pertenencia
                else (g["n_label_favorable"] if g["n_label"] else None),
                "label_favorable_rate": None
                if sin_pertenencia
                else ((g["n_label_favorable"] / g["n_label"]) if g["n_label"] else None),
                "n_labeled": g["n_label"],
            }
        )
    total_n = len(registros)
    total_label = sum(g["n_label"] for g in grupos.values())
    return {
        "groups": por_grupo,
        "total": {
            "n": total_n,
            "pred_favorable_rate": None
            if sin_pertenencia
            else (sum(g["n_pred_favorable"] for g in grupos.values()) / total_n)
            if total_n
            else None,
            "label_favorable_rate": None
            if sin_pertenencia
            else (sum(g["n_label_favorable"] for g in grupos.values()) / total_label)
            if total_label
            else None,
            "n_labeled": total_label,
        },
        "motivo": MOTIVO_SIN_RANGO if sin_pertenencia else None,
    }
