"""Tests del carril CORE-C: permutation, LIME y SHAP sobre `predict_proba`,
y estabilidad de la explicación global."""
from __future__ import annotations

import subprocess
import sys

import pytest

from vigia.core import explain
from vigia.core.schema import ExplanationResult, FeatureImportance, State
from vigia.core.thresholds import DEFAULT_EXPLAIN_THRESHOLDS
from vigia.sim.model import FEATURE_COLS_PLAIN, predict_proba


@pytest.fixture
def X_baseline(baseline_canonico):
    return explain.harness_feature_frame(baseline_canonico)


@pytest.fixture
def X_evento(evento_canonico):
    return explain.harness_feature_frame(evento_canonico)


def test_harness_feature_frame_devuelve_41_columnas_planas(X_baseline):
    assert list(X_baseline.columns) == FEATURE_COLS_PLAIN
    assert len(X_baseline) == 450
    assert X_baseline.dtypes.apply(lambda d: d == float).all()


def test_lime_fila_0_evento_e1_con_age_dominante(X_baseline, X_evento):
    res = explain.local_lime(
        predict_proba,
        X_baseline,
        X_evento.iloc[0],
        feature_names=list(X_baseline.columns),
        row_seq=450,
    )
    assert res.available
    assert res.features[0].feature == "Age"
    assert 0.0 <= res.prob_favorable <= 1.0


def test_lime_es_determinista_con_la_misma_semilla(X_baseline, X_evento):
    kwargs = {"feature_names": list(X_baseline.columns), "row_seq": 450}
    res1 = explain.local_lime(predict_proba, X_baseline, X_evento.iloc[0], **kwargs)
    res2 = explain.local_lime(predict_proba, X_baseline, X_evento.iloc[0], **kwargs)
    reglas1 = [(f.feature, f.rule, round(f.importance, 9)) for f in res1.features]
    reglas2 = [(f.feature, f.rule, round(f.importance, 9)) for f in res2.features]
    assert reglas1 == reglas2


def test_permutation_sin_y_es_determinista_y_age_entre_las_3_primeras(X_baseline):
    res1 = explain.global_permutation(predict_proba, X_baseline)
    res2 = explain.global_permutation(predict_proba, X_baseline)
    valores1 = [(f.feature, round(f.importance, 9)) for f in res1.features]
    valores2 = [(f.feature, round(f.importance, 9)) for f in res2.features]
    assert valores1 == valores2

    top3 = [f.feature for f in res1.features[:3]]
    assert "Age" in top3
    assert all(f.importance >= 0.0 for f in res1.features)
    assert res1.params["scoring"] == "sensibilidad_media"


def test_permutation_con_y_usa_auroc_drop_y_devuelve_41_features(X_baseline, baseline_canonico):
    y = baseline_canonico["label"].to_numpy()
    res = explain.global_permutation(predict_proba, X_baseline, y=y)
    assert res.params["scoring"] == "auroc_drop"
    assert len(res.features) == 41


def test_shap_disponible_en_este_equipo(X_baseline, X_evento):
    res = explain.global_shap(
        predict_proba,
        X_baseline,
        X_evento.iloc[:10],
        n_background=30,
        nsamples=50,
        seed=0,
    )
    assert res.available
    assert len(res.features) == 41
    assert all(f.importance >= 0.0 for f in res.features)
    # Orden real observado en este equipo (ver informe): Age queda primero,
    # dentro de las 5 primeras exigidas por la especificación.
    top5 = [f.feature for f in res.features[:5]]
    assert "Age" in top5


def test_shap_no_disponible_simulado_lime_sigue_funcionando(
    monkeypatch, X_baseline, X_evento
):
    monkeypatch.setitem(sys.modules, "shap", None)
    explain.shap_available.cache_clear()
    try:
        res = explain.global_shap(predict_proba, X_baseline, X_evento.iloc[:10])
        assert res.available is False
        assert res.motivo is not None
        assert res.motivo.startswith("SHAP no disponible en este equipo")

        res_lime = explain.local_lime(
            predict_proba,
            X_baseline,
            X_evento.iloc[0],
            feature_names=list(X_baseline.columns),
            row_seq=450,
        )
        assert res_lime.available
    finally:
        explain.shap_available.cache_clear()


# ---------------------------------------------------------------------------
# Explain_stability_ndcg y evaluate_explain
# ---------------------------------------------------------------------------


def _features(*importancias: tuple[str, float]) -> list[FeatureImportance]:
    """`importancias` ya en orden descendente, como llegan de
    `global_permutation`/`global_shap`."""
    return [FeatureImportance(feature=f, importance=v) for f, v in importancias]


