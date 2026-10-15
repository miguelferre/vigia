"""Calidad multiclase.

Las claves de siempre llevan el promedio macro; las métricas por clase salen
aparte para guardarse como `Measurement` con `group_code = "clase:<valor>"` y
sin umbral. Este módulo no importa `quality.py`: `quality.py` lo importa.
"""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)

from vigia.core.schema import (
    COL_LABEL,
    COL_LABEL_CLASS,
    COL_PREDICTION,
    COL_PREDICTION_CLASS,
    DatosNoValidos,
    TaskSpec,
    col_prob,
)

MOTIVO_SIN_CONJUNTO_FAVORABLE = "sin conjunto favorable: solo calidad por grupo"
MOTIVO_UMBRAL_PENDIENTE = "umbral pendiente de la línea base"

# Métricas que se publican también por clase: mismas claves de siempre.
CLAVES_POR_CLASE = (
    "precision",
    "recall",
    "f1_measure",
    "area_under_roc",
    "area_under_pr",
    "false_positive_rate",
    "label_rate",
    "prediction_rate",
)

_EPS = 1e-15


def columnas_probabilidad(k: int) -> list[str]:
    return [col_prob(i) for i in range(k)]


def exigir_columnas_clase(df: pd.DataFrame, columnas: tuple[str, ...]) -> None:
    """422 (`DatosNoValidos`) en español si a los datos de un proyecto multiclase
    les falta la columna de clase predicha o real, en vez de un `KeyError` (500)."""
    faltan = [c for c in columnas if c not in df.columns]
    if faltan:
        raise DatosNoValidos(
            "a los datos del proyecto les falta la columna de clase "
            f"({', '.join(faltan)}): vuelve a subir el fichero con las columnas de "
            "predicción y de etiqueta del mapeo"
        )


def validar_probabilidad_multiclase(
    df_labeled: pd.DataFrame, k: int, *, columna_original: str | None = None
) -> None:
    """Como `validar_probabilidad` pero sobre las `k` columnas `prob__i`: ni
    nulas ni fuera de 0 a 1 en las filas con etiqueta."""
    n = len(df_labeled)
    if n == 0:
        return
    columnas = columnas_probabilidad(k)
    faltan = [c for c in columnas if c not in df_labeled.columns]
    if faltan:
        raise DatosNoValidos(
            "faltan las probabilidades por clase en los datos: vuelve a subir el "
            "fichero con una columna de probabilidad por clase"
        )
    p = df_labeled[columnas].to_numpy(dtype=float)
    invalidas = np.isnan(p).any(axis=1) | (p < 0).any(axis=1) | (p > 1).any(axis=1)
    n_invalidas = int(invalidas.sum())
    if n_invalidas:
        referencia = (
            f"la columna {columna_original}" if columna_original else "las columnas de probabilidad"
        )
        raise DatosNoValidos(
            f"la probabilidad tiene {n_invalidas} de {n} filas nulas o fuera de 0 a 1: "
            f"revisa {referencia} del mapeo"
        )


def _normalizar_filas(p: np.ndarray) -> np.ndarray:
    suma = p.sum(axis=1, keepdims=True)
    k = p.shape[1]
    return np.where(suma > 0, p / np.where(suma > 0, suma, 1.0), 1.0 / k)


def _auc_por_clase(
    y: np.ndarray, p: np.ndarray, k: int
) -> tuple[list[float | None], list[float | None], list[tuple[int, str]]]:
    """AUC-ROC y AUC-PR uno contra el resto de cada clase. `None` (y la clase
    en `excluidas`, con su motivo) si no tiene positivos o no tiene negativos."""
    aucs: list[float | None] = []
    aps: list[float | None] = []
    excluidas: list[tuple[int, str]] = []
    n = len(y)
    for c in range(k):
        positivos = int((y == c).sum())
        if positivos == 0:
            aucs.append(None)
            aps.append(None)
            excluidas.append((c, "sin positivos en la ventana"))
        elif positivos == n:
            aucs.append(None)
            aps.append(None)
            excluidas.append((c, "sin negativos en la ventana"))
        else:
            aucs.append(float(roc_auc_score(y == c, p[:, c])))
            aps.append(float(average_precision_score(y == c, p[:, c])))
    return aucs, aps, excluidas


