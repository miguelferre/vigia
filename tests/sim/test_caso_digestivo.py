"""Tests del guion `caso_digestivo` (siete fases):
cinco semanas de línea base (`_BASELINES`, las mismas que
`timeline_completo`) más el evento y el recovery de escenario_1, todas con
`explain_global=True` y con `semanas_atras` para la fecha simulada.
"""
from __future__ import annotations

from datetime import UTC, datetime

from vigia.sim.scenarios import SCENARIOS, fecha_simulada_fase, get_scenario


def test_caso_digestivo_tiene_siete_fases_con_esas_claves():
    scenario = get_scenario("caso_digestivo")
    assert [p.key for p in scenario.phases] == [
        "b1",
        "b2",
        "b3",
        "b4",
        "b5",
        "e1_evento",
        "e1_recovery",
    ]


def test_caso_digestivo_titulo_y_dominio_tecnico():
    scenario = get_scenario("caso_digestivo")
    assert scenario.title == "Caso Digestivo"
    # El dominio técnico es reuma; Digestivo es capa de nombres.
    assert scenario.domain == "reuma"


def test_caso_digestivo_fases_tienen_enlatado_de_escenario_1():
    scenario = get_scenario("caso_digestivo")
    for phase in scenario.phases:
        assert phase.canned is not None
        assert phase.canned[0].startswith("escenario_1/")
        assert phase.canned[1].startswith("escenario_1/")


def test_caso_digestivo_generadores_son_los_de_escenario_1():
    scenario = get_scenario("caso_digestivo")
    generadores = {p.key: p.generator for p in scenario.phases}
    assert generadores == {
        "b1": "e1_baseline",
        "b2": "e1_baseline",
        "b3": "e1_baseline",
        "b4": "e1_baseline",
        "b5": "e1_baseline",
        "e1_evento": "e1_event",
        "e1_recovery": "e1_recovery",
    }


def test_caso_digestivo_fases_son_v1_y_b1_congela_la_linea_base():
    scenario = get_scenario("caso_digestivo")
    assert {p.model_version for p in scenario.phases} == {"v1"}
    congelan = {p.key for p in scenario.phases if p.freeze_baseline}
    assert congelan == {"b1"}


def test_caso_digestivo_explain_global_en_las_siete_fases():
    scenario = get_scenario("caso_digestivo")
    assert all(p.explain_global for p in scenario.phases)


def test_caso_digestivo_semanas_atras_seis_a_cero():
    """B1 seis semanas atrás … e1_recovery hoy (0)."""
    scenario = get_scenario("caso_digestivo")
    semanas = {p.key: p.semanas_atras for p in scenario.phases}
    assert semanas == {
        "b1": 6,
        "b2": 5,
        "b3": 4,
        "b4": 3,
        "b5": 2,
        "e1_evento": 1,
        "e1_recovery": 0,
    }


def test_fecha_simulada_fase_resta_semanas_completas():
    scenario = get_scenario("caso_digestivo")
    ahora = datetime(2026, 9, 16, 12, 0, 0, tzinfo=UTC)
    assert fecha_simulada_fase(scenario.phases[0], ahora=ahora) == "2026-08-05T12:00:00.000000+00:00"
    assert fecha_simulada_fase(scenario.phases[-1], ahora=ahora) == ahora.isoformat(
        timespec="microseconds"
    )


def test_fecha_simulada_fase_none_en_guiones_sin_semanas_atras():
    for key in ("timeline_completo", "consejeria_regional"):
        scenario = get_scenario(key)
        assert all(p.semanas_atras is None for p in scenario.phases)
        assert all(fecha_simulada_fase(p) is None for p in scenario.phases)


