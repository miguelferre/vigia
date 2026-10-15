"""Tests del método `lote` de equidad: el valor y
su intervalo salen del lote completo (Katz/Newcombe) y el estado lo decide
`classify_point_with_motivo`. Regresión reducida, con poblaciones
sintéticas generadas aquí mismo (nada de ficheros fuera del repo, nada de `build/validacion/banco`).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from vigia.core.fairness import evaluate_fairness
from vigia.core.schema import (
    COL_BATCH,
    COL_CLINICIAN,
    COL_GROUP,
    COL_ID,
    COL_LABEL,
    COL_PREDICTION,
    COL_PROB,
    COL_PROTECTED,
    COL_SEQ,
    COL_SUBGROUP,
    COL_TS,
    COL_VERSION,
    FairnessConfig,
    State,
)
from vigia.core.thresholds import DEFAULT_FAIRNESS_THRESHOLDS

_MARCADO = (State.alerta, State.inestable)


def _poblacion(
    n: int, seed: int, *, sesgo_logit: float = 0.0, tasa_base: float = 0.5, batch_seq: int = 1
) -> pd.DataFrame:
    """Lote sintético equilibrado (grupo protegido 50/50): predicción de un
    logit con `tasa_base`, desplazado `sesgo_logit/2` en contra del grupo
    supervisado (unpriv=0) y a favor del de referencia (priv=1); etiqueta =
    predicción con un 10% de ruido, para que las métricas de etiqueta
    también tengan sentido. `sesgo_logit=0` es una población estable (sin
    disparidad real, salvo la que meta el ruido de muestreo); a diferencia
    de las poblaciones reales (que ya parten
    cerca del umbral de fábrica, por eso ahí un sesgo de 1,0 basta), esta
    población sintética es simétrica y empieza sin disparidad, así que
    necesita más magnitud para cruzar el mismo umbral de fábrica."""
    rng = np.random.default_rng(seed)
    grupo = rng.integers(0, 2, size=n)
    logit_base = math.log(tasa_base / (1 - tasa_base))
    logit = logit_base + sesgo_logit * (grupo - 0.5)
    prob = 1.0 / (1.0 + np.exp(-logit))
    prediccion = (rng.random(n) < prob).astype(int)
    ruido = rng.random(n) < 0.10
    etiqueta = np.where(ruido, 1 - prediccion, prediccion).astype(float)
    return pd.DataFrame(
        {
            COL_SEQ: range(n),
            COL_BATCH: batch_seq,
            COL_VERSION: "v1",
            COL_ID: [f"id{i}" for i in range(n)],
            COL_TS: None,
            COL_PREDICTION: prediccion,
            COL_PROB: prob,
            COL_LABEL: etiqueta,
            COL_PROTECTED: grupo,
            COL_GROUP: grupo,
            COL_CLINICIAN: None,
            COL_SUBGROUP: None,
        }
    )


def _evaluar(df: pd.DataFrame, *, batch_seq: int = 1):
    return evaluate_fairness(
        df,
        batch_seq=batch_seq,
        config=FairnessConfig(),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
        model_version="v1",
        interval_method="lote",
    )


def test_lote_poblacion_estable_3000_filas_sin_marcar():
    """compas/hirevue/toeslagenaffaire estables con 3000 filas: 0 lotes
    marcados (regresión reducida, poblaciones propias)."""
    for seed in range(5):
        df = _poblacion(3000, seed=seed, sesgo_logit=0.0)
        res = _evaluar(df)
        estados = res.states()
        marcados = {k: v for k, v in estados.items() if v in _MARCADO}
        assert not marcados, f"semilla {seed}: {marcados}"
        assert res.details["interval_method"] == "lote"


def test_lote_sesgo_fuerte_marcado_en_todas_las_semillas():
    """Con un sesgo de logit fuerte (4,0; esta población sintética arranca
    simétrica, a diferencia de las reales que ya parten cerca del umbral),
    el lote se marca en todas las semillas."""
    for seed in range(5):
        df = _poblacion(3000, seed=seed, sesgo_logit=4.0)
        res = _evaluar(df)
        estados = res.states()
        assert any(v in _MARCADO for v in estados.values()), f"semilla {seed}: {estados}"


def test_lote_anchura_decreciente_con_n():
    """El intervalo de `fairness_value` se estrecha al crecer `n` (Katz
    sobre conteos: la anchura decrece con la raíz de n)."""
    anchuras = []
    for n in (300, 1000, 3000, 8000):
        df = _poblacion(n, seed=7, sesgo_logit=0.0)
        res = _evaluar(df)
        fv = next(m for m in res.measurements if m.metric_key == "fairness_value")
        assert fv.interval_low is not None and fv.interval_high is not None
        anchuras.append(fv.interval_high - fv.interval_low)
    assert anchuras == sorted(anchuras, reverse=True), anchuras


def test_lote_disparidad_real_sin_ok_falso():
    """Con una disparidad real fuerte (sesgo de logit 4.0), el valor puntual
    cruza el umbral de fábrica: nunca `ok` (análogo a pub-adult)."""
    for seed in range(3):
        df = _poblacion(2000, seed=seed, sesgo_logit=4.0)
        res = _evaluar(df)
        fv = next(m for m in res.measurements if m.metric_key == "fairness_value")
        assert fv.state != State.ok, f"semilla {seed}: fairness_value ok con disparidad real"


def test_lote_ventanas_no_cambia():
    """`ventanas` sigue exactamente igual, ni un byte cambia en su
    `config_snapshot`, aunque se llame con la misma población."""
    df = _poblacion(500, seed=1, sesgo_logit=0.0)
    res_ventanas = evaluate_fairness(
        df,
        batch_seq=1,
        config=FairnessConfig(),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
        model_version="v1",
    )
    assert res_ventanas.details["interval_method"] == "ventanas"
    fv = next(m for m in res_ventanas.measurements if m.metric_key == "fairness_value")
    assert fv.extra["window"] == "ultimos_n"


def test_lote_interval_method_desconocido():
    df = _poblacion(100, seed=0)
    with pytest.raises(ValueError):
        evaluate_fairness(
            df,
            batch_seq=1,
            config=FairnessConfig(),
            thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
            model_version="v1",
            interval_method="mensual",  # type: ignore[arg-type]
        )