def metricas_multiclase(
    df_labeled: pd.DataFrame,
    task: TaskSpec,
    *,
    min_group: int = 20,
    columna_probabilidad: str | None = None,
) -> dict[str, Any]:
    """Métricas de calidad multiclase sobre filas con etiqueta de una clase
    declarada. Devuelve las claves escalares de `quality_metrics` (macro),
    más `por_clase` (medidas por clase) y `details` (matriz de
    confusión, F1 ponderada, AUC excluidas, distribución de la etiqueta)."""
    k = task.k
    claves = list(task.claves)
    exigir_columnas_clase(df_labeled, (COL_LABEL_CLASS, COL_PREDICTION_CLASS))
    validar_probabilidad_multiclase(df_labeled, k, columna_original=columna_probabilidad)
    indice = {c: i for i, c in enumerate(claves)}
    y_serie = df_labeled[COL_LABEL_CLASS].map(indice)
    valida = y_serie.notna() & df_labeled[COL_PREDICTION_CLASS].isin(indice)
    df = df_labeled[valida]
    n = len(df)
    y = y_serie[valida].to_numpy(dtype=int)
    yhat = df[COL_PREDICTION_CLASS].map(indice).to_numpy(dtype=int)
    p = _normalizar_filas(df[columnas_probabilidad(k)].to_numpy(dtype=float))

    cm = confusion_matrix(y, yhat, labels=list(range(k)))
    soporte = cm.sum(axis=1)
    predichas = cm.sum(axis=0)
    presentes = sorted(set(y.tolist()) | set(yhat.tolist()))
    accuracy = float(np.trace(cm)) / n if n else 0.0

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        precision = float(
            precision_score(y, yhat, labels=presentes, average="macro", zero_division=0)
        )
        recall = float(recall_score(y, yhat, labels=presentes, average="macro", zero_division=0))
        f1_macro = float(f1_score(y, yhat, labels=presentes, average="macro", zero_division=0))
        f1_pond = float(f1_score(y, yhat, labels=presentes, average="weighted", zero_division=0))
        mcc = float(matthews_corrcoef(y, yhat))

    onehot = np.eye(k)[y]
    brier = float(np.mean(np.sum((p - onehot) ** 2, axis=1)))
    log_loss_val = float(-np.mean(np.log(np.clip(p[np.arange(n), y], _EPS, 1.0))))

    aucs, aps, excluidas = _auc_por_clase(y, p, k)
    validas_auc = [a for a in aucs if a is not None]
    validas_ap = [a for a in aps if a is not None]
    if len(validas_auc) < 2:
        area_under_roc: float | None = None
        area_under_pr: float | None = None
        gini: float | None = None
    else:
        area_under_roc = float(np.mean(validas_auc))
        area_under_pr = float(np.mean(validas_ap))
        gini = 2.0 * area_under_roc - 1.0

    # uno contra el resto, por clase
    fpr_por_clase: list[float | None] = []
    for c in range(k):
        tp = int(cm[c, c])
        fp = int(predichas[c]) - tp
        negativos = n - int(soporte[c])
        fpr_por_clase.append(fp / negativos if negativos else None)
    fprs_presentes = [fpr_por_clase[c] for c in presentes if fpr_por_clase[c] is not None]
    false_positive_rate = float(np.mean(fprs_presentes)) if fprs_presentes else 0.0

    # favorable contra el resto (`details.confusion`;: sin conjunto)
    if task.sin_conjunto_favorable:
        tp = fp = fn = tn = None
        label_rate: float | None = None
        prediction_rate: float | None = None
    else:
        y01 = df[COL_LABEL].astype(int).to_numpy()
        yhat01 = df[COL_PREDICTION].astype(int).to_numpy()
        tn_, fp_, fn_, tp_ = confusion_matrix(y01, yhat01, labels=[0, 1]).ravel()
        tp, fp, fn, tn = int(tp_), int(fp_), int(fn_), int(tn_)
        label_rate = float(y01.mean()) if n else None
        prediction_rate = float(yhat01.mean()) if n else None

    por_clase: dict[str, dict[str, Any]] = {}
    tabla: dict[str, dict[str, Any]] = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for c, clase in enumerate(claves):
            sop = int(soporte[c])
            pred_n = int(predichas[c])
            tp_c = int(cm[c, c])
            insuficiente = sop < min_group
            prec_c = tp_c / pred_n if pred_n else 0.0
            rec_c = tp_c / sop if sop else 0.0
            f1_c = 2 * prec_c * rec_c / (prec_c + rec_c) if (prec_c + rec_c) else 0.0
            valores: dict[str, float | None] = {
                "precision": prec_c,
                "recall": rec_c,
                "f1_measure": f1_c,
                "area_under_roc": aucs[c],
                "area_under_pr": aps[c],
                "false_positive_rate": fpr_por_clase[c],
                "label_rate": sop / n if n else None,
                "prediction_rate": pred_n / n if n else None,
            }
            por_clase[clase] = {
                "n": sop,
                "insuficiente": insuficiente,
                "valores": valores,
            }
            tabla[clase] = {
                "precision": None if insuficiente else prec_c,
                "recall": None if insuficiente else rec_c,
                "f1_measure": None if insuficiente else f1_c,
                "soporte": sop,
                "predichas": pred_n,
                "tasa_predicha": pred_n / n if n else None,
                "muestra_insuficiente": insuficiente,
            }

    details: dict[str, Any] = {
        "confusion_matrix": {"classes": claves, "matrix": cm.astype(int).tolist()},
        "por_clase": tabla,
        "f1_ponderada": f1_pond,
        "distribucion_etiqueta": {
            clase: (float(soporte[c]) / n if n else None) for c, clase in enumerate(claves)
        },
        "auc_clases_excluidas": [
            {"clase": claves[c], "motivo": motivo} for c, motivo in excluidas
        ],
    }

    return {
        "n": n,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "accuracy": accuracy,
        "area_under_roc": area_under_roc,
        "area_under_pr": area_under_pr,
        "true_positive_rate": recall,
        "false_positive_rate": false_positive_rate,
        "precision": precision,
        "recall": recall,
        "f1_measure": f1_macro,
        "log_loss": log_loss_val,
        "matthews_correlation_coefficient": mcc,
        "gini_coefficient": gini,
        "brier_score": brier,
        "label_rate": label_rate,
        "prediction_rate": prediction_rate,
        "por_clase": por_clase,
        "details": details,
    }


def clases_desconocidas(
    historia: pd.DataFrame, task: TaskSpec, *, hasta_batch: int | None = None
) -> dict[str, int]:
    """Filas con una etiqueta de una clase que no está en `task.classes`
    (`label_class` presente, `label` nulo). Quedan fuera de la calidad."""
    if COL_LABEL_CLASS not in historia.columns:
        return {}
    filas = historia
    if hasta_batch is not None and "batch_seq" in filas.columns:
        filas = filas[filas["batch_seq"] <= hasta_batch]
    claves = set(task.claves)
    texto = filas[COL_LABEL_CLASS]
    desconocidas = filas[texto.notna() & ~texto.isin(claves)]
    return {str(k): int(v) for k, v in desconocidas[COL_LABEL_CLASS].value_counts().items()}
