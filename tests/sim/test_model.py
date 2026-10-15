from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from vigia.sim import model as m


def _row(diag: str | None, age: float = 55.0, prev: float = 1.0) -> pd.DataFrame:
    row = {"Age": age, "Previous_PC_episodes": prev}
    for d in m.DIAGNOSIS_CODES:
        row[f"PC_Diagnosis_{d}"] = 0
    if diag is not None:
        row[f"PC_Diagnosis_{diag}"] = 1
    return pd.DataFrame([row])


def test_l92_pesa_1_15_por_el_typo_medium_risk_any():
    w = m.compute_diag_weight(_row("L92"))
    assert w[0] == pytest.approx(1.15)


def test_l93_pesa_1_15_por_el_typo_medium_risk_any():
    w = m.compute_diag_weight(_row("L93"))
    assert w[0] == pytest.approx(1.15)


def test_l88_solo_high_pesa_0_75():
    w = m.compute_diag_weight(_row("L88"))
    assert w[0] == pytest.approx(0.75)


def test_l20_solo_medium_pesa_0_50_por_el_typo_medium_risk_any():
    # L20 es medium puro (no high): med_risk_any=1, pero low_risk_any usa
    # el vector-cero (never poblado por el typo) en vez de restar
    # medium_risk_any, así que también suma 0.10 de low. 0.40 + 0.10 = 0.50.
    w = m.compute_diag_weight(_row("L20"))
    assert w[0] == pytest.approx(0.50)


def test_sin_diagnostico_pesa_0_10_low():
    w = m.compute_diag_weight(_row(None))
    assert w[0] == pytest.approx(0.10)


def test_score_determinista_sin_ruido():
    df = _row("L20", age=65, prev=3)
    out1 = m.score(df, seed=0, prob_noise=0.0, accuracy_target=1.0)
    out2 = m.score(df, seed=0, prob_noise=0.0, accuracy_target=1.0)
    assert out1["PROBABILITIES"].iloc[0] == out2["PROBABILITIES"].iloc[0]


def test_prediction_coincide_con_p1_mayor_igual_0_5():
    df = _row("L88", age=70, prev=4)
    out = m.score(df, seed=0, prob_noise=0.0, accuracy_target=1.0)
    p1 = out["PROBABILITIES"].iloc[0][1]
    assert bool(out["PREDICTION"].iloc[0]) == (p1 >= 0.5)


def test_temperature_alta_acerca_p1_a_0_5():
    df = _row("L88", age=80, prev=5)
    out_normal = m.score(df, seed=0, prob_noise=0.0, accuracy_target=1.0, temperature=1.0)
    out_temp = m.score(df, seed=0, prob_noise=0.0, accuracy_target=1.0, temperature=2.0)
    p_normal = out_normal["PROBABILITIES"].iloc[0][1]
    p_temp = out_temp["PROBABILITIES"].iloc[0][1]
    assert abs(p_temp - 0.5) < abs(p_normal - 0.5)


def test_diag_weight_override_sustituye_al_peso():
    df = _row("L88", age=55, prev=1)
    out_default = m.score(df, seed=0, prob_noise=0.0, accuracy_target=1.0)
    out_override = m.score(
        df, seed=0, prob_noise=0.0, accuracy_target=1.0,
        diag_weight_override=np.array([0.0]),
    )
    assert out_default["PROBABILITIES"].iloc[0] != out_override["PROBABILITIES"].iloc[0]


def test_predict_proba_acepta_nombres_pc_diagnosis():
    df = _row("L88", age=55, prev=1)
    proba = m.predict_proba(df)
    assert proba.shape == (1, 2)
    assert proba[0].sum() == pytest.approx(1.0)


def test_predict_proba_acepta_nombres_planos():
    df = _row("L88", age=55, prev=1).rename(columns=m.DIAGNOSIS_MAPPING)
    proba = m.predict_proba(df)
    assert proba.shape == (1, 2)
    assert proba[0].sum() == pytest.approx(1.0)
