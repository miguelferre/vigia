"""Calidad multiclase."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)

from vigia.core.quality import evaluate_quality, quality_metrics
from vigia.core.schema import (
    COL_LABEL_CLASS,
    COL_PREDICTION_CLASS,
    MonitorThresholds,
    QualityConfig,
    State,
    Threshold,
    ThresholdKind,
    col_prob,
    grupo_clase,
)
from vigia.core.thresholds import DEFAULT_QUALITY_THRESHOLDS

from ._datos_multiclase import CLASES, canonico, historia, tarea

TOL = 1e-9


def _por_clave(res, group_code=None):
    return {m.metric_key: m for m in res.measurements if m.group_code == group_code}


def test_macro_en_las_claves_de_siempre_coincide_con_sklearn():
    df = canonico(500, seed=3)
    r = quality_metrics(df, task=tarea())
    y = df[COL_LABEL_CLASS].map({c: i for i, c in enumerate(CLASES)}).to_numpy()
    yh = df[COL_PREDICTION_CLASS].map({c: i for i, c in enumerate(CLASES)}).to_numpy()
    p = df[[col_prob(i) for i in range(3)]].to_numpy()
    assert abs(r["accuracy"] - accuracy_score(y, yh)) < TOL
    assert abs(r["precision"] - precision_score(y, yh, average="macro")) < TOL
    assert abs(r["recall"] - recall_score(y, yh, average="macro")) < TOL
    assert abs(r["true_positive_rate"] - r["recall"]) < TOL
    assert abs(r["f1_measure"] - f1_score(y, yh, average="macro")) < TOL
    assert abs(r["matthews_correlation_coefficient"] - matthews_corrcoef(y, yh)) < TOL
    pn = p / p.sum(axis=1, keepdims=True)
    assert abs(r["area_under_roc"] - roc_auc_score(y, pn, multi_class="ovr", average="macro")) < 1e-9
    assert abs(r["gini_coefficient"] - (2 * r["area_under_roc"] - 1)) < TOL
    brier = np.mean(np.sum((pn - np.eye(3)[y]) ** 2, axis=1))
    assert abs(r["brier_score"] - brier) < TOL
    ll = -np.mean(np.log(pn[np.arange(len(y)), y]))
    assert abs(r["log_loss"] - ll) < 1e-9
    assert abs(r["details"]["f1_ponderada"] - f1_score(y, yh, average="weighted")) < TOL
    cm = confusion_matrix(y, yh, labels=[0, 1, 2])
    assert r["details"]["confusion_matrix"] == {"classes": CLASES, "matrix": cm.tolist()}


def test_confusion_favorable_contra_el_resto_y_distribucion_de_etiqueta():
    df = canonico(400, seed=4, favorables=("alta", "media"))
    r = quality_metrics(df, task=tarea(favorables=("alta", "media")))
    fav = {"alta", "media"}
    y = df[COL_LABEL_CLASS].isin(fav)
    yh = df[COL_PREDICTION_CLASS].isin(fav)
    assert r["tp"] == int((y & yh).sum()) and r["tn"] == int((~y & ~yh).sum())
    assert abs(r["label_rate"] - y.mean()) < TOL
    dist = r["details"]["distribucion_etiqueta"]
    assert abs(sum(dist.values()) - 1.0) < TOL
    assert set(dist) == set(CLASES)


def test_titulares_esperan_a_la_linea_base_con_umbrales_de_fabrica():
    """Con los umbrales de fábrica los tres titulares quedan en sin_datos."""
    h = historia(canonico(300, seed=1))
    res = evaluate_quality(
        h, batch_seq=0, config=QualityConfig(), thresholds=DEFAULT_QUALITY_THRESHOLDS, task=tarea()
    )
    m = _por_clave(res)
    for clave in ("accuracy", "f1_measure", "area_under_roc"):
        assert m[clave].state == State.sin_datos
        assert m[clave].motivo == "umbral pendiente de la línea base"
        assert m[clave].threshold_low is None
        assert m[clave].extra["valor_calculado"] is not None
    for clave in ("precision", "recall", "log_loss", "brier_score"):
        assert m[clave].state == State.ok and m[clave].threshold_low is None
        assert m[clave].threshold_high is None
    assert res.worst_state == State.sin_datos


def test_con_umbral_de_la_linea_base_los_titulares_se_clasifican():
    h = historia(canonico(300, seed=1))
    umbrales = MonitorThresholds(
        thresholds=[
            Threshold(
                metric_key="accuracy", kind=ThresholdKind.lower_limit, value=0.99, origen="linea_base"
            ),
            Threshold(
                metric_key="f1_measure", kind=ThresholdKind.lower_limit, value=0.10, origen="linea_base"
            ),
        ]
    )
    res = evaluate_quality(
        h, batch_seq=0, config=QualityConfig(), thresholds=umbrales, task=tarea()
    )
    m = _por_clave(res)
    assert m["accuracy"].state == State.alerta and m["accuracy"].threshold_low == 0.99
    assert m["f1_measure"].state == State.ok
    assert m["area_under_roc"].state == State.sin_datos  # sin umbral propio
    assert res.worst_state == State.alerta


def test_umbral_editado_sin_origen_si_se_evalua_y_el_de_fabrica_no():
    """Sin origen, un umbral es de fábrica solo si coincide con el
    de `DEFAULT_QUALITY_THRESHOLDS`; uno editado (p. ej. por `set_monitor`) cuenta."""
    h = historia(canonico(300, seed=1))
    umbrales = MonitorThresholds(
        thresholds=[
            Threshold(metric_key="accuracy", kind=ThresholdKind.lower_limit, value=0.99),
            Threshold(metric_key="f1_measure", kind=ThresholdKind.lower_limit, value=0.70),
        ]
    )
    res = evaluate_quality(
        h, batch_seq=0, config=QualityConfig(), thresholds=umbrales, task=tarea()
    )
    m = _por_clave(res)
    assert m["accuracy"].state == State.alerta and m["accuracy"].threshold_low == 0.99
    assert m["f1_measure"].state == State.sin_datos  # 0,70 sin origen es el de fábrica
    assert m["f1_measure"].motivo == "umbral pendiente de la línea base"


def test_medidas_por_clase_con_group_code_y_sin_umbral():
    h = historia(canonico(500, seed=2))
    res = evaluate_quality(
        h, batch_seq=0, config=QualityConfig(), thresholds=DEFAULT_QUALITY_THRESHOLDS, task=tarea()
    )
    for clase in CLASES:
        m = _por_clave(res, grupo_clase(clase))
        assert {"n", "precision", "recall", "f1_measure", "area_under_roc", "area_under_pr"} <= set(m)
        for medida in m.values():
            assert medida.threshold_low is None and medida.threshold_high is None
            assert medida.state == State.ok and medida.value is not None
        assert m["n"].value == (h[COL_LABEL_CLASS] == clase).sum()
    assert grupo_clase("alta") == "clase:alta"
    d = res.details
    assert set(d["por_clase"]) == set(CLASES)
    assert d["por_clase"]["alta"]["soporte"] == int((h[COL_LABEL_CLASS] == "alta").sum())
    assert d["clases_desconocidas"] == {}


def test_clase_rara_da_sin_datos_nunca_cero():
    """Una clase con menos de `min_group` filas no publica métricas."""
    df = canonico(400, seed=5, pesos=[0.5, 0.47, 0.03])
    h = historia(df)
    n_baja = int((df[COL_LABEL_CLASS] == "baja").sum())
    assert 0 < n_baja < 20
    res = evaluate_quality(
        h, batch_seq=0, config=QualityConfig(), thresholds=DEFAULT_QUALITY_THRESHOLDS,
        task=tarea(), min_group=20,
    )
    m = _por_clave(res, grupo_clase("baja"))
    for clave in ("precision", "recall", "f1_measure", "area_under_roc"):
        assert m[clave].state == State.sin_datos and m[clave].value is None
        assert "se piden al menos 20" in m[clave].motivo
    assert m["n"].value == n_baja
    assert res.details["por_clase"]["baja"]["recall"] is None


def test_auc_macro_excluye_clases_sin_positivos_y_las_lista():
    df = canonico(300, seed=6)
    df = df[df[COL_LABEL_CLASS] != "baja"]  # la clase baja no tiene positivos
    r = quality_metrics(df, task=tarea())
    excl = r["details"]["auc_clases_excluidas"]
    assert excl == [{"clase": "baja", "motivo": "sin positivos en la ventana"}]
    y = df[COL_LABEL_CLASS].map({c: i for i, c in enumerate(CLASES)}).to_numpy()
    p = df[[col_prob(0), col_prob(1), col_prob(2)]].to_numpy()
    esperado = np.mean([roc_auc_score(y == c, p[:, c]) for c in (0, 1)])
    assert abs(r["area_under_roc"] - esperado) < 1e-9


def test_con_menos_de_dos_clases_validas_el_auc_es_sin_datos():
    df = canonico(200, seed=7)
    df = df[df[COL_LABEL_CLASS] == "alta"]
    r = quality_metrics(df, task=tarea())
    assert r["area_under_roc"] is None and r["gini_coefficient"] is None


def test_sin_conjunto_favorable_las_medidas_de_pertenencia_son_sin_datos():
    """Tp/fp/label_rate/label_skew no se calculan como 0."""
    df = canonico(300, seed=8, favorables=None)
    h = historia(df)
    res = evaluate_quality(
        h, batch_seq=0, config=QualityConfig(), thresholds=DEFAULT_QUALITY_THRESHOLDS,
        task=tarea(favorables=None), baseline_label_rate=None,
    )
    m = _por_clave(res)
    for clave in ("tp", "fp", "fn", "tn", "label_rate", "prediction_rate", "label_skew"):
        assert m[clave].value is None and m[clave].state == State.sin_datos, clave
        assert m[clave].motivo == "sin conjunto favorable: solo calidad por grupo", clave
    assert m["precision"].value is not None


def test_etiquetas_de_clase_desconocida_quedan_fuera_y_se_cuentan():
    from vigia.core.loaders import to_canonical

    from ._datos_multiclase import crudo, mapeo

    raw = crudo(300, seed=9)
    raw.loc[:9, "real"] = "rara"
    df = to_canonical(raw, mapeo(), task=tarea())
    res = evaluate_quality(
        historia(df), batch_seq=0, config=QualityConfig(),
        thresholds=DEFAULT_QUALITY_THRESHOLDS, task=tarea(),
    )
    assert res.details["clases_desconocidas"] == {"rara": 10}
    assert res.window.n == 290


def test_k2_declarado_binario_da_lo_mismo_que_sin_tarea():
    """Una tarea binaria no cambia nada respecto a no pasar tarea."""
    from vigia.core.schema import TaskSpec

    df = canonico(200, seed=10)
    df = df.assign(prediction=(df.index % 2), label=((df.index // 2) % 2).astype(float), prob_favorable=0.6)
    a = quality_metrics(df)
    b = quality_metrics(df, task=TaskSpec.binario())
    assert a == b
    assert "details" not in a
