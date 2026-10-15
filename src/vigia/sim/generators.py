"""generators — Generación de batches sintéticos de episodios de AP.

Puerto de `escenarios/shared/generators.py` del harness de demo
(el harness de la demo original, solo lectura), sin config ni variables de
entorno: ninguna función de este módulo escribe a disco (eso vive en
`serialize.py`).

Cubre:
  - Muestreo demográfico y de diagnósticos CIAP-2 con multiplicadores
    epidemiológicos (mismos que el flujo del servicio regional del harness).
  - Scoring del modelo logístico (`score_dataframe`, delega en `model.score`).
  - Generadores puros de los batches de escenario 1 y 2 (baseline, evento,
    recovery), réplica exacta del orden de llamadas al rng de los scripts
    `0N_*.py` del harness.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from vigia.core.schema import DatosNoValidos

from . import model as m
from .model import DIAGNOSIS_CODES, DIAGNOSIS_MAPPING

__all__ = [
    "BASE_DIAG_PROBS",
    "DIAGNOSIS_CODES",
    "DIAGNOSIS_MAPPING",
    "build_episode_row",
    "feedback_path_for",
    "generate_age_split_batch",
    "generate_baseline",
    "generate_e1_baseline",
    "generate_e1_event",
    "generate_e1_recovery",
    "generate_e2_event",
    "generate_e2_recovery",
    "random_date",
    "sample_age",
    "sample_age_min36",
    "sample_diagnosis",
    "sample_prev_episodes",
    "score_dataframe",
]

_EPS = 0.002
BASE_DIAG_PROBS: dict[str, float] = {
    "L01": 0.07, "L02": 0.03, "L03": 0.09, "L04": 0.03, "L05": _EPS,
    "L07": _EPS, "L08": 0.05, "L09": 0.01, "L10": 0.01, "L11": 0.01,
    "L12": 0.03, "L13": 0.03, "L14": 0.02, "L15": 0.08, "L16": 0.01,
    "L17": 0.06, "L18": 0.03, "L18.01": 0.01, "L19": _EPS,
    "L20": 0.04, "L28": _EPS, "L29": 0.01, "L83": 0.01, "L84": 0.01,
    "L85": _EPS, "L86": 0.05, "L87": 0.09, "L88": 0.02, "L88.01": _EPS,
    "L89": _EPS, "L90": 0.01, "L91": 0.03, "L92": 0.05, "L93": 0.02,
    "L94": _EPS, "L95": 0.02, "L98": 0.01, "L99": 0.03, "T92": 0.01,
}

_CHRONIC_DIAGS: set[str] = {"L88", "L88.01", "L95", "L90", "L91", "L18.01"}


def sample_diagnosis(
    age: int,
    sex_f: bool,
    rng: np.random.Generator,
    diag_probs: dict[str, float] | None = None,
) -> str:
    base = diag_probs if diag_probs is not None else BASE_DIAG_PROBS
    mx: dict[str, float] = {d: 1.0 for d in DIAGNOSIS_CODES}

    if not sex_f and age > 40:
        mx["T92"] = 3.5
    elif sex_f and age < 50:
        mx["T92"] = 0.25

    if sex_f and 40 <= age <= 65:
        mx["L88"] = 2.5
    elif not sex_f:
        mx["L88"] = 0.5

    if sex_f and age > 60:
        mx["L95"] = 3.0
    elif sex_f and 50 <= age <= 60:
        mx["L95"] = 1.5
    elif not sex_f and age < 70:
        mx["L95"] = 0.2

    if sex_f and 30 <= age <= 60:
        mx["L18.01"] = 3.5
    elif not sex_f:
        mx["L18.01"] = 0.3

    age_f = max(0.4, min(3.0, 1.0 + (age - 55) * 0.05)) if age > 55 else 0.4
    mx["L90"] = age_f
    mx["L91"] = age_f

    if 30 <= age <= 55:
        mx["L03"] = 1.5
        mx["L86"] = 1.5
    elif age > 70:
        mx["L03"] = 0.7
        mx["L86"] = 0.7

    adjusted = np.array([base[d] * mx[d] for d in DIAGNOSIS_CODES])
    adjusted /= adjusted.sum()
    return str(rng.choice(DIAGNOSIS_CODES, p=adjusted))


def sample_prev_episodes(chosen_diag: str, rng: np.random.Generator) -> int:
    lam = 1.8 if chosen_diag in _CHRONIC_DIAGS else 0.4
    return int(np.clip(rng.poisson(lam), 0, 9))


def sample_age(
    rng: np.random.Generator,
    mean: float = 62.4,
    std: float = 15.4,
    min_age: int = 20,
    max_age: int = 102,
) -> int:
    return int(np.clip(rng.normal(mean, std), min_age, max_age))


# Tope de intentos del muestreo de edades con corte. Con los valores de
# siempre (62,4 y 15,4) se rechaza un 4 % de las edades; 10 000 intentos seguidos
# solo se agotan si la combinación nunca llega a 36 años.
MAX_INTENTOS_EDAD = 10_000


def sample_age_min36(rng: np.random.Generator, mean: float, std: float) -> int:
    """Edad de la cohorte de 36 años o más, con el mismo consumo de `rng` que el bucle
    de rechazo de siempre (`sample_age` hasta que no baje de 36), pero con tope."""
    age = sample_age(rng, mean=mean, std=std)
    intentos = 0
    while age < 36:
        intentos += 1
        if intentos > MAX_INTENTOS_EDAD:
            raise DatosNoValidos(
                f"con age_mean={mean:g} y age_std={std:g} no se consigue generar edades de 36 "
                "años o más: sube age_mean o age_std"
            )
        age = sample_age(rng, mean=mean, std=std)
    return age


def random_date(
    rng: np.random.Generator,
    start_year: int = 2025,
    end_year: int = 2026,
) -> datetime:
    # Naive a propósito (réplica exacta del harness): solo se usa la fecha
    # (strftime "%Y-%m-%d"), la zona horaria es irrelevante para el resultado.
    start = datetime(start_year, 1, 1)  # noqa: DTZ001
    end = datetime(end_year, 12, 31)  # noqa: DTZ001
    return start + timedelta(days=int(rng.integers(0, (end - start).days + 1)))


def build_episode_row(
    age: int,
    sex_f: bool,
    chosen_diag: str,
    prev_episodes: int,
    rng: np.random.Generator,
    id_rng: np.random.Generator | None = None,
) -> dict:
    """Construye una fila de episodio.

    `rng` es el generador principal del batch: NO debe consumir nada
    distinto de lo que consume en el harness (solo `random_date`), o se
    rompe la regeneración byte a byte. Los ids se sacan de `id_rng` si se
    pasa (determinista, `PAT_`+10 hex / `EP_`+12 hex vía `bytes().hex()`);
    si es None, se usa `uuid.uuid4()` como el harness (no reproducible).
    """
    episode_start = random_date(rng)
    episode_window_start = episode_start - timedelta(days=365)
    if id_rng is not None:
        patient_id = f"PAT_{id_rng.bytes(5).hex()}"
        episode_id = f"EP_{id_rng.bytes(6).hex()}"
    else:
        import uuid

        patient_id = f"PAT_{uuid.uuid4().hex[:10]}"
        episode_id = f"EP_{uuid.uuid4().hex[:12]}"
    row: dict = {
        "Patient_Id": patient_id,
        "Episode_Id": episode_id,
        "Episode_Start_Date": episode_start.strftime("%Y-%m-%d"),
        "Episode_Window_Start": episode_window_start.strftime("%Y-%m-%d"),
        "Age": age,
        "Sex": "F" if sex_f else "M",
        "Previous_PC_episodes": prev_episodes,
    }
    for d in DIAGNOSIS_CODES:
        row[f"PC_Diagnosis_{d}"] = int(chosen_diag == d)
    return row


def generate_baseline(
    n: int = 450,
    seed: int = 100,
    age_mean: float = 62.4,
    age_std: float = 15.4,
) -> pd.DataFrame:
    """Genera un DataFrame baseline limpio (sin sesgos artificiales)."""
    rng = np.random.default_rng(seed)
    id_rng = np.random.default_rng([seed, 0xC1A0])
    rows = []
    for _ in range(n):
        age = sample_age(rng, mean=age_mean, std=age_std)
        sex_f = bool(rng.random() < 0.55)
        diag = sample_diagnosis(age, sex_f, rng)
        prev = sample_prev_episodes(diag, rng)
        rows.append(build_episode_row(age, sex_f, diag, prev, rng, id_rng=id_rng))
    df = pd.DataFrame(rows)
    rng.shuffle(df.values)
    return df


def generate_age_split_batch(
    *,
    n_total: int,
    frac_young: float,
    seed: int,
    age_mean: float = 62.4,
    age_std: float = 15.4,
) -> pd.DataFrame:
    """Genera un batch con composición demográfica 18-35 vs 36-75 controlada.

    Patrón compartido por baseline y recovery del escenario 1: una fracción
    `frac_young` del batch tiene edad 18-35 (suficiente para que la ventana
    fairness disponga de estadística), el resto sigue la distribución
    del servicio regional Normal(`age_mean`, `age_std`) con corte >=36. Las filas se
    permutan al final con el rng del seed. `age_mean`/`age_std` por defecto
    son los mismos que usa `generate_baseline` (62.4, 15.4): sin pasarlos,
    el batch generado no cambia (parámetros del laboratorio).

    Antes se llamaba `young_frac` aquí y `frac_young` en
    `generate_e1_event`, dos nombres del mismo control conviviendo en el
    diccionario de defaults del laboratorio (`sim/scenarios.py`). Unificado
    a `frac_young`.
    """
    rng = np.random.default_rng(seed)
    id_rng = np.random.default_rng([seed, 0xC1A0])
    n_young = int(n_total * frac_young)
    n_rest = n_total - n_young

    rows = []
    for _ in range(n_rest):
        sex_f = rng.random() < 0.76
        age = sample_age_min36(rng, age_mean, age_std)
        diag = sample_diagnosis(age, sex_f, rng)
        prev = sample_prev_episodes(diag, rng)
        rows.append(build_episode_row(age, sex_f, diag, prev, rng, id_rng=id_rng))

    for _ in range(n_young):
        sex_f = rng.random() < 0.55
        age = int(rng.integers(18, 36))
        diag = sample_diagnosis(age, sex_f, rng)
        prev = sample_prev_episodes(diag, rng)
        rows.append(build_episode_row(age, sex_f, diag, prev, rng, id_rng=id_rng))

    perm = rng.permutation(len(rows))
    rows = [rows[i] for i in perm]
    return pd.DataFrame(rows)


def score_dataframe(
    df: pd.DataFrame,
    seed: int | None = None,
    *,
    accuracy_target: float | None = None,
    temperature: float = 1.0,
    diag_weight_override: np.ndarray | None = None,
    prob_noise: float | None = None,
) -> pd.DataFrame:
    """Delega en `model.score`, pasando solo los argumentos no None.

    Nota: el `accuracy_target` de aquí (y de `model.score`) controla flips
    de PREDICTION —el modelo se equivoca respecto a su propia probabilidad—.
    Es distinto del `accuracy_target` de `save_feedback_json` en
    `serialize.py`, que controla el ruido de la ETIQUETA (ground truth)
    respecto a PREDICTION; en la UI se llamará "acierto de la etiqueta".
    """
    kwargs: dict = {"temperature": temperature}
    if accuracy_target is not None:
        kwargs["accuracy_target"] = accuracy_target
    if diag_weight_override is not None:
        kwargs["diag_weight_override"] = diag_weight_override
    if prob_noise is not None:
        kwargs["prob_noise"] = prob_noise
    return m.score(df, seed=seed, **kwargs)


def feedback_path_for(payload_path):
    """Convierte una ruta de payload a la ruta de feedback hermana."""
    return payload_path.with_name(payload_path.name.replace("_payload.json", "_feedback.json"))


# ---------------------------------------------------------------------------
# Generadores de escenario — réplica pura de los scripts 0N_*.py del harness.
# Ninguno escribe a disco: eso vive en serialize.py.
# ---------------------------------------------------------------------------

def generate_e1_baseline(
    seed: int = 7000,
    n_total: int = 450,
    frac_young: float = 0.15,
    age_mean: float = 62.4,
    age_std: float = 15.4,
    temperature: float = 1.0,
) -> pd.DataFrame:
    """Réplica de `01_baseline.py` de escenario 1 (sin serializar).

    `age_mean`, `age_std` y `temperature` son parámetros del laboratorio:
    con sus valores por defecto, el batch generado es
    igual byte a byte al de antes de que existieran.
    """
    df_pre = generate_age_split_batch(
        n_total=n_total, frac_young=frac_young, seed=seed, age_mean=age_mean, age_std=age_std
    )
    return score_dataframe(df_pre, seed=seed, temperature=temperature)


def generate_e1_event(
    seed: int = 1001,
    n_total: int = 450,
    frac_young: float = 0.33,
    bias_additive: float = 1.1,
    age_mean: float = 62.4,
    age_std: float = 15.4,
    temperature: float = 1.0,
) -> tuple[pd.DataFrame, list[bool]]:
    """Réplica exacta de `_generate_event_batch` de `02_evento.py` (E1).

    Sobrerepresenta la cohorte 18-35 (`frac_young`) y le resta
    `bias_additive` al peso de diagnóstico estándar: simula el sesgo
    aprendido por el modelo (edad joven -> menor probabilidad). `age_mean`,
    `age_std` y `temperature` son parámetros del laboratorio (
    §3.4): con sus valores por defecto, el batch generado no cambia.
    """
    rng = np.random.default_rng(seed)
    id_rng = np.random.default_rng([seed, 0xC1A0])

    n_young = int(n_total * frac_young)
    n_base = n_total - n_young

    rows = []
    is_young_flags: list[bool] = []

    for _ in range(n_base):
        sex_f = rng.random() < 0.76
        age = sample_age_min36(rng, age_mean, age_std)
        diag = sample_diagnosis(age, sex_f, rng)
        prev = sample_prev_episodes(diag, rng)
        rows.append(build_episode_row(age, sex_f, diag, prev, rng, id_rng=id_rng))
        is_young_flags.append(False)

    for _ in range(n_young):
        sex_f = rng.random() < 0.55
        age = int(rng.integers(18, 36))
        diag = sample_diagnosis(age, sex_f, rng)
        prev = sample_prev_episodes(diag, rng)
        rows.append(build_episode_row(age, sex_f, diag, prev, rng, id_rng=id_rng))
        is_young_flags.append(True)

    perm = rng.permutation(len(rows))
    rows = [rows[i] for i in perm]
    is_young_flags = [is_young_flags[i] for i in perm]

    df_pre = pd.DataFrame(rows)
    standard_weights = m.compute_diag_weight(df_pre)

    final_weights = standard_weights.copy()
    for i, young in enumerate(is_young_flags):
        if young:
            final_weights[i] = standard_weights[i] - bias_additive

    df_scored = m.score(
        df_pre, seed=seed, diag_weight_override=final_weights, temperature=temperature
    )
    return df_scored, is_young_flags


def generate_e1_recovery(
    seed: int = 7003, n_total: int = 450, frac_young: float = 0.15
) -> pd.DataFrame:
    """Réplica de `03_recovery.py` de escenario 1 (misma mecánica, otro seed)."""
    df_pre = generate_age_split_batch(n_total=n_total, frac_young=frac_young, seed=seed)
    return score_dataframe(df_pre, seed=seed)


NEW_PROTOCOL_DIAGS: tuple[str, str] = ("L88.01", "L18.01")


def _focused_diag_probs(l88_01_frac: float, l18_01_frac: float) -> dict[str, float]:
    """Probabilidades de diagnóstico con L88.01 y L18.01 sobrerepresentados."""
    probs = dict(BASE_DIAG_PROBS)
    rest_total = sum(v for k, v in BASE_DIAG_PROBS.items() if k not in NEW_PROTOCOL_DIAGS)
    target_focus = l88_01_frac + l18_01_frac
    target_rest = 1.0 - target_focus
    rest_factor = target_rest / rest_total
    for k in probs:
        if k not in NEW_PROTOCOL_DIAGS:
            probs[k] = BASE_DIAG_PROBS[k] * rest_factor
    probs["L88.01"] = l88_01_frac
    probs["L18.01"] = l18_01_frac
    total = sum(probs.values())
    return {d: v / total for d, v in probs.items()}


def _build_protocol_ground_truth(
    predictions: np.ndarray,
    chosen_diags: list[str],
    seed: int,
    baseline_error_rate: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Ground truth bajo el protocolo NUEVO: L88.01/L18.01 -> derivar siempre.

    El resto del batch recibe ruido equivalente a `baseline_error_rate`.
    Devuelve (ground_truth, mask_new_protocol).
    """
    mask_new = np.array([d in NEW_PROTOCOL_DIAGS for d in chosen_diags])
    ground_truth = predictions.copy()
    ground_truth[mask_new] = 1

    rng = np.random.default_rng(seed + 100)
    non_affected = np.where(~mask_new)[0]
    idx_0 = non_affected[predictions[non_affected] == 0]
    idx_1 = non_affected[predictions[non_affected] == 1]
    n_flip_0 = round(len(idx_0) * baseline_error_rate)
    n_flip_1 = round(len(idx_1) * baseline_error_rate)
    if n_flip_0 > 0:
        ground_truth[rng.choice(idx_0, size=n_flip_0, replace=False)] = 1
    if n_flip_1 > 0:
        ground_truth[rng.choice(idx_1, size=n_flip_1, replace=False)] = 0
    return ground_truth, mask_new


