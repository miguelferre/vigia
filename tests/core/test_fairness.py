"""Tests de vigia.core.fairness contra los números de aceptación de
los resultados esperados del escenario 1 y research/verificacion_ventana.py
(tolerancia: diferencias abs < 5e-4; DI x100 < 5e-3).
"""
from __future__ import annotations

import pandas as pd
import pytest

from vigia.core.fairness import (
    _favorable_probability,
    assign_groups,
    evaluate_fairness,
    fairness_metrics,
)
from vigia.core.schema import COL_GROUP, COL_PROB, FairnessConfig, ProtectedKind, State
from vigia.core.thresholds import DEFAULT_FAIRNESS_THRESHOLDS

TOL = 5e-4
TOL_DI = 5e-3


def test_assign_groups_rangos_numericos():
    df = pd.DataFrame({"Age": [20, 40, 80, 36, 18, 76]})
    from vigia.core.schema import ColumnMapping

    mapping = ColumnMapping(
        prediction_col="p", protected_attr_col="Age", unpriv_groups=[[18, 35]], priv_groups=[[36, 75]]
    )
    grupos = assign_groups(df, mapping)
    assert list(grupos) == [0, 1, -1, 1, 0, -1]


def test_assign_groups_categoricas():
    from vigia.core.schema import ColumnMapping

    df = pd.DataFrame({"sexo": ["M", "F", "X"]})
    mapping = ColumnMapping(
        prediction_col="p",
        protected_attr_col="sexo",
        protected_kind=ProtectedKind.categorical,
        unpriv_groups=["F"],
        priv_groups=["M"],
    )
    grupos = assign_groups(df, mapping)
    assert list(grupos) == [1, 0, -1]


def test_fairness_metrics_evento_completo(evento_canonico):
    r = fairness_metrics(evento_canonico)
    assert r["n_unpriv"] == 148
    assert r["n_priv"] == 246
    assert abs(r["false_negative_rate_difference"] - 0.631) < TOL
    assert abs(r["statistical_parity_difference"] - (-0.335)) < TOL
    assert abs(r["average_odds_difference"] - (-0.358)) < TOL
    assert abs(r["error_rate_difference"] - 0.050) < TOL
    assert abs(r["fairness_value"] - 12.38) < TOL_DI


def test_favorable_probability_evento_completo(evento_canonico):
    # Bloque bin_edges (21 valores = 20 tramos), threshold,
    # by_group.unpriv/priv con sum(bin_counts) == n y 0 <= median <= 1.
    bloque, motivo = _favorable_probability(evento_canonico, min_group=20)
    assert motivo is None
    assert bloque is not None
    assert len(bloque["bin_edges"]) == 21
    assert bloque["bin_edges"][0] == 0.0
    assert bloque["bin_edges"][-1] == 1.0
    assert "threshold_motivo" in bloque
    for clave in ("unpriv", "priv"):
        grupo = bloque["by_group"][clave]
        assert sum(grupo["bin_counts"]) == grupo["n"]
        assert 0.0 <= grupo["median"] <= 1.0
        assert 0.0 <= grupo["rate_above_threshold"] <= 1.0


def test_favorable_probability_sin_probabilidad():
    # Version sin probability_col: prob_favorable entero NaN (loaders.py:132).
    df = pd.DataFrame(
        {
            "seq": range(40),
            "batch_seq": [0] * 40,
            "model_version": ["v1"] * 40,
            "prediction": [1] * 20 + [0] * 20,
            COL_PROB: [float("nan")] * 40,
            "label": [1.0] * 40,
            COL_GROUP: [0] * 20 + [1] * 20,
        }
    )
    bloque, motivo = _favorable_probability(df, min_group=20)
    assert bloque is None
    assert motivo == "esta versión no publica probabilidad favorable (prob_favorable)"


def test_evaluate_fairness_favorable_probability_en_details(historia_baseline_evento):
    batch_evento = historia_baseline_evento["batch_seq"].iloc[-1]
    res = evaluate_fairness(
        historia_baseline_evento,
        batch_seq=int(batch_evento),
        config=FairnessConfig(),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
    )
    bloque = res.details["favorable_probability"]
    assert "favorable_probability_motivo" not in res.details
    assert len(bloque["bin_edges"]) == 21
    assert set(bloque["by_group"]) == {"unpriv", "priv"}


