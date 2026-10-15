"""Mínimo de casos en el denominador de cada tasa de etiqueta.

Con `min_group` cumplido, un grupo de 20 filas con 5 casos reales favorables
daba un FNR de ruido que abría alertas en el lote pequeño de `u5-arkansas`.
Ahora esa tasa no se calcula y la medida dice qué casos faltan.
"""

from __future__ import annotations

import pandas as pd

from vigia.core.fairness import (
    MIN_CASOS_TASA_ETIQUETA,
    _motivo_pocas_etiquetas,
    _tasa_confusion,
    fairness_metrics,
)
from vigia.core.schema import COL_GROUP, COL_LABEL, COL_PREDICTION


def _grupo(codigo: int, n_pos: int, n_neg: int, fn: int, fp: int) -> pd.DataFrame:
    """Filas de un grupo: `n_pos` casos reales favorables (`fn` mal predichos)
    y `n_neg` no favorables (`fp` mal predichos)."""
    filas = []
    for i in range(n_pos):
        filas.append({COL_GROUP: codigo, COL_LABEL: 1, COL_PREDICTION: 0 if i < fn else 1})
    for i in range(n_neg):
        filas.append({COL_GROUP: codigo, COL_LABEL: 0, COL_PREDICTION: 1 if i < fp else 0})
    return pd.DataFrame(filas)


def _ventana(pos0: int, neg0: int) -> pd.DataFrame:
    return pd.concat(
        [_grupo(0, pos0, neg0, fn=2, fp=2), _grupo(1, 60, 60, fn=6, fp=6)], ignore_index=True
    )


def test_el_minimo_es_8():
    assert MIN_CASOS_TASA_ETIQUETA == 8


def test_con_5_positivos_del_grupo_no_hay_fnr_ni_odds_pero_si_fpr():
    m = fairness_metrics(_ventana(pos0=5, neg0=17))
    assert m["n_unpriv"] == 22
    assert m["fnr_unpriv"] is None and m["tpr_unpriv"] is None
    assert m["false_negative_rate_difference"] is None
    assert m["average_odds_difference"] is None and m["average_abs_odds_difference"] is None
    # El FPR tiene 17 negativos: sí se calcula.
    assert m["fpr_unpriv"] == 2 / 17
    assert m["false_positive_rate_difference"] is not None
    # Las medidas de predicción no dependen de la etiqueta.
    assert m["statistical_parity_difference"] is not None


def test_con_8_positivos_del_grupo_la_tasa_se_calcula():
    m = fairness_metrics(_ventana(pos0=8, neg0=14))
    assert m["fnr_unpriv"] == 2 / 8
    assert m["false_negative_rate_difference"] is not None
    assert m["average_odds_difference"] is not None


def test_sin_minimo_el_valor_es_el_de_antes():
    m = fairness_metrics(_ventana(pos0=5, neg0=17), min_casos_tasa=0)
    assert m["fnr_unpriv"] == 2 / 5


def test_el_motivo_dice_que_casos_faltan_y_en_que_grupo():
    ventana = _ventana(pos0=5, neg0=17)
    c0 = _tasa_confusion(ventana[ventana[COL_GROUP] == 0])
    c1 = _tasa_confusion(ventana[ventana[COL_GROUP] == 1])
    motivo = _motivo_pocas_etiquetas("false_negative_rate_difference", c0, c1, 8)
    assert motivo == (
        "pocos casos para esta tasa: 5 casos con resultado real favorable en el grupo "
        "supervisado (se piden al menos 8)"
    )
    assert _motivo_pocas_etiquetas("false_positive_rate_difference", c0, c1, 8) is None


def test_los_conteos_crudos_no_cambian():
    """Los intervalos de Newcombe leen los conteos, que no dependen del mínimo."""
    ventana = _ventana(pos0=5, neg0=17)
    g0 = ventana[ventana[COL_GROUP] == 0]
    sin, con = _tasa_confusion(g0), _tasa_confusion(g0, 8)
    for clave in ("fn", "fp", "tp", "tn", "npos", "nneg", "nlab", "npred_pos", "npred_neg"):
        assert sin[clave] == con[clave]
    assert sin["fnr"] == 2 / 5 and con["fnr"] is None
