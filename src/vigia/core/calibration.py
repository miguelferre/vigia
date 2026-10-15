"""Propuesta de umbrales por modelo desde su línea base: el umbral es de cada
modelo y no de la plataforma.

La función se llama desde `GET /projects/{id}/thresholds/proposal`.

Regla: remuestrear la línea base (marco canónico, el de `to_canonical`) al
tamaño de lote declarado, calcular cada métrica con umbral de fábrica del
monitor (`core/thresholds.defaults_for`) en cada remuestreo y proponer el
percentil que deja `cobertura` de los lotes estables del lado bueno, con
margen. Una métrica que no se puede calcular sale con `value=None` y motivo.

Regla (`build/validacion/gen_calibracion.py`, banco de medición):
el umbral no iguala el percentil observado, se empuja `_MARGEN_RELATIVO` más
allá hacia el lado malo para no calibrar al filo (percentil 1 empujado hacia
abajo para un mínimo, percentil 99 empujado hacia arriba para un máximo).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from vigia.core.fairness import fairness_metrics
from vigia.core.quality import label_skew, quality_metrics, validar_probabilidad
from vigia.core.quality_multiclase import metricas_multiclase
from vigia.core.quality_regresion import varianza_nula
from vigia.core.schema import (
    CLAVES_CALIDAD_REGRESION,
    CLAVES_EQUIDAD_ERROR,
    COL_GROUP,
    COL_LABEL,
    COL_LABEL_VALUE,
    COL_PREDICTION_CLASS,
    COL_PREDICTION_VALUE,
    COL_PROB,
    DatosNoValidos,
    FairnessConfig,
    MonitorType,
    QualityConfig,
    TaskSpec,
    Threshold,
    ThresholdKind,
)
from vigia.core.thresholds import defaults_for

__all__ = [
    "PropuestaUmbral",
    "monitor_de_umbral",
    "proponer_umbrales",
    "umbrales_linea_base_multiclase",
    "umbrales_linea_base_regresion",
]

# Margen relativo con el que se empuja el percentil observado más
# allá del lado malo. `gen_calibracion.py` usa 0,15 con 30 semillas por 12
# lotes (360 muestras); aquí, medido con el remuestreo por bootstrap de esta
# función (200 remuestreos por defecto), 0,15 se queda corto en el filo de
# la cobertura del 99% (0,988 medido en `tests/core/test_calibration.py`
# sobre una población sintética de 20 000 filas); 0,20 la deja por encima
# del 99% en las diez métricas de fábrica de equidad.
_MARGEN_RELATIVO = 0.20


class PropuestaUmbral(BaseModel):
    """Umbral propuesto para una métrica, junto al valor de la línea base."""

    model_config = ConfigDict(extra="forbid")

    metric_key: str
    kind: ThresholdKind
    # `None` si no se puede proponer (grupo pequeño, sin etiquetas...): `motivo` lo dice.
    value: float | None
    # Valor de la métrica sobre la línea base entera, para enseñarlo al lado.
    valor_linea_base: float | None
    motivo: str | None = None


def _empujar_con_margen(valor: float, *, kind: ThresholdKind) -> float:
    """El umbral no iguala el percentil, se empuja `_MARGEN_RELATIVO`
    más allá hacia el lado malo. En un `lower_limit` (el umbral es un
    mínimo) "más allá" es hacia abajo; en un `upper_limit` (máximo), hacia
    arriba. Con el percentil ya del lado malo del cero, empujar es acercarlo
    a cero (mismo signo que `gen_calibracion.py`, para no cruzar a un umbral
    del signo contrario)."""
    if kind == ThresholdKind.lower_limit:
        return valor * (1 - _MARGEN_RELATIVO) if valor >= 0 else valor * (1 + _MARGEN_RELATIVO)
    return valor * (1 + _MARGEN_RELATIVO) if valor >= 0 else valor * (1 - _MARGEN_RELATIVO)


def _percentil_de_cobertura(kind: ThresholdKind, cobertura: float) -> float:
    """Percentil 1 (cobertura 0.99) para un mínimo; percentil 99 para un
    máximo: el lado que deja `cobertura` de las muestras del lado bueno."""
    if kind == ThresholdKind.lower_limit:
        return (1 - cobertura) * 100
    return cobertura * 100


# Métricas de calidad que necesitan la probabilidad: sin una probabilidad
# válida en la línea base no se proponen; el resto (matriz de confusión y
# etiqueta) sí, porque salen de la predicción y la etiqueta.
_CLAVES_CON_PROBABILIDAD = frozenset(
    {"area_under_roc", "area_under_pr", "log_loss", "gini_coefficient", "brier_score"}
)


# Rango alcanzable de las métricas de calidad acotadas: un umbral fuera de él
# no vigila nada (p. ej. FPR máximo 1,12). Las no listadas no se acotan.
_RANGO_CALIDAD: dict[str, tuple[float, float]] = {
    "accuracy": (0.0, 1.0),
    "area_under_roc": (0.0, 1.0),
    "area_under_pr": (0.0, 1.0),
    "true_positive_rate": (0.0, 1.0),
    "false_positive_rate": (0.0, 1.0),
    "precision": (0.0, 1.0),
    "recall": (0.0, 1.0),
    "f1_measure": (0.0, 1.0),
    "brier_score": (0.0, 1.0),
    "gini_coefficient": (-1.0, 1.0),
    "matthews_correlation_coefficient": (-1.0, 1.0),
    # El R² no pasa de 1 (sin cota inferior: puede ser negativo).
    "r2": (float("-inf"), 1.0),
}


def _acotar(clave: str, valor: float, monitor: MonitorType) -> float:
    if monitor != MonitorType.quality or clave not in _RANGO_CALIDAD:
        return valor
    lo, hi = _RANGO_CALIDAD[clave]
    return min(max(valor, lo), hi)


def _probabilidad_invalida(etiquetadas: pd.DataFrame) -> str | None:
    """Motivo (frase de `DatosNoValidos`) si la probabilidad de las filas con
    etiqueta no es válida; `None` si lo es."""
    try:
        validar_probabilidad(etiquetadas)
    except DatosNoValidos as exc:
        return str(exc)
    return None


def _calidad(etiquetadas: pd.DataFrame, *, con_probabilidad: bool) -> dict[str, float | int | None]:
    """`quality_metrics`, o, si la línea base no trae probabilidad válida
    (con toda la probabilidad nula, `DatosNoValidos` vaciaba la
    calidad entera), las métricas que no la usan y `None` en las demás."""
    if con_probabilidad:
        return quality_metrics(etiquetadas)
    m = quality_metrics(etiquetadas.assign(**{COL_PROB: 0.5}))
    for clave in _CLAVES_CON_PROBABILIDAD:
        m[clave] = None
    return m


def _remuestrear(baseline: pd.DataFrame, rng: np.random.Generator, tamano_lote: int) -> pd.DataFrame:
    """Bootstrap con reemplazo: `tamano_lote` filas de `baseline`, simulando
    un lote que llegaría con esa población."""
    idx = rng.integers(0, len(baseline), size=tamano_lote)
    return baseline.iloc[idx]


def _valores_fairness(
    baseline: pd.DataFrame,
    *,
    rng: np.random.Generator,
    tamano_lote: int,
    n_remuestreos: int,
    config: FairnessConfig,
    claves: set[str],
) -> dict[str, list[float]]:
    valores: dict[str, list[float]] = {c: [] for c in claves}
    for _ in range(n_remuestreos):
        lote = _remuestrear(baseline, rng, tamano_lote)
        m = fairness_metrics(lote, min_group=config.min_group)
        for clave in claves:
            valor = m.get(clave)
            if isinstance(valor, (int, float)) and valor is not None:
                valores[clave].append(float(valor))
    return valores


def _valores_quality(
    baseline: pd.DataFrame,
    *,
    rng: np.random.Generator,
    tamano_lote: int,
    n_remuestreos: int,
    config: QualityConfig,
    claves: set[str],
    con_probabilidad: bool = True,
) -> tuple[dict[str, list[float]], str | None]:
    """Igual que `_valores_fairness`, pero de calidad: un remuestreo solo
    cuenta si tiene, al menos, `config.min_feedback` filas etiquetadas (el
    mismo suelo que usa `evaluate_quality` en producción para no publicar
    `sin_datos`). `label_skew` se calcula aparte (no lo da `quality_metrics`):
    tasa de etiqueta del remuestreo menos la de la línea base entera."""
    valores: dict[str, list[float]] = {c: [] for c in claves}
    etiquetadas_enteras = baseline[baseline[COL_LABEL].notna()]
    baseline_label_rate = (
        float(etiquetadas_enteras[COL_LABEL].mean()) if len(etiquetadas_enteras) else None
    )
    motivo_dato_invalido: str | None = None
    for _ in range(n_remuestreos):
        lote = _remuestrear(baseline, rng, tamano_lote)
        etiquetadas = lote[lote[COL_LABEL].notna()]
        if "label_skew" in claves and baseline_label_rate is not None and len(etiquetadas):
            skew = label_skew(float(etiquetadas[COL_LABEL].mean()), baseline_label_rate)
            if skew is not None:
                valores["label_skew"].append(skew)
        if len(etiquetadas) < config.min_feedback:
            continue
        try:
            m = _calidad(etiquetadas, con_probabilidad=con_probabilidad)
        except DatosNoValidos as exc:
            motivo_dato_invalido = str(exc)
            continue
        for clave in claves:
            if clave == "label_skew":
                continue
            valor = m.get(clave)
            if isinstance(valor, (int, float)) and valor is not None:
                valores[clave].append(float(valor))
    return valores, motivo_dato_invalido


def proponer_umbrales(
    baseline: pd.DataFrame,
    monitor: MonitorType,
    *,
    tamano_lote: int = 1000,
    n_remuestreos: int = 200,
    cobertura: float = 0.99,
    semilla: int = 0,
    fairness_config: FairnessConfig | None = None,
    quality_config: QualityConfig | None = None,
    task: TaskSpec | None = None,
) -> list[PropuestaUmbral]:
    """Propone un umbral por cada métrica con umbral de fábrica en `monitor`
    (solo `fairness` y `quality`; cualquier otro, `ValueError`).

    La propuesta de equidad corre sobre el 0/1 de pertenencia de
    `prediction` y `label`, que es la forma de esas columnas en binario, en
    multiclase con conjunto favorable y en regresión con rango. Sin conjunto o sin
    rango favorable (`task`), la pertenencia no existe y no se lista ninguna
    medida. En regresión la calidad no tiene valor de fábrica que proponer: sus
    umbrales salen de `umbrales_linea_base_regresion`."""
    if monitor not in (MonitorType.fairness, MonitorType.quality):
        raise ValueError(f"proponer_umbrales solo calibra fairness y quality, no {monitor!r}")
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "regression":
            if monitor == MonitorType.quality or task.sin_rango_favorable:  # type: ignore[union-attr]
                return []
        case "multiclass":
            if monitor == MonitorType.fairness and task.sin_conjunto_favorable:  # type: ignore[union-attr]
                return []
        case "binary":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")

    fabrica = defaults_for(monitor)
    if not fabrica.thresholds:
        return []

    claves = {t.metric_key for t in fabrica.thresholds}

    if len(baseline) == 0:
        motivo_vacio = "la línea base está vacía: no se puede calibrar"
        return [
            PropuestaUmbral(
                metric_key=t.metric_key,
                kind=t.kind,
                value=None,
                valor_linea_base=None,
                motivo=motivo_vacio,
            )
            for t in fabrica.thresholds
        ]

    rng = np.random.default_rng(semilla)
    motivo_dato_invalido: str | None = None
    motivo_prob: str | None = None

    if monitor == MonitorType.fairness:
        cfg_f = fairness_config or FairnessConfig()
        valores = _valores_fairness(
            baseline,
            rng=rng,
            tamano_lote=tamano_lote,
            n_remuestreos=n_remuestreos,
            config=cfg_f,
            claves=claves,
        )
        entera = fairness_metrics(baseline, min_group=cfg_f.min_group)
        motivo_entera = entera.get("motivo")
    else:
        cfg_q = quality_config or QualityConfig()
        etiquetadas_enteras = baseline[baseline[COL_LABEL].notna()]
        motivo_prob = _probabilidad_invalida(etiquetadas_enteras)
        con_prob = motivo_prob is None
        valores, motivo_dato_invalido = _valores_quality(
            baseline,
            rng=rng,
            tamano_lote=tamano_lote,
            n_remuestreos=n_remuestreos,
            config=cfg_q,
            claves=claves,
            con_probabilidad=con_prob,
        )
        if len(etiquetadas_enteras) < cfg_q.min_feedback:
            entera = dict.fromkeys(claves)
            motivo_entera = (
                f"la línea base tiene {len(etiquetadas_enteras)} filas con etiqueta, "
                f"se pedían {cfg_q.min_feedback}: no se puede calibrar calidad"
            )
        else:
            try:
                entera = _calidad(etiquetadas_enteras, con_probabilidad=con_prob)
                entera["label_skew"] = 0.0
                motivo_entera = None
            except DatosNoValidos as exc:
                entera = dict.fromkeys(claves)
                motivo_entera = str(exc)

    propuestas: list[PropuestaUmbral] = []
    for t in fabrica.thresholds:
        muestras = valores.get(t.metric_key, [])
        valor_base = entera.get(t.metric_key)
        if not muestras:
            sin_prob = monitor == MonitorType.quality and t.metric_key in _CLAVES_CON_PROBABILIDAD
            motivo = (motivo_prob if sin_prob else None) or motivo_entera or motivo_dato_invalido or (
                f"sin remuestreos válidos para {t.metric_key}: revisa la línea base"
            )
            propuestas.append(
                PropuestaUmbral(
                    metric_key=t.metric_key,
                    kind=t.kind,
                    value=None,
                    valor_linea_base=valor_base,
                    motivo=motivo,
                )
            )
            continue
        p = float(np.percentile(muestras, _percentil_de_cobertura(t.kind, cobertura)))
        propuesto = _acotar(t.metric_key, _empujar_con_margen(p, kind=t.kind), monitor)
        propuestas.append(
            PropuestaUmbral(
                metric_key=t.metric_key,
                kind=t.kind,
                value=round(propuesto, 6),
                valor_linea_base=valor_base,
                motivo=None,
            )
        )
    return propuestas


# --------------------------------------------------------------------------
# Umbrales desde la línea base de un proyecto multiclase
# --------------------------------------------------------------------------


def monitor_de_umbral(metric_key: str) -> MonitorType:
    """Monitor al que pertenece una `metric_key` con umbral: el de calidad, el
    de deriva, el de equidad o el de explicabilidad, según los umbrales de
    fábrica. `ValueError` si la clave no tiene umbral en ninguno."""
    for monitor in (
        MonitorType.quality,
        MonitorType.drift,
        MonitorType.fairness,
        MonitorType.explain,
    ):
        if any(t.metric_key == metric_key for t in defaults_for(monitor).thresholds):
            return monitor
    # Las claves de regresión no tienen valor de fábrica, pero sí monitor.
    if metric_key in CLAVES_CALIDAD_REGRESION:
        return MonitorType.quality
    if metric_key in CLAVES_EQUIDAD_ERROR:
        return MonitorType.fairness
    raise ValueError(f"{metric_key!r} no es una métrica con umbral de ningún monitor")


def _js_distribuciones(a: np.ndarray, b: np.ndarray) -> float:
    """Distancia de Jensen-Shannon (base 2) entre dos vectores de recuentos, con
    el mismo recorte que `drift.drift_categorical` (`js`)."""
    from scipy.spatial.distance import jensenshannon

    p = np.clip(a / a.sum(), 1e-9, None)
    q = np.clip(b / b.sum(), 1e-9, None)
    return float(jensenshannon(p, q, base=2))


def umbrales_linea_base_multiclase(
    baseline: pd.DataFrame,
    task: TaskSpec,
    *,
    tamano_lote: int = 1000,
    n_remuestreos: int = 200,
    cobertura: float = 0.99,
    semilla: int = 0,
    quality_config: QualityConfig | None = None,
    min_group: int = 20,
) -> list[Threshold]:
    """Umbrales de un proyecto multiclase desde su línea base, con la regla
 (remuestreo, percentil de la cobertura y margen del 20 %).

    - `accuracy` (suelo de `1/k`), `f1_measure` y `area_under_roc` (macro), en
      el monitor `quality`: percentil 1 de las métricas de remuestreos de
      `tamano_lote` filas con etiqueta, empujado el 20 % hacia abajo.
    - `prediction_drift_score`, en el monitor `drift`: percentil 99 de la
      distancia de Jensen-Shannon entre la distribución de la clase predicha de
      dos remuestreos independientes de la línea base (cada uno del tamaño de
      un lote, para que el ruido sea el de un lote contra una línea base de
      tamaño parecido), empujado el 20 % hacia arriba.

    Todos con `origen="linea_base"`. Una métrica que no se puede calcular (por
    ejemplo el AUC con menos de dos clases con positivos y negativos) no
    aparece. `monitor_de_umbral(metric_key)` dice a qué monitor va cada uno."""
    match task.task_type:
        case "multiclass":
            pass
        case "binary" | "regression":
            raise ValueError("umbrales_linea_base_multiclase solo vale para un proyecto multiclase")
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task.task_type!r}")
    cfg = quality_config or QualityConfig()
    rng = np.random.default_rng(semilla)
    k = task.k
    etiquetadas_base = baseline[baseline[COL_LABEL].notna()]
    umbrales: list[Threshold] = []
    p_bajo = _percentil_de_cobertura(ThresholdKind.lower_limit, cobertura)
    p_alto = _percentil_de_cobertura(ThresholdKind.upper_limit, cobertura)
    margen = round(_MARGEN_RELATIVO * 100)
    nota = (
        f"propuesto desde la línea base: percentil {p_bajo:g} de {n_remuestreos} "
        f"remuestreos de {tamano_lote} filas, con margen del {margen} %"
    )

    if len(etiquetadas_base) >= cfg.min_feedback:
        valores: dict[str, list[float]] = {
            "accuracy": [],
            "f1_measure": [],
            "area_under_roc": [],
        }
        for _ in range(n_remuestreos):
            lote = _remuestrear(etiquetadas_base, rng, tamano_lote)
            if len(lote) < cfg.min_feedback:
                continue
            try:
                m = metricas_multiclase(lote, task, min_group=min_group)
            except DatosNoValidos:
                continue
            for clave, muestras in valores.items():
                v = m.get(clave)
                if isinstance(v, (int, float)):
                    muestras.append(float(v))
        for clave, muestras in valores.items():
            if not muestras:
                continue
            p = float(np.percentile(muestras, p_bajo))
            propuesto = _acotar(
                clave, _empujar_con_margen(p, kind=ThresholdKind.lower_limit), MonitorType.quality
            )
            valor = round(propuesto, 6)
            if clave == "accuracy":
                # suelo de 1/k (el azar), redondeado hacia arriba para no quedar por debajo
                valor = max(valor, math.ceil(1e6 / k) / 1e6)
            umbrales.append(
                Threshold(
                    metric_key=clave,
                    kind=ThresholdKind.lower_limit,
                    value=valor,
                    origen="linea_base",
                    nota=nota,
                )
            )

    # prediction_drift_score: JS entre dos remuestreos de la clase predicha
    if len(baseline) >= 2 and COL_PREDICTION_CLASS in baseline.columns:
        indice = {c: i for i, c in enumerate(task.claves)}
        clases = baseline[COL_PREDICTION_CLASS].map(indice).dropna().to_numpy(dtype=int)
        if len(clases):
            puntuaciones: list[float] = []
            for _ in range(n_remuestreos):
                a = np.bincount(rng.choice(clases, size=tamano_lote), minlength=k).astype(float)
                b = np.bincount(rng.choice(clases, size=tamano_lote), minlength=k).astype(float)
                puntuaciones.append(_js_distribuciones(a, b))
            p = float(np.percentile(puntuaciones, p_alto))
            umbrales.append(
                Threshold(
                    metric_key="prediction_drift_score",
                    kind=ThresholdKind.upper_limit,
                    value=round(_empujar_con_margen(p, kind=ThresholdKind.upper_limit), 6),
                    origen="linea_base",
                    nota=(
                        f"propuesto desde la línea base: percentil {p_alto:g} de "
                        f"{n_remuestreos} pares de remuestreos de {tamano_lote} filas, "
                        f"con margen del {margen} %"
                    ),
                )
            )
    return umbrales


# --------------------------------------------------------------------------
# Umbrales desde la línea base de un proyecto de regresión
# --------------------------------------------------------------------------


def _redondear_umbral(valor: float) -> float:
    """Seis decimales como mínimo y, si la unidad es pequeña (concentraciones de
    1e-7), seis cifras significativas: un MAE de 3e-7 no puede redondearse a 0."""
    if valor == 0 or not math.isfinite(valor):
        return valor
    return round(valor, max(6, 5 - math.floor(math.log10(abs(valor)))))


def _umbral(clave: str, kind: ThresholdKind, valor: float, nota: str) -> Threshold:
    acotado = _acotar(clave, valor, MonitorType.quality)
    return Threshold(
        metric_key=clave,
        kind=kind,
        value=_redondear_umbral(acotado),
        origen="linea_base",
        nota=nota,
    )


def umbrales_linea_base_regresion(
    baseline: pd.DataFrame,
    task: TaskSpec,
    *,
    tamano_lote: int = 1000,
    n_remuestreos: int = 200,
    cobertura: float = 0.99,
    semilla: int = 0,
    quality_config: QualityConfig | None = None,
    fairness_config: FairnessConfig | None = None,
    min_group: int = 20,
) -> list[Threshold]:
    """Umbrales de un proyecto de regresión desde su línea base. No hay
    valor de fábrica en unidades de la salida, así que todos salen de remuestreos
    de la línea base del tamaño de un lote (200 filas), con origen
    `linea_base`. Con `p1` y `p99` los percentiles de `1 - cobertura` y `cobertura`
    de la métrica en los remuestreos y `w = p99 - p1`:

    - `mean_absolute_error` y `root_mean_squared_error`: máximo `p99 + 0,2 w`.
    - `r2`: mínimo `p1 - 0,2 w` (con techo 1).
    - `mean_error` y `mean_error_difference`: mínimo `p1 - 0,2 w` y máximo
      `p99 + 0,2 w` (dos lados, con signo).
    - `mean_absolute_error_difference`: máximo `p99 + 0,2 w`.
    - `mean_absolute_error_ratio`: máximo `p99 x 1,2`.
    - `prediction_drift_score`: KS entre dos remuestreos independientes de la
      predicción de la línea base, máximo `p99 x 1,2`.

    El margen es aditivo donde la métrica puede valer 0 o ser negativa (un
    margen multiplicativo no empuja un sesgo cercano a 0). Una métrica que no se
    puede calcular (línea base con menos de `min_feedback` filas con etiqueta, un
    solo grupo, sin varianza del valor real para el R²) no aparece.
    `monitor_de_umbral(metric_key)` dice a qué monitor va cada una.

    Cada resultado lleva `origen="linea_base"`. `ValueError` si `task` no es una
    regresión."""
    match task.task_type:
        case "regression":
            pass
        case "binary" | "multiclass":
            raise ValueError(
                "umbrales_linea_base_regresion solo vale para un proyecto de regresión"
            )
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task.task_type!r}")
    cfg = quality_config or QualityConfig()
    min_grupo = fairness_config.min_group if fairness_config is not None else min_group
    rng = np.random.default_rng(semilla)
    p_bajo = _percentil_de_cobertura(ThresholdKind.lower_limit, cobertura)
    p_alto = _percentil_de_cobertura(ThresholdKind.upper_limit, cobertura)
    margen = round(_MARGEN_RELATIVO * 100)
    nota = (
        f"propuesto desde la línea base: percentiles {p_bajo:g} y {p_alto:g} de "
        f"{n_remuestreos} remuestreos de {tamano_lote} filas, con margen del {margen} %"
    )
    umbrales: list[Threshold] = []
    m_aditivo = _MARGEN_RELATIVO

    def banda(muestras: list[float]) -> tuple[float, float, float]:
        p1 = float(np.percentile(muestras, p_bajo))
        p99 = float(np.percentile(muestras, p_alto))
        return p1, p99, p99 - p1

    if COL_PREDICTION_VALUE not in baseline.columns or COL_LABEL_VALUE not in baseline.columns:
        etiquetadas = baseline.iloc[0:0]
    else:
        etiquetadas = baseline[
            np.isfinite(baseline[COL_PREDICTION_VALUE].to_numpy(dtype=float))
            & np.isfinite(baseline[COL_LABEL_VALUE].to_numpy(dtype=float))
        ]

    if len(etiquetadas) >= cfg.min_feedback:
        y = etiquetadas[COL_LABEL_VALUE].to_numpy(dtype=float)
        error = etiquetadas[COL_PREDICTION_VALUE].to_numpy(dtype=float) - y
        grupo = (
            etiquetadas[COL_GROUP].to_numpy()
            if COL_GROUP in etiquetadas.columns
            else np.full(len(etiquetadas), -1)
        )
        calidad: dict[str, list[float]] = {
            c: [] for c in ("mean_absolute_error", "root_mean_squared_error", "r2", "mean_error")
        }
        equidad: dict[str, list[float]] = {c: [] for c in CLAVES_EQUIDAD_ERROR}
        for _ in range(n_remuestreos):
            idx = rng.integers(0, len(etiquetadas), size=tamano_lote)
            e, yy, gg = error[idx], y[idx], grupo[idx]
            calidad["mean_absolute_error"].append(float(np.abs(e).mean()))
            calidad["root_mean_squared_error"].append(float(np.sqrt((e**2).mean())))
            calidad["mean_error"].append(float(e.mean()))
            if not varianza_nula(yy):
                ss_tot = float(((yy - yy.mean()) ** 2).sum())
                calidad["r2"].append(float(1.0 - (e**2).sum() / ss_tot))
            m0, m1 = gg == 0, gg == 1
            if m0.sum() >= min_grupo and m1.sum() >= min_grupo:
                mae0, mae1 = float(np.abs(e[m0]).mean()), float(np.abs(e[m1]).mean())
                equidad["mean_absolute_error_difference"].append(mae0 - mae1)
                if mae1 > 0:
                    equidad["mean_absolute_error_ratio"].append(mae0 / mae1)
                equidad["mean_error_difference"].append(float(e[m0].mean() - e[m1].mean()))

        for clave in ("mean_absolute_error", "root_mean_squared_error"):
            if calidad[clave]:
                _p1, p99, w = banda(calidad[clave])
                umbrales.append(_umbral(clave, ThresholdKind.upper_limit, p99 + m_aditivo * w, nota))
        if calidad["r2"]:
            p1, _p99, w = banda(calidad["r2"])
            umbrales.append(_umbral("r2", ThresholdKind.lower_limit, p1 - m_aditivo * w, nota))
        for clave, muestras in (
            ("mean_error", calidad["mean_error"]),
            ("mean_error_difference", equidad["mean_error_difference"]),
        ):
            if muestras:
                p1, p99, w = banda(muestras)
                umbrales.append(_umbral(clave, ThresholdKind.lower_limit, p1 - m_aditivo * w, nota))
                umbrales.append(_umbral(clave, ThresholdKind.upper_limit, p99 + m_aditivo * w, nota))
        if equidad["mean_absolute_error_difference"]:
            _p1, p99, w = banda(equidad["mean_absolute_error_difference"])
            umbrales.append(
                _umbral(
                    "mean_absolute_error_difference",
                    ThresholdKind.upper_limit,
                    p99 + m_aditivo * w,
                    nota,
                )
            )
        if equidad["mean_absolute_error_ratio"]:
            _p1, p99, _w = banda(equidad["mean_absolute_error_ratio"])
            umbrales.append(
                _umbral(
                    "mean_absolute_error_ratio",
                    ThresholdKind.upper_limit,
                    p99 * (1 + _MARGEN_RELATIVO),
                    nota,
                )
            )

    # prediction_drift_score: KS entre dos remuestreos independientes de la predicción.
    if COL_PREDICTION_VALUE in baseline.columns:
        from scipy import stats as sps

        pred = baseline[COL_PREDICTION_VALUE].to_numpy(dtype=float)
        pred = pred[np.isfinite(pred)]
        if len(pred) >= 2:
            ks = [
                float(
                    sps.ks_2samp(
                        rng.choice(pred, size=tamano_lote), rng.choice(pred, size=tamano_lote)
                    ).statistic
                )
                for _ in range(n_remuestreos)
            ]
            p99 = float(np.percentile(ks, p_alto))
            umbrales.append(
                Threshold(
                    metric_key="prediction_drift_score",
                    kind=ThresholdKind.upper_limit,
                    value=round(p99 * (1 + _MARGEN_RELATIVO), 6),
                    origen="linea_base",
                    nota=(
                        f"propuesto desde la línea base: percentil {p_alto:g} de "
                        f"{n_remuestreos} pares de remuestreos de {tamano_lote} filas, "
                        f"con margen del {margen} %"
                    ),
                )
            )
    return umbrales