def test_evaluate_fairness_favorable_probability_motivo_sin_probabilidad():
    df = pd.DataFrame(
        {
            "seq": range(40),
            "batch_seq": [0] * 40,
            "model_version": ["v1"] * 40,
            "prediction": [1] * 20 + [0] * 20,
            COL_PROB: [float("nan")] * 40,
            "label": [1.0] * 40,
            COL_GROUP: [0] * 20 + [1] * 20,
        }
    )
    res = evaluate_fairness(
        df,
        batch_seq=0,
        config=FairnessConfig(min_records=40, min_group=20),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
    )
    assert "favorable_probability" not in res.details
    assert res.details["favorable_probability_motivo"] == (
        "esta versión no publica probabilidad favorable (prob_favorable)"
    )


def test_fairness_metrics_baseline_completo(baseline_canonico):
    r = fairness_metrics(baseline_canonico)
    assert abs(r["fairness_value"] - 23.93) < TOL_DI
    assert abs(r["false_negative_rate_difference"] - 0.305) < TOL


def test_fairness_metrics_ultimas_200_evento(evento_canonico):
    r = fairness_metrics(evento_canonico.tail(200))
    assert abs(r["fairness_value"] - 19.50) < TOL_DI


def test_fairness_metrics_ultimas_200_baseline_evento(historia_baseline_evento):
    r = fairness_metrics(historia_baseline_evento.tail(200))
    assert abs(r["fairness_value"] - 19.50) < TOL_DI


@pytest.mark.parametrize(
    "n,esperado",
    [(50, 27.81), (100, 20.86), (150, 23.52), (250, 21.72), (300, 17.93)],
)
def test_fairness_metrics_barrido_ultimas_n(evento_canonico, n, esperado):
    # min_group=0: el barrido de referencia (research/verificacion_ventana.py)
    # no aplica ningun umbral de tamano de grupo; aqui solo se compara el
    # calculo de la metrica, no la puerta de min_group (cubierta aparte).
    r = fairness_metrics(evento_canonico.tail(n), min_group=0)
    assert abs(r["fairness_value"] - esperado) < TOL_DI


def test_fairness_metrics_grupo_insuficiente_min_group():
    # frame sintetico: 10 no priv + 10 priv, por debajo de min_group=20
    df = pd.DataFrame(
        {
            "prediction": [1] * 10 + [0] * 10,
            "prob_favorable": [0.9] * 20,
            "label": [1.0] * 20,
            COL_GROUP: [0] * 10 + [1] * 10,
        }
    )
    r = fairness_metrics(df, min_group=20)
    assert r["fairness_value"] is None
    assert "motivo" in r


def test_fairness_metrics_sin_etiqueta_solo_prediccion(evento_canonico):
    sin_label = evento_canonico.copy()
    sin_label["label"] = float("nan")
    r = fairness_metrics(sin_label)
    assert r["fairness_value"] is not None
    assert r["false_negative_rate_difference"] is None
    assert r["average_odds_difference"] is None


