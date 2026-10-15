"""Monitor de calidad: métricas de clasificación sobre feedback etiquetado y
evaluación con acumulación de batches. Réplica de `quality` de
`research/proto_oss.py` sobre el frame canónico, con las claves de métrica
del glosario.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)

from vigia.core import CORE_VERSION
from vigia.core.quality_multiclase import (
    CLAVES_POR_CLASE,
    MOTIVO_SIN_CONJUNTO_FAVORABLE,
    MOTIVO_UMBRAL_PENDIENTE,
    clases_desconocidas,
    metricas_multiclase,
)
from vigia.core.quality_regresion import (
    MOTIVO_SIN_PARES,
    detalles_regresion,
    metricas_regresion,
)
from vigia.core.schema import (
    CLAVES_CALIDAD_REGRESION,
    CLAVES_CALIDAD_REGRESION_DETALLE,
    COL_BATCH,
    COL_LABEL,
    COL_PREDICTION,
    COL_PROB,
    COL_SEQ,
    COL_VERSION,
    DatosNoValidos,
    EvaluationResult,
    Measurement,
    MonitorThresholds,
    MonitorType,
    QualityConfig,
    State,
    TaskSpec,
    Threshold,
    ThresholdKind,
    WindowInfo,
    grupo_clase,
)
from vigia.core.states import classify_with_motivo, decimales_para
from vigia.core.thresholds import DEFAULT_QUALITY_THRESHOLDS

# Claves publicadas en `quality_metrics` que tienen umbral y por tanto se
# clasifican con `classify`; el resto (n, tp, fp, fn, tn, label_rate,
# prediction_rate) se publican como medida `ok` sin umbral cuando hay valor.
_CLAVES_UMBRAL = (
    "accuracy",
    "area_under_roc",
    "area_under_pr",
    "true_positive_rate",
    "false_positive_rate",
    "precision",
    "recall",
    "f1_measure",
    "log_loss",
    "matthews_correlation_coefficient",
    "gini_coefficient",
    "brier_score",
)


def validar_probabilidad(
    df_labeled: pd.DataFrame, *, columna_original: str | None = None
) -> None:
    """Antes de calcular, comprueba que `prob_favorable` es válida
    (no nula, en [0, 1]) en las filas con etiqueta. Si no, lanza
    `DatosNoValidos` con un mensaje en español, sin traza ni texto de
    sklearn, que la ingesta (`evaluate_motivo`) y la evaluación suelta
    (`routers/evaluations.py`) guardan tal cual.

    El motor no conoce el nombre de la columna original del fichero (eso
    lo sabe el mapeo, en la capa de ingesta): `columna_original` es un
    parámetro opcional para que quien sí lo sabe lo complete;
    sin él, el mensaje dice «la columna de probabilidad» (decisión propia
    de este módulo).
    """
    n = len(df_labeled)
    if n == 0:
        return
    p1 = df_labeled[COL_PROB]
    invalidas = p1.isna() | (p1 < 0) | (p1 > 1)
    n_invalidas = int(invalidas.sum())
    if n_invalidas:
        referencia = f"la columna {columna_original}" if columna_original else "la columna de probabilidad"
        raise DatosNoValidos(
            f"la probabilidad tiene {n_invalidas} de {n} filas nulas o fuera de 0 a 1: "
            f"revisa {referencia} del mapeo"
        )


# En multiclase los tres titulares esperan a un umbral de la línea
# base; sin uno que no sea de fábrica quedan en `sin_datos`.
_TITULARES = ("accuracy", "f1_measure", "area_under_roc")


def quality_metrics(
    df_labeled: pd.DataFrame,
    *,
    columna_probabilidad: str | None = None,
    task: TaskSpec | None = None,
    min_group: int = 20,
) -> dict[str, Any]:
    """Métricas de calidad sobre un frame ya filtrado a filas con `label` no
    NaN. Claves con el nombre de métrica del glosario.

    Valida la probabilidad antes de calcular (`validar_probabilidad`):
    con nulos o valores fuera de 0 a 1 entre las filas con etiqueta, lanza
    `DatosNoValidos` en vez de dejar que `roc_auc_score` u otra métrica de
    sklearn revienten con su propio mensaje en inglés.

    Con `task` multiclase devuelve las mismas claves con promedio
    macro y, además, `por_clase` y `details` (ver `quality_multiclase`).
    Con `task=None` o binario, todo como antes.
    """
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "multiclass":
            return metricas_multiclase(
                df_labeled, task, min_group=min_group, columna_probabilidad=columna_probabilidad  # type: ignore[arg-type]
            )
        case "regression":
            # Sin probabilidad ni matriz; ver `quality_regresion`.
            return metricas_regresion(df_labeled)
        case "binary":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    validar_probabilidad(df_labeled, columna_original=columna_probabilidad)
    y = df_labeled[COL_LABEL].astype(int).to_numpy()
    yhat = df_labeled[COL_PREDICTION].astype(int).to_numpy()
    p1 = df_labeled[COL_PROB].to_numpy(dtype=float)
    n = len(df_labeled)

    tn, fp, fn, tp = confusion_matrix(y, yhat, labels=[0, 1]).ravel()

    accuracy = float(accuracy_score(y, yhat))
    precision = float(precision_score(y, yhat, zero_division=0))
    recall = float(recall_score(y, yhat, zero_division=0))
    f1_measure = float(f1_score(y, yhat, zero_division=0))
    brier_score = float(brier_score_loss(y, p1))
    log_loss_val = float(log_loss(y, p1, labels=[0, 1]))
    mcc = float(matthews_corrcoef(y, yhat))

    n_clases = len(np.unique(y))
    if n_clases < 2:
        area_under_roc: float | None = None
        area_under_pr: float | None = None
        gini_coefficient: float | None = None
    else:
        area_under_roc = float(roc_auc_score(y, p1))
        area_under_pr = float(average_precision_score(y, p1))
        gini_coefficient = 2.0 * area_under_roc - 1.0

    true_positive_rate = recall
    false_positive_rate = float(fp) / (fp + tn) if (fp + tn) else 0.0

    return {
        "n": n,
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
        "accuracy": accuracy,
        "area_under_roc": area_under_roc,
        "area_under_pr": area_under_pr,
        "true_positive_rate": true_positive_rate,
        "false_positive_rate": false_positive_rate,
        "precision": precision,
        "recall": recall,
        "f1_measure": f1_measure,
        "log_loss": log_loss_val,
        "matthews_correlation_coefficient": mcc,
        "gini_coefficient": gini_coefficient,
        "brier_score": brier_score,
        "label_rate": float(df_labeled[COL_LABEL].mean()) if n else None,
        "prediction_rate": float(df_labeled[COL_PREDICTION].mean()) if n else None,
    }


def label_skew(
    label_rate_window: float | None, baseline_label_rate: float | None
) -> float | None:
    """Desviación de la tasa de etiqueta favorable de la ventana frente a la
    tasa de referencia (baseline). Criterio propio: `label_rate_window - baseline_label_rate`, en
    [-1, 1].
    """
    if label_rate_window is None or baseline_label_rate is None:
        return None
    return label_rate_window - baseline_label_rate


def _version_de_batch(df_history: pd.DataFrame, batch_seq: int) -> str | None:
    versiones = df_history.loc[df_history[COL_BATCH] == batch_seq, COL_VERSION].unique()
    return str(versiones[0]) if len(versiones) else None


MOTIVO_AUC_PR_PENDIENTE = "umbral de AUC-PR pendiente de la línea base congelada"


def _umbral_relativo(thresholds: MonitorThresholds, clave: str) -> Threshold | None:
    """El umbral de `clave` que es relativo a la prevalencia, si lo hay."""
    for t in thresholds.thresholds:
        if t.metric_key == clave and t.relativo_a is not None:
            return t
    return None


def _limites(thresholds: MonitorThresholds, clave: str) -> tuple[float | None, float | None]:
    """Límites absolutos de `clave`. Un umbral relativo sin resolver no aporta
    límite: su `value` es una fracción, no un valor de la métrica."""
    if _umbral_relativo(thresholds, clave) is None:
        return thresholds.limits(clave)
    absolutos = MonitorThresholds(
        thresholds=[
            t
            for t in thresholds.thresholds
            if not (t.metric_key == clave and t.relativo_a is not None)
        ]
    )
    return absolutos.limits(clave)


def resolver_umbral_relativo(
    relativo: Threshold, baseline: pd.DataFrame | None
) -> tuple[float | None, dict[str, float] | None, str | None]:
    """`prevalencia + fraccion x (AUC-PR de la línea base -
    prevalencia)`, sobre las filas con etiqueta de la línea base congelada.
    Devuelve `(umbral, extra, motivo)`; sin línea base o sin dos resultados
    con etiqueta y probabilidad válida, `umbral` es `None` y `motivo` dice por
    qué."""
    if relativo.metric_key != "area_under_pr":
        return None, None, f"el umbral relativo de {relativo.metric_key} no tiene fórmula"
    if baseline is None or len(baseline) == 0:
        return None, None, MOTIVO_AUC_PR_PENDIENTE
    etiquetadas = baseline[baseline[COL_LABEL].notna()]
    if len(etiquetadas) == 0 or etiquetadas[COL_LABEL].nunique() < 2:
        return None, None, "la línea base no tiene los dos resultados con etiqueta: " + (
            MOTIVO_AUC_PR_PENDIENTE
        )
    p = etiquetadas[COL_PROB].to_numpy(dtype=float)
    if np.isnan(p).any() or (p < 0).any() or (p > 1).any():
        return None, None, "la línea base no tiene una probabilidad válida: " + (
            MOTIVO_AUC_PR_PENDIENTE
        )
    y = etiquetadas[COL_LABEL].astype(int).to_numpy()
    prevalencia = float(y.mean())
    auc_pr = float(average_precision_score(y, p))
    fraccion = float(relativo.value)
    umbral = prevalencia + fraccion * (auc_pr - prevalencia)
    extra = {"prevalencia": prevalencia, "auc_pr_linea_base": auc_pr, "fraccion": fraccion}
    return umbral, extra, None


def _resultado_sin_datos(
    *,
    config: QualityConfig,
    thresholds: MonitorThresholds,
    motivo: str,
    model_version: str | None,
    task: TaskSpec | None = None,
) -> EvaluationResult:
    """Resultado `sin_datos` en todas las medidas, sin tocar `df_history`.
    Se usa cuando no hay forma segura de determinar la ventana (por ejemplo,
    `batch_seq` sin filas propias y sin `model_version` explícito: no se
    debe mezclar versiones sin avisar).: en regresión publica las
    claves de regresión, nunca las de clasificación.
    """
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "regression":
            return _resultado_sin_datos_regresion(
                config=config,
                thresholds=thresholds,
                motivo=motivo,
                model_version=model_version,
                task=task,  # type: ignore[arg-type]
            )
        case "binary" | "multiclass":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    measurements: list[Measurement] = []
    for clave in (*_CLAVES_UMBRAL, "label_skew"):
        low, high = _limites(thresholds, clave)
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
    for clave in ("n", "tp", "fp", "fn", "tn", "label_rate", "prediction_rate"):
        measurements.append(
            Measurement(metric_key=clave, value=None, state=State.sin_datos, motivo=motivo)
        )

    window_info = WindowInfo(
        kind="batch",
        n=0,
        requested_n=config.min_feedback,
        batches=[],
        model_version=model_version,
        complete=False,
        motivo=motivo,
    )
    details: dict[str, Any] = {
        "confusion": {"tp": None, "fp": None, "fn": None, "tn": None},
        "n_labeled_by_batch": {},
    }
    return EvaluationResult(
        monitor=MonitorType.quality,
        window=window_info,
        measurements=measurements,
        config_snapshot=config.model_dump(),
        core_version=CORE_VERSION,
        details=details,
    )


def _seleccionar_ventana(
    df_history: pd.DataFrame, batch_seq: int, config: QualityConfig, version: str
) -> tuple[pd.DataFrame, pd.DataFrame, list[int], dict[str, int]]:
    """Ventana de calidad: batches con etiqueta de la versión, del más
    reciente al más antiguo, hasta `min_feedback` filas."""
    historia_version = df_history[df_history[COL_VERSION] == version]
    etiquetadas = historia_version[historia_version[COL_LABEL].notna()]

    candidatos = sorted(
        (b for b in etiquetadas[COL_BATCH].unique() if b <= batch_seq), reverse=True
    )

    used_batches: list[int] = []
    partes: list[pd.DataFrame] = []
    n_acumulado = 0
    n_labeled_by_batch: dict[str, int] = {}
    for b in candidatos:
        filas = etiquetadas[etiquetadas[COL_BATCH] == b]
        n_labeled_by_batch[str(int(b))] = len(filas)
        if n_acumulado >= config.min_feedback:
            continue
        partes.append(filas)
        used_batches.append(int(b))
        n_acumulado += len(filas)

    ventana = pd.concat(partes) if partes else etiquetadas.iloc[0:0]
    return historia_version, ventana, used_batches, n_labeled_by_batch


def _medida_multiclase_sin_umbral(
    clave: str, valor: float | None, *, motivo_nulo: str | None
) -> Measurement:
    estado = State.ok if valor is not None else State.sin_datos
    return Measurement(
        metric_key=clave,
        value=valor,
        state=estado,
        motivo=motivo_nulo if valor is None else None,
    )


def _evaluate_quality_multiclase(
    *,
    historia_version: pd.DataFrame,
    ventana: pd.DataFrame,
    used_batches: list[int],
    n_labeled_by_batch: dict[str, int],
    batch_seq: int,
    config: QualityConfig,
    thresholds: MonitorThresholds,
    task: TaskSpec,
    baseline_label_rate: float | None,
    version: str,
    columna_probabilidad: str | None,
    min_group: int,
) -> EvaluationResult:
    """Calidad multiclase: macro en las claves de siempre, medidas por
    clase sin umbral, y umbrales solo si no son de fábrica."""
    n = len(ventana)
    sin_datos_final = n == 0 or n < config.min_feedback
    # Un umbral de fábrica no vale en multiclase. Es de fábrica si su
    # origen es `fabrica`, o si no tiene origen y coincide en clave,
    # tipo y valor con el de `DEFAULT_QUALITY_THRESHOLDS`: un umbral editado sin
    # origen (p. ej. por `set_monitor`) sí se evalúa.
    de_fabrica = {
        (t.metric_key, t.kind, t.value) for t in DEFAULT_QUALITY_THRESHOLDS.thresholds
    }
    validos = MonitorThresholds(
        thresholds=[
            t
            for t in thresholds.thresholds
            if t.relativo_a is None
            and t.origen != "fabrica"
            and not (t.origen is None and (t.metric_key, t.kind, t.value) in de_fabrica)
        ]
    )
    sin_conjunto = task.sin_conjunto_favorable
    motivo_ventana: str | None = None
    por_clase: dict[str, dict[str, Any]] = {}
    detalle: dict[str, Any] = {}
    if sin_datos_final:
        motivo_ventana = (
            f"solo hay {n} filas etiquetadas disponibles, se pedían {config.min_feedback}"
        )
        metricas: dict[str, Any] = {
            c: None for c in _CLAVES_UMBRAL + ("n", "tp", "fp", "fn", "tn")
        }
        metricas["n"] = n
        metricas["label_rate"] = None
        metricas["prediction_rate"] = None
    else:
        metricas = metricas_multiclase(
            ventana, task, min_group=min_group, columna_probabilidad=columna_probabilidad
        )
        por_clase = metricas.pop("por_clase")
        detalle = metricas.pop("details")

    skew = (
        None
        if sin_conjunto
        else label_skew(metricas.get("label_rate"), baseline_label_rate)
    )
    publicadas = dict(metricas)
    publicadas["label_skew"] = skew

    measurements: list[Measurement] = []
    for clave in (*_CLAVES_UMBRAL, "label_skew"):
        valor = publicadas.get(clave)
        low, high = validos.limits(clave)
        if sin_datos_final:
            measurements.append(
                Measurement(
                    metric_key=clave,
                    value=None,
                    threshold_low=low,
                    threshold_high=high,
                    state=State.sin_datos,
                    motivo=motivo_ventana,
                )
            )
            continue
        motivo_nulo = None
        if valor is None:
            if clave == "label_skew" and sin_conjunto:
                motivo_nulo = MOTIVO_SIN_CONJUNTO_FAVORABLE
            elif clave in (
                "area_under_roc",
                "area_under_pr",
                "gini_coefficient",
            ):
                motivo_nulo = (
                    "menos de dos clases con positivos y negativos en la ventana"
                )
        if low is None and high is None:
            if clave in _TITULARES:
                measurements.append(
                    Measurement(
                        metric_key=clave,
                        value=None,
                        state=State.sin_datos,
                        motivo=MOTIVO_UMBRAL_PENDIENTE,
                        extra={"umbral_pendiente": True, "valor_calculado": valor},
                    )
                )
            else:
                measurements.append(
                    _medida_multiclase_sin_umbral(clave, valor, motivo_nulo=motivo_nulo)
                )
            continue
        estado, motivo_medida = classify_with_motivo(valor, low, high)
        measurements.append(
            Measurement(
                metric_key=clave,
                value=valor,
                threshold_low=low,
                threshold_high=high,
                state=estado,
                motivo=motivo_medida or (motivo_nulo if valor is None else None),
            )
        )

    for clave in ("n", "tp", "fp", "fn", "tn", "label_rate", "prediction_rate"):
        valor = metricas.get(clave)
        estado = State.ok if valor is not None else State.sin_datos
        if valor is None:
            motivo_nulo_extra = motivo_ventana or (
                MOTIVO_SIN_CONJUNTO_FAVORABLE if sin_conjunto else None
            )
        else:
            motivo_nulo_extra = None
        measurements.append(
            Measurement(
                metric_key=clave,
                value=float(valor) if valor is not None else None,
                state=estado,
                motivo=motivo_nulo_extra,
            )
        )

    # Métricas por clase, sin umbral; una clase con menos de
    # `min_group` filas reales en la ventana da `sin_datos`, nunca 0.
    for clase, bloque in por_clase.items():
        codigo = grupo_clase(clase)
        measurements.append(
            Measurement(
                metric_key="n",
                value=float(bloque["n"]),
                state=State.ok,
                group_code=codigo,
            )
        )
        for clave in CLAVES_POR_CLASE:
            valor = bloque["valores"].get(clave)
            if bloque["insuficiente"] or valor is None:
                motivo = (
                    f"clase con {bloque['n']} filas en la ventana, se piden al menos {min_group}"
                    if bloque["insuficiente"]
                    else "sin positivos o sin negativos de esta clase en la ventana"
                )
                measurements.append(
                    Measurement(
                        metric_key=clave,
                        value=None,
                        state=State.sin_datos,
                        group_code=codigo,
                        motivo=motivo,
                    )
                )
            else:
                measurements.append(
                    Measurement(
                        metric_key=clave, value=valor, state=State.ok, group_code=codigo
                    )
                )

    kind = "batch" if used_batches in ([batch_seq], []) else "acumulado"
    window_info = WindowInfo(
        kind=kind,  # type: ignore[arg-type]
        n=n,
        requested_n=config.min_feedback,
        start_seq=int(ventana[COL_SEQ].min()) if n else None,
        end_seq=int(ventana[COL_SEQ].max()) if n else None,
        batches=sorted(used_batches),
        model_version=version,
        complete=not sin_datos_final,
        motivo=motivo_ventana,
    )
    details: dict[str, Any] = {
        "confusion": {
            "tp": metricas.get("tp"),
            "fp": metricas.get("fp"),
            "fn": metricas.get("fn"),
            "tn": metricas.get("tn"),
        },
        "n_labeled_by_batch": n_labeled_by_batch,
        "clases_desconocidas": clases_desconocidas(
            historia_version, task, hasta_batch=batch_seq
        ),
        **detalle,
    }
    return EvaluationResult(
        monitor=MonitorType.quality,
        window=window_info,
        measurements=measurements,
        config_snapshot=config.model_dump(),
        core_version=CORE_VERSION,
        details=details,
    )


def _medida_regresion(
    clave: str,
    valor: float | None,
    thresholds: MonitorThresholds,
    *,
    titular: bool,
    motivo_nulo: str | None,
) -> Measurement:
    """Una medida de calidad de regresión. Un titular sin umbral
    espera a la línea base: `sin_datos` con `umbral_pendiente` y el valor
    calculado en `extra`. Una medida de detalle sin umbral sale `ok`."""
    low, high = thresholds.limits(clave)
    if valor is None:
        return Measurement(
            metric_key=clave,
            value=None,
            threshold_low=low,
            threshold_high=high,
            state=State.sin_datos,
            motivo=motivo_nulo,
        )
    if low is None and high is None:
        if titular:
            return Measurement(
                metric_key=clave,
                value=None,
                state=State.sin_datos,
                motivo=MOTIVO_UMBRAL_PENDIENTE,
                extra={"umbral_pendiente": True, "valor_calculado": valor},
            )
        return Measurement(metric_key=clave, value=valor, state=State.ok)
    # Sin banda de aviso: el umbral de la línea base ya incluye su margen (como en
    # la multiclase), y el 10 % del umbral es más ancho que ese margen, así que un
    # lote sano saldría siempre en `aviso`.
    estado, motivo = classify_with_motivo(
        valor, low, high, aviso_frac=0.0, decimales=decimales_para(valor, low, high)
    )
    return Measurement(
        metric_key=clave,
        value=valor,
        threshold_low=low,
        threshold_high=high,
        state=estado,
        motivo=motivo,
    )


def _resultado_sin_datos_regresion(
    *,
    config: QualityConfig,
    thresholds: MonitorThresholds,
    motivo: str,
    model_version: str | None,
    task: TaskSpec,
) -> EvaluationResult:
    """`_resultado_sin_datos` de una regresión: las claves de regresión."""
    measurements = [
        _medida_regresion(clave, None, thresholds, titular=True, motivo_nulo=motivo)
        for clave in (*CLAVES_CALIDAD_REGRESION, *CLAVES_CALIDAD_REGRESION_DETALLE)
    ]
    claves_extra = ["n"]
    if not task.sin_rango_favorable:
        measurements.append(
            _medida_regresion("label_skew", None, thresholds, titular=False, motivo_nulo=motivo)
        )
        claves_extra += ["label_rate", "prediction_rate"]
    for clave in claves_extra:
        measurements.append(
            Measurement(metric_key=clave, value=None, state=State.sin_datos, motivo=motivo)
        )
    window_info = WindowInfo(
        kind="batch",
        n=0,
        requested_n=config.min_feedback,
        batches=[],
        model_version=model_version,
        complete=False,
        motivo=motivo,
    )
    return EvaluationResult(
        monitor=MonitorType.quality,
        window=window_info,
        measurements=measurements,
        config_snapshot=config.model_dump(),
        core_version=CORE_VERSION,
        details={
            "task_type": "regression",
            "unidad": task.unidad,
            "n_labeled_by_batch": {},
        },
    )


def _evaluate_quality_regresion(
    *,
    ventana: pd.DataFrame,
    used_batches: list[int],
    n_labeled_by_batch: dict[str, int],
    batch_seq: int,
    config: QualityConfig,
    thresholds: MonitorThresholds,
    task: TaskSpec,
    baseline_label_rate: float | None,
    version: str,
) -> EvaluationResult:
    """Calidad de regresión: MAE, RMSE, R² y sesgo medio como
    titulares con umbral de la línea base (E5), MSE y mediana del error
    absoluto sin umbral, y `details` con residuos, predicho frente a real y la
    distribución del valor real. Con rango favorable publica además `label_rate`,
    `prediction_rate` y `label_skew` sobre la pertenencia; sin rango, no."""
    n = len(ventana)
    sin_datos_final = n == 0 or n < config.min_feedback
    con_rango = not task.sin_rango_favorable
    motivo_ventana: str | None = None
    detalle: dict[str, Any] = {}
    if sin_datos_final:
        motivo_ventana = (
            f"solo hay {n} filas etiquetadas disponibles, se pedían {config.min_feedback}"
        )
        metricas: dict[str, Any] = {
            c: None for c in (*CLAVES_CALIDAD_REGRESION, *CLAVES_CALIDAD_REGRESION_DETALLE)
        }
        metricas["n"] = n
        metricas["motivo_r2"] = None
    else:
        metricas = metricas_regresion(ventana)
        detalle = detalles_regresion(ventana, task.unidad)
        if metricas["n"] == 0:
            motivo_ventana = MOTIVO_SIN_PARES

    label_rate = prediction_rate = skew = None
    if con_rango and not sin_datos_final:
        label_rate = float(ventana[COL_LABEL].mean())
        prediction_rate = float(ventana[COL_PREDICTION].mean())
        skew = label_skew(label_rate, baseline_label_rate)

    measurements: list[Measurement] = []
    for clave in CLAVES_CALIDAD_REGRESION:
        motivo_nulo = motivo_ventana
        if clave == "r2" and not sin_datos_final:
            motivo_nulo = metricas.get("motivo_r2")
        measurements.append(
            _medida_regresion(clave, metricas.get(clave), thresholds, titular=True,
                              motivo_nulo=motivo_nulo)
        )
    for clave in CLAVES_CALIDAD_REGRESION_DETALLE:
        measurements.append(
            _medida_regresion(clave, metricas.get(clave), thresholds, titular=False,
                              motivo_nulo=motivo_ventana)
        )
    if con_rango:
        measurements.append(
            _medida_regresion("label_skew", skew, thresholds, titular=False,
                              motivo_nulo=motivo_ventana or "sin línea base congelada para esta versión")
        )
    claves_extra: list[tuple[str, float | None]] = [("n", float(n))]
    if con_rango:
        claves_extra += [("label_rate", label_rate), ("prediction_rate", prediction_rate)]
    for clave, valor in claves_extra:
        measurements.append(
            Measurement(
                metric_key=clave,
                value=valor,
                state=State.ok if valor is not None else State.sin_datos,
                motivo=motivo_ventana if valor is None else None,
            )
        )

    kind = "batch" if used_batches in ([batch_seq], []) else "acumulado"
    window_info = WindowInfo(
        kind=kind,  # type: ignore[arg-type]
        n=n,
        requested_n=config.min_feedback,
        start_seq=int(ventana[COL_SEQ].min()) if n else None,
        end_seq=int(ventana[COL_SEQ].max()) if n else None,
        batches=sorted(used_batches),
        model_version=version,
        complete=not sin_datos_final,
        motivo=motivo_ventana,
    )
    details: dict[str, Any] = {
        "task_type": "regression",
        "unidad": task.unidad,
        "n_labeled_by_batch": n_labeled_by_batch,
        **{k: v for k, v in detalle.items() if k not in ("task_type", "unidad")},
    }
    return EvaluationResult(
        monitor=MonitorType.quality,
        window=window_info,
        measurements=measurements,
        config_snapshot=config.model_dump(),
        core_version=CORE_VERSION,
        details=details,
    )


def evaluate_quality(
    df_history: pd.DataFrame,
    *,
    batch_seq: int,
    config: QualityConfig,
    thresholds: MonitorThresholds,
    baseline_label_rate: float | None = None,
    model_version: str | None = None,
    columna_probabilidad: str | None = None,
    task: TaskSpec | None = None,
    baseline: pd.DataFrame | None = None,
    min_group: int = 20,
) -> EvaluationResult:
    """`task` multiclase activa la calidad macro, las medidas por
    clase y los umbrales solo si no son de fábrica. `baseline` es
    la línea base congelada de la versión: resuelve el umbral de `area_under_pr`
    relativo a la prevalencia. `min_group` es el mínimo de filas de
    una clase para publicar sus métricas. Sin `task`, como antes."""
    version = model_version if model_version is not None else _version_de_batch(
        df_history, batch_seq
    )
    if version is None:
        return _resultado_sin_datos(
            config=config,
            thresholds=thresholds,
            motivo="batch sin filas",
            model_version=None,
            task=task,
        )
    historia_version, ventana, used_batches, n_labeled_by_batch = _seleccionar_ventana(
        df_history, batch_seq, config, version
    )
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "multiclass":
            return _evaluate_quality_multiclase(
                historia_version=historia_version,
                ventana=ventana,
                used_batches=used_batches,
                n_labeled_by_batch=n_labeled_by_batch,
                batch_seq=batch_seq,
                config=config,
                thresholds=thresholds,
                task=task,  # type: ignore[arg-type]
                baseline_label_rate=baseline_label_rate,
                version=version,
                columna_probabilidad=columna_probabilidad,
                min_group=min_group,
            )
        case "regression":
            return _evaluate_quality_regresion(
                ventana=ventana,
                used_batches=used_batches,
                n_labeled_by_batch=n_labeled_by_batch,
                batch_seq=batch_seq,
                config=config,
                thresholds=thresholds,
                task=task,  # type: ignore[arg-type]
                baseline_label_rate=baseline_label_rate,
                version=version,
            )
        case "binary":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")

    n = len(ventana)
    sin_datos_final = n == 0 or n < config.min_feedback

    if sin_datos_final:
        motivo = f"solo hay {n} filas etiquetadas disponibles, se pedían {config.min_feedback}"
        metricas: dict[str, float | int | None] = {
            clave: None for clave in _CLAVES_UMBRAL + ("n", "tp", "fp", "fn", "tn")
        }
        metricas["n"] = n
        metricas["label_rate"] = None
        metricas["prediction_rate"] = None
    else:
        motivo = None
        metricas = quality_metrics(ventana, columna_probabilidad=columna_probabilidad)

    skew = label_skew(metricas.get("label_rate"), baseline_label_rate)
    metricas_publicadas = dict(metricas)
    metricas_publicadas["label_skew"] = skew

    kind = "batch" if used_batches in ([batch_seq], []) else "acumulado"

    # Umbrales relativos a la prevalencia, resueltos con la línea base.
    relativos: dict[str, tuple[float | None, dict[str, float] | None, str | None]] = {}
    if not sin_datos_final:
        for clave in _CLAVES_UMBRAL:
            relativo = _umbral_relativo(thresholds, clave)
            if relativo is not None:
                relativos[clave] = resolver_umbral_relativo(relativo, baseline)

    measurements: list[Measurement] = []
    for clave in (*_CLAVES_UMBRAL, "label_skew"):
        valor = metricas_publicadas.get(clave)
        low, high = _limites(thresholds, clave)
        if sin_datos_final:
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
            continue
        if clave in relativos:
            umbral, extra_relativo, motivo_relativo = relativos[clave]
            if umbral is None:
                measurements.append(
                    Measurement(
                        metric_key=clave,
                        value=None,
                        state=State.sin_datos,
                        motivo=motivo_relativo,
                        extra={"umbral_pendiente": True, "valor_calculado": valor},
                    )
                )
                continue
            tipo = _umbral_relativo(thresholds, clave)
            if tipo is not None and tipo.kind == ThresholdKind.upper_limit:
                low, high = None, umbral
            else:
                low, high = umbral, None
            # La banda de aviso del 10 % del umbral no sirve aquí: el umbral ya
            # incluye el azar (la prevalencia), así que se mide sobre el margen
            # por encima de la prevalencia y los estados de run_scenario no se mueven.
            prevalencia = (extra_relativo or {}).get("prevalencia", 0.0)
            banda = 0.10 * (umbral - prevalencia) / umbral if umbral > 0 else 0.10
            estado, motivo_medida = classify_with_motivo(valor, low, high, aviso_frac=banda)
            extra_relativo = {**(extra_relativo or {}), "banda_aviso": banda * umbral}
            measurements.append(
                Measurement(
                    metric_key=clave,
                    value=valor,
                    threshold_low=low,
                    threshold_high=high,
                    state=estado,
                    motivo=motivo_medida,
                    extra={"umbral_relativo": extra_relativo},
                )
            )
            continue
        if low is None and high is None:
            estado = State.ok if valor is not None else State.sin_datos
            motivo_medida = None
        else:
            estado, motivo_medida = classify_with_motivo(valor, low, high)
        measurements.append(
            Measurement(
                metric_key=clave,
                value=valor,
                threshold_low=low,
                threshold_high=high,
                state=estado,
                motivo=motivo_medida,
            )
        )

    for clave in ("n", "tp", "fp", "fn", "tn", "label_rate", "prediction_rate"):
        valor = metricas.get(clave)
        estado = State.ok if valor is not None else State.sin_datos
        measurements.append(
            Measurement(
                metric_key=clave,
                value=float(valor) if valor is not None else None,
                state=estado,
                motivo=motivo if valor is None else None,
            )
        )

    window_info = WindowInfo(
        kind=kind,  # type: ignore[arg-type]
        n=n,
        requested_n=config.min_feedback,
        start_seq=int(ventana[COL_SEQ].min()) if n else None,
        end_seq=int(ventana[COL_SEQ].max()) if n else None,
        batches=sorted(used_batches),
        model_version=version,
        complete=not sin_datos_final,
        motivo=motivo,
    )

    details: dict[str, Any] = {
        "confusion": {
            "tp": metricas.get("tp"),
            "fp": metricas.get("fp"),
            "fn": metricas.get("fn"),
            "tn": metricas.get("tn"),
        },
        "n_labeled_by_batch": n_labeled_by_batch,
    }

    return EvaluationResult(
        monitor=MonitorType.quality,
        window=window_info,
        measurements=measurements,
        config_snapshot=config.model_dump(),
        core_version=CORE_VERSION,
        details=details,
    )
