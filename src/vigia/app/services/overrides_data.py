"""Lectura común de `usage_log` para los overrides: la comparten
`overrides.py` y `overrides_me.py` para no duplicar el join con `Batch`.
"""

from __future__ import annotations

import pandas as pd
from sqlmodel import Session, select

from vigia.app.models import Batch, UsageLog

__all__ = ["usage_df"]


def _es_override(f: UsageLog) -> int | None:
    """Override de una fila: multiclase compara las clases (una
    discrepancia entre dos clases no favorables también es un override);
    binario, o una fila sin clases, compara los enteros de siempre. Regresión:
    los enteros guardan la pertenencia al rango favorable, así que el
    override es que el profesional y el modelo caigan a distinto lado del corte."""
    if f.human_class is not None and f.model_class is not None:
        return int(f.human_class != f.model_class)
    if f.human_decision is None or f.model_output is None:
        return None
    return int(f.human_decision != f.model_output)


def usage_df(session: Session, project_id: int, model_version_id: int) -> pd.DataFrame:
    """Filas de `usage_log` de la versión, con `phase` unida desde `Batch.phase_label`.

    Filas sin `batch_id` (diario subido a mano) van al grupo `"sin_fase"`.
    """
    filas = session.exec(
        select(UsageLog).where(
            UsageLog.project_id == project_id,
            UsageLog.model_version_id == model_version_id,
        )
    ).all()
    batch_ids = {f.batch_id for f in filas if f.batch_id is not None}
    fases: dict[int, str | None] = {}
    if batch_ids:
        lotes = session.exec(select(Batch).where(Batch.id.in_(batch_ids))).all()
        fases = {b.id: b.phase_label for b in lotes}
    registros = [
        {
            "date": f.date or None,
            "clinician_pseudonym": f.clinician_pseudonym,
            "subgroup": f.subgroup if f.subgroup is not None else "sin_subgrupo",
            "phase": (fases.get(f.batch_id) or "sin_fase") if f.batch_id is not None else "sin_fase",
            "override": _es_override(f),
            # las cifras de una regresión; nulas en clasificación.
            "human_value": f.human_value,
            "model_value": f.model_value,
        }
        for f in filas
    ]
    return pd.DataFrame(
        registros,
        columns=[
            "date",
            "clinician_pseudonym",
            "subgroup",
            "phase",
            "override",
            "human_value",
            "model_value",
        ],
    )
