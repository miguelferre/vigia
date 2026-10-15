"""En el método `lote` de equidad, si el lote
completo tiene menos de `FairnessConfig.min_records` filas, el caso que hoy da
`inestable` (valor que cruza el umbral y un intervalo que toca el lado bueno)
da `aviso`. Todo el intervalo del lado malo sigue siendo `alerta`; un lote
normal no cambia. El tamaño es el del lote completo, no el de sus filas
con etiqueta. Cubre los tres tipos por `evaluate_fairness`."""

from __future__ import annotations

import numpy as np
import pytest

from tests.core import _datos_multiclase as m4
from tests.core import _datos_regresion as m5
from tests.core.test_fairness_lote import _poblacion
from vigia.core.fairness import evaluate_fairness
from vigia.core.schema import (
    COL_BATCH,
    COL_LABEL,
    FairnessConfig,
    MonitorThresholds,
    State,
    Threshold,
    ThresholdKind,
)
from vigia.core.states import classify_point, classify_point_with_motivo

MOTIVO_A2 = "lote pequeño ({n} filas, menos de {m}): valor"


# ---------------------------------------------------------------------------
# La regla, sola (classify_point_with_motivo)
# ---------------------------------------------------------------------------


def test_lote_de_150_con_minimo_200_y_un_intervalo_que_cruza_da_aviso_con_el_motivo():
    estado, motivo = classify_point_with_motivo(
        -0.142, -0.123, None, interval=(-0.305, 0.162), n_filas_lote=150, min_filas_lote=200
    )
    assert estado == State.aviso
    assert motivo == (
        "lote pequeño (150 filas, menos de 200): valor -0.142 cruza el umbral inferior "
        "-0.123, pero el intervalo [-0.305, 0.162] cruza al lado bueno"
    )


def test_lote_pequeno_con_todo_el_intervalo_del_lado_malo_sigue_siendo_alerta():
    estado, motivo = classify_point_with_motivo(
        -0.30, -0.123, None, interval=(-0.40, -0.20), n_filas_lote=150, min_filas_lote=200
    )
    assert estado == State.alerta and "todo el intervalo" in motivo


def test_lote_pequeno_sin_intervalo_sigue_siendo_alerta():
    estado, _ = classify_point_with_motivo(
        -0.30, -0.123, None, n_filas_lote=150, min_filas_lote=200
    )
    assert estado == State.alerta


def test_lote_de_1000_con_el_mismo_intervalo_sigue_siendo_inestable():
    estado, motivo = classify_point_with_motivo(
        -0.142, -0.123, None, interval=(-0.305, 0.162), n_filas_lote=1000, min_filas_lote=200
    )
    assert estado == State.inestable and "todavía toca el lado bueno" in motivo


def test_el_limite_exacto_no_es_lote_pequeno():
    estado, _ = classify_point_with_motivo(
        -0.142, -0.123, None, interval=(-0.305, 0.162), n_filas_lote=200, min_filas_lote=200
    )
    assert estado == State.inestable


@pytest.mark.parametrize("n,minimo", [(None, 200), (150, None), (None, None)])
def test_si_falta_uno_de_los_dos_parametros_el_comportamiento_es_el_de_hoy(n, minimo):
    estado, _ = classify_point_with_motivo(
        -0.142, -0.123, None, interval=(-0.305, 0.162), n_filas_lote=n, min_filas_lote=minimo
    )
    assert estado == State.inestable
    assert classify_point(-0.142, -0.123, None, interval=(-0.305, 0.162)) == State.inestable


def test_lote_pequeno_por_el_lado_superior_tambien_da_aviso():
    estado, motivo = classify_point_with_motivo(
        0.50, None, 0.40, interval=(0.30, 0.70), n_filas_lote=50, min_filas_lote=200
    )
    assert estado == State.aviso and "umbral superior 0.40" in motivo