def _explicacion(*importancias: tuple[str, float], kind="global_permutation") -> ExplanationResult:
    return ExplanationResult(kind=kind, available=True, features=_features(*importancias))


def test_ndcg_ranking_identico_a_la_referencia_da_1():
    referencia = _features(("Age", 0.6), ("B", 0.3), ("C", 0.1))
    assert explain.explain_stability_ndcg(referencia, referencia, p=3) == pytest.approx(1.0)


def test_ndcg_ejemplo_del_docstring():
    """Referencia A=0.6, B=0.3, C=0.1; actual intercambia las dos primeras
    posiciones. Valor exacto anotado en el docstring de la función."""
    referencia = _features(("A", 0.6), ("B", 0.3), ("C", 0.1))
    actual = _features(("B", 0.3), ("A", 0.6), ("C", 0.1))
    assert explain.explain_stability_ndcg(actual, referencia, p=3) == pytest.approx(
        0.8681, abs=1e-3
    )


def test_ndcg_ranking_mas_corto_rellena_con_ganancia_cero_y_penaliza():
    """TRUNCADO DECLARADO: un ranking con menos de `p`
    elementos rellena con ganancia cero, no se descarta ni se recorta `p`.
    Con las 12 características de la referencia, un `actual` que solo trae
    las 3 primeras (en el mismo orden) sale peor que uno con las 10
    primeras, aunque ambos acierten en lo que traen."""
    referencia = _features(*[(f"f{i}", 1.0 / (i + 1)) for i in range(12)])
    actual_10 = referencia[:10]
    actual_3 = referencia[:3]

    ndcg_10 = explain.explain_stability_ndcg(actual_10, referencia)
    ndcg_3 = explain.explain_stability_ndcg(actual_3, referencia)

    assert ndcg_10 == pytest.approx(1.0)
    assert ndcg_3 < ndcg_10


def test_ndcg_ranking_totalmente_distinto_baja_mucho():
    referencia = _features(("A", 0.6), ("B", 0.3), ("C", 0.1))
    actual = _features(("Z", 0.9), ("Y", 0.5), ("X", 0.2))
    assert explain.explain_stability_ndcg(actual, referencia, p=3) == pytest.approx(0.0)


def test_ndcg_referencia_vacia_no_revienta_y_da_1():
    assert explain.explain_stability_ndcg([], [], p=10) == pytest.approx(1.0)


def test_evaluate_explain_sin_referencia_da_sin_datos_no_error():
    actual = _explicacion(("Age", 0.6), ("B", 0.3))
    resultado = explain.evaluate_explain(
        actual, None, thresholds=DEFAULT_EXPLAIN_THRESHOLDS, model_version="v1", batch_seq=3
    )
    medida = resultado.measurements[0]
    assert medida.metric_key == "explain_stability_ndcg"
    assert medida.value is None
    assert medida.state == State.sin_datos
    assert "v1" in medida.motivo
    assert resultado.window.model_version == "v1"
    assert resultado.window.complete is False


def test_evaluate_explain_con_referencia_clasifica_por_umbral():
    referencia = _explicacion(("Age", 0.6), ("B", 0.3), ("C", 0.1))
    igual = _explicacion(("Age", 0.6), ("B", 0.3), ("C", 0.1))
    resultado_ok = explain.evaluate_explain(
        igual, referencia, thresholds=DEFAULT_EXPLAIN_THRESHOLDS, model_version="v1"
    )
    medida_ok = resultado_ok.measurements[0]
    assert medida_ok.value == pytest.approx(1.0)
    assert medida_ok.state == State.ok
    assert resultado_ok.details["referencia_disponible"] is True

    # Age domina la referencia (1,0 frente a 0,01 del resto) y cae a la
    # última posición en `distinta`: valor calculado 0,320, bajo el umbral.
    resto = [(f"f{i}", 0.01) for i in range(1, 10)]
    referencia_dominante = _explicacion(("Age", 1.0), *resto)
    distinta = _explicacion(*resto, ("Age", 1.0))
    resultado_alerta = explain.evaluate_explain(
        distinta, referencia_dominante, thresholds=DEFAULT_EXPLAIN_THRESHOLDS, model_version="v1"
    )
    medida_alerta = resultado_alerta.measurements[0]
    assert medida_alerta.value == pytest.approx(0.3203, abs=1e-3)
    assert medida_alerta.state == State.alerta


def test_importar_vigia_core_no_carga_shap_lime_ni_matplotlib():
    codigo = (
        "import sys\n"
        "import vigia.core.explain\n"
        "nombres = {'shap', 'lime', 'matplotlib'}\n"
        "cargados = nombres & set(sys.modules)\n"
        "assert not cargados, cargados\n"
    )
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
