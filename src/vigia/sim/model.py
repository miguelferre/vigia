"""model — Modelo logístico de derivación AP -> Reumatología.

Puerto íntegro de `escenarios/shared/model.py` del harness de demo
(el harness de la demo original, solo lectura). Replica EXACTAMENTE el
scoring_fn embebido en el notebook que generó configuration_archive.tar.gz
y el endpoint desplegado en la plataforma de datos.

Particularidades replicadas (no son bugs a corregir):

  1. `medium_risk_any` se inicializa a ceros y el código asigna al typo
     `med_risk_any`. El cálculo de `low_risk_any = 1 - high - medium_risk_any`
     usa el vector-cero (nunca el poblado), y el peso final usa
     `med_risk_any`. Efecto: un diagnóstico que está en ambas listas
     (L92, L93) recibe peso HIGH + MEDIUM = 0.75 + 0.40 = 1.15, porque
     `low_risk_any` no lo resta al no ver `medium_risk_any` poblado.
  2. Listas de riesgo del notebook:
       HIGH = ["L88", "L90", "L99", "L93", "L92"]
       MEDIUM = ["L15","L17","L20","L83","L84","L86","L87","L92","L93","L94","L95"]
  3. accuracy_target=0.96 aplica flips aleatorios sobre PREDICTION (4%).
  4. Coeficientes: intercept=-0.95, AGE60=+0.5, PREV3=+0.55, prob_noise=0.03.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HIGH_RISK_DIAGS: list[str] = ["L88", "L90", "L99", "L93", "L92"]

MEDIUM_RISK_DIAGS: list[str] = [
    "L15", "L17", "L20",
    "L83", "L84", "L86", "L87",
    "L92", "L93", "L94", "L95",
]

MODEL_INTERCEPT: float = -0.95
MODEL_COEF_AGE: float = 0.012
MODEL_COEF_PREV: float = 0.20
MODEL_COEF_AGE60: float = 0.5
MODEL_COEF_PREV3: float = 0.55

MODEL_WEIGHT_HIGH: float = 0.75
MODEL_WEIGHT_MEDIUM: float = 0.40
MODEL_WEIGHT_LOW: float = 0.10

DEFAULT_PROB_NOISE: float = 0.03
DEFAULT_ACCURACY_TARGET: float = 0.96


# ---------------------------------------------------------------------------
# Mapa CIAP-2 y columnas de features (única fuente: generators.py lo importa
# de aquí para no duplicar el diccionario).
# ---------------------------------------------------------------------------

DIAGNOSIS_MAPPING: dict[str, str] = {
    "PC_Diagnosis_L01": "Neck_signs_symptoms",
    "PC_Diagnosis_L02": "Dorsal_signs_symptoms",
    "PC_Diagnosis_L03": "Lumbar_signs_symptoms",
    "PC_Diagnosis_L04": "Thoracic_signs_symptoms",
    "PC_Diagnosis_L05": "Flanks_armpits_signs_symptoms",
    "PC_Diagnosis_L07": "Jaw_signs_symptoms",
    "PC_Diagnosis_L08": "Shoulder_signs_symptoms",
    "PC_Diagnosis_L09": "Arm_signs_symptoms",
    "PC_Diagnosis_L10": "Elbow_signs_symptoms",
    "PC_Diagnosis_L11": "Wrist_signs_symptoms",
    "PC_Diagnosis_L12": "Hand_fingers_signs_symptoms",
    "PC_Diagnosis_L13": "Hip_signs_symptoms",
    "PC_Diagnosis_L14": "Thigh_leg_signs_symptoms",
    "PC_Diagnosis_L15": "Knee_signs_symptoms",
    "PC_Diagnosis_L16": "Ankle_signs_symptoms",
    "PC_Diagnosis_L17": "Foot_toes_signs_symptoms",
    "PC_Diagnosis_L18": "Muscle_pain",
    "PC_Diagnosis_L18.01": "Fibromyalgia",
    "PC_Diagnosis_L19": "Other_unspecified_muscular_signs_symptoms",
    "PC_Diagnosis_L20": "Unspecified_joint_signs_symptoms",
    "PC_Diagnosis_L28": "Locomotor_system_disability",
    "PC_Diagnosis_L29": "Other_locomotor_system_signs_symptoms",
    "PC_Diagnosis_L83": "Neck_syndromes",
    "PC_Diagnosis_L84": "Lumbar_thoracic_syndromes_without_irradiation",
    "PC_Diagnosis_L85": "Acquired_spinal_deformities",
    "PC_Diagnosis_L86": "Lumbar_thoracic_syndromes_with_irradiation",
    "PC_Diagnosis_L87": "Bursitis_tendinitis_synovitis_unspecified",
    "PC_Diagnosis_L88": "Rheumatoid_arthritis",
    "PC_Diagnosis_L88.01": "Ankylosing_spondylitis",
    "PC_Diagnosis_L89": "Hip_osteoarthritis",
    "PC_Diagnosis_L90": "Knee_arthrosis",
    "PC_Diagnosis_L91": "Other_arthrosis",
    "PC_Diagnosis_L92": "Shoulder_syndromes",
    "PC_Diagnosis_L93": "Tennis_elbow",
    "PC_Diagnosis_L94": "Osteochondrosis",
    "PC_Diagnosis_L95": "Osteoporosis",
    "PC_Diagnosis_L98": "Acquired_limb_deformities",
    "PC_Diagnosis_L99": "Other_locomotor_diseases",
    "PC_Diagnosis_T92": "Gout",
}

DIAGNOSIS_CODES: list[str] = [k.replace("PC_Diagnosis_", "") for k in DIAGNOSIS_MAPPING]

_DIAGNOSIS_MAPPING_INVERSE: dict[str, str] = {v: k for k, v in DIAGNOSIS_MAPPING.items()}

FEATURE_COLS_RAW: list[str] = ["Age", "Previous_PC_episodes"] + [
    f"PC_Diagnosis_{d}" for d in DIAGNOSIS_CODES
]
FEATURE_COLS_PLAIN: list[str] = ["Age", "Previous_PC_episodes"] + [
    DIAGNOSIS_MAPPING[f"PC_Diagnosis_{d}"] for d in DIAGNOSIS_CODES
]


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -500.0, 500.0)))


def compute_diag_weight(
    df: pd.DataFrame,
    high_risk_diags: list[str] = HIGH_RISK_DIAGS,
    medium_risk_diags: list[str] = MEDIUM_RISK_DIAGS,
) -> np.ndarray:
    n = len(df)
    high_cols = [f"PC_Diagnosis_{d}" for d in high_risk_diags if f"PC_Diagnosis_{d}" in df.columns]
    medium_cols = [
        f"PC_Diagnosis_{d}" for d in medium_risk_diags if f"PC_Diagnosis_{d}" in df.columns
    ]

    high_risk_any = np.zeros(n, dtype=float)
    if high_cols:
        high_risk_any = (df[high_cols].astype(int).sum(axis=1).to_numpy() > 0).astype(float)

    # Typo original del notebook: medium_risk_any queda a cero, el cómputo
    # real de "hay diagnóstico medio" va a med_risk_any. low_risk_any usa
    # el vector-cero, así que un diagnóstico HIGH+MEDIUM no se resta nunca
    # de low_risk_any (ver docstring del módulo, punto 1).
    medium_risk_any = np.zeros(n, dtype=float)
    med_risk_any = np.zeros(n, dtype=float)
    if medium_cols:
        med_risk_any = (df[medium_cols].astype(int).sum(axis=1).to_numpy() > 0).astype(float)

    low_risk_any = 1.0 - high_risk_any - medium_risk_any

    return (
        MODEL_WEIGHT_HIGH * high_risk_any
        + MODEL_WEIGHT_MEDIUM * med_risk_any
        + MODEL_WEIGHT_LOW * low_risk_any
    )


def compute_diag_weight_scalar(chosen_diag: str) -> float:
    h = 1.0 if chosen_diag in HIGH_RISK_DIAGS else 0.0
    m = 1.0 if chosen_diag in MEDIUM_RISK_DIAGS else 0.0
    low = 1.0 - h
    return MODEL_WEIGHT_HIGH * h + MODEL_WEIGHT_MEDIUM * m + MODEL_WEIGHT_LOW * low


def score(
    df: pd.DataFrame,
    seed: int | None = None,
    prob_noise: float = DEFAULT_PROB_NOISE,
    temperature: float = 1.0,
    clip_eps: float = 1e-6,
    accuracy_target: float = DEFAULT_ACCURACY_TARGET,
    diag_weight_override: np.ndarray | None = None,
) -> pd.DataFrame:
    out = df.copy()
    rng = np.random.default_rng(seed)
    n = len(out)

    age = out["Age"].astype(float).to_numpy()
    prev = out["Previous_PC_episodes"].astype(float).to_numpy()

    age_over_60 = (age > 60).astype(float)
    prev_ge_3 = (prev >= 3).astype(float)

    if diag_weight_override is not None:
        diag_w = np.asarray(diag_weight_override, dtype=float)
    else:
        diag_w = compute_diag_weight(out)

    z = (
        MODEL_INTERCEPT
        + MODEL_COEF_AGE * (age - 50.0)
        + MODEL_COEF_PREV * prev
        + MODEL_COEF_AGE60 * age_over_60
        + MODEL_COEF_PREV3 * prev_ge_3
        + diag_w
    )

    z_scaled = z / float(temperature)
    p1 = sigmoid(z_scaled)
    p1 = p1 + rng.normal(0.0, float(prob_noise), size=n)
    p1 = np.clip(p1, clip_eps, 1.0 - clip_eps)

    y_base = (p1 >= 0.5).astype(int)
    flip = rng.random(n) < (1.0 - float(accuracy_target))
    y_pred = y_base.copy()
    y_pred[flip] = 1 - y_pred[flip]

    out["PROBABILITIES"] = [[round(1.0 - float(p), 6), round(float(p), 6)] for p in p1]
    out["PREDICTION"] = y_pred.astype(int)

    return out


def predict_proba(df_features: pd.DataFrame) -> np.ndarray:
    """Scoring determinista para inferencia (sin ruido, sin flips).

    Acepta columnas `PC_Diagnosis_*` (nombres crudos) o los nombres planos
    de `DIAGNOSIS_MAPPING` (los renombra internamente con el mapa inverso).
    Devuelve un array (n, 2) con columnas [1 - p1, p1].
    """
    df = df_features.copy()
    plain_present = [c for c in df.columns if c in _DIAGNOSIS_MAPPING_INVERSE]
    if plain_present:
        df = df.rename(columns=_DIAGNOSIS_MAPPING_INVERSE)

    scored = score(df, seed=0, prob_noise=0.0, accuracy_target=1.0)
    p1 = np.array([row[1] for row in scored["PROBABILITIES"]], dtype=float)
    return np.column_stack([1.0 - p1, p1])
