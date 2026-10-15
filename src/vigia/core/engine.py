"""engine — Orquestación pura del motor: `MonitorSettings`, `History`,
`evaluate_batch` y `run_scenario`. Sin base de datos, sin I/O salvo el que
ya hacen `vigia.sim.scenarios.materialize_phase` (lectura de enlatados) y
los generadores. Funciones puras y una clase de estado explícito
(`History`), nunca estado global mutable.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from vigia.core.drift import evaluate_drift
from vigia.core.explain import evaluate_explain
from vigia.core.fairness import evaluate_fairness
from vigia.core.loaders import concat_history, to_canonical
from vigia.core.quality import evaluate_quality
from vigia.core.schema import (
    COL_BATCH,
    COL_LABEL,
    COL_SEQ,
    COL_VERSION,
    HARNESS_FEEDBACK_MAPPING,
    ColumnMapping,
    CrossAlertResult,
    DriftConfig,
    EvaluationResult,
    ExplanationResult,
    FairnessConfig,
    MonitorThresholds,
    QualityConfig,
    State,
    TaskSpec,
    es_columna_canonica,
)
from vigia.core.thresholds import (
    DEFAULT_DRIFT_CONFIG,
    DEFAULT_DRIFT_THRESHOLDS,
    DEFAULT_EXPLAIN_THRESHOLDS,
    DEFAULT_FAIRNESS_CONFIG,
    DEFAULT_FAIRNESS_THRESHOLDS,
    DEFAULT_QUALITY_CONFIG,
    DEFAULT_QUALITY_THRESHOLDS,
)
from vigia.human.cross_alerts import CrossReference, build_reference, evaluate_cross
from vigia.sim.human import HumanParams, simulate_decisions
from vigia.sim.scenarios import get_scenario, materialize_phase, phase_sequence

_START_DATE = date(2026, 1, 5)


class MonitorSettings(BaseModel):
    """Configuración de los tres monitores más sus umbrales, en un único
    objeto que viaja por `evaluate_batch` y queda en `config_snapshot`.
    """

    fairness: FairnessConfig = Field(default_factory=FairnessConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    drift: DriftConfig = Field(default_factory=DriftConfig)
    thresholds: dict[str, MonitorThresholds] = Field(default_factory=dict)

    @classmethod
    def defaults(cls) -> MonitorSettings:
        return cls(
            fairness=DEFAULT_FAIRNESS_CONFIG.model_copy(deep=True),
            quality=DEFAULT_QUALITY_CONFIG.model_copy(deep=True),
            drift=DEFAULT_DRIFT_CONFIG.model_copy(deep=True),
            thresholds={
                "fairness": DEFAULT_FAIRNESS_THRESHOLDS.model_copy(deep=True),
                "quality": DEFAULT_QUALITY_THRESHOLDS.model_copy(deep=True),
                "drift": DEFAULT_DRIFT_THRESHOLDS.model_copy(deep=True),
                "explain": DEFAULT_EXPLAIN_THRESHOLDS.model_copy(deep=True),
            },
        )


class PhaseReport(BaseModel):
    """Resultado de evaluar una fase de un guion: los tres monitores, su
    peor estado, la comparación con lo esperado por el guion y, si se pidió
    `with_human`, las alertas cruzadas sobre el diario acumulado.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    phase_key: str
    batch_seq: int
    model_version: str
    n: int
    orden_manipulado: bool
    results: dict[str, EvaluationResult]
    states: dict[str, State]
    expected: dict[str, str]
    matches_expected: dict[str, bool]
    cross: CrossAlertResult | None = None


