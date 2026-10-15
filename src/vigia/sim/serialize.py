"""serialize — Payload/feedback de la demo y post-shuffle Age-window.

Puerto de las funciones de serialización de
`escenarios/shared/generators.py` del harness de demo (solo lectura),
separadas en su propio módulo y hechas puras donde el harness leía o
escribía disco directamente (`reorder_for_fairness_window` -> aquí
`reorder_last_window`, que opera sobre el DataFrame y devuelve la
permutación en vez de reordenar ficheros en sitio).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .model import DIAGNOSIS_MAPPING

_MASK_PAT = re.compile(r"PAT_[0-9a-f]{10}")
_MASK_EP = re.compile(r"EP_[0-9a-f]{12}")


def _json_default(o: object) -> object:
    if isinstance(o, (datetime, pd.Timestamp)):
        return o.isoformat()
    if isinstance(o, (np.integer, np.floating)):
        return o.item()
    raise TypeError(f"Type {type(o)} not serializable")


def payload_dict(df_scored: pd.DataFrame) -> dict:
    """Payload: input_data (features) + output_data (predicción)."""
    df_out = df_scored.rename(columns=DIAGNOSIS_MAPPING)
    exclude = {"PREDICTION", "PROBABILITIES"}
    input_fields = [c for c in df_out.columns if c not in exclude]

    return {
        "input_data": [
            {
                "fields": input_fields,
                "values": df_out[input_fields].values.tolist(),
            }
        ],
        "output_data": [
            {
                "fields": ["PREDICTION", "PROBABILITIES"],
                "values": df_scored[["PREDICTION", "PROBABILITIES"]].values.tolist(),
            }
        ],
    }


def feedback_dict(
    df_scored: pd.DataFrame,
    *,
    seed: int | None = None,
    accuracy_target: float = 0.86,
    ground_truth_override: np.ndarray | None = None,
    label_column: str = "Has_Referral_in_Window",
) -> dict:
    """Feedback: features + predicción original + etiqueta.

    La etiqueta (ground truth) es `PREDICTION` con flips aleatorios según
    `1 - accuracy_target` salvo que se pase `ground_truth_override`
    (protocolo nuevo del escenario 2, donde la etiqueta no depende de
    ruido sino de una regla clínica).
    """
    rng = np.random.default_rng(seed)
    df_out = df_scored.rename(columns=DIAGNOSIS_MAPPING)
    exclude = {"PREDICTION", "PROBABILITIES"}
    input_fields = [c for c in df_out.columns if c not in exclude]
    df_input = df_out[input_fields].copy()

    if ground_truth_override is not None:
        ground_truth = np.asarray(ground_truth_override, dtype=int)
    else:
        predictions = df_scored["PREDICTION"].astype(int).values.copy()
        ground_truth = predictions.copy()
        error_rate = 1.0 - accuracy_target
        idx_0 = np.where(predictions == 0)[0]
        idx_1 = np.where(predictions == 1)[0]
        n_flip_0 = round(len(idx_0) * error_rate)
        n_flip_1 = round(len(idx_1) * error_rate)
        if n_flip_0 > 0:
            ground_truth[rng.choice(idx_0, size=n_flip_0, replace=False)] = 1
        if n_flip_1 > 0:
            ground_truth[rng.choice(idx_1, size=n_flip_1, replace=False)] = 0

    df_fb = df_input.copy()
    df_fb["_original_prediction"] = df_scored["PREDICTION"].values
    df_fb["_original_probability"] = df_scored["PROBABILITIES"].values
    df_fb[label_column] = ground_truth

    return {
        "fields": df_fb.columns.tolist(),
        "values": df_fb.values.tolist(),
    }


def dump_json(obj: dict, path: str | Path, indent: int | None) -> Path:
    """Vuelca `obj` a `path` en modo texto (CRLF en Windows), como el harness.

    `indent=2` reproduce los enlatados de escenario 1 (`json.dumps(...,
    indent=2, ...)` seguido de `f.write`); `indent=None` reproduce el
    volcado compacto de escenario 2 (salida de `reorder_for_fairness_window`,
    `json.dump(obj, f, ensure_ascii=False)` sin indent).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if indent is not None:
            f.write(json.dumps(obj, indent=indent, ensure_ascii=False, default=_json_default))
        else:
            json.dump(obj, f, ensure_ascii=False, default=_json_default)
    return path


