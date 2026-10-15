"""Umbrales de regresión y propuesta de equidad sobre la pertenencia."""
from __future__ import annotations

import numpy as np
import pytest

from vigia.core.calibration import (
    _acotar,
    monitor_de_umbral,
    proponer_umbrales,
    umbrales_linea_base_regresion,
)
from vigia.core.loaders import to_canonical
from vigia.core.schema import (
    CLAVES_CALIDAD_REGRESION,
    CLAVES_EQUIDAD_ERROR,
    COL_GROUP,
    COL_LABEL_VALUE,
    COL_PREDICTION_VALUE,
    MonitorType,
    QualityConfig,
    TaskSpec,
    ThresholdKind,
)
from vigia.core.thresholds import (
    DEFAULT_FAIRNESS_THRESHOLDS,
    DEFAULT_QUALITY_THRESHOLDS,
    defaults_for,
    defaults_regresion,
)

from . import _datos_multiclase
from ._datos_regresion import crudo, mapeo, tarea

TAMANO_LOTE = 500


def _base(n=4000, seed=0, **kw):
    return to_canonical(crudo(n, seed=seed, **kw), mapeo(), task=tarea())


def _umbrales(base, **kw):
    kw.setdefault("tamano_lote", TAMANO_LOTE)
    return {(u.metric_key, u.kind): u for u in umbrales_linea_base_regresion(base, tarea(), **kw)}


# --------------------------------------------------------------------------
# Umbrales desde la línea base
# --------------------------------------------------------------------------


def test_devuelve_las_diez_con_origen_linea_base_y_nota():
    u = _umbrales(_base())
    claves = {(k, kind.value) for k, kind in u}
    assert claves == {
        ("mean_absolute_error", "upper_limit"),
        ("root_mean_squared_error", "upper_limit"),
        ("r2", "lower_limit"),
        ("mean_error", "lower_limit"),
        ("mean_error", "upper_limit"),
        ("mean_error_difference", "lower_limit"),
        ("mean_error_difference", "upper_limit"),
        ("mean_absolute_error_difference", "upper_limit"),
        ("mean_absolute_error_ratio", "upper_limit"),
        ("prediction_drift_score", "upper_limit"),
    }
    for umbral in u.values():
        assert umbral.origen == "linea_base" and umbral.nota and "remuestreos" in umbral.nota


def test_cada_clave_va_a_su_monitor():
    for clave in CLAVES_CALIDAD_REGRESION:
        assert monitor_de_umbral(clave) == MonitorType.quality
    for clave in CLAVES_EQUIDAD_ERROR:
        assert monitor_de_umbral(clave) == MonitorType.fairness
    assert monitor_de_umbral("prediction_drift_score") == MonitorType.drift
    # las claves de siempre siguen donde estaban
    assert monitor_de_umbral("accuracy") == MonitorType.quality
    assert monitor_de_umbral("explain_stability_ndcg") == MonitorType.explain
    with pytest.raises(ValueError):
        monitor_de_umbral("no_existe")


def test_cobertura_del_99_por_ciento_de_remuestreos_nuevos():
    """Remuestreos que no se usaron para fijar el umbral caen del lado bueno en al
    menos el 99 %, clave a clave."""
    base = _base()
    u = _umbrales(base, n_remuestreos=300, semilla=0)
    y = base[COL_LABEL_VALUE].to_numpy()
    e = base[COL_PREDICTION_VALUE].to_numpy() - y
    g = base[COL_GROUP].to_numpy()
    rng = np.random.default_rng(12345)  # otra semilla
    dentro = {k: 0 for k in (*CLAVES_CALIDAD_REGRESION, *CLAVES_EQUIDAD_ERROR)}
    n_re = 400
    for _ in range(n_re):
        idx = rng.integers(0, len(base), size=TAMANO_LOTE)
        ee, yy, gg = e[idx], y[idx], g[idx]
        valores = {
            "mean_absolute_error": np.abs(ee).mean(),
            "root_mean_squared_error": np.sqrt((ee**2).mean()),
            "r2": 1 - (ee**2).sum() / ((yy - yy.mean()) ** 2).sum(),
            "mean_error": ee.mean(),
            "mean_error_difference": ee[gg == 0].mean() - ee[gg == 1].mean(),
            "mean_absolute_error_difference": np.abs(ee[gg == 0]).mean() - np.abs(ee[gg == 1]).mean(),
            "mean_absolute_error_ratio": np.abs(ee[gg == 0]).mean() / np.abs(ee[gg == 1]).mean(),
        }
        for clave, v in valores.items():
            bajo = u.get((clave, ThresholdKind.lower_limit))
            alto = u.get((clave, ThresholdKind.upper_limit))
            if (bajo is None or v >= bajo.value) and (alto is None or v <= alto.value):
                dentro[clave] += 1
    for clave in ("mean_absolute_error", "root_mean_squared_error", "r2", "mean_error",
                  "mean_error_difference", "mean_absolute_error_difference",
                  "mean_absolute_error_ratio"):
        assert dentro[clave] / n_re >= 0.99, (clave, dentro[clave] / n_re)


