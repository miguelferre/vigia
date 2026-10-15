"""`supera_umbral` en las reglas de `GET /projects/{id}/cross/latest`.

La tarjeta de una regla cruzada decía «desviación -3,6 (muy fuera de lo normal)»
aunque la regla estuviera en «Correcto». Ahora la API dice si el valor cruza el
umbral en el sentido en que la regla alerta, leído de `cross_alerts.py`:

  CX-1  z del override <= -z_alert        CX-2  z del override global >= z_alert
  CX-3  z del rescate  <= -z_alert        CX-6  |z| >= z_alert (dos colas)
"""

from __future__ import annotations

import pytest

from vigia.app.models import Measurement
from vigia.app.schemas.cross import CrossRuleOut
from vigia.app.services.human_layer import _cross_rules_from_measurements


def _medida(clave: str, valor: float | None, grupo: str | None = None) -> Measurement:
    return Measurement(evaluation_id=1, metric_key=clave, value=valor, state="ok", group_code=grupo)


def _supera(clave: str, valor: float | None, **kw) -> bool | None:
    reglas = _cross_rules_from_measurements([_medida(clave, valor, "g")], **kw)
    assert len(reglas) == 1
    CrossRuleOut(**reglas[0])
    return reglas[0]["supera_umbral"]


def test_la_regla_de_la_api_lleva_supera_umbral():
    assert "supera_umbral" in CrossRuleOut.model_fields


@pytest.mark.parametrize(
    ("clave", "valor", "esperado"),
    [
        ("cx1_override_z:g", -3.6, True),
        ("cx1_override_z:g", -3.0, True),  # el umbral es inclusivo (<=)
        ("cx1_override_z:g", -2.9, False),
        ("cx1_override_z:g", 4.0, False),  # lejos, pero hacia el lado que no alerta
        ("cx2_override_z", 3.5, True),
        ("cx2_override_z", 2.4, False),
        ("cx2_override_z", -5.0, False),
        ("cx3_rescue_z", -3.2, True),
        ("cx3_rescue_z", -1.0, False),
        ("cx3_rescue_z", 3.2, False),
        ("cx6_override_z:g", -3.1, True),
        ("cx6_override_z:g", 3.1, True),  # CX-6 es de dos colas
        ("cx6_override_z:g", 2.0, False),
    ],
)
def test_supera_umbral_va_en_el_sentido_en_que_la_regla_alerta(clave, valor, esperado):
    assert _supera(clave, valor) is esperado


@pytest.mark.parametrize(
    "clave", ["cx5_chi2_p", "cx4_deskilling", "human_review_zero"]
)
def test_las_reglas_sin_desviacion_no_traen_supera_umbral(clave):
    assert _supera(clave, 0.0001) is None


def test_sin_valor_no_hay_juicio():
    assert _supera("cx1_override_z:g", None) is None


def test_el_umbral_es_el_z_alert_configurado_del_monitor():
    assert _supera("cx1_override_z:g", -2.5) is False
    assert _supera("cx1_override_z:g", -2.5, z_alert=2.0) is True


def test_cross_latest_sirve_supera_umbral_en_cx6(client, session):
    from tests.api.test_human_cruzadas_cascada_servicio import _evaluar, _preparar_hasta_cx6

    proyecto, _ = _preparar_hasta_cx6(client, session, "b3-supera-umbral")
    _evaluar(client, proyecto["id"])
    reglas = client.get(f"/api/projects/{proyecto['id']}/cross/latest").json()["rules"]
    cx6 = [r for r in reglas if r["rule"] == "CX-6" and r["group"] == "b"]
    assert cx6 and cx6[0]["state"] == "alerta" and cx6[0]["supera_umbral"] is True
    cx5 = [r for r in reglas if r["rule"] == "CX-5"]
    assert all(r["supera_umbral"] is None for r in cx5)