class History:
    """Acumulador de batches canónicos, en memoria, sin base de datos.

    Cada `add_batch` reasigna `batch_seq` (correlativo, salvo que se fuerce
    uno) y recalcula `seq` global sobre toda la historia con
    `concat_history` (el orden de ingesta es el que manda en las
    ventanas deslizantes de equidad). El baseline congelado, la referencia
    de alertas cruzadas y la explicación de referencia se
    guardan por versión de modelo.
    """

    def __init__(self) -> None:
        self._frames: list[pd.DataFrame] = []
        self._meta: list[dict[str, Any]] = []
        self._next_batch_seq = 0
        self._baseline: dict[str, pd.DataFrame] = {}
        self._reference: dict[str, CrossReference] = {}
        self._explain_reference: dict[str, ExplanationResult] = {}

    def add_batch(
        self,
        df_canonical_raw: pd.DataFrame,
        *,
        mapping: ColumnMapping,
        model_version: str,
        batch_seq: int | None = None,
        phase_label: str | None = None,
        orden_manipulado: bool = False,
        motivo: str | None = None,
    ) -> int:
        seq = batch_seq if batch_seq is not None else self._next_batch_seq
        self._next_batch_seq = max(self._next_batch_seq, seq + 1)
        df = df_canonical_raw.copy()
        df[COL_BATCH] = seq
        df[COL_VERSION] = model_version
        self._frames.append(df)
        self._meta.append(
            {
                "batch_seq": seq,
                "n": len(df),
                "model_version": model_version,
                "phase_label": phase_label,
                "orden_manipulado": orden_manipulado,
                "motivo": motivo,
                "is_baseline": False,
                "mapping": mapping,
            }
        )
        return seq

    def frame(self) -> pd.DataFrame:
        if not self._frames:
            raise ValueError("History: no hay batches todavía")
        return concat_history(self._frames)

    def batch(self, batch_seq: int) -> pd.DataFrame:
        frame = self.frame()
        return frame[frame[COL_BATCH] == batch_seq]

    def freeze_baseline(self, batch_seq: int, model_version: str) -> None:
        self._baseline[model_version] = self.batch(batch_seq).copy()
        for meta in self._meta:
            if meta["batch_seq"] == batch_seq and meta["model_version"] == model_version:
                meta["is_baseline"] = True

    def baseline_for(self, model_version: str) -> pd.DataFrame | None:
        return self._baseline.get(model_version)

    def label_rate_baseline(self, model_version: str) -> float | None:
        baseline = self._baseline.get(model_version)
        if baseline is None or not baseline[COL_LABEL].notna().any():
            return None
        return float(baseline[COL_LABEL].mean())

    def set_reference(self, model_version: str, reference: CrossReference) -> None:
        self._reference[model_version] = reference

    def reference_for(self, model_version: str) -> CrossReference | None:
        return self._reference.get(model_version)

    def set_explain_reference(self, model_version: str, explanation: ExplanationResult) -> None:
        """Fija la explicación global de referencia de una versión,
        paralelo a `freeze_baseline`: la fija quien orquesta (el guion o el
        reproductor), no `evaluate_batch`.
        """
        self._explain_reference[model_version] = explanation

    def explain_reference_for(self, model_version: str) -> ExplanationResult | None:
        return self._explain_reference.get(model_version)

    @property
    def batches(self) -> list[dict[str, Any]]:
        claves = (
            "batch_seq",
            "n",
            "model_version",
            "phase_label",
            "orden_manipulado",
            "motivo",
            "is_baseline",
        )
        return [{k: meta[k] for k in claves} for meta in self._meta]


def _default_feature_cols(frame: pd.DataFrame) -> list[str]:
    heredadas = HARNESS_FEEDBACK_MAPPING.feature_cols
    if all(c in frame.columns for c in heredadas):
        return list(heredadas)
    return [c for c in frame.columns if not es_columna_canonica(c)]


def _batch_meta(history: History, batch_seq: int) -> dict[str, Any]:
    for meta in history.batches:
        if meta["batch_seq"] == batch_seq:
            return meta
    raise KeyError(f"batch_seq {batch_seq} no está en la historia")


def _drift_baseline_frame(
    history: History, *, model_version: str, batch_seq: int, drift_config: DriftConfig
) -> pd.DataFrame:
    """Frame contra el que comparar el batch actual en el monitor de
    deriva: el baseline congelado de la versión (`baseline_mode="frozen"`,
    por defecto) o el batch inmediatamente anterior de la misma versión
    (`baseline_mode="previous_batch"`). Si no hay ninguno, un frame vacío
    (mismas columnas) para que `evaluate_drift` lo trate como `sin_datos`
    con motivo, sin romper por índice fuera de rango.
    """
    frame = history.frame()
    if drift_config.baseline_mode == "previous_batch":
        anteriores = sorted(
            m["batch_seq"]
            for m in history.batches
            if m["model_version"] == model_version and m["batch_seq"] < batch_seq
        )
        if not anteriores:
            return frame.iloc[0:0]
        return history.batch(anteriores[-1])

    baseline = history.baseline_for(model_version)
    if baseline is None:
        return frame.iloc[0:0]
    return baseline


