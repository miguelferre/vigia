from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from vigia.sim import generators
from vigia.sim import model as m


def _compare_against_feedback_enlatado(df: pd.DataFrame, feedback_path: Path) -> None:
    with open(feedback_path, encoding="utf-8") as f:
        fb = json.load(f)
    fields = fb["fields"]
    values = fb["values"]
    idx = {name: i for i, name in enumerate(fields)}

    df_out = df.rename(columns=m.DIAGNOSIS_MAPPING)
    non_id_cols = [
        c for c in df_out.columns if c not in ("Patient_Id", "Episode_Id", "PREDICTION", "PROBABILITIES")
    ]
    for col in non_id_cols:
        expected = [row[idx[col]] for row in values]
        actual = df_out[col].tolist()
        assert actual == expected, f"columna {col} no coincide"

    expected_pred = [row[idx["_original_prediction"]] for row in values]
    assert df_out["PREDICTION"].tolist() == expected_pred

    expected_proba = [row[idx["_original_probability"]] for row in values]
    assert df_out["PROBABILITIES"].tolist() == expected_proba


def test_generate_e1_baseline_reproduce_feedback_enlatado(e1_dir):
    df = generators.generate_e1_baseline()
    _compare_against_feedback_enlatado(df, e1_dir / "01_baseline_feedback.json")


def test_generate_e1_event_reproduce_feedback_enlatado(e1_dir):
    df, _is_young = generators.generate_e1_event()
    _compare_against_feedback_enlatado(df, e1_dir / "02_evento_feedback.json")


def test_bias_additive_cero_acerca_fnr_jovenes_a_mayores():
    df_bias, is_young = generators.generate_e1_event(bias_additive=1.1)
    df_sin, is_young2 = generators.generate_e1_event(bias_additive=0.0)
    is_young = np.array(is_young)
    is_young2 = np.array(is_young2)

    def fnr(df: pd.DataFrame, mask: np.ndarray) -> float:
        sub = df[mask]
        positivos_reales = sub["PREDICTION"].sum()  # proxy sin ground truth: usar tasa de PREDICTION=1
        return 1.0 - (positivos_reales / len(sub)) if len(sub) else float("nan")

    tasa_jovenes_bias = fnr(df_bias, is_young)
    tasa_mayores_bias = fnr(df_bias, ~is_young)
    tasa_jovenes_sin = fnr(df_sin, is_young2)
    tasa_mayores_sin = fnr(df_sin, ~is_young2)

    gap_bias = abs(tasa_jovenes_bias - tasa_mayores_bias)
    gap_sin = abs(tasa_jovenes_sin - tasa_mayores_sin)
    assert gap_sin < gap_bias


def test_ids_deterministas_con_la_misma_semilla():
    df1 = generators.generate_e1_baseline(seed=42, n_total=20)
    df2 = generators.generate_e1_baseline(seed=42, n_total=20)
    assert df1["Patient_Id"].tolist() == df2["Patient_Id"].tolist()
    assert df1["Episode_Id"].tolist() == df2["Episode_Id"].tolist()


def test_ids_distintos_con_otra_semilla():
    df1 = generators.generate_e1_baseline(seed=42, n_total=20)
    df3 = generators.generate_e1_baseline(seed=43, n_total=20)
    assert df1["Patient_Id"].tolist() != df3["Patient_Id"].tolist()


def test_id_rng_none_da_ids_con_formato_uuid():
    rng = np.random.default_rng(1)
    row = generators.build_episode_row(50, True, "L88", 1, rng, id_rng=None)
    assert re.fullmatch(r"PAT_[0-9a-f]{10}", row["Patient_Id"])
    assert re.fullmatch(r"EP_[0-9a-f]{12}", row["Episode_Id"])


# ---------------------------------------------------------------------------
# Parámetros del laboratorio: age_mean, age_std, temperature
# en generate_e1_baseline y generate_e1_event. Sin pasarlos, el lote generado
# es igual byte a byte al de antes.
# ---------------------------------------------------------------------------


def test_age_mean_std_temperature_explicitos_por_defecto_reproducen_e1_baseline(e1_dir):
    df = generators.generate_e1_baseline(age_mean=62.4, age_std=15.4, temperature=1.0)
    _compare_against_feedback_enlatado(df, e1_dir / "01_baseline_feedback.json")


def test_age_mean_std_temperature_explicitos_por_defecto_reproducen_e1_event(e1_dir):
    df, _is_young = generators.generate_e1_event(age_mean=62.4, age_std=15.4, temperature=1.0)
    _compare_against_feedback_enlatado(df, e1_dir / "02_evento_feedback.json")


def test_age_mean_distinto_cambia_las_edades_e1_baseline():
    df_default = generators.generate_e1_baseline(seed=11, n_total=60)
    df_mayor = generators.generate_e1_baseline(seed=11, n_total=60, age_mean=80.0)
    assert df_default["Age"].tolist() != df_mayor["Age"].tolist()


def test_age_mean_distinto_cambia_las_edades_e1_event():
    df_default, _ = generators.generate_e1_event(seed=11, n_total=60)
    df_mayor, _ = generators.generate_e1_event(seed=11, n_total=60, age_mean=80.0)
    assert df_default["Age"].tolist() != df_mayor["Age"].tolist()


def test_age_std_distinto_cambia_las_edades_e1_baseline():
    df_default = generators.generate_e1_baseline(seed=11, n_total=60)
    df_std = generators.generate_e1_baseline(seed=11, n_total=60, age_std=1.0)
    assert df_default["Age"].tolist() != df_std["Age"].tolist()


def test_generate_age_split_batch_age_mean_cambia_la_cohorte_no_joven():
    df_default = generators.generate_age_split_batch(n_total=60, frac_young=0.15, seed=5)
    df_mayor = generators.generate_age_split_batch(
        n_total=60, frac_young=0.15, seed=5, age_mean=85.0
    )
    assert df_default["Age"].tolist() != df_mayor["Age"].tolist()


def test_temperature_distinta_cambia_las_probabilidades_e1_baseline():
    df_default = generators.generate_e1_baseline(seed=11, n_total=60)
    df_temp = generators.generate_e1_baseline(seed=11, n_total=60, temperature=2.0)
    assert list(df_default["PROBABILITIES"]) != list(df_temp["PROBABILITIES"])


def test_temperature_distinta_cambia_las_probabilidades_e1_event():
    df_default, _ = generators.generate_e1_event(seed=11, n_total=60)
    df_temp, _ = generators.generate_e1_event(seed=11, n_total=60, temperature=2.0)
    assert list(df_default["PROBABILITIES"]) != list(df_temp["PROBABILITIES"])