def test_un_sesgo_de_linea_base_cero_da_una_banda_no_vacia_a_los_dos_lados():
    # con residuos de media ~0 un margen multiplicativo dejaría umbrales pegados al 0
    base = _base(4000)
    assert abs(float((base[COL_PREDICTION_VALUE] - base[COL_LABEL_VALUE]).mean())) < 0.3
    u = _umbrales(base)
    bajo, alto = u[("mean_error", ThresholdKind.lower_limit)], u[("mean_error", ThresholdKind.upper_limit)]
    assert bajo.value < 0 < alto.value
    assert alto.value - bajo.value > 0.1
    bajo_d = u[("mean_error_difference", ThresholdKind.lower_limit)]
    alto_d = u[("mean_error_difference", ThresholdKind.upper_limit)]
    assert bajo_d.value < 0 < alto_d.value


def test_las_reglas_con_p1_p99_y_margen_aditivo():
    """Reproduce la regla a mano para el MAE: máximo = p99 + 0,2 w."""
    base = _base(2000)
    y = base[COL_LABEL_VALUE].to_numpy()
    e = base[COL_PREDICTION_VALUE].to_numpy() - y
    rng = np.random.default_rng(0)
    maes = []
    for _ in range(200):
        idx = rng.integers(0, len(base), size=TAMANO_LOTE)
        maes.append(np.abs(e[idx]).mean())
    p1, p99 = np.percentile(maes, 1), np.percentile(maes, 99)
    esperado = p99 + 0.2 * (p99 - p1)
    u = _umbrales(base, semilla=0)
    assert u[("mean_absolute_error", ThresholdKind.upper_limit)].value == pytest.approx(
        esperado, abs=1e-5
    )


def test_tiene_techo_1_y_la_deriva_es_un_ks_sin_unidad():
    u = _umbrales(_base())
    assert u[("r2", ThresholdKind.lower_limit)].value < 1.0
    ks = u[("prediction_drift_score", ThresholdKind.upper_limit)].value
    assert 0.0 < ks < 0.5
    assert _acotar("r2", 1.3, MonitorType.quality) == 1.0
    assert _acotar("r2", -4.0, MonitorType.quality) == -4.0


def test_lo_que_no_se_puede_calcular_no_aparece():
    # línea base con pocas filas con etiqueta (min_feedback = 100): solo la deriva
    pocas = _base(60)
    claves = {k for k, _ in _umbrales(pocas)}
    assert claves == {"prediction_drift_score"}
    # sin un grupo: nada de equidad
    un_grupo = _base(2000)
    un_grupo[COL_GROUP] = 0
    claves = {k for k, _ in _umbrales(un_grupo)}
    assert not claves & set(CLAVES_EQUIDAD_ERROR)
    assert set(CLAVES_CALIDAD_REGRESION) <= claves
    # el valor real constante: no hay R²
    constante = _base(2000)
    constante[COL_LABEL_VALUE] = 3.0
    assert "r2" not in {k for k, _ in _umbrales(constante)}


def test_es_reproducible_y_otra_semilla_cambia_poco_los_umbrales_de_un_solo_lado():
    base = _base(1500)
    a = [(u.metric_key, u.kind, u.value) for u in umbrales_linea_base_regresion(base, tarea(), tamano_lote=300)]
    b = [(u.metric_key, u.kind, u.value) for u in umbrales_linea_base_regresion(base, tarea(), tamano_lote=300)]
    assert a == b
    otra = {
        (u.metric_key, u.kind): u.value
        for u in umbrales_linea_base_regresion(base, tarea(), tamano_lote=300, semilla=7)
    }
    for clave, kind, valor in a:
        if clave in ("mean_absolute_error", "root_mean_squared_error", "mean_absolute_error_ratio"):
            assert otra[(clave, kind)] == pytest.approx(valor, rel=0.10), clave


def test_solo_vale_para_regresion_y_la_funcion_multiclase_rechaza_regresion():
    from vigia.core.calibration import umbrales_linea_base_multiclase

    with pytest.raises(ValueError, match="regresión"):
        umbrales_linea_base_regresion(_base(300), TaskSpec.binario())
    with pytest.raises(ValueError, match="multiclase"):
        umbrales_linea_base_multiclase(_base(300), tarea())


def test_usa_min_group_del_fairness_config_si_se_pasa():
    from vigia.core.schema import FairnessConfig

    base = _base(1000)

    def claves(min_group):
        u = umbrales_linea_base_regresion(
            base, tarea(), tamano_lote=100, fairness_config=FairnessConfig(min_group=min_group)
        )
        return {x.metric_key for x in u}

    assert "mean_error_difference" not in claves(200)
    assert "mean_error_difference" in claves(5)
    assert QualityConfig().min_feedback == 100