def evaluate_batch(
    history: History,
    batch_seq: int,
    settings: MonitorSettings,
    *,
    feature_cols: list[str] | None = None,
    explanation: ExplanationResult | None = None,
    fairness_interval_method: Literal["ventanas", "lote"] = "ventanas",
    columna_probabilidad: str | None = None,
    task: TaskSpec | None = None,
) -> dict[str, EvaluationResult]:
    """Evalúa un batch ya en `history` en los tres monitores, y en el de
    explicabilidad si se pasa `explanation`.

    `fairness_interval_method` es el método del intervalo de
    equidad de la versión; con "ventanas", el de siempre, nada cambia.
    `columna_probabilidad` es el nombre de la columna en el fichero
    del usuario, para que el mensaje de `DatosNoValidos` la nombre.

    Fairness sobre la ventana de últimos `min_records` de la versión del
    batch (implementado dentro de `evaluate_fairness`);
    quality con acumulación de batches con etiqueta y el `label_rate` del
    baseline congelado (`label_skew`); drift del batch contra el
    baseline congelado de su versión, o contra el batch anterior si
    `drift.baseline_mode == "previous_batch"`; si la versión no tiene
    baseline congelado (ni, en modo `previous_batch`, batch anterior),
    drift sale `sin_datos` con motivo.

    `explanation` es la explicación global ya calculada para este
    batch (calcularla requiere `predict_fn`, que el motor no tiene: la
    calcula quien orquesta, guion o reproductor, y la pasa aquí). Si se
    pasa, se añade la clave `"explain"` con el resultado de comparar
    `explanation` contra `history.explain_reference_for(model_version)`
    (`sin_datos` con motivo si esa versión todavía no tiene referencia
    fijada con `History.set_explain_reference`). Si no se pasa, el
    comportamiento es exactamente el de antes: sin clave `"explain"`.

    `task` es el `TaskSpec` del proyecto. Con `task=None` o binario,
    todo da lo mismo que antes (los 31 números); con multiclase,
    calidad macro y por clase, deriva de la clase predicha y equidad por
    conjunto favorable.
    """
    frame = history.frame()
    meta = _batch_meta(history, batch_seq)
    model_version = meta["model_version"]

    fairness_result = evaluate_fairness(
        frame,
        batch_seq=batch_seq,
        config=settings.fairness,
        thresholds=settings.thresholds["fairness"],
        model_version=model_version,
        interval_method=fairness_interval_method,
        task=task,
    )

    baseline_label_rate = history.label_rate_baseline(model_version)
    sin_tasa = task is not None and (task.sin_conjunto_favorable or task.sin_rango_favorable)
    if sin_tasa:
        # Sin conjunto favorable o sin rango favorable `label` vale
        # 0 en toda fila; la tasa de etiqueta de la línea base no existe, no es 0.
        # Con rango, `label` es la pertenencia, no la media del valor real.
        baseline_label_rate = None
    quality_result = evaluate_quality(
        frame,
        batch_seq=batch_seq,
        config=settings.quality,
        thresholds=settings.thresholds["quality"],
        baseline_label_rate=baseline_label_rate,
        model_version=model_version,
        columna_probabilidad=columna_probabilidad,
        task=task,
        baseline=history.baseline_for(model_version),
        min_group=settings.fairness.min_group,
    )

    if baseline_label_rate is None and not sin_tasa:
        # Sin línea base congelada, `label_skew` queda `sin_datos` y el
        # monitor lo enumera con este motivo.
        for medida in quality_result.measurements:
            if (
                medida.metric_key == "label_skew"
                and medida.state == State.sin_datos
                and medida.motivo is None
            ):
                medida.motivo = "sin línea base congelada para esta versión"

    cols = feature_cols if feature_cols is not None else _default_feature_cols(frame)
    df_baseline = _drift_baseline_frame(
        history, model_version=model_version, batch_seq=batch_seq, drift_config=settings.drift
    )
    df_current = history.batch(batch_seq)
    drift_result = evaluate_drift(
        df_baseline,
        df_current,
        config=settings.drift,
        thresholds=settings.thresholds["drift"],
        feature_cols=cols,
        batch_seq=batch_seq,
        model_version=model_version,
        task=task,
    )

    resultados = {"fairness": fairness_result, "quality": quality_result, "drift": drift_result}

    if explanation is not None:
        referencia = history.explain_reference_for(model_version)
        resultados["explain"] = evaluate_explain(
            explanation,
            referencia,
            thresholds=settings.thresholds.get("explain", DEFAULT_EXPLAIN_THRESHOLDS),
            model_version=model_version,
            batch_seq=batch_seq,
        )

    return resultados