# ---------------------------------------------------------------------------
# Los tres tipos, a través de evaluate_fairness
# ---------------------------------------------------------------------------


def _evaluar(df, thresholds, minimo, task=None, *, metodo="lote"):
    return evaluate_fairness(
        df,
        batch_seq=1,
        config=FairnessConfig(min_records=minimo),
        thresholds=thresholds,
        model_version="v1",
        interval_method=metodo,
        task=task,
    )


def _una(res, clave):
    medidas = [m for m in res.measurements if m.metric_key == clave]
    assert len(medidas) == 1, clave
    return medidas[0]


def _umbral_que_cruza(df, clave, task=None, minimo=200):
    """Umbral inferior de `clave` entre el valor y el extremo alto de su
    intervalo: el valor lo cruza y el intervalo todavía toca el lado bueno."""
    de_partida = MonitorThresholds(
        thresholds=[Threshold(metric_key=clave, kind=ThresholdKind.upper_limit, value=1e9)]
    )
    medida = _una(_evaluar(df, de_partida, minimo, task), clave)
    assert medida.value is not None and medida.interval_high is not None
    corte = medida.value + 0.5 * (medida.interval_high - medida.value)
    return MonitorThresholds(
        thresholds=[Threshold(metric_key=clave, kind=ThresholdKind.lower_limit, value=corte)]
    )


def _caso_binario():
    return _poblacion(150, 1, sesgo_logit=2.0), None


def _caso_multiclase():
    return m4.canonico(150, seed=3, batch=1), m4.tarea()


def _caso_regresion():
    h, tarea = m5.historia([m5.crudo(150, seed=1, recorte=3.0), m5.crudo(150, seed=2, recorte=3.0)])
    return h.frame(), tarea


def _caso_regresion_sin_rango():
    h, tarea = m5.historia(
        [m5.crudo(150, seed=1, recorte=3.0), m5.crudo(150, seed=2, recorte=3.0)], rangos=[]
    )
    return h.frame(), tarea


CASOS = [
    pytest.param(_caso_binario, "statistical_parity_difference", id="binario"),
    pytest.param(_caso_multiclase, "statistical_parity_difference", id="multiclase"),
    pytest.param(_caso_regresion, "statistical_parity_difference", id="regresion-pertenencia"),
    pytest.param(_caso_regresion, "mean_absolute_error_difference", id="regresion-error"),
    pytest.param(
        _caso_regresion_sin_rango, "mean_absolute_error_difference", id="regresion-sin-rango"
    ),
]


@pytest.mark.parametrize("caso,clave", CASOS)
def test_un_lote_de_150_con_minimo_200_da_aviso_y_con_minimo_150_inestable(caso, clave):
    df, tarea = caso()
    umbrales = _umbral_que_cruza(df, clave, tarea)

    chico = _una(_evaluar(df, umbrales, 200, tarea), clave)
    assert chico.state == State.aviso
    assert chico.motivo.startswith("lote pequeño (150 filas, menos de 200): valor ")
    assert chico.motivo.endswith("cruza al lado bueno")

    normal = _una(_evaluar(df, umbrales, 150, tarea), clave)
    assert normal.state == State.inestable
    assert "todavía toca el lado bueno" in normal.motivo
    # El valor, el intervalo y el umbral no cambian: solo el estado y su motivo.
    assert (chico.value, chico.interval_low, chico.interval_high) == (
        normal.value,
        normal.interval_low,
        normal.interval_high,
    )


@pytest.mark.parametrize("caso,clave", CASOS)
def test_un_lote_pequeno_con_todo_el_intervalo_malo_sigue_en_alerta(caso, clave):
    df, tarea = caso()
    de_partida = MonitorThresholds(
        thresholds=[Threshold(metric_key=clave, kind=ThresholdKind.upper_limit, value=1e9)]
    )
    medida = _una(_evaluar(df, de_partida, 200, tarea), clave)
    corte = medida.interval_high + 1.0  # todo el intervalo queda por debajo del umbral inferior
    umbrales = MonitorThresholds(
        thresholds=[Threshold(metric_key=clave, kind=ThresholdKind.lower_limit, value=corte)]
    )
    assert _una(_evaluar(df, umbrales, 200, tarea), clave).state == State.alerta