# --------------------------------------------------------------------------
# Valores de fábrica por monitor
# --------------------------------------------------------------------------


def test_defaults_regresion_por_monitor():
    assert defaults_regresion(MonitorType.quality, con_rango=True).thresholds == []
    assert defaults_regresion(MonitorType.quality, con_rango=False).thresholds == []
    drift = defaults_regresion(MonitorType.drift, con_rango=False)
    assert [(t.metric_key, t.value) for t in drift.thresholds] == [("feature_drift_score", 0.15)]
    con = defaults_regresion(MonitorType.fairness, con_rango=True)
    assert [t.metric_key for t in con.thresholds] == [
        t.metric_key for t in DEFAULT_FAIRNESS_THRESHOLDS.thresholds
    ]
    assert not {t.metric_key for t in con.thresholds} & set(CLAVES_EQUIDAD_ERROR)
    assert defaults_regresion(MonitorType.fairness, con_rango=False).thresholds == []
    assert defaults_regresion(MonitorType.explain, con_rango=False).thresholds == defaults_for(
        MonitorType.explain
    ).thresholds
    with pytest.raises(ValueError):
        defaults_regresion(MonitorType.cross, con_rango=True)


def test_defaults_regresion_devuelve_copias_y_no_toca_las_tablas_de_fabrica():
    antes = len(DEFAULT_FAIRNESS_THRESHOLDS.thresholds)
    copia = defaults_regresion(MonitorType.fairness, con_rango=True)
    copia.thresholds.clear()
    assert len(DEFAULT_FAIRNESS_THRESHOLDS.thresholds) == antes
    assert len(DEFAULT_QUALITY_THRESHOLDS.thresholds) == 14  # las de clasificación, intactas
    assert not {t.metric_key for t in DEFAULT_QUALITY_THRESHOLDS.thresholds} & set(
        CLAVES_CALIDAD_REGRESION
    )


# --------------------------------------------------------------------------
# La propuesta de equidad sobre el 0/1 de pertenencia
# --------------------------------------------------------------------------


def _claves(propuestas):
    return {p.metric_key for p in propuestas}


def test_regresion_con_rango_propone_las_medidas_de_pertenencia():
    base = _base(3000, recorte=3.0)
    propuestas = proponer_umbrales(
        base, MonitorType.fairness, tamano_lote=500, task=tarea()
    )
    assert _claves(propuestas) == {t.metric_key for t in DEFAULT_FAIRNESS_THRESHOLDS.thresholds}
    con_valor = [p for p in propuestas if p.value is not None]
    assert len(con_valor) >= 8  # sin etiqueta o con grupo pequeño alguna puede faltar, no la mayoría


def test_regresion_sin_rango_no_lista_ninguna_medida_de_pertenencia():
    base = to_canonical(crudo(2000), mapeo(rangos=[]), task=tarea(rangos=[]))
    assert proponer_umbrales(base, MonitorType.fairness, tamano_lote=500, task=tarea(rangos=[])) == []


def test_la_calidad_de_regresion_no_tiene_valor_de_fabrica_que_proponer():
    assert proponer_umbrales(_base(500), MonitorType.quality, tamano_lote=200, task=tarea()) == []


def test_multiclase_con_conjunto_favorable_propone_y_sin_conjunto_no():
    con = _datos_multiclase.canonico(2000, seed=3, favorables=("alta",))
    propuestas = proponer_umbrales(
        con, MonitorType.fairness, tamano_lote=500, task=_datos_multiclase.tarea(favorables=("alta",))
    )
    assert _claves(propuestas) == {t.metric_key for t in DEFAULT_FAIRNESS_THRESHOLDS.thresholds}
    assert any(p.value is not None for p in propuestas)
    sin = _datos_multiclase.canonico(2000, seed=3, favorables=())
    assert (
        proponer_umbrales(
            sin, MonitorType.fairness, tamano_lote=500, task=_datos_multiclase.tarea(favorables=())
        )
        == []
    )


def test_el_resultado_binario_no_cambia_con_o_sin_task():
    base = _datos_multiclase.canonico(2000, seed=4, favorables=("alta",))
    sin_task = proponer_umbrales(base, MonitorType.fairness, tamano_lote=400)
    con_task_binaria = proponer_umbrales(
        base, MonitorType.fairness, tamano_lote=400, task=TaskSpec.binario()
    )
    assert sin_task == con_task_binaria
    # y es lo que hacía antes de la regresión: una propuesta por cada clave de fábrica
    assert _claves(sin_task) == {t.metric_key for t in DEFAULT_FAIRNESS_THRESHOLDS.thresholds}


def test_la_propuesta_corre_sobre_un_frame_sin_prob_favorable():
    base = _base(2000)
    assert "prob_favorable" not in base.columns
    proponer_umbrales(base, MonitorType.fairness, tamano_lote=400, task=tarea())  # no lanza
