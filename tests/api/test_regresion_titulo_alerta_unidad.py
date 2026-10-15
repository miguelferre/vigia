"""El título de la alerta de una
medida en la unidad de la salida usa los decimales de la interfaz, no tres fijos."""

from types import SimpleNamespace

from vigia.app.services.alerting import _numero_unidad_es, _titulo


def _proyecto():
    return SimpleNamespace(task_type="regression", target_unit="horas por semana", mapping_template_json=None)


def test_d2_el_titulo_del_mae_usa_los_decimales_de_la_interfaz():
    t = _titulo(None, _proyecto(), "quality", metric_key="mean_absolute_error", group_code=None,
                value=7.43812, threshold_low=None, threshold_high=5.9123)
    assert t == "Error absoluto medio (MAE): 7,44 horas por semana (umbral <= 5,91)", t
    assert "7,438" not in t


def test_d2_decimales_por_magnitud():
    assert _numero_unidad_es(123.456) == "123"
    assert _numero_unidad_es(12.345) == "12,3"
    assert _numero_unidad_es(0.0456) == "0,046"


def test_d2_una_medida_sin_unidad_conserva_tres_decimales():
    t = _titulo(None, _proyecto(), "quality", metric_key="r2", group_code=None,
                value=0.73591, threshold_low=0.7, threshold_high=None)
    assert "0,736" in t and "(umbral >= 0,700)" in t, t
