"""Monitor de deriva: PSI, KS, confianza y deriva de predicción/feature
sobre el frame canónico. Réplica exacta de las funciones de deriva de
`research/proto_oss.py`.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sps
from scipy.spatial.distance import jensenshannon

from vigia.core import CORE_VERSION
from vigia.core.quality_multiclase import (
    MOTIVO_UMBRAL_PENDIENTE,
    columnas_probabilidad,
    exigir_columnas_clase,
)
from vigia.core.schema import (
    COL_BATCH,
    COL_LABEL_VALUE,
    COL_PREDICTION,
    COL_PREDICTION_CLASS,
    COL_PREDICTION_VALUE,
    COL_PROB,
    COL_SEQ,
    DatosNoValidos,
    DriftConfig,
    EvaluationResult,
    Measurement,
    MonitorThresholds,
    MonitorType,
    State,
    TaskSpec,
    WindowInfo,
)
from vigia.core.states import classify_with_motivo

SIN_EQUIVALENTE = [
    "model_quality_score",
    "output_metadata_drift_score",
    "input_metadata_drift_score",
]


def psi(
    expected: np.ndarray,
    actual: np.ndarray,
    bins: int = 10,
    *,
    return_bins: bool = False,
) -> float | tuple[float, dict[str, Any] | None]:
    """Population Stability Index: cortes por cuantiles de `expected`.
    NaN si hay menos de 3 cortes distintos. Idéntico a `psi` del prototipo.

    Con `return_bins=True` devuelve además el histograma
    con el que se calcula el PSI (`bin_edges`, y las dos frecuencias
    `bin_counts_base`/`bin_counts_actual`), en vez de descartarlo. `None`
    en la segunda posición si el PSI salió NaN (sin cortes suficientes).
    Con `return_bins=False` (por defecto) el comportamiento y el tipo de
    retorno son exactamente los de siempre: solo el float.
    """
    if len(expected) == 0 or len(actual) == 0:
        return (float("nan"), None) if return_bins else float("nan")
    quantiles = np.linspace(0, 1, bins + 1)
    cuts = np.unique(np.quantile(expected, quantiles))
    if len(cuts) < 3:
        return (float("nan"), None) if return_bins else float("nan")
    e_counts, _ = np.histogram(expected, bins=cuts)
    a_counts, _ = np.histogram(actual, bins=cuts)
    e_pct = np.clip(e_counts / len(expected), 1e-6, None)
    a_pct = np.clip(a_counts / len(actual), 1e-6, None)
    valor = float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))
    if not return_bins:
        return valor
    bins_info = {
        "bin_edges": [float(x) for x in cuts],
        "bin_counts_base": [int(x) for x in e_counts],
        "bin_counts_actual": [int(x) for x in a_counts],
    }
    return valor, bins_info


def confidence(prob_favorable: np.ndarray) -> np.ndarray:
    """Confianza de la predicción: `max(p, 1 - p)`."""
    p = np.asarray(prob_favorable, dtype=float)
    return np.maximum(p, 1 - p)


def confidence_drift(
    base_prob: np.ndarray,
    cur_prob: np.ndarray,
    *,
    bins: int = 20,
    psi_bins: int = 10,
    base_pred: np.ndarray | None = None,
    cur_pred: np.ndarray | None = None,
) -> dict[str, Any]:
    """Deriva de la confianza de la predicción (`max(p, 1 - p)`) entre línea
    base y lote actual: KS, PSI y Jensen-Shannon sobre el histograma global,
    más los `bin_edges`/`bin_counts_base`/`bin_counts_actual` con los que se
    calculó. Esta métrica global no cambia con `base_pred`/`cur_pred`:
    son los números de aceptación del motor.

    Con `base_pred` y `cur_pred` (la predicción de cada
    fila, alineada con `base_prob`/`cur_prob`) añade `"by_class"`: un
    histograma de confianza por cada clase predicha presente en cualquiera
    de los dos lotes (clave `str(int(clase))`, ordenadas de mayor a menor:
    `"1"` antes que `"0"`), calculado con los MISMOS `edges` que el
    histograma global sobre las filas de esa clase. Como cada fila
    pertenece a una única clase predicha, la suma por bin de todas las
    clases coincide con `bin_counts_base`/`bin_counts_actual` del histograma
    global. Sin `base_pred`/`cur_pred`, `by_class` no aparece
    (retrocompatible).
    """
    base_conf = confidence(base_prob)
    cur_conf = confidence(cur_prob)
    return _deriva_de_confianza(
        base_conf,
        cur_conf,
        np.linspace(0.5, 1.0, bins + 1),
        psi_bins=psi_bins,
        base_pred=base_pred,
        cur_pred=cur_pred,
    )


def confidence_drift_multiclase(
    base_probs: np.ndarray,
    cur_probs: np.ndarray,
    *,
    classes: tuple[str, ...],
    bins: int = 20,
    psi_bins: int = 10,
    base_pred: np.ndarray | None = None,
    cur_pred: np.ndarray | None = None,
) -> dict[str, Any]:
    """Deriva de la confianza en multiclase. La confianza es el máximo de
    las `k` probabilidades, con histograma sobre `linspace(1/k, 1)` (con `k = 2`
    es el de `confidence_drift`, bit a bit). `by_class` usa la clase predicha
    como texto (`str(clase)`), en el orden de `classes`."""
    base_conf = np.max(np.asarray(base_probs, dtype=float), axis=1)
    cur_conf = np.max(np.asarray(cur_probs, dtype=float), axis=1)
    k = len(classes)
    return _deriva_de_confianza(
        base_conf,
        cur_conf,
        np.linspace(1.0 / k, 1.0, bins + 1),
        psi_bins=psi_bins,
        base_pred=base_pred,
        cur_pred=cur_pred,
        classes=classes,
    )


def _deriva_de_confianza(
    base_conf: np.ndarray,
    cur_conf: np.ndarray,
    edges: np.ndarray,
    *,
    psi_bins: int,
    base_pred: np.ndarray | None,
    cur_pred: np.ndarray | None,
    classes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    ks = sps.ks_2samp(base_conf, cur_conf)
    psi_val = psi(base_conf, cur_conf, bins=psi_bins)

    p_hist, _ = np.histogram(base_conf, bins=edges)
    q_hist, _ = np.histogram(cur_conf, bins=edges)
    p_dist = np.clip(p_hist / p_hist.sum(), 1e-9, None)
    q_dist = np.clip(q_hist / q_hist.sum(), 1e-9, None)
    js_dist = float(jensenshannon(p_dist, q_dist, base=2))

    resultado: dict[str, Any] = {
        "ks_stat": float(ks.statistic),
        "ks_p": float(ks.pvalue),
        "psi": psi_val,
        "jensen_shannon_distance": js_dist,
        "jensen_shannon_divergence": js_dist**2,
        # Bins del histograma de confianza superpuesto
        # (escena 6), antes descartados.
        "bin_edges": [float(x) for x in edges],
        "bin_counts_base": [int(x) for x in p_hist],
        "bin_counts_actual": [int(x) for x in q_hist],
    }

    if base_pred is not None and cur_pred is not None:
        resultado["by_class"] = _confidence_by_class(
            base_conf,
            np.asarray(base_pred),
            cur_conf,
            np.asarray(cur_pred),
            edges,
            psi_bins=psi_bins,
            classes=classes,
        )

    return resultado


def _confidence_by_class(
    base_conf: np.ndarray,
    base_pred: np.ndarray,
    cur_conf: np.ndarray,
    cur_pred: np.ndarray,
    edges: np.ndarray,
    *,
    psi_bins: int = 10,
    classes: tuple[str, ...] | None = None,
) -> dict[str, dict[str, Any]]:
    """Histograma de confianza por clase predicha, con los mismos
    `edges` que el histograma global. Una entrada por clase presente en
    `base_pred` o `cur_pred`, de mayor a menor clave.

    Además del histograma, cada clase lleva sus propios `psi`,
    `ks_stat`, `ks_p` y `jensen_shannon_distance`, calculados con el mismo
    método que la métrica global (`psi()`, `sps.ks_2samp`, `jensenshannon`
    sobre el histograma de esa clase), sobre las filas de esa clase
    únicamente. Con una clase sin filas en alguno de los dos lotes, `ks_stat`
    y `jensen_shannon_distance` no se pueden calcular y quedan en `None`
    (`psi()` ya devuelve NaN en ese caso, igual que la métrica global)."""
    if classes is None:
        clases: list[Any] = sorted(
            {int(c) for c in np.unique(base_pred)} | {int(c) for c in np.unique(cur_pred)},
            reverse=True,
        )
    else:
        # La clase es texto, no un entero; solo las presentes, en el
        # orden de las clases del proyecto.
        presentes = {str(c) for c in np.unique(base_pred)} | {str(c) for c in np.unique(cur_pred)}
        clases = [c for c in classes if str(c) in presentes]
    por_clase: dict[str, dict[str, Any]] = {}
    for clase in clases:
        base_mask = base_pred == clase
        cur_mask = cur_pred == clase
        base_vals = base_conf[base_mask]
        cur_vals = cur_conf[cur_mask]
        base_hist, _ = np.histogram(base_vals, bins=edges)
        cur_hist, _ = np.histogram(cur_vals, bins=edges)

        if len(base_vals) and len(cur_vals):
            ks = sps.ks_2samp(base_vals, cur_vals)
            ks_stat: float | None = float(ks.statistic)
            ks_p: float | None = float(ks.pvalue)
            p_dist = np.clip(base_hist / base_hist.sum(), 1e-9, None) if base_hist.sum() else None
            q_dist = np.clip(cur_hist / cur_hist.sum(), 1e-9, None) if cur_hist.sum() else None
            js_dist: float | None = (
                float(jensenshannon(p_dist, q_dist, base=2))
                if p_dist is not None and q_dist is not None
                else None
            )
        else:
            ks_stat = None
            ks_p = None
            js_dist = None

        por_clase[str(clase)] = {
            "bin_counts_base": [int(x) for x in base_hist],
            "bin_counts_actual": [int(x) for x in cur_hist],
            "n_base": int(base_mask.sum()),
            "n_actual": int(cur_mask.sum()),
            "psi": psi(base_vals, cur_vals, bins=psi_bins),
            "ks_stat": ks_stat,
            "ks_p": ks_p,
            "jensen_shannon_distance": js_dist,
        }
    return por_clase


def prediction_drift(base_pred: np.ndarray, cur_pred: np.ndarray) -> dict[str, float]:
    """`n_base`/`n_actual` con el mismo patrón que
    `_confidence_by_class` (mismos nombres), para que la tarjeta de clases
    predichas pueda enseñar recuentos junto a las tasas."""
    rate_base = float(np.mean(base_pred))
    rate_cur = float(np.mean(cur_pred))
    diff = rate_cur - rate_base
    return {
        "rate_base": rate_base,
        "rate_cur": rate_cur,
        "diff": diff,
        "score": abs(diff),
        "n_base": len(base_pred),
        "n_actual": len(cur_pred),
    }


def prediction_drift_multiclase(
    base_class: pd.Series,
    cur_class: pd.Series,
    classes: tuple[str, ...],
    favorables: tuple[str, ...],
) -> dict[str, Any]:
    """En multiclase la deriva de la predicción es la distancia de
    Jensen-Shannon entre la distribución de la clase predicha del lote y la de
    la línea base (`drift_categorical`), y `details` nombra la clase con el mayor
    cambio. El cambio de la tasa del conjunto favorable no basta: no ve un
    movimiento entre clases no favorables."""
    base = base_class.astype(str)
    cur = cur_class.astype(str)
    cat = drift_categorical("prediction_class", base, cur)
    n_base, n_cur = len(base), len(cur)
    por_clase: dict[str, dict[str, float | None]] = {}
    mayor: tuple[float, str] | None = None
    for clase in classes:
        rb = float((base == clase).mean()) if n_base else None
        rc = float((cur == clase).mean()) if n_cur else None
        diff = (rc - rb) if rb is not None and rc is not None else None
        por_clase[clase] = {"base": rb, "actual": rc, "diff": diff}
        if diff is not None and (mayor is None or abs(diff) > mayor[0]):
            mayor = (abs(diff), clase)
    rate_base = rate_cur = diff_fav = None
    if favorables:
        rate_base = float(base.isin(favorables).mean()) if n_base else None
        rate_cur = float(cur.isin(favorables).mean()) if n_cur else None
        if rate_base is not None and rate_cur is not None:
            diff_fav = rate_cur - rate_base
    return {
        "metodo": "jensen_shannon",
        "rate_base": rate_base,
        "rate_cur": rate_cur,
        "diff": diff_fav,
        "score": cat["js"],
        "chi2": cat["chi2"],
        "p": cat["p"],
        "n_base": n_base,
        "n_actual": n_cur,
        "por_clase": por_clase,
        "clase_mayor_cambio": mayor[1] if mayor else None,
        "cambio_mayor": por_clase[mayor[1]]["diff"] if mayor else None,
    }


MOTIVO_PSI_POCOS_CORTES = "la predicción tiene menos de 3 cortes por cuantil"
N_CAJAS_PREDICCION = 20


def _histograma_comun(base: np.ndarray, cur: np.ndarray) -> dict[str, Any]:
    """Histograma de la línea base y del lote con los mismos cortes: 20 cajas
    iguales sobre el rango de los dos lados, para dibujarlos uno sobre otro."""
    union = np.concatenate([base, cur])
    bordes = np.histogram_bin_edges(union, bins=N_CAJAS_PREDICCION)
    cuentas_base, _ = np.histogram(base, bins=bordes)
    cuentas_cur, _ = np.histogram(cur, bins=bordes)
    return {
        "bin_edges": [float(b) for b in bordes],
        "bin_counts_base": [int(c) for c in cuentas_base],
        "bin_counts_actual": [int(c) for c in cuentas_cur],
    }


def prediction_drift_regresion(
    base: np.ndarray, cur: np.ndarray, *, psi_bins: int = 10
) -> dict[str, Any]:
    """En regresión la deriva de la predicción es el estadístico
    KS (de 0 a 1, sin unidad) entre `prediction_value` del lote y el de la línea
    base, la misma escala que `feature_drift_score` en variables numéricas. Va en
    `score`; PSI (o su motivo si la predicción tiene menos de 3 cortes por
    cuantil, p. ej. una salida en pocos escalones), `ks_p`, el histograma común y
    la diferencia de medias en la unidad van en el mismo bloque."""
    base_arr = np.asarray(base, dtype=float)
    cur_arr = np.asarray(cur, dtype=float)
    base_ok = base_arr[np.isfinite(base_arr)]
    cur_ok = cur_arr[np.isfinite(cur_arr)]
    if len(base_ok) == 0 or len(cur_ok) == 0:
        return {
            "metodo": "ks",
            "score": None,
            "ks": None,
            "ks_p": None,
            "psi": None,
            "psi_motivo": "sin predicciones válidas en la línea base o en el lote",
            "n_base": len(base_ok),
            "n_actual": len(cur_ok),
        }
    r = drift_numeric("prediction", base_ok, cur_ok, psi_bins=psi_bins)
    psi_val = r["psi"]
    psi_ok = isinstance(psi_val, float) and not math.isnan(psi_val)
    media_base, media_cur = float(base_ok.mean()), float(cur_ok.mean())
    return {
        "metodo": "ks",
        "score": r["ks_stat"],
        "ks": r["ks_stat"],
        "ks_p": r["ks_p"],
        "psi": psi_val if psi_ok else None,
        "psi_motivo": None if psi_ok else MOTIVO_PSI_POCOS_CORTES,
        **_histograma_comun(base_ok, cur_ok),
        "media_base": media_base,
        "media_actual": media_cur,
        "diferencia_medias": media_cur - media_base,
        "n_base": len(base_ok),
        "n_actual": len(cur_ok),
    }


def label_drift_regresion(base: np.ndarray, cur: np.ndarray) -> dict[str, Any] | None:
    """Deriva del valor real, sin umbral, solo si los dos lados tienen
    etiqueta: KS, su p y la diferencia de medias en la unidad."""
    base_arr = np.asarray(base, dtype=float)
    cur_arr = np.asarray(cur, dtype=float)
    base_ok = base_arr[np.isfinite(base_arr)]
    cur_ok = cur_arr[np.isfinite(cur_arr)]
    if len(base_ok) == 0 or len(cur_ok) == 0:
        return None
    ks = sps.ks_2samp(base_ok, cur_ok)
    return {
        "ks": float(ks.statistic),
        "ks_p": float(ks.pvalue),
        "diferencia_medias": float(cur_ok.mean() - base_ok.mean()),
    }


def drift_numeric(
    name: str, base: np.ndarray, cur: np.ndarray, *, psi_bins: int = 10
) -> dict[str, Any]:
    """Quita los nulos de `base` y `cur` antes de calcular (un
    `NaN` en KS o en los cuantiles de `psi` no es un dato, es su ausencia).
    Si algún lado se queda sin filas válidas, `ks_stat` sale `None` (no
    `NaN`: `feature_drift_score` lo excluye al agregar) y `psi` en
    `NaN`, igual que cuando `psi()` no tiene cortes suficientes.
    """
    base_arr = np.asarray(base, dtype=float)
    cur_arr = np.asarray(cur, dtype=float)
    base_validos = base_arr[~np.isnan(base_arr)]
    cur_validos = cur_arr[~np.isnan(cur_arr)]
    if len(base_validos) == 0 or len(cur_validos) == 0:
        return {"feature": name, "ks_stat": None, "ks_p": None, "psi": float("nan")}

    ks = sps.ks_2samp(base_validos, cur_validos)
    psi_val, bins_info = psi(base_validos, cur_validos, bins=psi_bins, return_bins=True)
    resultado: dict[str, Any] = {
        "feature": name,
        "ks_stat": float(ks.statistic),
        "ks_p": float(ks.pvalue),
        "psi": psi_val,
    }
    # Bins del PSI (antes descartados en la línea que los construye),
    # ausentes cuando el PSI salió NaN (sin cortes suficientes).
    if bins_info is not None:
        resultado.update(bins_info)
    return resultado


def _clave_orden_categoria(valor: Any) -> tuple[int, Any]:
    """Orden estable para categorías mixtas (`sorted` no debe romper
    con `float` y `str` a la vez, típico cuando una columna categórica trae
    números y texto). Números antes que texto, cada grupo en su propio
    orden natural; texto comparado como cadena para evitar el `TypeError`
    de comparar tipos distintos directamente.
    """
    if isinstance(valor, bool):
        return (1, str(valor))
    if isinstance(valor, (int, float)):
        return (0, valor)
    return (1, str(valor))


def drift_categorical(name: str, base: pd.Series, cur: pd.Series) -> dict[str, Any]:
    # Los nulos se quitan antes de calcular (no son una
    # categoría), tanto de las categorías como de los recuentos.
    base = base.dropna()
    cur = cur.dropna()
    cats = sorted(
        set(base.unique().tolist()) | set(cur.unique().tolist()),
        key=_clave_orden_categoria,
    )
    obs = np.array(
        [
            [int((base == c).sum()) for c in cats],
            [int((cur == c).sum()) for c in cats],
        ]
    )
    try:
        chi2, p, _dof, _exp = sps.chi2_contingency(obs)
        chi2_val: float | None = float(chi2)
        p_val: float | None = float(p)
    except ValueError:
        chi2_val = None
        p_val = None

    p_dist = np.clip(obs[0] / obs[0].sum(), 1e-9, None) if obs[0].sum() else None
    q_dist = np.clip(obs[1] / obs[1].sum(), 1e-9, None) if obs[1].sum() else None
    js = float(jensenshannon(p_dist, q_dist, base=2)) if p_dist is not None and q_dist is not None else None

    # Marca, no regla. Con valores en los dos lados pero ninguna
    # categoria compartida el JS sale ~1 (identificador, texto libre o una
    # fecha de un valor por fichero). El score no cambia; la fila lo dice para
    # que la interfaz y el titulo de la alerta lo enseñen.
    sin_valores_comunes = bool(
        len(base) and len(cur) and not (set(base.unique().tolist()) & set(cur.unique().tolist()))
    )

    return {
        "feature": name,
        "chi2": chi2_val,
        "p": p_val,
        "js": js,
        "sin_valores_comunes": sin_valores_comunes,
        # Recuento por categoría (antes descartado en `obs`).
        "categories": cats,
        "bin_counts_base": [int(x) for x in obs[0]],
        "bin_counts_actual": [int(x) for x in obs[1]],
    }


def _es_numerica(base: pd.Series, cur: pd.Series, *, forzar_categorica: bool) -> bool:
    if forzar_categorica:
        return False
    if not (pd.api.types.is_numeric_dtype(base) and pd.api.types.is_numeric_dtype(cur)):
        return False
    union = pd.concat([base, cur]).dropna().unique()
    return len(union) > 2


def feature_drift(
    df_base: pd.DataFrame,
    df_cur: pd.DataFrame,
    feature_cols: list[str],
    *,
    categorical: list[str] | None = None,
    psi_bins: int = 10,
) -> list[dict[str, Any]]:
    categoricas = set(categorical or [])
    filas: list[dict[str, Any]] = []
    for col in feature_cols:
        base = df_base[col]
        cur = df_cur[col]
        # Fracción de nulos del lote actual para esta variable, sin
        # estado propio (se publica en `details.features[].null_fraction`,
        # el umbral queda sin calibrar hasta tener datos reales).
        null_fraction = float(cur.isna().mean()) if len(cur) else None
        numerica = _es_numerica(base, cur, forzar_categorica=col in categoricas)
        if numerica:
            base_num = base.to_numpy(dtype=float)
            cur_num = cur.to_numpy(dtype=float)
            r = drift_numeric(col, base_num, cur_num, psi_bins=psi_bins)
            filas.append(
                {
                    "feature": col,
                    "kind": "numerica",
                    "score": r["ks_stat"],
                    "null_fraction": null_fraction,
                    **r,
                }
            )
        else:
            r = drift_categorical(col, base, cur)
            # `js` solo sale `None` cuando la variable se queda sin
            # filas validas en base o en actual (drift_categorical); antes
            # se leia como "sin deriva" (0.0), pero es "sin dato" y
            # feature_drift_score debe ignorarla al agregar, no premiarla.
            filas.append(
                {
                    "feature": col,
                    "kind": "categorica",
                    "score": r["js"],
                    "null_fraction": null_fraction,
                    **r,
                }
            )
    return filas


def feature_drift_score(rows: list[dict[str, Any]]) -> float | None:
    """Máximo de `score` entre las features: el máximo del KS (numéricas)
    o JS (categóricas) por feature. Criterio propio.

    Ignora los `None` y los `NaN` al agregar (una variable sin filas
    válidas en base o en el lote actual no debe apagar ni contaminar el
    máximo); si todas las variables se quedan sin score, `sin_datos`
    (`None`), nunca un `TypeError` ni un `NaN` propagado por `max()`.
    """
    valores = [
        r["score"]
        for r in rows
        if r.get("score") is not None and not (isinstance(r["score"], float) and math.isnan(r["score"]))
    ]
    if not valores:
        return None
    return float(max(valores))


def _drift_sin_datos(
    *,
    df_current: pd.DataFrame,
    config: DriftConfig,
    thresholds: MonitorThresholds,
    model_version: str | None,
    motivo: str,
    task: TaskSpec | None = None,
) -> EvaluationResult:
    """Resultado `sin_datos` en las tres medidas cuando `df_baseline` o
    `df_current` está vacío: evita que `psi`/`np.quantile` revienten sobre
    un array vacío (simétrico entre baseline y batch actual vacíos).:
    una regresión no tiene `confidence_drift_score`.
    """
    tipo = task.task_type if task is not None else "binary"
    claves = ("prediction_drift_score", "confidence_drift_score", "feature_drift_score")
    match tipo:
        case "regression":
            claves = ("prediction_drift_score", "feature_drift_score")
        case "binary" | "multiclass":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    measurements: list[Measurement] = []
    for clave in claves:
        low, high = thresholds.limits(clave)
        measurements.append(
            Measurement(
                metric_key=clave,
                value=None,
                threshold_low=low,
                threshold_high=high,
                state=State.sin_datos,
                motivo=motivo,
            )
        )

    n_cur = len(df_current)
    window_info = WindowInfo(
        kind="baseline_vs_batch",
        n=n_cur,
        start_seq=int(df_current[COL_SEQ].min()) if n_cur else None,
        end_seq=int(df_current[COL_SEQ].max()) if n_cur else None,
        batches=sorted(int(b) for b in df_current[COL_BATCH].unique()) if n_cur else [],
        model_version=model_version,
        complete=False,
        motivo=motivo,
    )
    details: dict[str, Any] = {"sin_equivalente": SIN_EQUIVALENTE}
    return EvaluationResult(
        monitor=MonitorType.drift,
        window=window_info,
        measurements=measurements,
        config_snapshot=config.model_dump(),
        core_version=CORE_VERSION,
        details=details,
    )


_SUELO_MOTIVO_PLANTILLA = "lote de {n} filas: por debajo de 200 la deriva no es fiable"


def _techo_por_suelo_n(
    n_cur: int, estado: State, motivo: str | None
) -> tuple[State, str | None]:
    """Suelo de `n` en deriva, medido en
    una simulación propia (0 % de falsa alarma desde
    200 filas en 60 semillas por dos fuentes). Por debajo de 20 filas la
    deriva no se evalúa (`sin_datos`); entre 20 y 199, `aviso` actúa de
    techo: si el cálculo ya daba `alerta` o `inestable`, se rebaja, porque
    con tan pocas filas esos estados son ruido de muestreo, no señal. Desde
    200 filas, sin cambios.
    """
    if n_cur < 20:
        return State.sin_datos, _SUELO_MOTIVO_PLANTILLA.format(n=n_cur)
    if n_cur < 200 and estado in (State.alerta, State.inestable):
        return State.aviso, _SUELO_MOTIVO_PLANTILLA.format(n=n_cur)
    return estado, motivo


def evaluate_drift(
    df_baseline: pd.DataFrame,
    df_current: pd.DataFrame,
    *,
    config: DriftConfig,
    thresholds: MonitorThresholds,
    feature_cols: list[str],
    batch_seq: int | None = None,
    model_version: str | None = None,
    task: TaskSpec | None = None,
) -> EvaluationResult:
    n_base = len(df_baseline)
    n_cur = len(df_current)
    if n_base == 0 or n_cur == 0:
        motivo = "baseline vacío" if n_base == 0 else "batch actual vacío"
        return _drift_sin_datos(
            df_current=df_current,
            config=config,
            thresholds=thresholds,
            model_version=model_version,
            motivo=motivo,
            task=task,
        )

    motivo_confianza: str | None = None
    tipo = task.task_type if task is not None else "binary"
    rama_regresion = rama_multiclase = False
    match tipo:
        case "regression":
            rama_regresion = True
        case "multiclass":
            rama_multiclase = True
        case "binary":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    etiqueta_deriva: dict[str, Any] | None = None
    if rama_regresion:
        # KS de la predicción continua; sin confianza ni clases.
        for marco in (df_baseline, df_current):
            if COL_PREDICTION_VALUE not in marco.columns:
                raise DatosNoValidos(
                    "a los datos del proyecto les falta el valor de la predicción "
                    f"({COL_PREDICTION_VALUE}): vuelve a subir el fichero con la columna de "
                    "predicción del mapeo"
                )
        conf = {}
        pred = prediction_drift_regresion(
            df_baseline[COL_PREDICTION_VALUE].to_numpy(dtype=float),
            df_current[COL_PREDICTION_VALUE].to_numpy(dtype=float),
            psi_bins=config.psi_bins,
        )
        if COL_LABEL_VALUE in df_baseline.columns and COL_LABEL_VALUE in df_current.columns:
            etiqueta_deriva = label_drift_regresion(
                df_baseline[COL_LABEL_VALUE].to_numpy(dtype=float),
                df_current[COL_LABEL_VALUE].to_numpy(dtype=float),
            )
    elif rama_multiclase:
        # Confianza `max` sobre `k` y predicción por Jensen-Shannon.
        exigir_columnas_clase(df_baseline, (COL_PREDICTION_CLASS,))
        exigir_columnas_clase(df_current, (COL_PREDICTION_CLASS,))
        columnas_prob = columnas_probabilidad(task.k)
        sin_prob = any(
            c not in df_baseline.columns or c not in df_current.columns for c in columnas_prob
        )
        base_p = None if sin_prob else df_baseline[columnas_prob].to_numpy(dtype=float)
        cur_p = None if sin_prob else df_current[columnas_prob].to_numpy(dtype=float)
        if base_p is None or cur_p is None or np.isnan(base_p).any() or np.isnan(cur_p).any():
            conf: dict[str, Any] = {}
            motivo_confianza = "esta versión no publica probabilidad por clase"
        else:
            conf = confidence_drift_multiclase(
                base_p,
                cur_p,
                classes=task.claves,
                bins=config.confidence_bins,
                psi_bins=config.psi_bins,
                base_pred=df_baseline[COL_PREDICTION_CLASS].to_numpy(),
                cur_pred=df_current[COL_PREDICTION_CLASS].to_numpy(),
            )
        pred = prediction_drift_multiclase(
            df_baseline[COL_PREDICTION_CLASS],
            df_current[COL_PREDICTION_CLASS],
            task.claves,
            tuple(task.claves[task.indice(f)] for f in task.favorables),
        )
    else:
        conf = confidence_drift(
            df_baseline[COL_PROB].to_numpy(dtype=float),
            df_current[COL_PROB].to_numpy(dtype=float),
            bins=config.confidence_bins,
            psi_bins=config.psi_bins,
            base_pred=df_baseline[COL_PREDICTION].to_numpy(),
            cur_pred=df_current[COL_PREDICTION].to_numpy(),
        )
        pred = prediction_drift(
            df_baseline[COL_PREDICTION].to_numpy(),
            df_current[COL_PREDICTION].to_numpy(),
        )
    features = feature_drift(
        df_baseline,
        df_current,
        feature_cols,
        # El tipo de cada variable lo decide su dtype (`_es_numerica`),
        # no una lista fija de nombres de la demo.
        categorical=None,
        psi_bins=config.psi_bins,
    )

    valores = {
        "prediction_drift_score": pred["score"],
        "confidence_drift_score": conf.get("jensen_shannon_distance"),
        "feature_drift_score": feature_drift_score(features),
    }
    if rama_regresion:
        # Una regresión no tiene confianza; la medida no se crea.
        del valores["confidence_drift_score"]

    measurements: list[Measurement] = []
    for clave, valor in valores.items():
        low, high = thresholds.limits(clave)
        if rama_regresion and clave == "prediction_drift_score" and low is None and high is None:
            # Sin valor de fábrica en regresión; espera a la línea base.
            measurements.append(
                Measurement(
                    metric_key=clave,
                    value=None,
                    state=State.sin_datos,
                    motivo=MOTIVO_UMBRAL_PENDIENTE,
                    extra={"umbral_pendiente": True, "valor_calculado": valor},
                )
            )
            continue
        # En regresión el umbral de la línea base ya incluye su margen: sin banda de aviso.
        estado, motivo_medida = classify_with_motivo(
            valor, low, high, aviso_frac=0.0 if rama_regresion else 0.10
        )
        estado_previo = estado
        estado, motivo_medida = _techo_por_suelo_n(n_cur, estado, motivo_medida)
        # Por debajo de 20 filas el suelo fuerza sin_datos: el valor
        # calculado deja de publicarse, igual que en el resto de `sin_datos`
        # del motor. Entre 20 y 199, si solo se rebaja la severidad (techo
        # de aviso), el valor calculado sigue siendo real y se publica.
        valor_publicado = None if estado == State.sin_datos and estado_previo != State.sin_datos else valor
        if valor is None and clave == "confidence_drift_score" and motivo_confianza:
            motivo_medida = motivo_confianza
        measurements.append(
            Measurement(
                metric_key=clave,
                value=valor_publicado,
                threshold_low=low,
                threshold_high=high,
                state=estado,
                motivo=motivo_medida,
            )
        )

    n_cur = len(df_current)
    motivo_ventana = f"baseline con {len(df_baseline)} filas"
    window_info = WindowInfo(
        kind="baseline_vs_batch",
        n=n_cur,
        start_seq=int(df_current[COL_SEQ].min()) if n_cur else None,
        end_seq=int(df_current[COL_SEQ].max()) if n_cur else None,
        batches=sorted(int(b) for b in df_current[COL_BATCH].unique()) if n_cur else [],
        model_version=model_version,
        complete=True,
        motivo=motivo_ventana,
    )

    details: dict[str, Any] = {
        "confidence": conf,
        "prediction": pred,
        "features": features,
        "sin_equivalente": SIN_EQUIVALENTE,
    }
    if rama_regresion:
        # Sin `confidence` (no existe), y la deriva del valor real sin umbral.
        del details["confidence"]
        if etiqueta_deriva is not None:
            details["etiqueta"] = etiqueta_deriva

    return EvaluationResult(
        monitor=MonitorType.drift,
        window=window_info,
        measurements=measurements,
        config_snapshot=config.model_dump(),
        core_version=CORE_VERSION,
        details=details,
    )