def save_payload_json(df_scored: pd.DataFrame, path: str | Path, *, indent: int = 2) -> Path:
    return dump_json(payload_dict(df_scored), path, indent)


def save_feedback_json(
    df_scored: pd.DataFrame, path: str | Path, *, indent: int = 2, **kw
) -> Path:
    return dump_json(feedback_dict(df_scored, **kw), path, indent)


def mask_ids(text: str) -> str:
    """Sustituye ids no deterministas (uuid4 del harness) por un patrón fijo."""
    text = _MASK_PAT.sub("PAT_XXXXXXXXXX", text)
    text = _MASK_EP.sub("EP_XXXXXXXXXXXX", text)
    return text


def reorder_last_window(
    df_scored: pd.DataFrame,
    *,
    window_size: int = 200,
    target_young: int = 30,
    target_pos_young: int = 5,
    seed: int = 7777,
    age_col: str = "Age",
    pred_col: str = "PREDICTION",
) -> np.ndarray:
    """Permutación que fuerza minoría (18-35) en las últimas `window_size` filas.

    Workaround del harness, desactivado por defecto; manipula la ventana de
    últimos N para que la ventana fairness "last N records" no caiga en una
    zona sin minoría (falsa alerta fairness_value=0). Los batches que la
    usan se marcan `orden_manipulado`. Réplica pura de
    `reorder_for_fairness_window` del harness: mismo uso del rng
    (`shuffle(young_pos)`, `shuffle(young_neg)`, `shuffle(nonyoung)`,
    `shuffle(last_window)`, `shuffle(rest)`), pero no lee ni escribe
    ficheros: opera sobre `df_scored` en su orden actual y devuelve el
    array de índices `new_order` (a aplicar con `apply_permutation` /
    `permute_dicts`).
    """
    ages = df_scored[age_col].astype(int).tolist()
    preds = df_scored[pred_col].astype(int).tolist()
    n = len(df_scored)

    young = [i for i in range(n) if 18 <= ages[i] <= 35]
    young_pos = [i for i in young if preds[i] == 1]
    young_neg = [i for i in young if preds[i] == 0]
    nonyoung = [i for i in range(n) if not (18 <= ages[i] <= 35)]

    pick_pos = min(target_pos_young, len(young_pos))
    pick_neg = target_young - pick_pos
    pick_nonyoung = window_size - target_young

    rng = np.random.default_rng(seed)
    rng.shuffle(young_pos)
    rng.shuffle(young_neg)
    rng.shuffle(nonyoung)

    last_window = young_pos[:pick_pos] + young_neg[:pick_neg] + nonyoung[:pick_nonyoung]
    rng.shuffle(last_window)

    used = set(last_window)
    rest = [i for i in range(n) if i not in used]
    rng.shuffle(rest)
    new_order = rest + last_window
    if len(set(new_order)) != n:
        raise RuntimeError("permutación tiene índices duplicados")

    return np.asarray(new_order, dtype=int)


def apply_permutation(df: pd.DataFrame, perm: np.ndarray) -> pd.DataFrame:
    return df.iloc[perm].reset_index(drop=True)


def permute_dicts(payload: dict, feedback: dict, perm: np.ndarray) -> tuple[dict, dict]:
    """Aplica `perm` a los tres bloques de valores (payload x2 + feedback)."""
    perm = list(perm)
    in_values = payload["input_data"][0]["values"]
    out_values = payload["output_data"][0]["values"]
    fb_values = feedback["values"]

    payload = dict(payload)
    payload["input_data"] = [dict(payload["input_data"][0])]
    payload["input_data"][0]["values"] = [in_values[i] for i in perm]
    payload["output_data"] = [dict(payload["output_data"][0])]
    payload["output_data"][0]["values"] = [out_values[i] for i in perm]

    feedback = dict(feedback)
    feedback["values"] = [fb_values[i] for i in perm]

    return payload, feedback