def test_caso_digestivo_umbrales_calidad_dejan_las_siete_fases_en_ok():
    """Los umbrales del guion, aplicados
    sobre `DEFAULT_QUALITY_THRESHOLDS`, clasifican en `ok` las 13 métricas
    de calidad en las siete fases (peor caso `e1_evento`)."""
    from vigia.core.engine import run_scenario
    from vigia.core.schema import ThresholdKind
    from vigia.core.states import classify_with_motivo
    from vigia.core.thresholds import DEFAULT_QUALITY_THRESHOLDS

    scenario = get_scenario("caso_digestivo")
    assert scenario.umbrales_calidad == {
        "accuracy": 0.75,
        "area_under_roc": 0.70,
        "true_positive_rate": 0.65,
        "recall": 0.65,
        "gini_coefficient": 0.50,
    }

    umbrales: dict[str, dict[ThresholdKind, float]] = {}
    relativos: set[str] = set()
    for t in DEFAULT_QUALITY_THRESHOLDS.thresholds:
        if t.relativo_a is not None:
            # `value` es la fracción; el umbral lo resuelve el motor
            # con la línea base y viaja en `threshold_low` de la medida.
            relativos.add(t.metric_key)
            continue
        umbrales.setdefault(t.metric_key, {})[t.kind] = t.value
    for metric_key, valor in scenario.umbrales_calidad.items():
        umbrales[metric_key][ThresholdKind.lower_limit] = valor

    for reporte in run_scenario("caso_digestivo"):
        for m in reporte.results["quality"].measurements:
            if m.metric_key in relativos and m.group_code is None:
                # La banda de aviso de un umbral relativo es la del motor
                # (sobre el margen hasta la prevalencia), no la estándar.
                assert m.state.value == "ok", (reporte.phase_key, m.metric_key, m.value, m.extra)
                continue
            elif m.metric_key not in umbrales:
                continue
            else:
                low = umbrales[m.metric_key].get(ThresholdKind.lower_limit)
                high = umbrales[m.metric_key].get(ThresholdKind.upper_limit)
            estado, motivo = classify_with_motivo(m.value, low, high)
            assert estado.value == "ok", (reporte.phase_key, m.metric_key, m.value, motivo)


def test_caso_digestivo_default_params_igual_que_timeline_completo():
    caso = get_scenario("caso_digestivo")
    timeline = get_scenario("timeline_completo")
    assert caso.default_params == timeline.default_params


def test_caso_digestivo_descripcion_sin_vocabulario_del_harness():
    descripcion = get_scenario("caso_digestivo").description.lower()
    for palabra in ("baseline", "e1", "e2", "recovery"):
        assert palabra not in descripcion


# ---------------------------------------------------------------------------
# Regresión: los dos guiones existentes no cambian por reutilizar sus fases
# (replace() de un dataclass frozen no muta el original).
# ---------------------------------------------------------------------------


def test_timeline_completo_conserva_9_fases_sin_explain_global_en_e1():
    scenario = get_scenario("timeline_completo")
    assert len(scenario.phases) == 9
    por_clave = {p.key: p for p in scenario.phases}
    assert por_clave["b1"].explain_global is True
    assert por_clave["e1_evento"].explain_global is False
    assert por_clave["e1_recovery"].explain_global is False


def test_consejeria_regional_conserva_6_fases_sin_explain_global_en_e1_evento():
    scenario = get_scenario("consejeria_regional")
    assert len(scenario.phases) == 6
    por_clave = {p.key: p for p in scenario.phases}
    assert por_clave["e1_evento"].explain_global is False


def test_caso_digestivo_esta_en_el_registro_junto_a_los_otros_dos():
    assert set(SCENARIOS) == {"timeline_completo", "consejeria_regional", "caso_digestivo"}


def test_caso_digestivo_lleva_los_parametros_humanos_del_guion():
    """El guion fija `k_sub` del grupo joven, que es la
    condición de override de CX-1; los demás guiones no lo llevan."""
    assert get_scenario("caso_digestivo").human_params == {"k_sub": {"18-35": 0.5}}
    assert get_scenario("timeline_completo").human_params == {}
    assert get_scenario("consejeria_regional").human_params == {}
