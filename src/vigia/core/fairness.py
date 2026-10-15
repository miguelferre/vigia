"""Monitor de equidad: asignación de grupos, métricas de una ventana y
evaluación con ventanas deslizantes. Réplica exacta de
`manual_fairness` de `research/proto_oss.py` sobre el frame canónico.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from vigia.core import CORE_VERSION
from vigia.core.fairness_regresion import medidas_error_por_grupo, prediccion_por_grupo
from vigia.core.quality_multiclase import MOTIVO_SIN_CONJUNTO_FAVORABLE, exigir_columnas_clase
from vigia.core.quality_regresion import exigir_columnas_valor
from vigia.core.schema import (
    COL_BATCH,
    COL_GROUP,
    COL_LABEL,
    COL_LABEL_CLASS,
    COL_PREDICTION,
    COL_PREDICTION_CLASS,
    COL_PROB,
    COL_VERSION,
    MOTIVO_SIN_PROBABILIDAD,
    MOTIVO_SIN_RANGO,
    ColumnMapping,
    EvaluationResult,
    FairnessConfig,
    Measurement,
    MonitorThresholds,
    MonitorType,
    ProtectedKind,
    State,
    TaskSpec,
)
from vigia.core.states import classify_point_with_motivo, classify_with_motivo
from vigia.core.windows import interval_windows, last_n, window_info_for

# Z de la normal para el 95%, en Katz (escala
# log del cociente) y Newcombe (diferencia de dos proporciones, método 10 de
# Newcombe con dos intervalos de Wilson), sobre el lote completo del método
# `lote`. Valor de la constante de la normal estándar.
_Z95 = 1.959963984540054


def _katz_log_ci(
    x1: int, n1: int, x2: int, n2: int, *, z: float = _Z95
) -> tuple[float | None, float | None, float | None]:
    """CI del cociente p1/p2 (Katz, escala log). Devuelve (razon, lo, hi),
    `None` los tres si no se puede calcular (algún grupo vacío). Corrección
    de continuidad (+0,5 en los cuatro conteos) si algún conteo de éxito o
    fracaso es 0, para evitar `log(0)` o división por 0."""
    if n1 <= 0 or n2 <= 0:
        return None, None, None
    necesita_correccion = x1 == 0 or x2 == 0 or x1 == n1 or x2 == n2
    if necesita_correccion:
        x1c, n1c, x2c, n2c = x1 + 0.5, n1 + 1.0, x2 + 0.5, n2 + 1.0
    else:
        x1c, n1c, x2c, n2c = float(x1), float(n1), float(x2), float(n2)
    p1, p2 = x1c / n1c, x2c / n2c
    if p1 <= 0 or p2 <= 0:
        return (p1 / p2 if p2 else None), None, None
    razon = p1 / p2
    se = math.sqrt(1.0 / x1c - 1.0 / n1c + 1.0 / x2c - 1.0 / n2c)
    return razon, razon * math.exp(-z * se), razon * math.exp(z * se)


def _wilson_ci(x: int, n: int, *, z: float = _Z95) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    phat = x / n
    denom = 1.0 + z * z / n
    centro = (phat + z * z / (2 * n)) / denom
    margen = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return centro - margen, centro + margen


def _newcombe_diff_ci(
    x1: int, n1: int, x2: int, n2: int, *, z: float = _Z95
) -> tuple[float | None, float | None, float | None]:
    """CI de p1 - p2 (Newcombe, método 10: híbrido de dos intervalos de
    Wilson). Devuelve (diferencia, lo, hi), `None` los tres si algún grupo
    está vacío."""
    if n1 <= 0 or n2 <= 0:
        return None, None, None
    p1, p2 = x1 / n1, x2 / n2
    diff = p1 - p2
    l1, u1 = _wilson_ci(x1, n1, z=z)
    l2, u2 = _wilson_ci(x2, n2, z=z)
    if None in (l1, u1, l2, u2):
        return diff, None, None
    lo = diff - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)  # type: ignore[operator]
    hi = diff + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)  # type: ignore[operator]
    return diff, lo, hi

_SIN_GRUPOS = ("n_unpriv", "n_priv", "positives_unpriv", "positives_priv", "motivo")

# Métricas que solo necesitan la predicción: se calculan sobre la ventana
# de últimos N. Las de etiqueta (abajo) se calculan sobre el batch
# con etiqueta, sin intervalo.
_METRICAS_PREDICCION = (
    "rate_unpriv",
    "rate_priv",
    "disparate_impact",
    "fairness_value",
    "impact_score",
    "statistical_parity_difference",
)

_METRICAS_ETIQUETA = (
    "false_negative_rate_difference",
    "false_positive_rate_difference",
    "false_discovery_rate_difference",
    "false_omission_rate_difference",
    "error_rate_difference",
    "average_odds_difference",
    "average_abs_odds_difference",
    "fnr_unpriv",
    "fnr_priv",
    "fpr_unpriv",
    "fpr_priv",
    "tpr_unpriv",
    "tpr_priv",
)


def assign_groups(df: pd.DataFrame, mapping: ColumnMapping) -> pd.Series:
    """Devuelve una serie int 0 (no privilegiado) / 1 (privilegiado) / -1
    (fuera de ambos grupos) según `mapping.protected_attr_col`.
    """
    valores = df[mapping.protected_attr_col]
    grupo = pd.Series(-1, index=df.index, dtype="int64")
    if mapping.protected_kind == ProtectedKind.categorical:
        grupo = grupo.mask(valores.isin(mapping.unpriv_groups), 0)
        grupo = grupo.mask(valores.isin(mapping.priv_groups), 1)
        return grupo
    valores_num = pd.to_numeric(valores, errors="coerce")
    for lo, hi in mapping.unpriv_groups:  # type: ignore[misc]
        grupo = grupo.mask((valores_num >= lo) & (valores_num <= hi), 0)
    for lo, hi in mapping.priv_groups:  # type: ignore[misc]
        grupo = grupo.mask((valores_num >= lo) & (valores_num <= hi), 1)
    return grupo


# Mínimo de casos en el denominador de cada tasa de etiqueta de
# un grupo. Con `min_group` cumplido, un grupo de 20 filas puede traer solo 5
# casos reales favorables, y su FNR o su FPR es ruido que abría alertas en un
# lote pequeño. Por debajo, la tasa no se calcula y la medida sale `sin_datos`
# con el motivo de `_motivo_pocas_etiquetas`. Vale en los tres tipos.
MIN_CASOS_TASA_ETIQUETA = 8

# Denominadores de `_tasa_confusion` que usa cada medida de etiqueta, con el
# nombre que se da en el motivo.
_DENOMINADORES_ETIQUETA: dict[str, tuple[str, ...]] = {
    "false_negative_rate_difference": ("npos",),
    "false_positive_rate_difference": ("nneg",),
    "false_discovery_rate_difference": ("npred_pos",),
    "false_omission_rate_difference": ("npred_neg",),
    "error_rate_difference": ("nlab",),
    "average_odds_difference": ("npos", "nneg"),
    "average_abs_odds_difference": ("npos", "nneg"),
    "fnr_unpriv": ("npos",),
    "fnr_priv": ("npos",),
    "fpr_unpriv": ("nneg",),
    "fpr_priv": ("nneg",),
    "tpr_unpriv": ("npos",),
    "tpr_priv": ("npos",),
}
_NOMBRE_DENOMINADOR = {
    "npos": "casos con resultado real favorable",
    "nneg": "casos con resultado real no favorable",
    "npred_pos": "predicciones favorables con etiqueta",
    "npred_neg": "predicciones no favorables con etiqueta",
    "nlab": "filas con etiqueta",
}


def _tasa(num: int, den: int, minimo: int) -> float | None:
    return num / den if den and den >= minimo else None


def _tasa_confusion(grupo: pd.DataFrame, minimo: int = 0) -> dict[str, float | int | None]:
    etiquetados = grupo[grupo[COL_LABEL].notna()]
    positivos = etiquetados[etiquetados[COL_LABEL] == 1]
    negativos = etiquetados[etiquetados[COL_LABEL] == 0]
    tp = int((positivos[COL_PREDICTION] == 1).sum())
    fn = int((positivos[COL_PREDICTION] == 0).sum())
    fp = int((negativos[COL_PREDICTION] == 1).sum())
    tn = int((negativos[COL_PREDICTION] == 0).sum())
    npos, nneg, nlab = len(positivos), len(negativos), len(etiquetados)
    npred_pos, npred_neg = fp + tp, fn + tn
    return {
        "fnr": _tasa(fn, npos, minimo),
        "fpr": _tasa(fp, nneg, minimo),
        "tpr": _tasa(tp, npos, minimo),
        "fdr": _tasa(fp, npred_pos, minimo),
        "for_": _tasa(fn, npred_neg, minimo),
        "err": _tasa(fp + fn, nlab, minimo),
        # Conteos crudos: el método `lote` los necesita para Newcombe,
        # además de la tasa ya calculada arriba.
        "fn": fn,
        "fp": fp,
        "tp": tp,
        "tn": tn,
        "npos": npos,
        "nneg": nneg,
        "nlab": nlab,
        "npred_pos": npred_pos,
        "npred_neg": npred_neg,
        "err_num": fp + fn,
    }


# Qué fórmula de intervalo usa cada métrica de solo-predicción bajo el
# método `lote` ("katz" para un cociente, "newcombe" para una diferencia); el
# resto (rate_unpriv, rate_priv, average_odds...) no tiene fórmula en el
# contrato y se queda sin intervalo.
_CI_PREDICCION_KATZ = ("disparate_impact", "impact_score", "fairness_value")
_CI_PREDICCION_NEWCOMBE = ("statistical_parity_difference",)

# Pares (numerador, denominador) de `_tasa_confusion` para el Newcombe de
# cada diferencia de tasa de error bajo `lote`; `average_odds_difference` y
# su variante absoluta son una combinación de FPR y TPR sin fórmula propia
# en el contrato: se quedan sin intervalo (decisión propia, ver resultado.md).
_CI_ETIQUETA_NEWCOMBE = {
    "false_negative_rate_difference": ("fn", "npos"),
    "false_positive_rate_difference": ("fp", "nneg"),
    "false_discovery_rate_difference": ("fp", "npred_pos"),
    "false_omission_rate_difference": ("fn", "npred_neg"),
    "error_rate_difference": ("err_num", "nlab"),
}


def _intervalo_prediccion_lote(
    clave: str, metricas: dict[str, float | int | None]
) -> tuple[float, float] | None:
    """Intervalo de una métrica de solo-predicción bajo el método `lote`:
    Katz en escala log para el cociente (`disparate_impact`,
    `impact_score`, la misma razón sin escalar, y `fairness_value`, que es
    ese cociente x100), Newcombe para la diferencia
    (`statistical_parity_difference`)."""
    n_unpriv = int(metricas.get("n_unpriv") or 0)
    n_priv = int(metricas.get("n_priv") or 0)
    x_unpriv = int(metricas.get("positives_unpriv") or 0)
    x_priv = int(metricas.get("positives_priv") or 0)
    if clave in _CI_PREDICCION_KATZ:
        _, lo, hi = _katz_log_ci(x_unpriv, n_unpriv, x_priv, n_priv)
        if lo is None or hi is None:
            return None
        escala = 100.0 if clave == "fairness_value" else 1.0
        return lo * escala, hi * escala
    if clave in _CI_PREDICCION_NEWCOMBE:
        _, lo, hi = _newcombe_diff_ci(x_unpriv, n_unpriv, x_priv, n_priv)
        if lo is None or hi is None:
            return None
        return lo, hi
    return None


def _intervalos_etiqueta_lote(
    c0: dict[str, float | int | None], c1: dict[str, float | int | None]
) -> dict[str, tuple[float, float] | None]:
    """Intervalo Newcombe de cada diferencia de tasa de error del método
    `lote`, a partir de los conteos crudos de cada grupo
    (`_tasa_confusion`, grupo 0 = no privilegiado, grupo 1 = privilegiado)."""
    salida: dict[str, tuple[float, float] | None] = {}
    for clave, (num_key, den_key) in _CI_ETIQUETA_NEWCOMBE.items():
        n0, n1 = c0.get(den_key), c1.get(den_key)
        x0, x1 = c0.get(num_key), c1.get(num_key)
        if None in (x0, n0, x1, n1) or not n0 or not n1:
            salida[clave] = None
            continue
        _, lo, hi = _newcombe_diff_ci(int(x0), int(n0), int(x1), int(n1))  # type: ignore[arg-type]
        salida[clave] = None if lo is None or hi is None else (lo, hi)
    return salida


def _motivo_pocas_etiquetas(
    clave: str, c0: dict[str, float | int | None], c1: dict[str, float | int | None], minimo: int
) -> str | None:
    """Motivo de una medida de etiqueta sin valor por `MIN_CASOS_TASA_ETIQUETA`,
    o `None` si no es esa la causa."""
    partes: list[str] = []
    for den in _DENOMINADORES_ETIQUETA.get(clave, ()):
        for nombre_grupo, c in (("grupo supervisado", c0), ("grupo de referencia", c1)):
            n = int(c.get(den) or 0)
            if 0 < n < minimo:
                partes.append(f"{n} {_NOMBRE_DENOMINADOR[den]} en el {nombre_grupo}")
    if not partes:
        return None
    return f"pocos casos para esta tasa: {'; '.join(partes)} (se piden al menos {minimo})"


def fairness_metrics(
    df_window: pd.DataFrame, *, min_group: int = 20, min_casos_tasa: int = MIN_CASOS_TASA_ETIQUETA
) -> dict[str, float | int | None]:
    """Réplica de `manual_fairness` (research/proto_oss.py) sobre
    `group_code` 0 (no privilegiado) y 1 (privilegiado) del frame canónico.
    Una tasa de etiqueta de un grupo con menos de `min_casos_tasa` casos en
    su denominador no se calcula.
    """
    g0 = df_window[df_window[COL_GROUP] == 0]
    g1 = df_window[df_window[COL_GROUP] == 1]
    n0, n1 = len(g0), len(g1)

    resultado: dict[str, float | int | None] = {
        "n_unpriv": n0,
        "n_priv": n1,
        "positives_unpriv": int((g0[COL_PREDICTION] == 1).sum()) if n0 else 0,
        "positives_priv": int((g1[COL_PREDICTION] == 1).sum()) if n1 else 0,
        "rate_unpriv": None,
        "rate_priv": None,
        "disparate_impact": None,
        "fairness_value": None,
        "impact_score": None,
        "statistical_parity_difference": None,
        "false_negative_rate_difference": None,
        "false_positive_rate_difference": None,
        "false_discovery_rate_difference": None,
        "false_omission_rate_difference": None,
        "error_rate_difference": None,
        "average_odds_difference": None,
        "average_abs_odds_difference": None,
        "fnr_unpriv": None,
        "fnr_priv": None,
        "fpr_unpriv": None,
        "fpr_priv": None,
        "tpr_unpriv": None,
        "tpr_priv": None,
    }

    if n0 < min_group or n1 < min_group:
        # Sin `protected_attr_col` configurado, `assign_groups`
        # (via `to_canonical`, capa de ingesta) deja `group_code=-1` en toda
        # fila, así que aquí no llega nadie a los grupos 0 ni 1: n0 == n1 ==
        # 0. Es distinto de un grupo genuinamente pequeño (n0 y/o n1 > 0 pero
        # por debajo de min_group), que sigue con el motivo de siempre.
        if n0 == 0 and n1 == 0:
            resultado["motivo"] = (
                "no hay atributo protegido configurado: defínelo en el modelo "
                "para vigilar la equidad"
            )
        else:
            resultado["motivo"] = (
                f"grupo insuficiente: n_unpriv={n0}, n_priv={n1}, min_group={min_group}"
            )
        return resultado

    rate0 = float(g0[COL_PREDICTION].mean())
    rate1 = float(g1[COL_PREDICTION].mean())
    resultado["rate_unpriv"] = rate0
    resultado["rate_priv"] = rate1
    di = rate0 / rate1 if rate1 else None
    resultado["disparate_impact"] = di
    resultado["fairness_value"] = di * 100 if di is not None else None
    resultado["impact_score"] = di
    resultado["statistical_parity_difference"] = rate0 - rate1

    if not df_window[COL_LABEL].notna().any():
        return resultado

    c0 = _tasa_confusion(g0, min_casos_tasa)
    c1 = _tasa_confusion(g1, min_casos_tasa)
    resultado["fnr_unpriv"], resultado["fnr_priv"] = c0["fnr"], c1["fnr"]
    resultado["fpr_unpriv"], resultado["fpr_priv"] = c0["fpr"], c1["fpr"]
    resultado["tpr_unpriv"], resultado["tpr_priv"] = c0["tpr"], c1["tpr"]

    def diff(clave: str) -> float | None:
        a, b = c0[clave], c1[clave]
        return (a - b) if a is not None and b is not None else None  # type: ignore[operator]

    resultado["false_negative_rate_difference"] = diff("fnr")
    resultado["false_positive_rate_difference"] = diff("fpr")
    resultado["false_discovery_rate_difference"] = diff("fdr")
    resultado["false_omission_rate_difference"] = diff("for_")
    resultado["error_rate_difference"] = diff("err")

    fpr0, fpr1, tpr0, tpr1 = c0["fpr"], c1["fpr"], c0["tpr"], c1["tpr"]
    if None not in (fpr0, fpr1, tpr0, tpr1):
        resultado["average_odds_difference"] = 0.5 * ((fpr0 - fpr1) + (tpr0 - tpr1))  # type: ignore[operator]
        resultado["average_abs_odds_difference"] = 0.5 * (
            abs(fpr0 - fpr1) + abs(tpr0 - tpr1)  # type: ignore[operator]
        )

    return resultado


def _favorable_probability(
    ventana: pd.DataFrame, *, min_group: int
) -> tuple[dict[str, Any] | None, str | None]:
    """Distribución de `prob_favorable` por grupo para el violín de equidad
    (análoga a `_confidence_by_class`
    de `drift.py`). Devuelve (bloque, motivo): bloque es `None` cuando la
    versión no publica probabilidad (`COL_PROB` entero `NaN` en la ventana),
    con `motivo` explicando el porqué.
    """
    probs = ventana[COL_PROB]
    if not probs.notna().any():
        return None, "esta versión no publica probabilidad favorable (prob_favorable)"

    con_prob = ventana[probs.notna()]
    pred = con_prob[COL_PREDICTION]
    prob_no_favorable = con_prob.loc[pred == 0, COL_PROB].astype(float)
    prob_favorable = con_prob.loc[pred == 1, COL_PROB].astype(float)

    # Sin campo de umbral en ColumnMapping,
    # se estima como el punto medio entre la mayor probabilidad con
    # prediccion no favorable y la menor con prediccion favorable; 0,5 si
    # las dos clases se solapan (el modelo no es monotono en prob_favorable
    # respecto a la prediccion) o falta alguna de las dos.
    if (
        len(prob_no_favorable) == 0
        or len(prob_favorable) == 0
        or prob_no_favorable.max() >= prob_favorable.min()
    ):
        threshold = 0.5
        threshold_motivo = (
            "0,5 por defecto: la ventana no tiene un punto de corte único "
            "entre predicción 0 y 1"
        )
    else:
        maximo_no_favorable = float(prob_no_favorable.max())
        minimo_favorable = float(prob_favorable.min())
        threshold = (maximo_no_favorable + minimo_favorable) / 2
        threshold_motivo = (
            f"estimado: punto medio entre {maximo_no_favorable:.2f} (máximo con "
            f"predicción 0) y {minimo_favorable:.2f} (mínimo con predicción 1)"
        )

    bin_edges = np.linspace(0.0, 1.0, 21)
    by_group: dict[str, Any] = {}
    for clave, codigo in (("unpriv", 0), ("priv", 1)):
        grupo = con_prob[con_prob[COL_GROUP] == codigo]
        n = len(grupo)
        if n < min_group:
            by_group[clave] = {
                "motivo": f"grupo insuficiente: n={n}, min_group={min_group}"
            }
            continue
        valores = grupo[COL_PROB].astype(float).to_numpy()
        hist, _ = np.histogram(valores, bins=bin_edges)
        by_group[clave] = {
            "bin_counts": [int(x) for x in hist],
            "n": n,
            "median": float(np.median(valores)),
            "rate_above_threshold": float((valores >= threshold).mean()),
        }

    return {
        "bin_edges": [float(x) for x in bin_edges],
        "threshold": float(threshold),
        "threshold_motivo": threshold_motivo,
        "by_group": by_group,
    }, None


def _historia_efectiva(
    df_history: pd.DataFrame, batch_seq: int, model_version: str | None
) -> pd.DataFrame:
    """Filas hasta `batch_seq` (inclusive) de la versión indicada: reevaluar
    un batch antiguo no ve el futuro.
    """
    historia = df_history
    if model_version is not None:
        historia = historia[historia[COL_VERSION] == model_version]
    return historia[historia[COL_BATCH] <= batch_seq]


def _ventana_etiqueta(
    historia_efectiva: pd.DataFrame, batch_seq: int, label_min_records: int
) -> tuple[pd.DataFrame, str, bool, str | None]:
    """Filas con etiqueta del batch evaluado; si no llegan a
    `label_min_records`, se acumulan batches anteriores de más reciente a
    más antiguo. Devuelve (ventana, kind, completa, motivo).
    """
    etiquetada = historia_efectiva[historia_efectiva[COL_LABEL].notna()]
    if len(etiquetada) == 0:
        return etiquetada, "batch", False, "sin feedback con etiqueta"

    del_batch = etiquetada[etiquetada[COL_BATCH] == batch_seq]
    partes = [del_batch]
    total = len(del_batch)
    kind = "batch"
    if total < label_min_records:
        batches_previos = sorted(
            (int(b) for b in etiquetada[COL_BATCH].unique() if b < batch_seq), reverse=True
        )
        for b in batches_previos:
            if total >= label_min_records:
                break
            fila_b = etiquetada[etiquetada[COL_BATCH] == b]
            partes.append(fila_b)
            total += len(fila_b)
            kind = "acumulado"
    ventana = pd.concat(partes) if len(partes) > 1 else partes[0]
    completa = len(ventana) >= label_min_records
    motivo = None
    if not completa:
        motivo = f"solo hay {len(ventana)} filas con etiqueta, se pedian {label_min_records}"
    return ventana, kind, completa, motivo


def _group_code_de_clave(clave: str) -> str | None:
    """`group_code` (`core/schema.py:237`) de una métrica por el
    sufijo de su nombre: las variantes propias de un grupo (`rate_unpriv`,
    `fnr_priv`...) llevan `"unpriv"`/`"priv"`; las de comparación entre los
    dos grupos (`disparate_impact`, `false_negative_rate_difference`...) se
    quedan en `None`, como hasta ahora (de eso depende
    `test_titulo_legible_con_etiqueta_de_metrica_y_grupo_del_mapeo`: FNRD no
    tiene grupo propio, así que el título usa la etiqueta del mapeo)."""
    if clave.endswith("_unpriv"):
        return "unpriv"
    if clave.endswith("_priv"):
        return "priv"
    return None


def tabla_por_clase(
    ventana: pd.DataFrame, task: TaskSpec, min_group: int
) -> dict[str, dict[str, Any]]:
    """Tabla informativa (sin umbral, sin alerta): para cada clase, la tasa
    con que se predice en cada grupo, la razón entre grupos y el `n` de cada
    celda. Una celda de un grupo con menos de `min_group` filas no da tasa."""
    exigir_columnas_clase(ventana, (COL_PREDICTION_CLASS,))
    claves = task.claves
    grupos = {"unpriv": ventana[ventana[COL_GROUP] == 0], "priv": ventana[ventana[COL_GROUP] == 1]}
    tabla: dict[str, dict[str, Any]] = {}
    for clase in claves:
        fila: dict[str, Any] = {}
        tasas: dict[str, float | None] = {}
        for nombre, g in grupos.items():
            n = len(g)
            n_clase = int((g[COL_PREDICTION_CLASS] == clase).sum()) if n else 0
            tasa = (n_clase / n) if n >= min_group else None
            tasas[nombre] = tasa
            fila[nombre] = {"n": n, "n_clase": n_clase, "tasa": tasa}
        t0, t1 = tasas["unpriv"], tasas["priv"]
        fila["razon"] = (t0 / t1) if t0 is not None and t1 else None
        tabla[clase] = fila
    return tabla


def _f1_macro_grupo(g: pd.DataFrame) -> float:
    from sklearn.metrics import f1_score

    y = g[COL_LABEL_CLASS].astype(str).to_numpy()
    yhat = g[COL_PREDICTION_CLASS].astype(str).to_numpy()
    labels = sorted(set(y.tolist()) | set(yhat.tolist()))
    return float(f1_score(y, yhat, labels=labels, average="macro", zero_division=0))


def _evaluate_fairness_sin_conjunto(
    historia_efectiva: pd.DataFrame,
    *,
    batch_seq: int,
    config: FairnessConfig,
    thresholds: MonitorThresholds,
    model_version: str | None,
    interval_method: str,
    task: TaskSpec,
) -> EvaluationResult:
    """Sin conjunto favorable, la equidad calcula exactitud y F1 macro por
    grupo, con su diferencia, su razón y el `n` de cada grupo. Son medidas sin
    umbral; las que leen la pertenencia al conjunto (`label_rate`,
    `prediction_rate`, las diez de umbral...) dan `sin_datos` con el motivo,
    nunca un 0. El estado del monitor sale `sin_datos` con ese motivo."""
    exigir_columnas_clase(historia_efectiva, (COL_LABEL_CLASS, COL_PREDICTION_CLASS))
    motivo = MOTIVO_SIN_CONJUNTO_FAVORABLE
    if interval_method == "lote":
        ventana_label = historia_efectiva[historia_efectiva[COL_BATCH] == batch_seq]
        ventana_label = ventana_label[ventana_label[COL_LABEL].notna()]
        kind_label = "batch"
        completa_label = len(ventana_label) > 0
        motivo_ventana_label = None if completa_label else "el lote no tiene filas con etiqueta"
    else:
        ventana_label, kind_label, completa_label, motivo_ventana_label = _ventana_etiqueta(
            historia_efectiva, batch_seq, config.label_min_records
        )

    measurements: list[Measurement] = []
    for clave in (*_METRICAS_PREDICCION, *_METRICAS_ETIQUETA):
        low, high = thresholds.limits(clave)
        measurements.append(
            Measurement(
                metric_key=clave,
                value=None,
                threshold_low=low,
                threshold_high=high,
                state=State.sin_datos,
                group_code=_group_code_de_clave(clave),
                motivo=motivo,
            )
        )

    por_grupo: dict[str, dict[str, Any]] = {}
    for nombre, codigo in (("unpriv", 0), ("priv", 1)):
        g = ventana_label[ventana_label[COL_GROUP] == codigo] if len(ventana_label) else ventana_label
        n = len(g)
        if n >= config.min_group:
            exactitud: float | None = float(
                (g[COL_PREDICTION_CLASS].astype(str) == g[COL_LABEL_CLASS].astype(str)).mean()
            )
            f1: float | None = _f1_macro_grupo(g)
            motivo_grupo = None
        else:
            exactitud = f1 = None
            motivo_grupo = f"grupo insuficiente: n={n}, min_group={config.min_group}"
        por_grupo[nombre] = {"n": n, "accuracy": exactitud, "f1_measure": f1, "motivo": motivo_grupo}

    for clave in ("accuracy", "f1_measure"):
        for nombre, datos in por_grupo.items():
            valor = datos[clave]
            measurements.append(
                Measurement(
                    metric_key=clave,
                    value=valor,
                    state=State.ok if valor is not None else State.sin_datos,
                    group_code=nombre,
                    motivo=None if valor is not None else datos["motivo"],
                    extra={"window": kind_label, "n": datos["n"]},
                )
            )
        a, b = por_grupo["unpriv"][clave], por_grupo["priv"][clave]
        diferencia = (a - b) if a is not None and b is not None else None
        razon = (a / b) if a is not None and b else None
        motivo_cmp = None if diferencia is not None else "grupo insuficiente en alguno de los dos"
        for sufijo, valor in (("difference", diferencia), ("ratio", razon)):
            measurements.append(
                Measurement(
                    metric_key=f"{clave}_{sufijo}",
                    value=valor,
                    state=State.ok if valor is not None else State.sin_datos,
                    motivo=None if valor is not None else motivo_cmp,
                    extra={"window": kind_label},
                )
            )
    for nombre, datos in por_grupo.items():
        measurements.append(
            Measurement(
                metric_key="n",
                value=float(datos["n"]),
                state=State.ok,
                group_code=nombre,
                extra={"window": kind_label},
            )
        )

    window_info = window_info_for(
        ventana_label,
        kind=kind_label,  # type: ignore[arg-type]
        requested_n=config.label_min_records if interval_method == "ventanas" else None,
        model_version=model_version,
        complete=completa_label,
        motivo=motivo_ventana_label,
    )
    details: dict[str, Any] = {
        "interval_method": interval_method,
        "motivo": motivo,
        "sin_conjunto_favorable": True,
        "por_grupo": por_grupo,
        "counts_label": {"n_unpriv": por_grupo["unpriv"]["n"], "n_priv": por_grupo["priv"]["n"]},
        "label_window": window_info.model_dump(),
    }
    return EvaluationResult(
        monitor=MonitorType.fairness,
        window=window_info,
        measurements=measurements,
        config_snapshot=config.model_dump(),
        core_version=CORE_VERSION,
        details=details,
    )


def _evaluate_fairness_regresion_sin_rango(
    historia_efectiva: pd.DataFrame,
    *,
    batch_seq: int,
    config: FairnessConfig,
    thresholds: MonitorThresholds,
    model_version: str | None,
    interval_method: str,
    task: TaskSpec,
) -> EvaluationResult:
    """Sin rango favorable la equidad publica solo las medidas de
    error por grupo, que sí llevan umbral y deciden el estado. Las 19 medidas que
    leen la pertenencia dan `sin_datos` con el motivo, nunca un 0."""
    exigir_columnas_valor(historia_efectiva)
    if interval_method == "lote":
        ventana = historia_efectiva[historia_efectiva[COL_BATCH] == batch_seq]
        window_kind = "batch"
        ventana_completa = len(ventana) > 0
        motivo_ventana = None if ventana_completa else "el lote no tiene filas"
        ventana_label = ventana[ventana[COL_LABEL].notna()]
        kind_label = "batch"
        completa_label = len(ventana_label) > 0
        motivo_ventana_label = None if completa_label else "el lote no tiene filas con etiqueta"
    else:
        ventana, info_base = last_n(
            historia_efectiva, config.min_records, model_version=model_version
        )
        window_kind = "ultimos_n"
        ventana_completa = info_base.complete
        motivo_ventana = info_base.motivo
        ventana_label, kind_label, completa_label, motivo_ventana_label = _ventana_etiqueta(
            historia_efectiva, batch_seq, config.label_min_records
        )

    measurements: list[Measurement] = []
    for clave in (*_METRICAS_PREDICCION, *_METRICAS_ETIQUETA):
        low, high = thresholds.limits(clave)
        measurements.append(
            Measurement(
                metric_key=clave,
                value=None,
                threshold_low=low,
                threshold_high=high,
                state=State.sin_datos,
                group_code=_group_code_de_clave(clave),
                motivo=MOTIVO_SIN_RANGO,
            )
        )
    medidas_error, detalle_error = medidas_error_por_grupo(
        ventana_label,
        thresholds=thresholds,
        min_group=config.min_group,
        interval_method=interval_method,
        kind_label=kind_label,
        n_filas_lote=len(ventana),
        min_filas_lote=config.min_records,
    )
    measurements.extend(medidas_error)

    n_unpriv = int((ventana[COL_GROUP] == 0).sum()) if len(ventana) else 0
    n_priv = int((ventana[COL_GROUP] == 1).sum()) if len(ventana) else 0
    window_info = window_info_for(
        ventana,
        kind=window_kind,  # type: ignore[arg-type]
        requested_n=config.min_records if interval_method == "ventanas" else None,
        model_version=model_version,
        complete=ventana_completa,
        motivo=motivo_ventana,
    )
    label_window_info = window_info_for(
        ventana_label,
        kind=kind_label,  # type: ignore[arg-type]
        requested_n=config.label_min_records if interval_method == "ventanas" else None,
        model_version=model_version,
        complete=completa_label,
        motivo=motivo_ventana_label,
    )
    details: dict[str, Any] = {
        "interval_method": interval_method,
        "motivo": MOTIVO_SIN_RANGO,
        "sin_rango_favorable": True,
        "counts": {"n_unpriv": n_unpriv, "n_priv": n_priv},
        "counts_label": {
            "n_unpriv": detalle_error["unpriv"]["n"],
            "n_priv": detalle_error["priv"]["n"],
        },
        "favorable_probability_motivo": MOTIVO_SIN_PROBABILIDAD,
        "error_por_grupo": detalle_error,
        "prediccion_por_grupo": prediccion_por_grupo(ventana, min_group=config.min_group),
        "rangos_favorables": [],
        "label_window": label_window_info.model_dump(),
    }
    return EvaluationResult(
        monitor=MonitorType.fairness,
        window=window_info,
        measurements=measurements,
        config_snapshot=config.model_dump(),
        core_version=CORE_VERSION,
        details=details,
    )


def evaluate_fairness(
    df_history: pd.DataFrame,
    *,
    batch_seq: int,
    config: FairnessConfig,
    thresholds: MonitorThresholds,
    model_version: str | None = None,
    interval_method: str = "ventanas",
    task: TaskSpec | None = None,
) -> EvaluationResult:
    """`interval_method`: `"ventanas"` (la de
    siempre, sin cambios, ni en su `config_snapshot`) o `"lote"`, en la que
    el valor y su intervalo salen del lote completo (Katz/Newcombe) y el
    estado lo decide `classify_point_with_motivo` en vez de
    `classify_with_motivo`. `details["interval_method"]` lo nombra siempre,
    para que la pantalla lo enseñe en la cabecera de la ventana."""
    if interval_method not in ("ventanas", "lote"):
        raise ValueError(
            f"interval_method desconocido: {interval_method!r} (se esperaba "
            "'ventanas' o 'lote')"
        )

    historia_efectiva = _historia_efectiva(df_history, batch_seq, model_version)

    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "binary" | "multiclass" | "regression":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    if task is not None and task.sin_conjunto_favorable:
        return _evaluate_fairness_sin_conjunto(
            historia_efectiva,
            batch_seq=batch_seq,
            config=config,
            thresholds=thresholds,
            model_version=model_version,
            interval_method=interval_method,
            task=task,
        )
    if task is not None and task.sin_rango_favorable:
        return _evaluate_fairness_regresion_sin_rango(
            historia_efectiva,
            batch_seq=batch_seq,
            config=config,
            thresholds=thresholds,
            model_version=model_version,
            interval_method=interval_method,
            task=task,
        )

    if interval_method == "lote":
        ventana = historia_efectiva[historia_efectiva[COL_BATCH] == batch_seq]
        window_kind = "batch"
        ventana_completa = len(ventana) > 0
        motivo_ventana = None if ventana_completa else "el lote no tiene filas"
    else:
        ventana, info_base = last_n(
            historia_efectiva, config.min_records, model_version=model_version
        )
        window_kind = "ultimos_n"
        ventana_completa = info_base.complete
        motivo_ventana = info_base.motivo

    metricas = fairness_metrics(ventana, min_group=config.min_group)
    motivo_grupo = metricas.get("motivo")

    valores_por_metrica: dict[str, list[float]] = {}
    ventanas_informativas = 0
    ventanas_excluidas = 0
    ventanas_intervalo: list[pd.DataFrame] = []
    if interval_method == "ventanas":
        n_ventana = len(ventana) if len(ventana) else config.min_records
        ventanas_intervalo = interval_windows(
            historia_efectiva,
            batch_seq,
            n_ventana,
            config.window_step,
            model_version=model_version,
            max_windows=config.interval_windows_max,
        )

        # Una ventana deslizante con menos de min_positives resultados
        # favorables en algun grupo no es informativa (no mide la metrica, no
        # informa de inestabilidad) y se excluye del intervalo.
        for vent in ventanas_intervalo:
            vm = fairness_metrics(vent, min_group=config.min_group)
            pu_vent = vm.get("positives_unpriv") or 0
            pp_vent = vm.get("positives_priv") or 0
            if pu_vent < config.min_positives or pp_vent < config.min_positives:
                ventanas_excluidas += 1
                continue
            ventanas_informativas += 1
            for clave, valor in vm.items():
                if clave in _SIN_GRUPOS:
                    continue
                if isinstance(valor, (int, float)) and valor is not None:
                    valores_por_metrica.setdefault(clave, []).append(float(valor))

    # El valor puntual se publica siempre que min_group se cumpla; si
    # algun grupo tiene menos de min_positives favorables, se marca fragil
    # sin cambiar el estado calculado por classify.
    positives_unpriv = metricas.get("positives_unpriv") or 0
    positives_priv = metricas.get("positives_priv") or 0
    fragil: bool | None = None
    motivo_fragil: str | None = None
    if metricas["fairness_value"] is not None:
        insuficiente_unpriv = positives_unpriv < config.min_positives
        insuficiente_priv = positives_priv < config.min_positives
        fragil = insuficiente_unpriv or insuficiente_priv
        if fragil:
            partes = []
            if insuficiente_unpriv:
                partes.append(
                    f"valor frágil: solo {positives_unpriv} resultados favorables en el "
                    f"grupo supervisado (mínimo {config.min_positives})"
                )
            if insuficiente_priv:
                partes.append(
                    f"valor frágil: solo {positives_priv} resultados favorables en el "
                    f"grupo de referencia (mínimo {config.min_positives})"
                )
            motivo_fragil = "; ".join(partes)

    measurements: list[Measurement] = []
    for clave in _METRICAS_PREDICCION:
        valor = metricas[clave]
        low, high = thresholds.limits(clave)
        if interval_method == "lote":
            intervalo = _intervalo_prediccion_lote(clave, metricas)
        else:
            vals = valores_por_metrica.get(clave, [])
            intervalo = (min(vals), max(vals)) if vals else None
        if low is None and high is None:
            estado = State.ok if valor is not None else State.sin_datos
            motivo = motivo_grupo if valor is None else None
        else:
            if interval_method == "lote":
                estado, motivo = classify_point_with_motivo(
                    valor,
                    low,
                    high,
                    interval=intervalo,
                    n_filas_lote=len(ventana),
                    min_filas_lote=config.min_records,
                )
            else:
                estado, motivo = classify_with_motivo(valor, low, high, interval=intervalo)
            if valor is None and motivo_grupo:
                motivo = motivo_grupo
        extra: dict[str, Any] = {"window": window_kind}
        if fragil is not None:
            extra["fragil"] = fragil
            extra["positives_unpriv"] = positives_unpriv
            extra["positives_priv"] = positives_priv
            if motivo_fragil:
                extra["motivo"] = motivo_fragil
        measurements.append(
            Measurement(
                metric_key=clave,
                value=valor,
                interval_low=intervalo[0] if intervalo else None,
                interval_high=intervalo[1] if intervalo else None,
                threshold_low=low,
                threshold_high=high,
                state=estado,
                group_code=_group_code_de_clave(clave),
                motivo=motivo,
                extra=extra,
            )
        )

    # -- ventana de etiqueta (`lote` usa las
    # filas con etiqueta del lote completo, sin acumular batches anteriores) --
    if interval_method == "lote":
        ventana_label = ventana[ventana[COL_LABEL].notna()]
        kind_label = "batch"
        completa_label = len(ventana_label) > 0
        motivo_ventana_label = None if completa_label else "el lote no tiene filas con etiqueta"
    else:
        ventana_label, kind_label, completa_label, motivo_ventana_label = _ventana_etiqueta(
            historia_efectiva, batch_seq, config.label_min_records
        )
    n_unpriv_label = int((ventana_label[COL_GROUP] == 0).sum()) if len(ventana_label) else 0
    n_priv_label = int((ventana_label[COL_GROUP] == 1).sum()) if len(ventana_label) else 0

    intervalos_label: dict[str, tuple[float, float] | None] = {}
    conteos_label: tuple[dict[str, float | int | None], dict[str, float | int | None]] | None = None
    if completa_label:
        metricas_label = fairness_metrics(ventana_label, min_group=config.min_group)
        motivo_label_final = metricas_label.get("motivo")
        g0_label = ventana_label[ventana_label[COL_GROUP] == 0]
        g1_label = ventana_label[ventana_label[COL_GROUP] == 1]
        conteos_label = (_tasa_confusion(g0_label), _tasa_confusion(g1_label))
        if interval_method == "lote":
            intervalos_label = _intervalos_etiqueta_lote(*conteos_label)
    else:
        metricas_label = dict.fromkeys(_METRICAS_ETIQUETA)
        motivo_label_final = motivo_ventana_label

    for clave in _METRICAS_ETIQUETA:
        valor = metricas_label.get(clave)
        low, high = thresholds.limits(clave)
        # Una tasa sin valor no lleva intervalo, y su motivo dice qué casos faltan.
        intervalo = intervalos_label.get(clave) if valor is not None else None
        motivo_medida = motivo_label_final
        if valor is None and motivo_medida is None and conteos_label is not None:
            motivo_medida = _motivo_pocas_etiquetas(clave, *conteos_label, MIN_CASOS_TASA_ETIQUETA)
        if low is None and high is None:
            estado = State.ok if valor is not None else State.sin_datos
            motivo = None if valor is not None else motivo_medida
        else:
            if interval_method == "lote":
                # A2: el tamaño es el del lote completo, no el de sus filas con etiqueta.
                estado, motivo = classify_point_with_motivo(
                    valor,
                    low,
                    high,
                    interval=intervalo,
                    n_filas_lote=len(ventana),
                    min_filas_lote=config.min_records,
                )
            else:
                estado, motivo = classify_with_motivo(valor, low, high, interval=intervalo)
            if valor is None and motivo_medida:
                motivo = motivo_medida
        measurements.append(
            Measurement(
                metric_key=clave,
                value=valor,
                interval_low=intervalo[0] if intervalo else None,
                interval_high=intervalo[1] if intervalo else None,
                threshold_low=low,
                threshold_high=high,
                state=estado,
                group_code=_group_code_de_clave(clave),
                motivo=motivo,
                extra={"window": kind_label, "n": len(ventana_label)},
            )
        )

    details: dict[str, Any] = {
        "interval_method": interval_method,
        "counts": {
            "n_unpriv": metricas["n_unpriv"],
            "n_priv": metricas["n_priv"],
            "positives_unpriv": metricas["positives_unpriv"],
            "positives_priv": metricas["positives_priv"],
        },
        "counts_label": {"n_unpriv": n_unpriv_label, "n_priv": n_priv_label},
        "interval_windows": ventanas_informativas,
        "interval_windows_total": len(ventanas_intervalo),
        "interval_windows_excluidas": ventanas_excluidas,
        "fairness_value_windows": valores_por_metrica.get("fairness_value", []),
    }
    if motivo_grupo:
        details["motivo"] = motivo_grupo

    match tipo:
        case "binary" | "multiclass":
            favorable_probability, motivo_favorable_probability = _favorable_probability(
                ventana, min_group=config.min_group
            )
            if favorable_probability is not None:
                details["favorable_probability"] = favorable_probability
            else:
                details["favorable_probability_motivo"] = motivo_favorable_probability
        case "regression":
            # Una regresión no publica probabilidad.
            details["favorable_probability_motivo"] = MOTIVO_SIN_PROBABILIDAD

    window_info = window_info_for(
        ventana,
        kind=window_kind,  # type: ignore[arg-type]
        requested_n=config.min_records if interval_method == "ventanas" else None,
        model_version=model_version,
        complete=ventana_completa,
        motivo=motivo_ventana,
        interval_windows=ventanas_informativas if interval_method == "ventanas" else None,
    )
    label_window_info = window_info_for(
        ventana_label,
        kind=kind_label,  # type: ignore[arg-type]
        requested_n=config.label_min_records if interval_method == "ventanas" else None,
        model_version=model_version,
        complete=completa_label,
        motivo=motivo_ventana_label,
    )
    details["label_window"] = label_window_info.model_dump()
    match tipo:
        case "multiclass":
            # Tabla informativa por clase, sin medidas con umbral ni alertas.
            details["fairness"] = {
                "por_clase": tabla_por_clase(ventana, task, config.min_group)  # type: ignore[arg-type]
            }
        case "regression":
            # Con rango, además de la pertenencia (arriba, con los
            # umbrales de hoy), el error por grupo y la predicción por grupo.
            exigir_columnas_valor(historia_efectiva)
            medidas_error, detalle_error = medidas_error_por_grupo(
                ventana_label,
                thresholds=thresholds,
                min_group=config.min_group,
                interval_method=interval_method,
                kind_label=kind_label,
                n_filas_lote=len(ventana),
                min_filas_lote=config.min_records,
            )
            measurements.extend(medidas_error)
            details["error_por_grupo"] = detalle_error
            details["prediccion_por_grupo"] = prediccion_por_grupo(
                ventana, min_group=config.min_group
            )
            details["rangos_favorables"] = [
                [bajo, alto] for bajo, alto in task.rangos_favorables  # type: ignore[union-attr]
            ]
        case "binary":
            pass

    return EvaluationResult(
        monitor=MonitorType.fairness,
        window=window_info,
        measurements=measurements,
        config_snapshot=config.model_dump(),
        core_version=CORE_VERSION,
        details=details,
    )