def matches_expected(monitor_key: str, actual: State, expected_key: str) -> bool:
    """Regla de coincidencia con `Phase.expected` (los resultados esperados
    del harness solo distinguen OK de ALERT):

    - esperado `ok`: coinciden `ok` y `aviso` (la banda del 10 % sobre el
      umbral no es una alerta; el baseline E1 tiene accuracy 0,88 con umbral
      0,80 y sale `aviso`).
    - esperado `alerta` en `fairness`: coinciden `alerta` e `inestable`
      (la ventana de últimos N puede caer en el borde e informar
      `inestable` según el offset sin que eso sea un fallo del guion).
    - resto: igualdad estricta con el estado esperado.
    """
    if expected_key == "ok":
        return actual in (State.ok, State.aviso)
    if monitor_key == "fairness" and expected_key == "alerta":
        return actual in (State.alerta, State.inestable)
    return actual.value == expected_key


# Alias privado retenido para no romper referencias internas existentes.
_matches_expected = matches_expected


def _harness_scored_mapping() -> ColumnMapping:
    return HARNESS_FEEDBACK_MAPPING.model_copy(
        update={
            "prediction_col": "PREDICTION",
            "probability_col": "PROBABILITIES",
            "probability_format": "list",
            "probability_index": 1,
            "label_col": "Has_Referral_in_Window",
        }
    )


def run_scenario(
    scenario_key: str,
    *,
    source: Literal["canned", "generate"] = "canned",
    settings: MonitorSettings | None = None,
    params_override: dict[str, Any] | None = None,
    with_human: bool = False,
    human_seed: int = 0,
    data_dir: Path | None = None,
) -> list[PhaseReport]:
    """Recorre las fases de un guion (`vigia.sim.scenarios`), las evalúa en
    los tres monitores y, si `with_human`, simula el diario de uso y las
    alertas cruzadas sobre la ventana acumulada de la versión activa.

    La primera fase de cada versión de modelo se toma en modo `calibracion`
    (fija la referencia de override/error, guardada en `History`); el resto,
    en `vigilancia` contra esa referencia. `model_alert_groups` se fija a
    `{"18-35"}` cuando el peor estado de fairness de la fase es `alerta` o
    `inestable` (el guion solo modela sesgo en ese subgrupo), y se mantiene en
    las fases siguientes de la versión (sin personas, la alerta de
    equidad no se cierra); las CX-1 abiertas en la versión siguen vivas y callan
    CX-6 en su grupo.
    """
    settings = settings or MonitorSettings.defaults()
    scenario = get_scenario(scenario_key)
    history = History()
    mapping = _harness_scored_mapping()

    human_params: HumanParams | None = None
    if with_human:
        human_kwargs = {
            **scenario.human_params,
            **((params_override or {}).get("human") or {}),
        }
        human_params = HumanParams(**human_kwargs)
    usage_por_version: dict[str, list[pd.DataFrame]] = {}
    calibrado: set[str] = set()
    equidad_senalada: set[str] = set()
    cx1_vivas: dict[str, set[str]] = {}

    fases = phase_sequence(scenario)
    n_fases = len(fases)
    reports: list[PhaseReport] = []

    for i, phase in fases:
        phase_data = materialize_phase(
            phase, source=source, params_override=params_override, data_dir=data_dir
        )
        df_canon = to_canonical(
            phase_data.df_scored, mapping, batch_seq=0, model_version=phase.model_version
        )
        batch_seq = history.add_batch(
            df_canon,
            mapping=mapping,
            model_version=phase.model_version,
            phase_label=phase.key,
            orden_manipulado=phase.orden_manipulado,
            motivo=phase.motivo_manipulacion,
        )
        if phase.freeze_baseline:
            history.freeze_baseline(batch_seq, phase.model_version)

        results = evaluate_batch(history, batch_seq, settings)
        states = {k: v.worst_state for k, v in results.items()}
        matches_expected = {
            k: _matches_expected(k, states[k], v) for k, v in phase.expected.items()
        }

        cross_result = None
        if with_human:
            cross_result = _evaluar_cruzadas(
                history,
                phase=phase,
                phase_data=phase_data,
                index=i,
                n_fases=n_fases,
                batch_seq=batch_seq,
                human_seed=human_seed,
                human_params=human_params,
                usage_por_version=usage_por_version,
                calibrado=calibrado,
                fairness_worst=states["fairness"],
                equidad_senalada=equidad_senalada,
                cx1_vivas=cx1_vivas,
            )

        reports.append(
            PhaseReport(
                phase_key=phase.key,
                batch_seq=batch_seq,
                model_version=phase.model_version,
                n=len(df_canon),
                orden_manipulado=phase.orden_manipulado,
                results=results,
                states=states,
                expected=phase.expected,
                matches_expected=matches_expected,
                cross=cross_result,
            )
        )

    return reports