def test_evaluate_fairness_historia_baseline_evento(historia_baseline_evento):
    # Dos ventanas: las metricas de solo-prediccion salen
    # de la ventana de ultimos min_records (con intervalo); las de etiqueta
    # salen del batch con etiqueta (sin intervalo). La referencia publico para
    # el evento E1 fairness_value=19.50 (DI x100 de los ultimos 200) y a la
    # vez FNRD=0.631 (del batch completo de 450 filas con etiqueta): las dos
    # a la vez, cada una en su ventana.
    batch_evento = historia_baseline_evento["batch_seq"].iloc[-1]
    res = evaluate_fairness(
        historia_baseline_evento,
        batch_seq=int(batch_evento),
        config=FairnessConfig(),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
    )
    estados = res.states()
    valores = {m.metric_key: m for m in res.measurements}

    fv = valores["fairness_value"]
    assert abs(fv.value - 19.50) < TOL_DI
    # Min_positives=5 excluye del intervalo las ventanas con menos de
    # 5 derivaciones favorables en algun grupo; de las 26 ventanas del batch
    # solo 3 son informativas (era 0.00-20.98 con las 26 sin filtrar).
    assert abs(fv.interval_low - 19.50) < TOL_DI
    assert abs(fv.interval_high - 20.98) < TOL_DI
    assert fv.extra["window"] == "ultimos_n"
    assert res.details["interval_windows"] == 3
    assert res.details["interval_windows_total"] == 26
    # El intervalo cruza el umbral 20 -> inestable
    assert estados["fairness_value"] == State.inestable

    # SPD tambien es de solo-prediccion: misma ventana de ultimos 200
    # (valor anotado en el informe core-a2-build.md).
    spd = valores["statistical_parity_difference"]
    assert abs(spd.value - (-0.3277)) < TOL
    assert spd.extra["window"] == "ultimos_n"

    # FNRD es de etiqueta: ventana = batch del evento completo (450 filas
    # con etiqueta), sin intervalo. 0.631 > 0.55 -> alerta directa.
    fnrd = valores["false_negative_rate_difference"]
    assert abs(fnrd.value - 0.631) < TOL
    assert fnrd.interval_low is None
    assert fnrd.interval_high is None
    assert fnrd.extra["window"] == "batch"
    assert fnrd.extra["n"] == 450
    assert estados["false_negative_rate_difference"] == State.alerta

    # AOD tambien es de etiqueta, sobre las mismas 450 filas.
    aod = valores["average_odds_difference"]
    assert abs(aod.value - (-0.358)) < TOL
    assert aod.extra["window"] == "batch"
    assert aod.extra["n"] == 450

    assert res.details["label_window"]["kind"] == "batch"
    assert res.details["label_window"]["n"] == 450
    assert res.details["counts_label"]["n_unpriv"] + res.details["counts_label"]["n_priv"] <= 450


def test_fairness_metrics_sin_atributo_protegido_motivo_distinto():
    """Sin `protected_attr_col`, `group_code` queda en -1 en
    toda fila (lo pone `to_canonical` al no haber columna de atributo
    protegido); el motivo debe distinguirse del de un grupo pequeño."""
    df = pd.DataFrame(
        {
            "prediction": [1, 0, 1, 0],
            "prob_favorable": [0.6, 0.4, 0.6, 0.4],
            "label": [1.0, 0.0, 1.0, 0.0],
            COL_GROUP: [-1, -1, -1, -1],
        }
    )
    r = fairness_metrics(df, min_group=20)
    assert r["fairness_value"] is None
    assert r["motivo"] == (
        "no hay atributo protegido configurado: defínelo en el modelo para vigilar la equidad"
    )


def test_fairness_metrics_grupo_pequeno_motivo_distinto_de_sin_atributo():
    """Con atributo configurado pero grupos por debajo de `min_group`, el
    motivo sigue siendo el de grupo insuficiente, no el de la falta de atributo."""
    df = pd.DataFrame(
        {
            "prediction": [1] * 5 + [0] * 5,
            "prob_favorable": [0.6] * 10,
            "label": [1.0] * 10,
            COL_GROUP: [0] * 5 + [1] * 5,
        }
    )
    r = fairness_metrics(df, min_group=20)
    assert r["fairness_value"] is None
    assert r["motivo"] == "grupo insuficiente: n_unpriv=5, n_priv=5, min_group=20"


