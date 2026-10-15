"""Tests de tabla para vigia.core.states.classify."""
from __future__ import annotations

import math

import pytest

from vigia.core.schema import State
from vigia.core.states import (
    classify,
    classify_point,
    classify_point_with_motivo,
    classify_with_motivo,
)

# (value, low, high, interval, esperado)
CASOS = [
    (None, 20.0, None, None, State.sin_datos),
    (float("nan"), 20.0, None, None, State.sin_datos),
    (25.0, 20.0, None, None, State.ok),
    (19.0, 20.0, None, None, State.alerta),
    (20.0, 20.0, None, None, State.aviso),  # exactamente en el umbral: no es alerta, cae en banda
    (21.5, 20.0, None, None, State.aviso),  # banda 10% -> [20, 22]
    (22.5, 20.0, None, None, State.ok),
    (-0.55, -0.60, None, None, State.aviso),  # banda 10% de -0.60 -> [-0.60, -0.54]
    (-0.50, -0.60, None, None, State.ok),
    (-0.65, -0.60, None, None, State.alerta),
    (-0.60, -0.60, None, None, State.aviso),  # exactamente en el umbral: no es alerta, cae en banda
    (0.0, 0.0, None, None, State.ok),  # umbral 0: banda 0, nunca aviso
    (0.5, 0.0, None, None, State.ok),
    (-0.1, 0.0, None, None, State.alerta),
    (0.3, None, 0.5, None, State.ok),
    (0.49, None, 0.5, None, State.aviso),  # banda 10% -> (0.45, 0.5]
    (0.5, None, 0.5, None, State.aviso),  # exactamente en el umbral: no es alerta, cae en banda
    (0.6, None, 0.5, None, State.alerta),
    (-0.4, -0.5, 0.5, None, State.ok),  # label_skew, doble umbral, lado bajo
    (0.4, -0.5, 0.5, None, State.ok),  # label_skew, lado alto
    (-0.48, -0.5, 0.5, None, State.aviso),
    (0.48, -0.5, 0.5, None, State.aviso),
    (0.6, -0.5, 0.5, None, State.alerta),
    (-0.6, -0.5, 0.5, None, State.alerta),
    (19.5, 20.0, None, (18.0, 22.0), State.inestable),  # intervalo cruza el umbral
    (19.5, 20.0, None, (10.0, 15.0), State.alerta),  # intervalo no cruza: manda el valor
    (25.0, 20.0, None, (18.0, 22.0), State.inestable),  # valor ok pero intervalo cruza
    (0.6, None, 0.55, (0.46, 0.79), State.inestable),  # FNRD del evento E1
]


@pytest.mark.parametrize("value,low,high,interval,esperado", CASOS)
def test_classify_tabla(value, low, high, interval, esperado):
    assert classify(value, low, high, interval=interval) == esperado


def test_classify_with_motivo_sin_datos_no_lleva_motivo_generico():
    estado, motivo = classify_with_motivo(None, 20.0, None)
    assert estado == State.sin_datos
    assert motivo is None


def test_classify_with_motivo_alerta_lleva_motivo():
    estado, motivo = classify_with_motivo(19.0, 20.0, None)
    assert estado == State.alerta
    assert motivo is not None


def test_classify_with_motivo_inestable_menciona_intervalo():
    estado, motivo = classify_with_motivo(19.5, 20.0, None, interval=(18.0, 22.0))
    assert estado == State.inestable
    assert "18.0" in motivo and "22.0" in motivo


def test_classify_nan_es_sin_datos():
    assert classify(math.nan, 20.0, None) == State.sin_datos


# (value, low, high, interval, esperado): regla de valor puntual del método
# `lote`. Distinta de la tabla de arriba: aquí
# manda el valor puntual, no el intervalo.
CASOS_PUNTO = [
    (None, 20.0, None, None, State.sin_datos),
    (float("nan"), 20.0, None, None, State.sin_datos),
    (25.0, 20.0, None, None, State.ok),  # lado bueno: ok, aunque no haya intervalo
    (20.0, 20.0, None, None, State.ok),  # en el umbral: lado bueno (no hay banda de aviso)
    (19.0, 20.0, None, None, State.alerta),  # cruza, sin intervalo: alerta directa
    (19.0, 20.0, None, (18.0, 22.0), State.inestable),  # cruza, pero el intervalo toca el lado bueno
    (19.0, 20.0, None, (17.0, 19.5), State.alerta),  # cruza y todo el intervalo queda del lado malo
    (0.6, None, 0.5, None, State.alerta),  # umbral superior, sin intervalo
    (0.6, None, 0.5, (0.4, 0.7), State.inestable),  # umbral superior, intervalo toca el lado bueno
    (0.6, None, 0.5, (0.45, 0.7), State.inestable),  # el propio umbral está dentro del intervalo
]


@pytest.mark.parametrize("value,low,high,interval,esperado", CASOS_PUNTO)
def test_classify_point_tabla(value, low, high, interval, esperado):
    assert classify_point(value, low, high, interval=interval) == esperado


def test_classify_point_ok_no_lleva_motivo():
    estado, motivo = classify_point_with_motivo(25.0, 20.0, None)
    assert estado == State.ok
    assert motivo is None


def test_classify_point_alerta_menciona_lote_sin_intervalo():
    estado, motivo = classify_point_with_motivo(19.0, 20.0, None)
    assert estado == State.alerta
    assert "lote" in motivo


def test_classify_point_inestable_menciona_intervalo():
    estado, motivo = classify_point_with_motivo(19.0, 20.0, None, interval=(18.0, 22.0))
    assert estado == State.inestable
    assert "18.0" in motivo and "22.0" in motivo