@pytest.mark.parametrize("caso,clave", CASOS)
def test_el_metodo_ventanas_no_cambia_con_un_lote_pequeno(caso, clave):
    df, tarea = caso()
    umbrales = _umbral_que_cruza(df, clave, tarea)
    chica = _una(_evaluar(df, umbrales, 200, tarea, metodo="ventanas"), clave)
    assert not (chica.motivo or "").startswith("lote pequeño")


def test_el_tamano_es_el_del_lote_completo_y_no_el_de_sus_filas_con_etiqueta():
    """250 filas, 100 con etiqueta y `min_records` 200. El lote no es
    pequeño, así que una tasa de etiqueta que cruza con intervalo que toca el
    lado bueno sigue en `inestable`, aunque solo tenga 100 filas con etiqueta."""
    df = _poblacion(250, 1, sesgo_logit=2.0)
    df.loc[df.index[100:], COL_LABEL] = np.nan
    clave = "false_negative_rate_difference"
    umbrales = _umbral_que_cruza(df, clave)
    medida = _una(_evaluar(df, umbrales, 200), clave)
    assert medida.extra["n"] == 100
    assert medida.state == State.inestable

    # Con el mismo número de filas con etiqueta pero un lote de 150, sí es pequeño.
    chico = _poblacion(150, 1, sesgo_logit=2.0)
    chico.loc[chico.index[100:], COL_LABEL] = np.nan
    umbrales_chico = _umbral_que_cruza(chico, clave)
    assert _una(_evaluar(chico, umbrales_chico, 200), clave).state == State.aviso


def _regresion_con_pocas_etiquetas(filas_lote, con_etiqueta, *, rangos=m5.RANGO_ALTO):
    """Lote 1 de `filas_lote` filas del que solo `con_etiqueta` conservan el
    valor real: el tamaño del lote completo y el de sus filas etiquetadas
    difieren."""
    h, tarea = m5.historia(
        [m5.crudo(150, seed=1, recorte=3.0), m5.crudo(filas_lote, seed=2, recorte=3.0)],
        rangos=rangos,
    )
    df = h.frame()
    sin = df.index[df[COL_BATCH] == 1][con_etiqueta:]
    df.loc[sin, COL_LABEL] = np.nan
    df.loc[sin, "label_value"] = np.nan
    return df, tarea


@pytest.mark.parametrize(
    "rangos",
    [pytest.param(m5.RANGO_ALTO, id="con-rango"), pytest.param([], id="sin-rango")],
)
def test_regresion_error_el_tamano_es_el_del_lote_completo_y_no_el_de_las_etiquetadas(rangos):
    """En las dos llamadas de regresión (`medidas_error_por_grupo`):
    250 filas con 100 etiquetadas y `min_records` 200 no es lote pequeño
    (`inestable`); 150 filas con las mismas 100 etiquetadas sí (`aviso`)."""
    clave = "mean_absolute_error_difference"

    df, tarea = _regresion_con_pocas_etiquetas(250, 100, rangos=rangos)
    umbrales = _umbral_que_cruza(df, clave, tarea)
    grande = _una(_evaluar(df, umbrales, 200, tarea), clave)
    assert grande.state == State.inestable

    df, tarea = _regresion_con_pocas_etiquetas(150, 100, rangos=rangos)
    umbrales = _umbral_que_cruza(df, clave, tarea)
    chico = _una(_evaluar(df, umbrales, 200, tarea), clave)
    assert chico.state == State.aviso
    assert chico.motivo.startswith("lote pequeño (150 filas, menos de 200): valor ")
