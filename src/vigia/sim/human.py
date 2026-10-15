"""human — Simulador de la capa humana: decisiones de override sobre la
predicción del modelo, y su volcado a diario de uso (`usage_logs`).

Fórmula de la probabilidad de override:

    p_override = min(
        p_max,
        override_base * k_clin * k_sub * exp(-automation_bias * t) * rescue,
    )

donde `rescue = rescue_skill` si el modelo se equivoca en la fila (respecto
a la etiqueta) y `1.0` en caso contrario; `t` es la posición normalizada
0..1 de la fila dentro del guion temporal (`t_start`..`t_end`); `k_clin` es
un multiplicador por clínico (lognormal recortado, fijo por pseudónimo y
semilla); `k_sub` es un multiplicador por subgrupo demográfico (edad).

Si hay override, `human_decision` es la predicción invertida; si no, la
predicción del modelo tal cual.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from vigia.core.schema import USAGE_LOG_COLUMNS

DECISION_LABELS: dict[int, str] = {1: "refer", 0: "no-refer"}


class HumanParams(BaseModel):
    """Parámetros de la simulación de decisiones humanas."""

    override_base: float = 0.05
    k_clin_sigma: float = 0.25
    k_clin_min: float = 0.5
    k_clin_max: float = 2.0
    k_clin_override: dict[str, float] = Field(default_factory=dict)
    k_sub: dict[str, float] = Field(default_factory=dict)
    automation_bias: float = 0.0
    rescue_skill: float = 8.0
    p_max: float = 0.95
    n_clinicians: int = 8


def subgroup_by_age(age: float) -> str:
    """Subgrupo demográfico por edad: 18-35 no privilegiado, 36-75
    privilegiado, el resto ("otros") fuera de ambos grupos protegidos.

    Una edad no numérica (`NaN`) cae en "otros" en vez de romper con
    `ValueError`: no se da en los datos de demo actuales, pero la
    ingesta real (fuera) no garantiza `Age` completo.
    """
    if pd.isna(age):
        return "otros"
    a = int(age)
    if 18 <= a <= 35:
        return "18-35"
    if 36 <= a <= 75:
        return "36-75"
    return "otros"


def clinician_factors(seed: int, params: HumanParams) -> dict[str, float]:
    """`k_clin` por pseudónimo `clin-01`..`clin-NN`, lognormal recortado a
    `[k_clin_min, k_clin_max]`, con `k_clin_override` aplicado por encima.
    """
    rng = np.random.default_rng([seed, 0xC11])
    factors: dict[str, float] = {}
    for i in range(1, params.n_clinicians + 1):
        pseudonym = f"clin-{i:02d}"
        raw = rng.lognormal(mean=0.0, sigma=params.k_clin_sigma)
        clipped = float(np.clip(raw, params.k_clin_min, params.k_clin_max))
        factors[pseudonym] = clipped
    for pseudonym, value in params.k_clin_override.items():
        factors[pseudonym] = value
    return factors


def _resolve_col(df: pd.DataFrame, requested: str, fallback: str) -> str:
    """Devuelve `requested` si existe en `df`; si no, `fallback`.

    Si ninguna de las dos existe, levanta `ValueError` con un mensaje claro
    en vez de dejar que falle más adelante con un `KeyError` genérico de
    pandas al indexar `df[col]`.
    """
    if requested in df.columns:
        return requested
    if fallback in df.columns:
        return fallback
    raise ValueError(
        f"simulate_decisions: ni la columna '{requested}' (formato harness) "
        f"ni '{fallback}' (formato canónico) están en el DataFrame. "
        f"Columnas disponibles: {list(df.columns)}"
    )


def simulate_decisions(
    df: pd.DataFrame,
    *,
    seed: int,
    params: HumanParams | None = None,
    t_start: float = 0.0,
    t_end: float = 1.0,
    start_date: date,
    days: int = 7,
    model_version: str = "v1",
    record_seq_start: int = 0,
    pred_col: str = "PREDICTION",
    label_col: str = "Has_Referral_in_Window",
    age_col: str = "Age",
    subgroup_col: str | None = None,
) -> pd.DataFrame:
    """Simula la decisión humana fila a fila sobre un frame puntuado.

    Acepta el frame del harness (`PREDICTION`, `Has_Referral_in_Window`,
    `Age`) o el canónico (`prediction`, `label`, `protected_value`):
    detecta por nombre de columna. Devuelve un DataFrame con exactamente
    `USAGE_LOG_COLUMNS` de `vigia.core.schema`.
    """
    params = params or HumanParams()
    pred_col = _resolve_col(df, pred_col, "prediction")
    label_col = _resolve_col(df, label_col, "label")
    age_col = _resolve_col(df, age_col, "protected_value")

    n = len(df)
    preds = df[pred_col].astype(int).to_numpy()
    labels = df[label_col].astype(int).to_numpy()
    if subgroup_col is not None and subgroup_col in df.columns:
        subgroups = df[subgroup_col].astype(str).tolist()
    else:
        ages = df[age_col].to_numpy()
        subgroups = [subgroup_by_age(a) for a in ages]

    clin_factors = clinician_factors(seed, params)
    pseudonyms = [f"clin-{i:02d}" for i in range(1, params.n_clinicians + 1)]

    rng = np.random.default_rng(seed)

    rows: list[dict] = []
    for i in range(n):
        t = t_start + (t_end - t_start) * i / max(n - 1, 1)
        clin_idx = int(rng.integers(params.n_clinicians))
        pseudonym = pseudonyms[clin_idx]
        subgroup = subgroups[i]
        pred = int(preds[i])
        label = int(labels[i])
        model_wrong = pred != label

        k_clin = clin_factors[pseudonym]
        k_sub = params.k_sub.get(subgroup, 1.0)
        rescue = params.rescue_skill if model_wrong else 1.0
        p = min(
            params.p_max,
            params.override_base
            * k_clin
            * k_sub
            * float(np.exp(-params.automation_bias * t))
            * rescue,
        )
        override = bool(rng.random() < p)
        decision = (1 - pred) if override else pred

        day_offset = 0 if days <= 1 or n <= 1 else min(days - 1, int(i * days / n))
        row_date = start_date + timedelta(days=day_offset)

        rows.append(
            {
                "date": row_date.isoformat(),
                "clinician_pseudonym": pseudonym,
                "subgroup": subgroup,
                "human_decision": DECISION_LABELS[decision],
                "model_output": DECISION_LABELS[pred],
                "ground_truth": DECISION_LABELS[label],
                "record_seq": record_seq_start + i,
                "model_version": model_version,
            }
        )

    return pd.DataFrame(rows, columns=list(USAGE_LOG_COLUMNS))


def _rate(flags: pd.Series) -> float:
    return float(flags.mean()) if len(flags) else float("nan")


def _usage_summary_block(df_usage: pd.DataFrame) -> dict:
    n = len(df_usage)
    if n == 0:
        return {
            "n": 0,
            "override_rate": None,
            "human_accuracy": None,
            "model_accuracy": None,
            "rescue_rate": None,
        }
    override = df_usage["human_decision"] != df_usage["model_output"]
    human_ok = df_usage["human_decision"] == df_usage["ground_truth"]
    model_ok = df_usage["model_output"] == df_usage["ground_truth"]
    model_wrong = df_usage[~model_ok]
    rescue_rate = (
        float((model_wrong["human_decision"] == model_wrong["ground_truth"]).mean())
        if len(model_wrong)
        else None
    )
    return {
        "n": n,
        "override_rate": _rate(override),
        "human_accuracy": _rate(human_ok),
        "model_accuracy": _rate(model_ok),
        "rescue_rate": rescue_rate,
    }


def summarize_usage(df_usage: pd.DataFrame) -> dict:
    """Resumen del diario de uso: tasas globales y por subgrupo."""
    summary = _usage_summary_block(df_usage)
    by_subgroup: dict[str, dict] = {}
    for subgroup, group_df in df_usage.groupby("subgroup"):
        by_subgroup[str(subgroup)] = _usage_summary_block(group_df)
    summary["by_subgroup"] = by_subgroup
    return summary


def usage_to_csv(df_usage: pd.DataFrame, path: str | Path) -> Path:
    """Vuelca `df_usage` a CSV UTF-8 con la cabecera de `USAGE_LOG_COLUMNS`,
    compatible con `interaction_review.telemetry.load_records`.
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_usage.to_csv(out_path, columns=list(USAGE_LOG_COLUMNS), index=False, encoding="utf-8")
    return out_path