def generate_e2_event(
    seed: int = 3003,
    n_total: int = 2000,
    l88_01_frac: float = 0.30,
    l18_01_frac: float = 0.10,
    baseline_error_rate: float = 0.14,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, list[str]]:
    """Réplica exacta de `_generate_event_batch` de `02_evento.py` (E2).

    Scoring con protocolo ANTIGUO (L88.01/L18.01 con peso LOW); el ground
    truth simula el protocolo NUEVO (derivación directa para ambos).
    Devuelve (df_scored, ground_truth, mask_new, chosen_diags).
    """
    rng = np.random.default_rng(seed)
    id_rng = np.random.default_rng([seed, 0xC1A0])
    diag_probs = _focused_diag_probs(l88_01_frac, l18_01_frac)

    rows = []
    chosen_diags: list[str] = []

    for _ in range(n_total):
        sex_f = rng.random() < 0.76
        age = int(np.clip(rng.normal(62.4, 15.4), 20, 102))
        diag = sample_diagnosis(age, sex_f, rng, diag_probs=diag_probs)
        prev = sample_prev_episodes(diag, rng)
        rows.append(build_episode_row(age, sex_f, diag, prev, rng, id_rng=id_rng))
        chosen_diags.append(diag)

    df_pre = pd.DataFrame(rows)
    df_scored = m.score(df_pre, seed=seed)

    predictions = df_scored["PREDICTION"].astype(int).values.copy()
    ground_truth, mask_new = _build_protocol_ground_truth(
        predictions, chosen_diags, seed, baseline_error_rate
    )

    return df_scored, ground_truth, mask_new, chosen_diags


def generate_e2_recovery(seed: int = 7777, n_total: int = 3000) -> pd.DataFrame:
    """Réplica de `_generate_recovery_batch` de `03_recovery.py` (E2)."""
    rng = np.random.default_rng(seed)
    id_rng = np.random.default_rng([seed, 0xC1A0])

    rows = []
    for _ in range(n_total):
        sex_f = rng.random() < 0.76
        age = sample_age(rng)
        diag = sample_diagnosis(age, sex_f, rng)
        prev = sample_prev_episodes(diag, rng)
        rows.append(build_episode_row(age, sex_f, diag, prev, rng, id_rng=id_rng))

    return score_dataframe(pd.DataFrame(rows), seed=seed)
