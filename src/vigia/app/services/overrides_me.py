"""Vista propia del profesional: `GET /overrides/me`.

Separado de `overrides.py` por tamaño (regla de estilo, §8.1): mismo
cálculo de tasas con `pandas`, sin `interaction_review`.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import HTTPException
from sqlmodel import Session

from vigia.app.services.overrides_data import usage_df

__all__ = ["overrides_me"]


def _ventana_servicio(tramo: pd.DataFrame) -> dict[str, Any]:
    """Media y p25-p75 de todos los profesionales presentes en `tramo` (sin el
    umbral de anonimato de `min_clinician`: aquí no se nombra a nadie más que a
    quien pregunta)."""
    n = len(tramo)
    con_clinico = tramo.dropna(subset=["clinician_pseudonym", "override"])
    if con_clinico.empty:
        return {"n": n, "override_rate": None, "p25": None, "p75": None}
    tasas = con_clinico.groupby("clinician_pseudonym")["override"].agg(["size", "mean"])
    valores = tasas["mean"]
    return {
        "n": n,
        "override_rate": float(valores.mean()),
        "p25": float(valores.quantile(0.25)),
        "p75": float(valores.quantile(0.75)),
    }


def overrides_me(
    session: Session,
    project_id: int,
    model_version_id: int,
    clinician: str,
    *,
    n_windows: int = 4,
) -> dict[str, Any]:
    """`GET /overrides/me`: curvas de `clinician` frente a la media y el p25-p75
    del servicio, en `n_windows` tramos iguales del rango de fechas del diario.
    """
    df = usage_df(session, project_id, model_version_id)
    pseudonimos = set(df["clinician_pseudonym"].dropna()) if not df.empty else set()
    if clinician not in pseudonimos:
        raise HTTPException(
            404,
            f"el pseudónimo {clinician} no está en el registro de uso de esta versión: "
            "elige uno de la lista",
        )

    df = df.dropna(subset=["date"]).copy()
    df = df[df["date"] != ""]
    df["fecha"] = pd.to_datetime(df["date"])
    inicio, fin = df["fecha"].min(), df["fecha"].max()
    total_dias = (fin - inicio).days
    ancho = total_dias / n_windows if n_windows else 0

    limites = [inicio + pd.Timedelta(days=ancho * i) for i in range(n_windows)] + [fin]

    windows: list[dict[str, Any]] = []
    for i in range(n_windows):
        ini, fin_tramo = limites[i], limites[i + 1]
        if i < n_windows - 1:
            mascara = (df["fecha"] >= ini) & (df["fecha"] < fin_tramo)
        else:
            mascara = (df["fecha"] >= ini) & (df["fecha"] <= fin_tramo)
        tramo = df[mascara]
        propio = tramo[tramo["clinician_pseudonym"] == clinician]
        n_propio = len(propio)
        con_override_propio = propio.dropna(subset=["override"])
        override_propio = (
            float(con_override_propio["override"].mean()) if not con_override_propio.empty else None
        )
        windows.append(
            {
                "start": ini.date().isoformat(),
                "end": fin_tramo.date().isoformat(),
                "mine": {"n": n_propio, "override_rate": override_propio},
                "service": _ventana_servicio(tramo),
            }
        )

    return {
        "clinician": clinician,
        "model_version_id": model_version_id,
        "n_windows": n_windows,
        "windows": windows,
    }
