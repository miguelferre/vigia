"""Tests de vigia.core.drift contra los números de aceptación de
los resultados esperados del escenario 1 (tolerancia: diferencias
abs < 5e-4, salvo donde se indica).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from vigia.core.drift import (
    confidence,
    confidence_drift,
    drift_categorical,
    drift_numeric,
    evaluate_drift,
    feature_drift,
    feature_drift_score,
    prediction_drift,
    psi,
)
from vigia.core.loaders import load_feedback, to_canonical
from vigia.core.schema import (
    COL_PREDICTION,
    COL_PROB,
    HARNESS_FEEDBACK_MAPPING,
    DriftConfig,
    State,
)
from vigia.core.thresholds import DEFAULT_DRIFT_THRESHOLDS

TOL = 5e-4

FEATURE_COLS = HARNESS_FEEDBACK_MAPPING.feature_cols
CATEGORICAS = [c for c in FEATURE_COLS if c not in ("Age", "Previous_PC_episodes")]


@pytest.fixture
def e1_recovery_feedback_path(e1_baseline_feedback_path):
    return e1_baseline_feedback_path.parent / "03_recovery_feedback.json"


def test_psi_identico_es_casi_cero():
    rng = np.random.default_rng(0)
    datos = rng.normal(size=500)
    assert abs(psi(datos, datos)) < 1e-6


def test_psi_pocos_cortes_da_nan():
    datos = np.array([1.0, 1.0, 1.0, 1.0])
    assert math.isnan(psi(datos, datos))


def test_psi_expected_o_actual_vacio_da_nan():
    datos = np.array([1.0, 2.0, 3.0])
    vacio = np.array([])
    assert math.isnan(psi(vacio, datos))
    assert math.isnan(psi(datos, vacio))
    assert math.isnan(psi(vacio, vacio))


def test_confidence_maximo_de_p_y_1_menos_p():
    p = np.array([0.1, 0.5, 0.9])
    assert list(confidence(p)) == pytest.approx([0.9, 0.5, 0.9])


def test_confidence_drift_baseline_vs_evento_e1(baseline_canonico, evento_canonico):
    r = confidence_drift(
        baseline_canonico[COL_PROB].to_numpy(dtype=float),
        evento_canonico[COL_PROB].to_numpy(dtype=float),
    )
    assert abs(r["jensen_shannon_distance"] - 0.370) < TOL
    assert abs(r["psi"] - 0.391) < TOL
    assert abs(r["ks_stat"] - 0.287) < TOL


def test_prediction_drift_baseline_vs_evento_e1(baseline_canonico, evento_canonico):
    r = prediction_drift(
        baseline_canonico["prediction"].to_numpy(), evento_canonico["prediction"].to_numpy()
    )
    assert abs(r["rate_base"] - 0.413) < TOL
    assert abs(r["rate_cur"] - 0.331) < TOL


def test_drift_numeric_age_baseline_vs_evento_e1(baseline_canonico, evento_canonico):
    r = drift_numeric(
        "Age",
        baseline_canonico["Age"].to_numpy(dtype=float),
        evento_canonico["Age"].to_numpy(dtype=float),
    )
    assert abs(r["ks_stat"] - 0.189) < TOL


def test_drift_categorical_devuelve_js():
    base = pd.Series(["A", "A", "B", "B", "A"])
    cur = pd.Series(["A", "B", "B", "B", "B"])
    r = drift_categorical("cat", base, cur)
    assert r["js"] is not None
    assert r["js"] >= 0.0


def test_feature_drift_clasifica_numericas_y_categoricas(baseline_canonico, evento_canonico):
    filas = feature_drift(
        baseline_canonico, evento_canonico, FEATURE_COLS, categorical=CATEGORICAS
    )
    assert len(filas) == 41
    por_feature = {f["feature"]: f for f in filas}
    assert por_feature["Age"]["kind"] == "numerica"
    assert por_feature["Previous_PC_episodes"]["kind"] == "numerica"
    assert por_feature["Rheumatoid_arthritis"]["kind"] == "categorica"
    assert por_feature["Neck_signs_symptoms"]["kind"] == "categorica"


def test_feature_drift_score_es_el_maximo():
    filas = [{"score": 0.1}, {"score": 0.4}, {"score": None}, {"score": 0.2}]
    assert feature_drift_score(filas) == pytest.approx(0.4)
    assert feature_drift_score([]) is None


def test_drift_numeric_respeta_psi_bins(baseline_canonico, evento_canonico):
    """`psi_bins` debe cambiar el PSI
    devuelto por `drift_numeric`, no quedar fijo en el default de `psi`."""
    base = baseline_canonico["Age"].to_numpy(dtype=float)
    cur = evento_canonico["Age"].to_numpy(dtype=float)
    r_10 = drift_numeric("Age", base, cur, psi_bins=10)
    r_20 = drift_numeric("Age", base, cur, psi_bins=20)
    assert r_10["psi"] != pytest.approx(r_20["psi"])


def test_confidence_drift_respeta_psi_bins(baseline_canonico, evento_canonico):
    base = baseline_canonico[COL_PROB].to_numpy(dtype=float)
    cur = evento_canonico[COL_PROB].to_numpy(dtype=float)
    r_10 = confidence_drift(base, cur, psi_bins=10)
    r_20 = confidence_drift(base, cur, psi_bins=20)
    assert r_10["psi"] != pytest.approx(r_20["psi"])


def test_evaluate_drift_enhebra_psi_bins_de_la_config(baseline_canonico, evento_canonico):
    """`DriftConfig.psi_bins` debe llegar hasta `psi()`: con dos configs de
    `psi_bins` distintas, el PSI de deriva de features (via
    `feature_drift_score`) cambia."""
    res_10 = evaluate_drift(
        baseline_canonico,
        evento_canonico,
        config=DriftConfig(psi_bins=10),
        thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=FEATURE_COLS,
    )
    res_20 = evaluate_drift(
        baseline_canonico,
        evento_canonico,
        config=DriftConfig(psi_bins=20),
        thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=FEATURE_COLS,
    )
    edad_10 = next(f for f in res_10.details["features"] if f["feature"] == "Age")
    edad_20 = next(f for f in res_20.details["features"] if f["feature"] == "Age")
    assert edad_10["psi"] != pytest.approx(edad_20["psi"])


def test_evaluate_drift_baseline_vs_evento_e1_estados(baseline_canonico, evento_canonico):
    res = evaluate_drift(
        baseline_canonico,
        evento_canonico,
        config=DriftConfig(),
        thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=FEATURE_COLS,
    )
    valores = {m.metric_key: m for m in res.measurements}
    assert abs(valores["confidence_drift_score"].value - 0.370) < TOL
    assert valores["confidence_drift_score"].state == State.alerta
    assert abs(valores["prediction_drift_score"].value - 0.082) < TOL
    assert res.details["sin_equivalente"] == [
        "model_quality_score",
        "output_metadata_drift_score",
        "input_metadata_drift_score",
    ]
    assert res.window.kind == "baseline_vs_batch"
    assert res.window.n == 450


def test_evaluate_drift_baseline_vs_baseline_es_practicamente_nulo(baseline_canonico):
    res = evaluate_drift(
        baseline_canonico,
        baseline_canonico,
        config=DriftConfig(),
        thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=FEATURE_COLS,
    )
    valores = {m.metric_key: m for m in res.measurements}
    assert valores["prediction_drift_score"].value == pytest.approx(0.0, abs=1e-9)
    assert valores["confidence_drift_score"].value == pytest.approx(0.0, abs=1e-9)
    assert valores["prediction_drift_score"].state == State.ok
    assert valores["confidence_drift_score"].state == State.ok


def test_evaluate_drift_baseline_vs_recovery_e1(baseline_canonico, e1_recovery_feedback_path):
    fb_recovery = load_feedback(e1_recovery_feedback_path)
    recovery = to_canonical(
        fb_recovery, HARNESS_FEEDBACK_MAPPING, batch_seq=2, model_version="v1", seq_start=900
    )
    res = evaluate_drift(
        baseline_canonico,
        recovery,
        config=DriftConfig(),
        thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=FEATURE_COLS,
    )
    valores = {m.metric_key: m for m in res.measurements}
    # valores obtenidos (ver informe core-b-build.md): confidence 0.1384,
    # prediction_drift_score 0.0022
    assert valores["confidence_drift_score"].value < 0.30
    assert valores["prediction_drift_score"].value < 0.08
    assert valores["confidence_drift_score"].state in (State.ok, State.aviso)
    assert valores["prediction_drift_score"].state in (State.ok, State.aviso)


def test_evaluate_drift_baseline_vacio_no_revienta(evento_canonico):
    """Hallazgo 4.3: `df_baseline` vacío no debe lanzar `IndexError` (via
    `psi`/`np.quantile`): degrada a `sin_datos` en las tres medidas con
    `window.motivo` "baseline vacío", simétrico al caso de batch actual
    vacío."""
    base_vacio = evento_canonico.iloc[0:0]
    res = evaluate_drift(
        base_vacio,
        evento_canonico,
        config=DriftConfig(),
        thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=FEATURE_COLS,
    )
    valores = {m.metric_key: m for m in res.measurements}
    assert valores["prediction_drift_score"].state == State.sin_datos
    assert valores["confidence_drift_score"].state == State.sin_datos
    assert valores["feature_drift_score"].state == State.sin_datos
    assert res.window.motivo == "baseline vacío"


def test_psi_return_bins_publica_cortes_e_histogramas():
    rng = np.random.default_rng(0)
    expected = rng.normal(size=200)
    actual = rng.normal(loc=0.3, size=200)
    valor, bins_info = psi(expected, actual, bins=10, return_bins=True)
    assert bins_info is not None
    assert len(bins_info["bin_edges"]) == len(bins_info["bin_counts_base"]) + 1
    assert len(bins_info["bin_counts_base"]) == len(bins_info["bin_counts_actual"])
    # Los cortes salen de los cuantiles de `expected`: por construcción
    # cubren todo su rango, así que el histograma base suma exactamente
    # `len(expected)`. El de `actual` puede sumar menos si trae valores
    # fuera de ese rango (aquí, desplazado en media): es el mismo
    # comportamiento que ya tenía `psi()`, ahora visible en vez de tirado.
    assert sum(bins_info["bin_counts_base"]) == len(expected)
    assert 0 < sum(bins_info["bin_counts_actual"]) <= len(actual)
    assert valor == pytest.approx(psi(expected, actual, bins=10))


def test_psi_return_bins_pocos_cortes_da_none():
    datos = np.array([1.0, 1.0, 1.0, 1.0])
    valor, bins_info = psi(datos, datos, return_bins=True)
    assert math.isnan(valor)
    assert bins_info is None


def test_confidence_drift_publica_bins_del_histograma_de_confianza(
    baseline_canonico, evento_canonico
):
    r = confidence_drift(
        baseline_canonico[COL_PROB].to_numpy(dtype=float),
        evento_canonico[COL_PROB].to_numpy(dtype=float),
        bins=20,
    )
    assert len(r["bin_edges"]) == 21
    assert len(r["bin_counts_base"]) == 20
    assert len(r["bin_counts_actual"]) == 20
    assert sum(r["bin_counts_base"]) == len(baseline_canonico)
    assert sum(r["bin_counts_actual"]) == len(evento_canonico)


def test_drift_numeric_publica_bins_del_psi(baseline_canonico, evento_canonico):
    r = drift_numeric(
        "Age",
        baseline_canonico["Age"].to_numpy(dtype=float),
        evento_canonico["Age"].to_numpy(dtype=float),
        psi_bins=10,
    )
    assert len(r["bin_edges"]) == len(r["bin_counts_base"]) + 1
    assert sum(r["bin_counts_base"]) == len(baseline_canonico)
    assert 0 < sum(r["bin_counts_actual"]) <= len(evento_canonico)


def test_drift_categorical_publica_categorias_y_recuentos():
    base = pd.Series(["A", "A", "B", "B", "A"])
    cur = pd.Series(["A", "B", "B", "B", "B"])
    r = drift_categorical("cat", base, cur)
    assert r["categories"] == ["A", "B"]
    assert r["bin_counts_base"] == [3, 2]
    assert r["bin_counts_actual"] == [1, 4]


def test_evaluate_drift_publica_bins_en_details(baseline_canonico, evento_canonico):
    """Los bins llegan hasta `details` de la evaluación de
    deriva completa, tanto en confianza como por característica."""
    res = evaluate_drift(
        baseline_canonico,
        evento_canonico,
        config=DriftConfig(),
        thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=FEATURE_COLS,
    )
    assert "bin_edges" in res.details["confidence"]
    assert "bin_counts_base" in res.details["confidence"]
    assert "bin_counts_actual" in res.details["confidence"]

    edad = next(f for f in res.details["features"] if f["feature"] == "Age")
    assert "bin_edges" in edad
    assert edad["kind"] == "numerica"

    categorica = next(f for f in res.details["features"] if f["feature"] == "Rheumatoid_arthritis")
    assert "categories" in categorica
    assert categorica["kind"] == "categorica"


def test_confidence_drift_by_class_reparte_los_globales_sin_solape(
    baseline_canonico, evento_canonico
):
    """`by_class` no es una métrica nueva, es el mismo
    histograma global repartido por clase predicha. Como cada fila cae en
    una sola clase, la suma por bin de todas las clases debe reconstruir
    `bin_counts_base`/`bin_counts_actual`, y `n_base`/`n_actual` deben sumar
    el total de filas de cada lote."""
    r = confidence_drift(
        baseline_canonico[COL_PROB].to_numpy(dtype=float),
        evento_canonico[COL_PROB].to_numpy(dtype=float),
        base_pred=baseline_canonico[COL_PREDICTION].to_numpy(),
        cur_pred=evento_canonico[COL_PREDICTION].to_numpy(),
    )
    by_class = r["by_class"]
    assert set(by_class) == {"0", "1"}
    assert list(by_class) == ["1", "0"]  # de mayor a menor clave

    n_bins = len(r["bin_counts_base"])
    suma_base = [0] * n_bins
    suma_actual = [0] * n_bins
    n_base_total = 0
    n_actual_total = 0
    for datos_clase in by_class.values():
        assert len(datos_clase["bin_counts_base"]) == n_bins
        assert len(datos_clase["bin_counts_actual"]) == n_bins
        for i in range(n_bins):
            suma_base[i] += datos_clase["bin_counts_base"][i]
            suma_actual[i] += datos_clase["bin_counts_actual"][i]
        n_base_total += datos_clase["n_base"]
        n_actual_total += datos_clase["n_actual"]

    assert suma_base == r["bin_counts_base"]
    assert suma_actual == r["bin_counts_actual"]
    assert n_base_total == len(baseline_canonico)
    assert n_actual_total == len(evento_canonico)


def test_confidence_drift_sin_predicciones_no_trae_by_class(baseline_canonico, evento_canonico):
    r = confidence_drift(
        baseline_canonico[COL_PROB].to_numpy(dtype=float),
        evento_canonico[COL_PROB].to_numpy(dtype=float),
    )
    assert "by_class" not in r


def test_confidence_drift_con_predicciones_no_cambia_la_metrica_global(
    baseline_canonico, evento_canonico
):
    base_prob = baseline_canonico[COL_PROB].to_numpy(dtype=float)
    cur_prob = evento_canonico[COL_PROB].to_numpy(dtype=float)
    sin_clases = confidence_drift(base_prob, cur_prob)
    con_clases = confidence_drift(
        base_prob,
        cur_prob,
        base_pred=baseline_canonico[COL_PREDICTION].to_numpy(),
        cur_pred=evento_canonico[COL_PREDICTION].to_numpy(),
    )
    assert con_clases["jensen_shannon_distance"] == pytest.approx(
        sin_clases["jensen_shannon_distance"]
    )
    assert con_clases["ks_stat"] == pytest.approx(sin_clases["ks_stat"])
    assert con_clases["psi"] == pytest.approx(sin_clases["psi"])
    assert con_clases["bin_counts_base"] == sin_clases["bin_counts_base"]
    assert con_clases["bin_counts_actual"] == sin_clases["bin_counts_actual"]


def test_evaluate_drift_incluye_by_class_en_confidence(baseline_canonico, evento_canonico):
    """`evaluate_drift` enhebra `COL_PREDICTION` hasta `confidence_drift`
    `details.confidence.by_class` llega hasta el resultado final."""
    res = evaluate_drift(
        baseline_canonico,
        evento_canonico,
        config=DriftConfig(),
        thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=FEATURE_COLS,
    )
    assert set(res.details["confidence"]["by_class"]) == {"0", "1"}


def test_evaluate_drift_batch_actual_vacio_no_revienta(evento_canonico):
    """Simétrico: `df_current` vacío tampoco debe reventar."""
    cur_vacio = evento_canonico.iloc[0:0]
    res = evaluate_drift(
        evento_canonico,
        cur_vacio,
        config=DriftConfig(),
        thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=FEATURE_COLS,
    )
    valores = {m.metric_key: m for m in res.measurements}
    assert valores["prediction_drift_score"].state == State.sin_datos
    assert valores["confidence_drift_score"].state == State.sin_datos
    assert res.window.motivo == "batch actual vacío"


def _poblacion_propia(rng: np.random.Generator, n: int, *, batch_seq: int, seq_start: int) -> pd.DataFrame:
    """Población con variables propias de un caso (ninguna se llama `Age`):
    cuatro continuas y una categórica, la misma distribución en todos los
    lotes. Es la línea de ruido de V1 (`linea-de-ruido.md` §1)."""
    edad = rng.normal(50, 12, n).round()
    ingresos = rng.lognormal(10, 0.4, n).round(2)
    puntuacion = rng.uniform(0, 100, n).round(1)
    visitas = rng.poisson(3, n).astype(float)
    region = rng.choice(["norte", "sur", "este"], n, p=[0.3, 0.5, 0.2])
    z = 0.03 * (edad - 50) + 0.02 * (puntuacion - 50) + 0.2 * (visitas - 3)
    prob = 1 / (1 + np.exp(-z))
    return pd.DataFrame(
        {
            "seq": np.arange(seq_start, seq_start + n),
            "batch_seq": batch_seq,
            "model_version": "v1",
            "prediction": (prob >= 0.5).astype(int),
            "prob_favorable": prob,
            "edad": edad,
            "ingresos": ingresos,
            "puntuacion": puntuacion,
            "visitas": visitas,
            "region": region,
        }
    )


def test_variables_propias_sin_efecto_no_alertan_deriva():
    """Con variables propias que no se llaman `Age` ni
    `Previous_PC_episodes`, doce lotes sin ningún efecto no dan
    `feature_drift_score` en alerta (antes, 60 de 60 lotes en V1) y cada
    variable continua se trata como numérica por su dtype."""
    cols = ["edad", "ingresos", "puntuacion", "visitas", "region"]
    en_alerta = 0
    for semilla in range(2):
        rng = np.random.default_rng(semilla)
        base = _poblacion_propia(rng, 5000, batch_seq=0, seq_start=0)
        for lote in range(1, 7):
            cur = _poblacion_propia(rng, 1000, batch_seq=lote, seq_start=5000 + 1000 * lote)
            res = evaluate_drift(
                base,
                cur,
                config=DriftConfig(),
                thresholds=DEFAULT_DRIFT_THRESHOLDS,
                feature_cols=cols,
            )
            m = {x.metric_key: x for x in res.measurements}["feature_drift_score"]
            if m.state in (State.alerta, State.inestable):
                en_alerta += 1
            tipos = {f["feature"]: f["kind"] for f in res.details["features"]}
            assert tipos == {
                "edad": "numerica",
                "ingresos": "numerica",
                "puntuacion": "numerica",
                "visitas": "numerica",
                "region": "categorica",
            }
    assert en_alerta == 0


def test_drift_numeric_quita_nulos_antes_de_calcular():
    """Los nulos no son un dato, se quitan antes de KS y PSI."""
    base = np.array([1.0, 2.0, 3.0, float("nan"), 4.0, 5.0])
    cur = np.array([1.5, 2.5, float("nan"), float("nan"), 4.5])
    r = drift_numeric("edad", base, cur)
    assert r["ks_stat"] is not None
    assert not math.isnan(r["ks_stat"])


def test_drift_numeric_todo_nulo_da_ks_stat_none():
    """Sin ninguna fila válida en un lado, `ks_stat` sale `None` (no
    `NaN`): `feature_drift_score` lo debe poder ignorar al agregar."""
    base = np.array([float("nan"), float("nan")])
    cur = np.array([1.0, 2.0, 3.0])
    r = drift_numeric("edad", base, cur)
    assert r["ks_stat"] is None
    assert math.isnan(r["psi"])


def test_drift_categorical_quita_nulos_antes_de_calcular():
    """Una variable categórica con nulos no rompe la evaluación (antes
    de este arreglo, mezclar `NaN` con texto en `sorted()` lanzaba
    `TypeError`)."""
    base = pd.Series(["A", "A", None, "B", "B"])
    cur = pd.Series(["A", None, "B", "B", "B"])
    r = drift_categorical("cat", base, cur)
    assert r["categories"] == ["A", "B"]
    assert sum(r["bin_counts_base"]) == 4  # 5 filas menos 1 nulo
    assert sum(r["bin_counts_actual"]) == 4


def test_drift_categorical_sorted_no_rompe_con_float_y_str():
    """El `sorted` de `drift.py:243` (señalado en el diseño) no debe lanzar
    `TypeError` al mezclar categorías numéricas y de texto."""
    base = pd.Series([0, 1, "otro", None])
    cur = pd.Series([1, "otro", "otro", None])
    r = drift_categorical("mixta", base, cur)
    assert set(r["categories"]) == {0, 1, "otro"}


def test_drift_categorical_todo_nulo_da_js_none():
    """Sin filas válidas en un lado, `js` sale `None` (no 0.0: eso se leería
    como "sin deriva" en vez de "sin dato")."""
    base = pd.Series([None, None])
    cur = pd.Series(["A", "B", "A"])
    r = drift_categorical("cat", base, cur)
    assert r["js"] is None
    # Sin valores en un lado no hay "valores comunes" que comparar: no se marca.
    assert r["sin_valores_comunes"] is False


def test_drift_categorical_marca_sin_valores_comunes_sin_tocar_el_score():
    """Una categorica de un valor por fichero (p. ej. `fecha`
    semanal) no comparte categorias entre la base y el lote. La fila lo marca
    y el score (JS) sigue siendo el de siempre (~1): marca visible, sin tocar el score."""
    base = pd.Series(["2026-09-01"] * 6)
    cur = pd.Series(["2026-09-08"] * 6)
    r = drift_categorical("fecha", base, cur)
    assert r["sin_valores_comunes"] is True
    assert r["js"] == pytest.approx(1.0, abs=1e-6)
    # Con una sola categoria compartida ya no se marca.
    r2 = drift_categorical("canal", pd.Series(["a", "b", "b"]), pd.Series(["b", "c", "c"]))
    assert r2["sin_valores_comunes"] is False


def test_feature_drift_publica_sin_valores_comunes_y_el_score_no_cambia():
    df_base = pd.DataFrame({"fecha": ["2026-09-01"] * 4, "canal": ["a", "b", "a", "b"]})
    df_cur = pd.DataFrame({"fecha": ["2026-09-08"] * 4, "canal": ["a", "b", "b", "b"]})
    filas = feature_drift(df_base, df_cur, ["fecha", "canal"])
    por_feature = {f["feature"]: f for f in filas}
    assert por_feature["fecha"]["sin_valores_comunes"] is True
    assert por_feature["canal"]["sin_valores_comunes"] is False
    # El score sigue siendo el maximo, incluida la columna marcada.
    assert feature_drift_score(filas) == pytest.approx(por_feature["fecha"]["score"])
    assert feature_drift_score(filas) > 0.99


def test_feature_drift_score_ignora_nan_al_agregar():
    """Un `score` en `NaN` no debe ganar el máximo ni reventar `max()`."""
    filas = [{"score": 0.2}, {"score": float("nan")}, {"score": 0.6}]
    assert feature_drift_score(filas) == pytest.approx(0.6)


def test_feature_drift_score_sin_datos_solo_si_todas_las_variables_lo_estan():
    """`sin_datos` (None) solo cuando NINGUNA variable tiene score."""
    filas = [{"score": None}, {"score": float("nan")}]
    assert feature_drift_score(filas) is None
    filas_con_una = [{"score": None}, {"score": 0.3}]
    assert feature_drift_score(filas_con_una) == pytest.approx(0.3)


def test_feature_drift_publica_null_fraction_por_variable():
    """`details.features[].null_fraction` sin estado propio."""
    df_base = pd.DataFrame({"edad": [10.0, 20.0, 30.0, 40.0], "cat": ["A", "B", "A", "B"]})
    df_cur = pd.DataFrame(
        {"edad": [15.0, None, 35.0, None], "cat": ["A", None, "B", "B"]}
    )
    filas = feature_drift(df_base, df_cur, ["edad", "cat"])
    por_feature = {f["feature"]: f for f in filas}
    assert por_feature["edad"]["null_fraction"] == pytest.approx(0.5)
    assert por_feature["cat"]["null_fraction"] == pytest.approx(0.25)


def test_evaluate_drift_categorica_con_nulos_no_revienta():
    """El trabajo nunca queda en error por un
    `TypeError` con nulos en una variable categórica."""
    n = 300
    rng = np.random.default_rng(0)
    cat_base = rng.choice(["norte", "sur", "este"], n).astype(object)
    cat_cur = rng.choice(["norte", "sur", "este"], n).astype(object)
    cat_cur[:30] = None  # 10 % de nulos
    df_base = pd.DataFrame(
        {
            "seq": range(n),
            "batch_seq": 0,
            "model_version": "v1",
            "prediction": (rng.random(n) > 0.5).astype(int),
            "prob_favorable": rng.random(n),
            "region": cat_base,
        }
    )
    df_cur = pd.DataFrame(
        {
            "seq": range(n, 2 * n),
            "batch_seq": 1,
            "model_version": "v1",
            "prediction": (rng.random(n) > 0.5).astype(int),
            "prob_favorable": rng.random(n),
            "region": cat_cur,
        }
    )
    res = evaluate_drift(
        df_base,
        df_cur,
        config=DriftConfig(),
        thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=["region"],
    )
    estados = res.states()
    assert estados["feature_drift_score"] != State.sin_datos
    region_detalle = next(f for f in res.details["features"] if f["feature"] == "region")
    assert region_detalle["null_fraction"] == pytest.approx(0.1)


@pytest.mark.parametrize("n", [10, 19, 50, 100, 150, 199])
def test_suelo_deriva_sin_alerta_por_debajo_de_200(n):
    """Barrido reducido. Por debajo de 200 filas,
    ninguna de las tres medidas de deriva sale en `alerta` ni `inestable`
    (aviso como techo); por debajo de 20, `sin_datos`."""
    claves = ("prediction_drift_score", "confidence_drift_score", "feature_drift_score")
    cols = ["edad", "ingresos", "puntuacion", "visitas", "region"]
    for semilla in range(5):
        rng = np.random.default_rng(semilla)
        base = _poblacion_propia(rng, 5000, batch_seq=0, seq_start=0)
        cur = _poblacion_propia(rng, n, batch_seq=1, seq_start=5000)
        res = evaluate_drift(
            base,
            cur,
            config=DriftConfig(),
            thresholds=DEFAULT_DRIFT_THRESHOLDS,
            feature_cols=cols,
        )
        estados = res.states()
        for clave in claves:
            assert estados[clave] not in (State.alerta, State.inestable), (n, semilla, clave)
        if n < 20:
            valores = {m.metric_key: m for m in res.measurements}
            for clave in claves:
                assert estados[clave] == State.sin_datos
                assert "por debajo de 200" in (valores[clave].motivo or "")


def test_suelo_deriva_evaluacion_normal_desde_200():
    """Desde 200 filas, el suelo no interfiere: se conserva el comportamiento
    de siempre (los 31 números de aceptación del motor, con `evento_canonico`/`baseline_canonico`
    ya cubiertos en otros tests de este fichero)."""
    cols = ["edad", "ingresos", "puntuacion", "visitas", "region"]
    rng = np.random.default_rng(0)
    base = _poblacion_propia(rng, 5000, batch_seq=0, seq_start=0)
    cur = _poblacion_propia(rng, 200, batch_seq=1, seq_start=5000)
    res = evaluate_drift(
        base,
        cur,
        config=DriftConfig(),
        thresholds=DEFAULT_DRIFT_THRESHOLDS,
        feature_cols=cols,
    )
    assert res.window.n == 200
