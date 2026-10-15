"""Matriz de riesgos, calibración y exportación de evidencias.

Cada test comprueba el control seguro de un apunte; ver `HUELLAS`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api.conftest import actor_headers
from tests.api.test_risks import _crear_proyecto, _primera_alerta, _reproducir_demo
from tests.seguridad import _base_proyecto as _base
from vigia.app.models import Alert
from vigia.app.services import risks as risks_service
from vigia.app.services import risks_data
from vigia.human import risk_levels

# Fixtures compartidas (carpeta de datos temporal y cliente con `base_url` local).
app, client, session, settings = _base.app, _base.client, _base.session, _base.settings

HUELLAS = {
    "test_calibration_until_solo_admite_fechas_iso": "calibration-iso-dates",
    "test_el_alta_de_riesgo_reintenta_ante_un_codigo_repetido": "risk-code-retry-and-day-bounds",
    "test_los_movimientos_acotan_los_dias": "risk-code-retry-and-day-bounds",
    "test_un_riesgo_no_nace_de_una_alerta_cerrada": "risk-from-closed-alert",
    "test_bajar_la_celda_propuesta_pide_un_motivo_con_contenido": "risk-from-closed-alert",
    "test_la_exportacion_de_evidencias_no_lleva_la_ruta_de_datos": "evidence-export-path",
}
CUERPO = {"actor": "miguel", "role": "auditor", "motivo": "riesgo abierto tras revisión del equipo"}


def test_calibration_until_solo_admite_fechas_iso(client: TestClient):
    """La fecha de calibración se valida al guardarla: un texto que no es una fecha
    ISO da 422 y no cambia el proyecto."""
    proyecto = _crear_proyecto(client, "s1c-calibracion")
    ruta = f"/api/projects/{proyecto['id']}"
    for malo in ("zzz", "2026-13-40", "mañana", "2026"):
        resp = client.patch(
            ruta,
            json={"actor": "miguel", "motivo": "prueba", "calibration_until": malo},
            headers=actor_headers("miguel"),
        )
        assert resp.status_code == 422, (malo, resp.text)
    assert client.get(ruta).json()["calibration_until"] is None
    for bueno in ("2026-12-31", "2026-12-31T10:00:00+00:00"):
        resp = client.patch(
            ruta,
            json={"actor": "miguel", "motivo": "prueba", "calibration_until": bueno},
            headers=actor_headers("miguel"),
        )
        assert resp.status_code == 200, (bueno, resp.text)


def test_el_alta_de_riesgo_reintenta_ante_un_codigo_repetido(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """Si otra alta se lleva el número que se acababa de calcular, el alta vuelve a
    calcularlo en vez de dar un error del servidor."""
    proyecto = _crear_proyecto(client, "s1c-codigo")
    url = f"/api/projects/{proyecto['id']}/risks"
    base = {"impact_level": 2, "probability_level": 2, "title": "uno", **CUERPO}
    assert client.post(url, json=base, headers=actor_headers("miguel")).json()["code"] == "R-001"
    real, llamadas = risks_data.siguiente_codigo, []

    def desfasado(session, project_id):
        llamadas.append(1)
        return "R-001" if len(llamadas) == 1 else real(session, project_id)

    monkeypatch.setattr(risks_service, "siguiente_codigo", desfasado, raising=False)
    monkeypatch.setattr(risks_data, "siguiente_codigo", desfasado)
    resp = client.post(url, json={**base, "title": "dos"}, headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == "R-002"


def test_los_movimientos_acotan_los_dias(client: TestClient):
    """El historial de movimientos rechaza un número de días fuera de rango."""
    proyecto = _crear_proyecto(client, "s1c-dias")
    url = f"/api/projects/{proyecto['id']}/risks/movements"
    assert client.get(url, params={"days": 36500}).status_code == 200
    for dias in (0, 36501, 10**12):
        resp = client.get(url, params={"days": dias})
        assert resp.status_code == 422, (dias, resp.text)


def _alerta_de_demo(client: TestClient) -> tuple[int, dict]:
    run = _reproducir_demo(client)
    return run["project_id"], _primera_alerta(client, run["project_id"])


def test_un_riesgo_no_nace_de_una_alerta_cerrada(client: TestClient, session: Session):
    """El alta desde una alerta exige que la alerta siga viva: cerrada o retirada, 409."""
    pid, alerta = _alerta_de_demo(client)
    url = f"/api/projects/{pid}/risks"
    for estado in ("cerrada", "retirada"):
        fila = session.get(Alert, alerta["id"])
        fila.status = estado
        session.add(fila)
        session.commit()
        resp = client.post(
            url,
            json={"origin_alert_id": alerta["id"], "title": "desde alerta fuera", **CUERPO},
            headers=actor_headers("miguel"),
        )
        assert resp.status_code == 409, (estado, resp.text)
    assert client.get(url).json()["total"] == 0


def test_bajar_la_celda_propuesta_pide_un_motivo_con_contenido(client: TestClient, session: Session):
    """Bajar impacto o probabilidad por debajo de la propuesta de la alerta exige un
    motivo con contenido y deja la propuesta en el diario."""
    pid, alerta = _alerta_de_demo(client)
    url = f"/api/projects/{pid}/risks"
    fila = session.get(Alert, alerta["id"])
    propuesta = risk_levels.PROPUESTA_POR_MONITOR[(fila.monitor_type, fila.severity)]
    bajo = {"origin_alert_id": alerta["id"], "title": "riesgo bajado", "impact_level": 1}
    assert propuesta[0] > 1
    corto = client.post(url, json={**bajo, **CUERPO, "motivo": "ok"}, headers=actor_headers("miguel"))
    assert corto.status_code == 422, corto.text
    largo = client.post(url, json={**bajo, **CUERPO}, headers=actor_headers("miguel"))
    assert largo.status_code == 200, largo.text
    eventos = client.get("/api/events", params={"project_id": pid, "limit": 500}).json()["items"]
    creado = next(e for e in eventos if e["action"] == "riesgo.creado")
    assert creado["after"]["por_debajo_de_la_propuesta"] is True
    assert creado["after"]["propuesta"] == {"impact_level": propuesta[0], "probability_level": propuesta[1]}
    sin_bajar = client.post(
        url,
        json={"origin_alert_id": alerta["id"], "title": "riesgo propuesto", **CUERPO, "motivo": "ok"},
        headers=actor_headers("miguel"),
    )
    assert sin_bajar.status_code == 200, sin_bajar.text


def test_la_exportacion_de_evidencias_no_lleva_la_ruta_de_datos(client: TestClient):
    """La exportación del diario de un proyecto no incluye la ruta absoluta de la
    carpeta de datos, ni en JSON ni en HTML, y el diario sigue sin tocarse."""
    proyecto = _crear_proyecto(client, "s1c-evidencias")
    carpeta = str(client.app.state.settings.data_dir)
    marca = client.app.state.settings.data_dir.parent.name
    for formato in ("json", "html"):
        resp = client.get("/api/events/export", params={"project_id": proyecto["id"], "format": formato})
        assert resp.status_code == 200, resp.text
        assert "sistema.arranque" in resp.text
        assert marca not in resp.text and "data_dir" not in resp.text, formato
    en_pantalla = client.get("/api/events", params={"limit": 500}).text
    assert carpeta.replace("\\", "\\\\") in en_pantalla or "data_dir" in en_pantalla
