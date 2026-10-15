"""Tests de `MonitorSettings`, `History`, `evaluate_batch`
y `run_scenario` sobre los dos guiones de demo. Los valores exactos que
salen aquí (fairness_value, FNRD, accuracy...) fijan las tolerancias.
"""
from __future__ import annotations

import time

import pytest

from vigia.core.engine import History, MonitorSettings, evaluate_batch, run_scenario
from vigia.core.schema import HARNESS_FEEDBACK_MAPPING, State


def _medida(resultado, clave: str):
    for m in resultado.measurements:
        if m.metric_key == clave:
            return m
    raise KeyError(clave)


def _reports_por_clave(reports):
    return {r.phase_key: r for r in reports}


# ---------------------------------------------------------------------------
# timeline_completo, canned
# ---------------------------------------------------------------------------


def test_timeline_completo_canned_nueve_fases():
    reports = run_scenario("timeline_completo", source="canned")
    assert len(reports) == 9
    claves = [r.phase_key for r in reports]
    assert claves == ["b1", "b2", "b3", "b4", "b5", "e1_evento", "e1_recovery", "e2_evento", "e2_recovery"]


def test_baselines_quality_ok_o_aviso_y_b1_drift_ok():
    reports = _reports_por_clave(run_scenario("timeline_completo", source="canned"))
    for clave in ("b1", "b2", "b3", "b4", "b5"):
        r = reports[clave]
        assert r.states["quality"] in (State.ok, State.aviso), (clave, r.states["quality"])
    assert reports["b1"].states["drift"] == State.ok


def test_baselines_fairness_ok_tras_min_positives():
    """`fairness_value` de la ventana de últimos 200 del propio batch
    baseline (450 filas) sale 56,81 (fuera del umbral 20), pero con
    `min_positives=5` solo 3 de las 26 ventanas del intervalo son
    informativas (49,12-56,81), que ya no cruzan 20 -> `ok` (con
    `extra["fragil"] == False`, 6 favorables jóvenes). Antes salía
    `inestable` porque el intervalo sin filtrar (0,00-56,81) sí cruzaba el
    umbral: era el síntoma que motivó la decisión (ver
    `tests/core/test_fairness.py::test_evaluate_fairness_baseline_solo`).
    """
    reports = _reports_por_clave(run_scenario("timeline_completo", source="canned"))
    for clave in ("b1", "b2", "b3", "b4", "b5"):
        r = reports[clave]
        assert r.states["fairness"] in (State.ok, State.aviso), (clave, r.states["fairness"])
        assert r.matches_expected["fairness"] is True, (clave, r.matches_expected)


def test_e1_evento_fairness_alerta_inestable_y_valores():
    reports = _reports_por_clave(run_scenario("timeline_completo", source="canned"))
    r = reports["e1_evento"]

    fairness_value = _medida(r.results["fairness"], "fairness_value")
    assert fairness_value.value == pytest.approx(19.50, abs=0.01)
    assert fairness_value.state == State.inestable

    fnrd = _medida(r.results["fairness"], "false_negative_rate_difference")
    assert fnrd.value == pytest.approx(0.631, abs=0.001)
    assert fnrd.state == State.alerta

    assert r.states["fairness"] in (State.alerta, State.inestable)
    assert r.states["quality"] in (State.ok, State.aviso)
    accuracy = _medida(r.results["quality"], "accuracy")
    assert accuracy.value == pytest.approx(0.860, abs=0.001)

    assert r.states["drift"] == State.alerta
    confianza = _medida(r.results["drift"], "confidence_drift_score")
    assert confianza.value == pytest.approx(0.370, abs=0.001)

    assert r.matches_expected["fairness"] is True
    # accuracy 0,86 cae en la banda de aviso (umbral 0,80 + 10 %); el guion
    # espera "ok" y `aviso` cuenta como "sin alerta": coincide.
    assert accuracy.state == State.aviso
    assert r.matches_expected["quality"] is True


def test_e1_recovery_fairness_no_alerta():
    reports = _reports_por_clave(run_scenario("timeline_completo", source="canned"))
    r = reports["e1_recovery"]
    assert r.states["fairness"] != State.alerta
    assert r.states["quality"] in (State.ok, State.aviso)
    assert r.states["drift"] in (State.ok, State.aviso)

    # Recovery E1 sin ventanas informativas en el intervalo (menos de
    # min_positives derivaciones jovenes) -> ok pero fragil.
    fairness_value = _medida(r.results["fairness"], "fairness_value")
    assert fairness_value.state == State.ok
    assert fairness_value.extra["fragil"] is True