def _evaluar_cruzadas(
    history: History,
    *,
    phase: Any,
    phase_data: Any,
    index: int,
    n_fases: int,
    batch_seq: int,
    human_seed: int,
    human_params: HumanParams | None,
    usage_por_version: dict[str, list[pd.DataFrame]],
    calibrado: set[str],
    fairness_worst: State,
    equidad_senalada: set[str],
    cx1_vivas: dict[str, set[str]],
) -> CrossAlertResult:
    """Simula el diario de uso de la fase y evalúa las cruzadas sobre el
    acumulado de la versión activa: `calibracion` en la primera
    fase de cada versión, `vigilancia` en las siguientes.
    """
    version = phase.model_version
    t_start = index / n_fases
    t_end = (index + 1) / n_fases
    phase_start_date = _START_DATE + timedelta(days=7 * index)
    record_seq_start = int(history.batch(batch_seq)[COL_SEQ].min())

    usage_df = simulate_decisions(
        phase_data.df_scored,
        seed=human_seed + index,
        params=human_params,
        t_start=t_start,
        t_end=t_end,
        start_date=phase_start_date,
        model_version=version,
        record_seq_start=record_seq_start,
    )
    usage_por_version.setdefault(version, []).append(usage_df)
    acumulado = pd.concat(usage_por_version[version], ignore_index=True)
    if fairness_worst in (State.alerta, State.inestable):
        equidad_senalada.add(version)

    if version not in calibrado:
        calibrado.add(version)
        referencia = build_reference(acumulado)
        history.set_reference(version, referencia)
        return evaluate_cross(acumulado, mode="calibracion")

    # Sin personas, una alerta de equidad abierta en la versión no
    # se cierra nunca, así que el grupo sigue excluido aunque fairness vuelva a ok
    # (refleja `services/human_layer._model_alert_groups`).
    equidad_viva = version in equidad_senalada
    model_alert_groups = (
        {"18-35"} if fairness_worst in (State.alerta, State.inestable) or equidad_viva else set()
    )
    resultado = evaluate_cross(
        acumulado,
        reference=history.reference_for(version),
        model_alert_groups=model_alert_groups,
        mode="vigilancia",
        cx1_alert_groups=cx1_vivas.get(version),
    )
    # La CX-1 que abre aquí sigue viva en las fases siguientes.
    cx1_vivas.setdefault(version, set()).update(
        a.group for a in resultado.alerts if a.rule == "CX-1" and a.group is not None
    )
    return resultado