def test_evaluate_fairness_sin_atributo_protegido_motivo_en_measurements():
    """El motivo de la falta de atributo llega hasta las medidas de `evaluate_fairness`,
    tanto en las de solo-predicción como en las de etiqueta."""
    n = 250
    df = pd.DataFrame(
        {
            "seq": range(n),
            "batch_seq": [0] * n,
            "model_version": ["v1"] * n,
            "prediction": ([1, 0] * (n // 2 + 1))[:n],
            COL_PROB: ([0.6, 0.4] * (n // 2 + 1))[:n],
            "label": ([1.0, 0.0] * (n // 2 + 1))[:n],
            COL_GROUP: [-1] * n,
        }
    )
    res = evaluate_fairness(
        df,
        batch_seq=0,
        config=FairnessConfig(),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
    )
    valores = {m.metric_key: m for m in res.measurements}
    assert valores["fairness_value"].state == State.sin_datos
    assert valores["fairness_value"].motivo == (
        "no hay atributo protegido configurado: defínelo en el modelo para vigilar la equidad"
    )


def test_evaluate_fairness_grupo_insuficiente_sin_datos():
    # frame sintetico de un unico batch con grupos por debajo de min_group
    df = pd.DataFrame(
        {
            "seq": range(20),
            "batch_seq": [0] * 20,
            "model_version": ["v1"] * 20,
            "prediction": [1] * 10 + [0] * 10,
            "prob_favorable": [0.9] * 20,
            "label": [1.0] * 20,
            COL_GROUP: [0] * 10 + [1] * 10,
        }
    )
    res = evaluate_fairness(
        df,
        batch_seq=0,
        config=FairnessConfig(min_records=20, min_group=20),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
    )
    estados = res.states()
    assert estados["fairness_value"] == State.sin_datos
    assert res.details.get("motivo") is not None


def test_evaluate_fairness_baseline_solo(baseline_canonico):
    res = evaluate_fairness(
        baseline_canonico,
        batch_seq=int(baseline_canonico["batch_seq"].iloc[0]),
        config=FairnessConfig(),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
    )
    valores = {m.metric_key: m for m in res.measurements}
    fv = valores["fairness_value"]
    # evaluate_fairness usa ventana de prediccion = last_n(min_records=200):
    # sobre el baseline (450 filas) es la cola de 200, no el batch completo
    # (23.93, que es el contrato de fairness_metrics(baseline_completo),
    # cubierto en test_fairness_metrics_baseline_completo). Valor anotado en
    # el informe core-a2-build.md.
    assert abs(fv.value - 56.8149) < TOL
    # Min_positives=5 excluye del intervalo las ventanas sin al menos
    # 5 derivaciones jovenes favorables; de las 26 ventanas quedan 3
    # informativas (49.12-56.81), que ya no cruzan 20 -> ok (la discrepancia
    # 'inestable' era el sintoma que motivo el filtro).
    assert abs(fv.interval_low - 49.12) < TOL_DI
    assert abs(fv.interval_high - 56.81) < TOL_DI
    assert res.details["interval_windows"] == 3
    assert fv.state == State.ok
    assert fv.extra["fragil"] is False
    assert fv.extra["positives_unpriv"] == 6

    # positives_unpriv/positives_priv viajan siempre en details["counts"],
    # no solo en extra cuando el valor es fragil . Deben
    # cuadrar con rate_unpriv/rate_priv de la ventana de prediccion, que es
    # la que describe details["counts"] (no counts_label).
    counts = res.details["counts"]
    assert counts["n_unpriv"] == 34
    assert counts["n_priv"] == 132
    assert counts["positives_unpriv"] == 6
    rate_unpriv = valores["rate_unpriv"].value
    rate_priv = valores["rate_priv"].value
    assert abs(counts["positives_unpriv"] / counts["n_unpriv"] - rate_unpriv) < TOL
    assert abs(counts["positives_priv"] / counts["n_priv"] - rate_priv) < TOL

    # FNRD es de etiqueta: ventana = batch baseline completo (450 filas con
    # etiqueta), 0.305 < 0.55 -> ok.
    fnrd = valores["false_negative_rate_difference"]
    assert abs(fnrd.value - 0.305) < TOL
    assert fnrd.state == State.ok
    assert fnrd.extra["window"] == "batch"
    assert fnrd.extra["n"] == 450


def test_evaluate_fairness_etiqueta_acumula_batches_anteriores(
    baseline_canonico, e1_evento_feedback_path
):
    # batch de 60 filas con etiqueta, por debajo de label_min_records=100,
    # detras del baseline (450 filas con etiqueta): se acumula el baseline
    # completo hasta llegar a 100 -> ventana 'acumulado' de 510 filas y
    # details["label_window"]["batches"] con los dos batches.
    from vigia.core.loaders import concat_history, load_feedback, to_canonical
    from vigia.core.schema import HARNESS_FEEDBACK_MAPPING

    batch_60 = to_canonical(
        load_feedback(e1_evento_feedback_path),
        HARNESS_FEEDBACK_MAPPING,
        batch_seq=1,
        model_version="v1",
        seq_start=450,
    ).head(60)
    historia = concat_history([baseline_canonico, batch_60])

    res = evaluate_fairness(
        historia,
        batch_seq=1,
        config=FairnessConfig(),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
    )
    fnrd = {m.metric_key: m for m in res.measurements}["false_negative_rate_difference"]
    assert fnrd.extra["window"] == "acumulado"
    assert fnrd.extra["n"] == 510
    assert res.details["label_window"]["kind"] == "acumulado"
    assert res.details["label_window"]["batches"] == [0, 1]


def test_evaluate_fairness_etiqueta_sin_historia_sin_datos(e1_evento_feedback_path):
    # batch de 60 filas con etiqueta, sin historia previa: no llega a
    # label_min_records=100 y no hay nada que acumular -> sin_datos.
    from vigia.core.loaders import load_feedback, to_canonical
    from vigia.core.schema import HARNESS_FEEDBACK_MAPPING

    batch_60 = to_canonical(
        load_feedback(e1_evento_feedback_path),
        HARNESS_FEEDBACK_MAPPING,
        batch_seq=1,
        model_version="v1",
        seq_start=450,
    ).head(60)

    res = evaluate_fairness(
        batch_60,
        batch_seq=1,
        config=FairnessConfig(),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
    )
    fnrd = {m.metric_key: m for m in res.measurements}["false_negative_rate_difference"]
    assert fnrd.value is None
    assert fnrd.state == State.sin_datos
    assert fnrd.motivo is not None
    assert res.details["label_window"]["complete"] is False


def test_evaluate_fairness_ignora_batch_posterior(
    historia_baseline_evento, e1_evento_feedback_path
):
    # reevaluar el batch del evento no debe cambiar si detras hay un batch
    # de recovery (posterior): la historia efectiva se corta en batch_seq.
    from vigia.core.loaders import concat_history, load_feedback, to_canonical
    from vigia.core.schema import HARNESS_FEEDBACK_MAPPING

    recovery = to_canonical(
        load_feedback(e1_evento_feedback_path),
        HARNESS_FEEDBACK_MAPPING,
        batch_seq=2,
        model_version="v1",
        seq_start=900,
    )
    historia_con_futuro = concat_history([historia_baseline_evento, recovery])
    batch_evento = int(historia_baseline_evento["batch_seq"].iloc[-1])

    res_sin_futuro = evaluate_fairness(
        historia_baseline_evento,
        batch_seq=batch_evento,
        config=FairnessConfig(),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
    )
    res_con_futuro = evaluate_fairness(
        historia_con_futuro,
        batch_seq=batch_evento,
        config=FairnessConfig(),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
    )
    assert res_sin_futuro.model_dump() == res_con_futuro.model_dump()


def test_evaluate_fairness_recovery_fragil_sin_intervalo_informativo(
    historia_baseline_evento,
):
    # En el recovery real (escenario_1/03_recovery), ninguna de las
    # 26 ventanas deslizantes del batch llega a min_positives=5 en el grupo
    # joven -> intervalo None, sin marcar 'inestable' (falta de datos, no
    # inestabilidad). El valor puntual se publica (min_group se cumple) pero
    # fragil: 3 derivaciones jovenes.
    from pathlib import Path

    from vigia.core.loaders import concat_history, load_feedback, to_canonical
    from vigia.core.schema import HARNESS_FEEDBACK_MAPPING

    repo_root = Path(__file__).resolve().parents[2]
    recovery_path = repo_root / "data" / "demo" / "escenario_1" / "03_recovery_feedback.json"
    recovery_canonico = to_canonical(
        load_feedback(recovery_path),
        HARNESS_FEEDBACK_MAPPING,
        batch_seq=2,
        model_version="v1",
        seq_start=900,
    )
    historia = concat_history([historia_baseline_evento, recovery_canonico])
    batch_recovery = int(recovery_canonico["batch_seq"].iloc[0])

    res = evaluate_fairness(
        historia,
        batch_seq=batch_recovery,
        config=FairnessConfig(),
        thresholds=DEFAULT_FAIRNESS_THRESHOLDS,
    )
    fv = {m.metric_key: m for m in res.measurements}["fairness_value"]
    assert abs(fv.value - 26.68) < TOL_DI
    assert fv.interval_low is None
    assert fv.interval_high is None
    assert fv.state == State.ok
    assert fv.extra["fragil"] is True
    assert fv.extra["positives_unpriv"] == 3
    assert "motivo" in fv.extra
    assert res.details["interval_windows"] == 0
    assert res.details["interval_windows_total"] == 26
    assert res.details["interval_windows_excluidas"] == 26