def test_e2_evento_quality_alerta_fairness_ok_orden_manipulado():
    reports = _reports_por_clave(run_scenario("timeline_completo", source="canned"))
    r = reports["e2_evento"]
    assert r.orden_manipulado is True

    assert r.states["quality"] == State.alerta
    accuracy = _medida(r.results["quality"], "accuracy")
    assert accuracy.value == pytest.approx(0.7140, abs=0.001)
    tpr = _medida(r.results["quality"], "true_positive_rate")
    f1 = _medida(r.results["quality"], "f1_measure")
    assert tpr.value is not None and f1.value is not None

    assert r.states["fairness"] != State.alerta
    fairness_value = _medida(r.results["fairness"], "fairness_value")
    assert fairness_value.value is not None

    assert r.matches_expected["quality"] is True
    assert r.matches_expected["fairness"] is True


def test_e2_recovery_v2_baseline_quality_ok():
    reports = _reports_por_clave(run_scenario("timeline_completo", source="canned"))
    r = reports["e2_recovery"]
    assert r.model_version == "v2"

    assert r.states["drift"] in (State.ok, State.sin_datos)
    accuracy = _medida(r.results["quality"], "accuracy")
    assert accuracy.value > 0.82
    assert r.states["quality"] == State.ok
    assert r.states["fairness"] != State.alerta

    assert r.matches_expected["quality"] is True
    assert r.matches_expected["fairness"] is True


# ---------------------------------------------------------------------------
# consejeria_regional
# ---------------------------------------------------------------------------


def test_consejeria_regional_seis_fases_ultima_fairness_alerta():
    reports = run_scenario("consejeria_regional", source="canned")
    assert len(reports) == 6
    assert reports[-1].phase_key == "e1_evento"
    assert reports[-1].states["fairness"] in (State.alerta, State.inestable)


# ---------------------------------------------------------------------------
# source="generate"
# ---------------------------------------------------------------------------


def test_source_generate_mismos_estados_que_canned():
    inicio = time.monotonic()
    reports_gen = run_scenario("timeline_completo", source="generate")
    duracion = time.monotonic() - inicio
    reports_canned = _reports_por_clave(run_scenario("timeline_completo", source="canned"))

    for r in reports_gen:
        esperado = reports_canned[r.phase_key]
        assert r.states == esperado.states, (r.phase_key, r.states, esperado.states)
    # tiempo anotado en el informe del carril, sin aserción de rendimiento
    assert duracion >= 0


# ---------------------------------------------------------------------------
# With_human: diario de uso y alertas cruzadas
# ---------------------------------------------------------------------------


def test_with_human_b1_calibracion():
    reports = _reports_por_clave(
        run_scenario("consejeria_regional", source="canned", with_human=True, human_seed=0)
    )
    r = reports["b1"]
    assert r.cross is not None
    assert r.cross.mode == "calibracion"
    assert r.cross.alerts == []


def test_with_human_defaults_no_dispara_cx1():
    reports = _reports_por_clave(
        run_scenario("consejeria_regional", source="canned", with_human=True, human_seed=0)
    )
    r = reports["e1_evento"]
    assert r.cross is not None
    assert r.cross.mode == "vigilancia"
    reglas = {a.rule for a in r.cross.alerts}
    assert "CX-1" not in reglas


def test_with_human_k_sub_dispara_cx1_en_ventana_acumulada():
    reports = _reports_por_clave(
        run_scenario(
            "consejeria_regional",
            source="canned",
            with_human=True,
            human_seed=0,
            params_override={"human": {"k_sub": {"18-35": 0.25}}},
        )
    )
    r = reports["e1_evento"]
    assert r.cross is not None
    cx1 = [a for a in r.cross.alerts if a.rule == "CX-1" and a.group == "18-35"]
    assert len(cx1) == 1
    assert cx1[0].z is not None and cx1[0].z <= -3.0


# ---------------------------------------------------------------------------
# Regla de equivalencia y History con dos versiones
# ---------------------------------------------------------------------------


def test_matches_expected_equivalencia_fairness_alerta_inestable():
    reports = _reports_por_clave(run_scenario("timeline_completo", source="canned"))
    r = reports["e1_evento"]
    assert r.expected["fairness"] == "alerta"
    assert r.states["fairness"] in (State.alerta, State.inestable)
    assert r.matches_expected["fairness"] is True


def test_history_dos_versiones_ventana_no_mezcla():
    reports = run_scenario("timeline_completo", source="canned")
    history_batches = {r.model_version for r in reports}
    assert history_batches == {"v1", "v2"}

    v1_batches = [r for r in reports if r.model_version == "v1"]
    v2_batches = [r for r in reports if r.model_version == "v2"]
    assert len(v1_batches) == 8
    assert len(v2_batches) == 1
    v2 = v2_batches[0]
    ventana_v1 = v1_batches[-1].results["fairness"].window
    ventana_v2 = v2.results["fairness"].window
    assert ventana_v2.model_version == "v2"
    assert ventana_v1.model_version == "v1"


