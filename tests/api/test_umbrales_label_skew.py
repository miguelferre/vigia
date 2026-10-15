"""La propuesta de umbrales empareja el umbral actual por
(métrica, tipo de límite). `label_skew` es la única métrica con dos límites y,
indexada solo por métrica, su mínimo recibía el valor del máximo."""

from __future__ import annotations

from unittest import mock

from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api.test_proyecto_plantilla_mapeo import _congelar_con_batch, _crear_proyecto
from vigia.core.calibration import PropuestaUmbral


def test_la_propuesta_de_label_skew_trae_el_limite_inferior_de_cada_fila(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="propuesta-label-skew")
    _congelar_con_batch(client, session, proyecto["id"], proyecto["active_version_id"])
    propuestas = [
        PropuestaUmbral(
            metric_key="label_skew", kind="lower_limit", value=-0.0225, valor_linea_base=0.0, motivo=None
        ),
        PropuestaUmbral(
            metric_key="label_skew", kind="upper_limit", value=0.0231, valor_linea_base=0.0, motivo=None
        ),
    ]
    with mock.patch("vigia.core.calibration.proponer_umbrales", return_value=propuestas):
        resp = client.get(f"/api/projects/{proyecto['id']}/thresholds/proposal")
    assert resp.status_code == 200, resp.text
    calidad = next(m for m in resp.json()["monitors"] if m["monitor_type"] == "quality")
    por_tipo = {p["kind"]: p for p in calidad["propuestas"] if p["metric_key"] == "label_skew"}
    assert por_tipo["lower_limit"]["umbral_actual"] == -0.5
    assert por_tipo["upper_limit"]["umbral_actual"] == 0.5
    assert por_tipo["lower_limit"]["origen_actual"] == "fabrica"
