"""Despacho exhaustivo en el motor y `to_canonical` de regresión."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from vigia.core.drift import evaluate_drift
from vigia.core.engine import MonitorSettings, _default_feature_cols, evaluate_batch
from vigia.core.fairness import evaluate_fairness
from vigia.core.loaders import (
    avisos_clases,
    avisos_regresion,
    detectar_cardinalidad_binaria,
    to_canonical,
)
from vigia.core.quality import evaluate_quality, quality_metrics
from vigia.core.schema import (
    CLAVES_SOLO_CLASIFICACION,
    COL_LABEL,
    COL_LABEL_VALUE,
    COL_PREDICTION,
    COL_PREDICTION_VALUE,
    COL_PROB,
    DatosNoValidos,
    DriftConfig,
    FairnessConfig,
    MonitorThresholds,
    QualityConfig,
    TaskSpec,
    es_columna_canonica,
)

from ._datos_regresion import RANGO_ALTO, crudo, historia, mapeo, tarea

# --------------------------------------------------------------------------
# To_canonical de regresión
# --------------------------------------------------------------------------


def test_con_rango_guarda_el_valor_y_la_pertenencia():
    df = pd.DataFrame(
        {"id": list("wxyz"), "p": [10.5, 37.2, 55.0, 81.0], "y": [12, 40, 56.0, None], "g": list("abab"), "x": [1, 2, 3, 4]}
    )
    canon = to_canonical(df, mapeo(), task=tarea())
    assert canon[COL_PREDICTION_VALUE].tolist() == [10.5, 37.2, 55.0, 81.0]
    assert canon[COL_PREDICTION_VALUE].dtype == float
    assert canon[COL_LABEL_VALUE].dtype == float
    assert np.isnan(canon[COL_LABEL_VALUE].iloc[3])
    # pertenencia a [55, +inf): extremo incluido
    assert canon[COL_PREDICTION].tolist() == [0, 0, 1, 1]
    assert canon[COL_PREDICTION].dtype.kind == "i"
    assert canon[COL_LABEL].iloc[:3].tolist() == [0.0, 0.0, 1.0]
    assert np.isnan(canon[COL_LABEL].iloc[3])


def test_un_valor_continuo_no_se_aplana_a_cero():
    # El defecto: 37,2 contra la favorable 1 daba False y se guardaba 0.
    df = pd.DataFrame({"id": ["i", "j"], "p": [37.2, 61.7], "y": [37.2, 61.7], "g": list("ab"), "x": [1, 2]})
    canon = to_canonical(df, mapeo(), task=tarea())
    assert canon[COL_PREDICTION_VALUE].tolist() == [37.2, 61.7]
    assert canon[COL_LABEL_VALUE].tolist() == [37.2, 61.7]


def test_sin_rango_prediction_es_0_y_label_es_0_con_etiqueta_y_nulo_sin_ella():
    df = pd.DataFrame({"id": ["i", "j", "k"], "p": [10.0, 90.0, 50.0], "y": [12.0, None, 40.0], "g": list("aba"), "x": [1, 2, 3]})
    canon = to_canonical(df, mapeo(rangos=[]), task=tarea(rangos=[]))
    assert canon[COL_PREDICTION].tolist() == [0, 0, 0]
    assert canon[COL_LABEL].iloc[0] == 0.0 and canon[COL_LABEL].iloc[2] == 0.0
    assert np.isnan(canon[COL_LABEL].iloc[1])  # el filtro «tiene etiqueta» sigue valiendo
    assert canon[COL_PREDICTION_VALUE].tolist() == [10.0, 90.0, 50.0]


def test_sin_probabilidad_ni_columnas_de_clase():
    canon = to_canonical(crudo(20), mapeo(), task=tarea())
    for columna in (COL_PROB, "prediction_class", "label_class", "prob__0"):
        assert columna not in canon.columns


def test_los_valores_no_son_variables_del_modelo():
    canon = to_canonical(crudo(30), mapeo(), task=tarea())
    assert es_columna_canonica(COL_PREDICTION_VALUE) and es_columna_canonica(COL_LABEL_VALUE)
    assert COL_PREDICTION_VALUE not in _default_feature_cols(canon)
    assert COL_LABEL_VALUE not in _default_feature_cols(canon)
    assert "x" in _default_feature_cols(canon)


def test_prediccion_con_unidad_pegada_da_datos_no_validos_con_recuento_y_fila():
    df = crudo(10)
    df["p"] = df["p"].astype(object)
    df.loc[3, "p"] = "12 h"
    with pytest.raises(DatosNoValidos) as exc:
        to_canonical(df, mapeo(), task=tarea())
    mensaje = str(exc.value)
    assert "1 de 10" in mensaje and "fila 4" in mensaje and "12 h" in mensaje
    assert "unidad" in mensaje


@pytest.mark.parametrize("malo", [None, float("nan"), float("inf"), float("-inf"), "n/d"])
def test_prediccion_vacia_nan_infinita_o_de_texto_detiene_la_ingesta(malo):
    df = crudo(10)
    df["p"] = df["p"].astype(object)
    df.loc[0, "p"] = malo
    with pytest.raises(DatosNoValidos, match="1 de 10"):
        to_canonical(df, mapeo(), task=tarea())


def test_etiqueta_de_texto_o_infinita_queda_sin_etiqueta_y_se_avisa():
    df = crudo(10)
    df["y"] = df["y"].astype(object)
    df.loc[1, "y"] = "12 h"
    df.loc[2, "y"] = float("inf")
    df.loc[3, "y"] = None  # vacía: sin etiqueta, sin aviso
    canon = to_canonical(df, mapeo(), task=tarea())
    assert canon[COL_LABEL_VALUE].isna().tolist()[:4] == [False, True, True, True]
    avisos = avisos_regresion(df, mapeo(), tarea())
    assert len(avisos) == 1 and avisos[0].startswith("2 filas")


def test_avisos_de_prediccion_constante_y_de_pocos_valores():
    constante = crudo(10)
    constante["p"] = 30.0
    avisos = avisos_regresion(constante, mapeo(), tarea())
    assert any("mismo valor" in a for a in avisos)
    dos = crudo(10)
    dos["p"] = [10.0, 20.0] * 5
    assert any("clasificación" in a for a in avisos_regresion(dos, mapeo(), tarea()))
    assert avisos_regresion(crudo(50), mapeo(), tarea()) == []


def test_avisos_regresion_vacios_en_clasificacion_y_avisos_clases_vacios_en_regresion():
    assert avisos_regresion(crudo(10), mapeo(), TaskSpec.binario()) == []
    assert avisos_clases(crudo(10), mapeo(), tarea(), es_linea_base=True) == []
    assert detectar_cardinalidad_binaria(crudo(10), mapeo(), tarea()) == []


# --------------------------------------------------------------------------
# Despacho exhaustivo
# --------------------------------------------------------------------------


def _claves_publicadas(resultados) -> set[str]:
    return {m.metric_key for r in resultados.values() for m in r.measurements}


@pytest.mark.parametrize("rangos", [RANGO_ALTO, []], ids=["con_rango", "sin_rango"])
@pytest.mark.parametrize("metodo", ["ventanas", "lote"])
def test_una_evaluacion_de_regresion_no_publica_ninguna_clave_de_clasificacion(rangos, metodo):
    h, t = historia([crudo(400, seed=0), crudo(400, seed=1, recorte=6)], rangos)
    resultados = evaluate_batch(
        h, 1, MonitorSettings.defaults(), task=t, fairness_interval_method=metodo
    )
    publicadas = _claves_publicadas(resultados)
    assert publicadas.isdisjoint(CLAVES_SOLO_CLASIFICACION), publicadas & set(CLAVES_SOLO_CLASIFICACION)
    # y no deja nada de clasificación en el detalle
    detalle = resultados["drift"].details
    assert "confidence" not in detalle and "by_class" not in str(detalle.get("prediction", {}))
    assert "confusion" not in resultados["quality"].details
    assert resultados["quality"].details["task_type"] == "regression"


def test_batch_sin_filas_de_regresion_tampoco_publica_claves_de_clasificacion():
    h, t = historia([crudo(200)])
    resultado = evaluate_quality(
        h.frame(),
        batch_seq=99,
        config=QualityConfig(),
        thresholds=MonitorThresholds(),
        task=t,
    )
    claves = {m.metric_key for m in resultado.measurements}
    assert claves.isdisjoint(CLAVES_SOLO_CLASIFICACION)
    assert {"mean_absolute_error", "r2"} <= claves
    assert all(m.state.value == "sin_datos" for m in resultado.measurements)


def test_deriva_con_linea_base_vacia_no_crea_la_confianza_en_regresion():
    h, t = historia([crudo(100)])
    vacio = h.frame().iloc[0:0]
    resultado = evaluate_drift(
        vacio,
        h.frame(),
        config=DriftConfig(),
        thresholds=MonitorThresholds(),
        feature_cols=["x"],
        task=t,
    )
    assert [m.metric_key for m in resultado.measurements] == [
        "prediction_drift_score",
        "feature_drift_score",
    ]


def test_un_tipo_de_tarea_desconocido_lanza_en_vez_de_caer_al_binario():
    raro = TaskSpec.model_construct(task_type="ordinal", classes=(), favorables=())
    h, _ = historia([crudo(200)])
    frame = h.frame()
    for llamada in (
        lambda: quality_metrics(frame, task=raro),
        lambda: evaluate_fairness(
            frame, batch_seq=0, config=FairnessConfig(), thresholds=MonitorThresholds(), task=raro
        ),
        lambda: evaluate_drift(
            frame, frame, config=DriftConfig(), thresholds=MonitorThresholds(),
            feature_cols=["x"], task=raro,
        ),
        lambda: detectar_cardinalidad_binaria(crudo(10), mapeo(), raro),
        lambda: to_canonical(crudo(10), mapeo(), task=raro),
    ):
        with pytest.raises(ValueError, match="no reconocido"):
            llamada()


def test_el_tipo_binario_y_el_multiclase_no_pasan_por_la_rama_de_regresion():
    # sin task, como antes de la multiclase y la regresión: la calidad pide probabilidad válida
    frame = pd.DataFrame(
        {COL_PROB: [0.9, 0.2, 0.7, 0.1], COL_LABEL: [1.0, 0.0, 1.0, 0.0], COL_PREDICTION: [1, 0, 1, 0]}
    )
    m = quality_metrics(frame)
    assert "accuracy" in m and "mean_absolute_error" not in m
