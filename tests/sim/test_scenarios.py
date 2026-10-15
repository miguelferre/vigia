"""Tests de vigia.sim.scenarios: registro, materialización canned/generate
y contrato de reproducción del orden manipulado.
"""
from __future__ import annotations

import pytest

from vigia.sim import scenarios
from vigia.sim.scenarios import (
    SCENARIOS,
    VAR_DATOS_DEMO,
    demo_data_dir,
    get_scenario,
    materialize_phase,
)

_DATA_DIR = None  # usa el data_dir por defecto de scenarios.py


def _fase(scenario_key: str, phase_key: str):
    scenario = get_scenario(scenario_key)
    for p in scenario.phases:
        if p.key == phase_key:
            return p
    raise AssertionError(f"fase {phase_key!r} no está en {scenario_key!r}")


def test_registro_tiene_las_tres_claves():
    assert set(SCENARIOS) == {"timeline_completo", "consejeria_regional", "caso_digestivo"}


def test_timeline_completo_tiene_9_fases():
    assert len(get_scenario("timeline_completo").phases) == 9


def test_consejeria_regional_tiene_6_fases():
    assert len(get_scenario("consejeria_regional").phases) == 6


@pytest.mark.parametrize(
    "scenario_key", ["timeline_completo", "consejeria_regional", "caso_digestivo"]
)
def test_todas_las_rutas_canned_existen(scenario_key):
    from pathlib import Path

    base = Path(__file__).resolve().parents[2] / "data" / "demo"
    scenario = get_scenario(scenario_key)
    for phase in scenario.phases:
        if phase.canned is None:
            continue
        payload_path, feedback_path = phase.canned
        assert (base / payload_path).exists(), f"{phase.key}: falta {payload_path}"
        assert (base / feedback_path).exists(), f"{phase.key}: falta {feedback_path}"


def test_solo_e2_lleva_orden_manipulado():
    scenario = get_scenario("timeline_completo")
    manipuladas = {p.key for p in scenario.phases if p.orden_manipulado}
    assert manipuladas == {"e2_evento", "e2_recovery"}


def test_solo_e2_recovery_es_v2_y_congela_baseline():
    scenario = get_scenario("timeline_completo")
    v2 = {p.key for p in scenario.phases if p.model_version == "v2"}
    assert v2 == {"e2_recovery"}
    congelan = {p.key for p in scenario.phases if p.freeze_baseline}
    assert congelan == {"b1", "e2_recovery"}


def test_materialize_b1_canned_450_filas_prediccion_y_etiqueta():
    b1 = _fase("timeline_completo", "b1")
    datos = materialize_phase(b1, source="canned")
    assert len(datos.df_scored) == 450
    assert "PREDICTION" in datos.df_scored.columns
    assert "Has_Referral_in_Window" in datos.df_scored.columns
    assert datos.source == "canned"
    assert datos.permutation is None


def test_materialize_b1_generate_coincide_con_canned():
    b1 = _fase("timeline_completo", "b1")
    canned = materialize_phase(b1, source="canned")
    generado = materialize_phase(b1, source="generate")

    assert (
        canned.df_scored["PREDICTION"].to_numpy() == generado.df_scored["PREDICTION"].to_numpy()
    ).all()
    assert list(canned.df_scored["PROBABILITIES"]) == list(generado.df_scored["PROBABILITIES"])
    assert (
        canned.df_scored["Has_Referral_in_Window"].to_numpy()
        == generado.df_scored["Has_Referral_in_Window"].to_numpy()
    ).all()


def test_materialize_e2_evento_generate_reproduce_orden_del_enlatado():
    e2 = _fase("timeline_completo", "e2_evento")
    canned = materialize_phase(e2, source="canned")
    generado = materialize_phase(e2, source="generate")

    assert generado.permutation is not None
    edades_canned = canned.df_scored["Age"].astype(int).tolist()
    edades_generado = generado.df_scored["Age"].astype(int).tolist()
    assert edades_canned == edades_generado


def test_params_override_bias_additive_cambia_predicciones():
    e1_evento = _fase("timeline_completo", "e1_evento")
    canned = materialize_phase(e1_evento, source="canned")
    generado = materialize_phase(
        e1_evento, source="generate", params_override={"bias_additive": 0.0}
    )
    assert not (
        canned.df_scored["PREDICTION"].to_numpy() == generado.df_scored["PREDICTION"].to_numpy()
    ).all()


def test_get_scenario_no_existe_lanza_key_error():
    with pytest.raises(KeyError):
        get_scenario("no_existe")


def test_expected_e1_evento_contiene_fairness():
    e1_evento = _fase("timeline_completo", "e1_evento")
    assert "fairness" in e1_evento.expected


def test_expected_e2_evento_contiene_quality_alerta_y_fairness_ok():
    e2_evento = _fase("timeline_completo", "e2_evento")
    assert e2_evento.expected["quality"] == "alerta"
    assert e2_evento.expected["fairness"] == "ok"


# ---------------------------------------------------------------------------
# demo_data_dir: los datos enlatados dentro y fuera del paquete
# ---------------------------------------------------------------------------


def test_demo_data_dir_apunta_a_los_datos_enlatados():
    base = demo_data_dir()
    assert base.is_dir()
    assert (base / "dossier_demo.json").is_file()
    assert (base / "escenario_1").is_dir()
    assert (base / "escenario_2").is_dir()


def test_demo_data_dir_respeta_la_variable_de_entorno(tmp_path, monkeypatch):
    (tmp_path / "escenario_1").mkdir()
    monkeypatch.setenv(VAR_DATOS_DEMO, str(tmp_path))
    assert demo_data_dir() == tmp_path


def test_demo_data_dir_ignora_la_variable_vacia(monkeypatch):
    monkeypatch.setenv(VAR_DATOS_DEMO, "   ")
    assert (demo_data_dir() / "dossier_demo.json").is_file()


def test_demo_data_dir_lista_las_rutas_probadas_si_no_hay_ninguna(tmp_path, monkeypatch):
    monkeypatch.setenv(VAR_DATOS_DEMO, str(tmp_path / "no_existe"))
    monkeypatch.setattr(
        scenarios,
        "_candidatos_datos_demo",
        lambda: [tmp_path / "no_existe", tmp_path / "tampoco"],
    )
    with pytest.raises(FileNotFoundError) as exc:
        demo_data_dir()
    mensaje = str(exc.value)
    assert "no_existe" in mensaje and "tampoco" in mensaje
    assert VAR_DATOS_DEMO in mensaje
