"""Agregación de overrides: vista de gestor.

Cálculo de tasas propio con `pandas` sobre `UsageLog`, sin pasar por
`Record` ni por `interaction_review`. "Override" es
`human_decision != model_output` (mismo criterio que `cross_alerts._counts`,
`cross_alerts.py:141`). La vista propia (`/overrides/me`) vive en
`overrides_me.py`, aparte por tamaño.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import HTTPException
from sqlmodel import Session, select

from vigia.app.models import UsageLog
from vigia.app.services.overrides_data import usage_df as _usage_df
from vigia.human.cross_alerts import CrossConfig
from vigia.human.ir_adapter import MIN_N

__all__ = [
    "GRUPOS_POR",
    "overrides_by_group",
    "overrides_clinicians",
]

GRUPOS_POR = ("subgroup", "phase", "clinician")

_MIN_CLINICIAN = CrossConfig().min_clinician
_BIN_EDGES = [round(i * 0.1, 1) for i in range(11)]


def _cuartiles_por_clinico(sub: pd.DataFrame) -> tuple[float | None, float | None, float | None]:
    """Cuartiles del `override_rate` entre profesionales cualificados de `sub`
    (`n >= CrossConfig.min_clinician` dentro del grupo). Con menos de dos
    cualificados, los tres campos son `None`.
    """
    con_clinico = sub.dropna(subset=["clinician_pseudonym", "override"])
    if con_clinico.empty:
        return None, None, None
    tasas = con_clinico.groupby("clinician_pseudonym")["override"].agg(["size", "mean"])
    cualificados = tasas[tasas["size"] >= _MIN_CLINICIAN]
    if len(cualificados) < 2:
        return None, None, None
    valores = cualificados["mean"]
    return (
        float(valores.quantile(0.25)),
        float(valores.quantile(0.5)),
        float(valores.quantile(0.75)),
    )


def _bin_counts(valores: pd.Series) -> list[int]:
    counts = [0] * (len(_BIN_EDGES) - 1)
    for v in valores:
        idx = min(max(int(v * 10), 0), len(counts) - 1)
        counts[idx] += 1
    return counts


def _diferencia_media(sub: pd.DataFrame, min_n: int) -> float | None:
    """Media de `|cifra del profesional - cifra del modelo|` en la unidad del proyecto,
    sobre las filas del grupo con las dos cifras. Con menos de `min_n` filas así, `None`."""
    con_cifras = sub.dropna(subset=["human_value", "model_value"])
    if len(con_cifras) < min_n:
        return None
    return float((con_cifras["human_value"] - con_cifras["model_value"]).abs().mean())


def _by_group(
    df: pd.DataFrame,
    by: str,
    model_version_id: int,
    n_total: int,
    min_n: int = MIN_N,
    *,
    unidad: str | None = None,
    con_diferencia: bool = False,
) -> dict[str, Any]:
    """Agregado por subgrupo o fase. una celda con menos de `min_n`
    decisiones da la tasa como `None` y conserva su `n`; `min_n` es
    `ir_adapter.MIN_N` por defecto. en regresión, `diferencia_media` por grupo
    (informativa, sin umbral ni alerta) y `unidad`; en clasificación, los dos son `None`."""
    columna = "subgroup" if by == "subgroup" else "phase"
    groups: list[dict[str, Any]] = []
    if not df.empty:
        for nombre, sub in df.groupby(columna):
            n = len(sub)
            con_override = sub.dropna(subset=["override"])
            # La celda se mide por las decisiones con override calculable
            # (revisión D): una celda grande con muchas filas en blanco no
            # da tasa; los cuartiles por profesional siguen la misma regla.
            suficiente = len(con_override) >= min_n
            tasa = float(con_override["override"].mean()) if suficiente else None
            p25, p50, p75 = _cuartiles_por_clinico(sub) if suficiente else (None, None, None)
            groups.append(
                {
                    "group": nombre,
                    "n": n,
                    "tasa": tasa,
                    "p25": p25,
                    "median": p50,
                    "p75": p75,
                    "diferencia_media": _diferencia_media(sub, min_n) if con_diferencia else None,
                }
            )
        groups.sort(key=lambda g: g["group"])
    return {
        "by": by,
        "model_version_id": model_version_id,
        "n_total": n_total,
        "min_n": min_n,
        "groups": groups,
        "unidad": unidad if con_diferencia else None,
    }


def _by_clinician(df: pd.DataFrame, model_version_id: int, n_total: int) -> dict[str, Any]:
    base = {"by": "clinician", "model_version_id": model_version_id, "n_total": n_total}
    con_clinico = df.dropna(subset=["clinician_pseudonym", "override"])
    if con_clinico.empty:
        return {
            **base,
            "n_clinicians": 0,
            "n_qualified": 0,
            "distribution": None,
            "motivo": "sin filas de diario para esta versión",
        }
    tasas = con_clinico.groupby("clinician_pseudonym")["override"].agg(["size", "mean"])
    n_clinicians = len(tasas)
    cualificados = tasas[tasas["size"] >= _MIN_CLINICIAN]
    n_qualified = len(cualificados)
    if n_qualified < 2:
        return {
            **base,
            "n_clinicians": n_clinicians,
            "n_qualified": n_qualified,
            "distribution": None,
            "motivo": (
                f"{n_qualified} profesionales con al menos {_MIN_CLINICIAN} decisiones "
                "registradas; hacen falta al menos 2 para comparar"
            ),
        }
    valores = cualificados["mean"]
    distribution = {
        "p25": float(valores.quantile(0.25)),
        "median": float(valores.quantile(0.5)),
        "p75": float(valores.quantile(0.75)),
        "bin_edges": _BIN_EDGES,
        "bin_counts": _bin_counts(valores),
    }
    return {
        **base,
        "n_clinicians": n_clinicians,
        "n_qualified": n_qualified,
        "distribution": distribution,
    }


def overrides_by_group(
    session: Session,
    project_id: int,
    model_version_id: int,
    by: str,
    *,
    min_n: int = MIN_N,
    unidad: str | None = None,
    con_diferencia: bool = False,
) -> dict[str, Any]:
    """`GET /overrides?by=subgroup|phase|clinician`. `by` fuera del catálogo, 422.
    `con_diferencia` (regresión) añade `diferencia_media` y `unidad` a las filas."""
    if by not in GRUPOS_POR:
        raise HTTPException(422, f"'by' debe ser uno de {GRUPOS_POR}; se recibió {by!r}")
    df = _usage_df(session, project_id, model_version_id)
    n_total = len(df)
    if by == "clinician":
        return _by_clinician(df, model_version_id, n_total)
    return _by_group(df, by, model_version_id, n_total, min_n, unidad=unidad, con_diferencia=con_diferencia)


def overrides_clinicians(session: Session, project_id: int, model_version_id: int) -> list[str]:
    """`GET /overrides/clinicians`: pseudónimos distintos con `n >= 1`, orden alfabético."""
    filas = session.exec(
        select(UsageLog.clinician_pseudonym).where(
            UsageLog.project_id == project_id,
            UsageLog.model_version_id == model_version_id,
        )
    ).all()
    return sorted({p for p in filas if p})
