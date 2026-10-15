"""Tests de `vigia.sim.human`: simulación de decisiones humanas y diario de uso."""
from __future__ import annotations

from datetime import date

import pandas as pd
from pandas.testing import assert_frame_equal

from vigia.core.schema import USAGE_LOG_COLUMNS
from vigia.sim.generators import generate_baseline, generate_e1_baseline, score_dataframe
from vigia.sim.human import (
    HumanParams,
    clinician_factors,
    simulate_decisions,
    summarize_usage,
    usage_to_csv,
)
from vigia.sim.serialize import feedback_dict

START = date(2026, 1, 5)


def _scored_labeled(seed: int, n: int | None = None, accuracy_target: float = 0.88) -> pd.DataFrame:
    """Frame puntuado (formato harness) con etiqueta `Has_Referral_in_Window`."""
    if n is None:
        df_scored = generate_e1_baseline(seed=seed)
    else:
        df_scored = score_dataframe(generate_baseline(n=n, seed=seed), seed=seed)
    df_scored = df_scored.reset_index(drop=True)
    fb = feedback_dict(df_scored, seed=seed + 6000, accuracy_target=accuracy_target)
    idx = fb["fields"].index("Has_Referral_in_Window")
    df_scored["Has_Referral_in_Window"] = [row[idx] for row in fb["values"]]
    return df_scored


def test_determinismo_misma_semilla_mismo_frame():
    df = _scored_labeled(seed=1, n=300)
    a = simulate_decisions(df, seed=42, start_date=START)
    b = simulate_decisions(df, seed=42, start_date=START)
    assert_frame_equal(a, b)


def test_columnas_exactas():
    df = _scored_labeled(seed=1, n=50)
    out = simulate_decisions(df, seed=1, start_date=START)
    assert list(out.columns) == list(USAGE_LOG_COLUMNS)


def test_tasa_override_cerca_del_valor_analitico():
    seed = 1
    df = _scored_labeled(seed=seed, n=2000, accuracy_target=0.88)
    params = HumanParams()
    out = simulate_decisions(df, seed=seed, params=params, start_date=START)

    factors = clinician_factors(seed, params)
    mean_k_clin = sum(factors.values()) / len(factors)
    error_rate = float((df["PREDICTION"].astype(int) != df["Has_Referral_in_Window"]).mean())

    analitico_override = params.override_base * mean_k_clin * (
        1 + (params.rescue_skill - 1) * error_rate
    )
    analitico_rescue = min(
        params.p_max, params.override_base * params.rescue_skill * mean_k_clin
    )

    resumen = summarize_usage(out)
    assert abs(resumen["override_rate"] - analitico_override) < 0.03
    assert abs(resumen["rescue_rate"] - analitico_rescue) < 0.06


def test_k_sub_baja_override_en_jovenes():
    df = _scored_labeled(seed=2)
    base = simulate_decisions(df, seed=5, params=HumanParams(), start_date=START)
    bajo = simulate_decisions(
        df, seed=5, params=HumanParams(k_sub={"18-35": 0.2}), start_date=START
    )

    resumen_base = summarize_usage(base)["by_subgroup"]
    resumen_bajo = summarize_usage(bajo)["by_subgroup"]
    assert "18-35" in resumen_base and "18-35" in resumen_bajo

    assert resumen_bajo["18-35"]["override_rate"] < resumen_base["18-35"]["override_rate"]
    if "36-75" in resumen_bajo:
        assert resumen_bajo["18-35"]["override_rate"] < resumen_bajo["36-75"]["override_rate"]


def test_automation_bias_baja_override_con_el_tiempo():
    df = _scored_labeled(seed=3, n=1500)
    out = simulate_decisions(
        df, seed=7, params=HumanParams(automation_bias=3.0), start_date=START
    )
    n = len(out)
    tercio = n // 3
    primero = out.iloc[:tercio]
    ultimo = out.iloc[-tercio:]

    override_primero = float((primero["human_decision"] != primero["model_output"]).mean())
    override_ultimo = float((ultimo["human_decision"] != ultimo["model_output"]).mean())
    assert override_ultimo < override_primero


def test_k_clin_override_sube_al_clinico():
    df = _scored_labeled(seed=4, n=2000)
    out = simulate_decisions(
        df, seed=9, params=HumanParams(k_clin_override={"clin-03": 4.0}), start_date=START
    )
    por_clinico = out.groupby("clinician_pseudonym").apply(
        lambda g: float((g["human_decision"] != g["model_output"]).mean())
    )
    assert por_clinico["clin-03"] > por_clinico.drop("clin-03").mean()


def test_csv_compatible_con_interaction_review(tmp_path):
    from vigia.human._vendor.interaction_review.telemetry import load_records

    df = _scored_labeled(seed=1, n=200)
    out = simulate_decisions(df, seed=1, start_date=START)
    path = usage_to_csv(out, tmp_path / "usage.csv")

    records = load_records(path)
    assert len(records) == len(out)