# ---------------------------------------------------------------------------
# MonitorSettings, History y evaluate_batch unitarios
# ---------------------------------------------------------------------------


def test_monitor_settings_defaults_tiene_las_cuatro_claves():
    settings = MonitorSettings.defaults()
    assert set(settings.thresholds) == {"fairness", "quality", "drift", "explain"}


def test_history_add_batch_y_evaluate_batch(baseline_canonico):
    history = History()
    batch_seq = history.add_batch(
        baseline_canonico, mapping=HARNESS_FEEDBACK_MAPPING, model_version="v1", phase_label="b1"
    )
    history.freeze_baseline(batch_seq, "v1")
    settings = MonitorSettings.defaults()
    resultados = evaluate_batch(history, batch_seq, settings)
    assert set(resultados) == {"fairness", "quality", "drift"}
    assert resultados["drift"].worst_state != State.sin_datos


# ---------------------------------------------------------------------------
# Explicación de referencia en History y evaluate_batch
# ---------------------------------------------------------------------------


def _explicacion(*importancias):
    from vigia.core.schema import ExplanationResult, FeatureImportance

    features = [FeatureImportance(feature=f, importance=v) for f, v in importancias]
    return ExplanationResult(kind="global_permutation", available=True, features=features)


def test_evaluate_batch_sin_explanation_no_anade_clave_explain(baseline_canonico):
    """Comportamiento exactamente igual que antes de explain cuando no se pasa
    `explanation`: sigue sin haber clave "explain"."""
    history = History()
    batch_seq = history.add_batch(
        baseline_canonico, mapping=HARNESS_FEEDBACK_MAPPING, model_version="v1", phase_label="b1"
    )
    history.freeze_baseline(batch_seq, "v1")
    resultados = evaluate_batch(history, batch_seq, MonitorSettings.defaults())
    assert "explain" not in resultados


def test_evaluate_batch_con_explanation_sin_referencia_da_sin_datos(baseline_canonico):
    history = History()
    batch_seq = history.add_batch(
        baseline_canonico, mapping=HARNESS_FEEDBACK_MAPPING, model_version="v1", phase_label="b1"
    )
    history.freeze_baseline(batch_seq, "v1")
    explicacion = _explicacion(("Age", 0.6), ("Previous_PC_episodes", 0.3))

    resultados = evaluate_batch(
        history, batch_seq, MonitorSettings.defaults(), explanation=explicacion
    )
    assert "explain" in resultados
    medida = resultados["explain"].measurements[0]
    assert medida.state == State.sin_datos
    assert medida.motivo is not None


def test_evaluate_batch_con_referencia_fijada_evalua_estabilidad(baseline_canonico):
    """Paralelo a `freeze_baseline`: quien orquesta fija la referencia con
    `History.set_explain_reference` (aquí, a mano) y `evaluate_batch` la usa
    para clasificar la explicación del siguiente batch."""
    history = History()
    batch_seq = history.add_batch(
        baseline_canonico, mapping=HARNESS_FEEDBACK_MAPPING, model_version="v1", phase_label="b1"
    )
    history.freeze_baseline(batch_seq, "v1")
    referencia = _explicacion(("Age", 0.6), ("Previous_PC_episodes", 0.3), ("Gout", 0.1))
    history.set_explain_reference("v1", referencia)
    assert history.explain_reference_for("v1") is referencia
    assert history.explain_reference_for("v2") is None

    igual = _explicacion(("Age", 0.6), ("Previous_PC_episodes", 0.3), ("Gout", 0.1))
    resultados = evaluate_batch(
        history, batch_seq, MonitorSettings.defaults(), explanation=igual
    )
    medida = resultados["explain"].measurements[0]
    assert medida.value == pytest.approx(1.0)
    assert medida.state == State.ok
    assert resultados["explain"].window.model_version == "v1"


def test_caso_digestivo_con_humano_abre_cx1_solo_en_el_lote_del_evento():
    """Sin `params_override`, el guion de
    la demo trae sus propios parámetros humanos (`Scenario.human_params`) y
    con ellos ninguna regla cruzada dispara en las cinco semanas de línea
    base (el paso 5 del guion promete «la tabla de alertas vacía») y CX-1
    abre alerta en el lote del evento.
    """
    reports = _reports_por_clave(
        run_scenario("caso_digestivo", source="canned", with_human=True, human_seed=0)
    )
    for clave in ("b1", "b2", "b3", "b4", "b5"):
        assert reports[clave].cross is not None
        assert reports[clave].cross.alerts == [], clave
    evento = reports["e1_evento"].cross
    assert evento is not None
    cx1 = [a for a in evento.alerts if a.rule == "CX-1" and a.group == "18-35"]
    assert len(cx1) == 1
    assert cx1[0].z is not None and cx1[0].z <= -3.0
