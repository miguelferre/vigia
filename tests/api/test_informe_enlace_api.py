"""El enlace de `informe_revision` y `deskilling_texto` con la API.

Cubren las funciones enlazadas con la API, que antes solo se probaban sueltas.
Se activan solos cuando el código está enlazado; mientras no, se saltan con el
motivo. Una vez enlazados, que fallen es una regresión."""

from __future__ import annotations

import inspect
import re

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

pytest.importorskip("vigia.human._vendor.interaction_review")

from tests.api.conftest import actor_headers
from tests.api.test_dossiers import _crear_dossier, _reproducir_demo
from vigia.app.services import dossiers
from vigia.human import ir_adapter

_INGLES_RESUMEN = re.compile(
    # Formas inglesas de «converge»: «convergencia» es español y vale.
    r"\b(Windows?|Trend|converg(?:e|es|ed|ing|ence)|rescue|accuracy|agreement|Caution|Insufficient|signal)\b"
    r"|Investigate; not a diagnosis",
    re.IGNORECASE,
)
_PALABRAS_MARCO_VIEJO = ("Findings", "Severity", "Remediation", "Summary", "Guideline")

_deskilling_enlazado = "resumen_md_es" in inspect.getsource(ir_adapter)
_informe_enlazado = hasattr(dossiers, "informe_html")


def _revision_b0(client: TestClient) -> tuple[int, int]:
    run = _reproducir_demo(client)
    creado = _crear_dossier(client, run["project_id"], include_telemetry=True)
    assert creado.status_code == 200, creado.text
    lanzada = client.post(
        f"/api/dossiers/{creado.json()['id']}/reviews",
        json={
            "approach": "b0",
            "corpus": "todas",
            "dedup": True,
            "crosswalk": True,
            "actor": "miguel",
            "role": "auditor",
            "motivo": "informe en español",
        },
        headers=actor_headers("miguel"),
    )
    assert lanzada.status_code == 200, lanzada.text
    revision = client.get(f"/api/dossiers/{creado.json()['id']}").json()["reviews"][0]
    return run["project_id"], revision["id"]


@pytest.mark.skipif(not _deskilling_enlazado, reason="deskilling sin enlazar en ir_adapter/routers.human")
def test_get_deskilling_da_resumen_y_motivo_en_espanol(client: TestClient):
    project_id, _ = _revision_b0(client)
    resp = client.get(f"/api/projects/{project_id}/deskilling")
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert not _INGLES_RESUMEN.search(cuerpo["summary_md"]), cuerpo["summary_md"]
    if cuerpo["signal"]:
        assert not _INGLES_RESUMEN.search(cuerpo["signal"]["reason"]), cuerpo["signal"]["reason"]


@pytest.mark.skipif(
    not _informe_enlazado, reason="informe sin enlazar en services/dossiers y routers/dossiers"
)
def test_informe_de_una_revision_vieja_se_redibuja_en_espanol(client: TestClient, session: Session):
    from vigia.app.models import DossierReview

    _, review_id = _revision_b0(client)
    fila = session.get(DossierReview, review_id)
    # Una revisión guardada con el informe antiguo: marco inglés en `report_html`.
    fila.report_html = "<html lang='en'><h2>Findings</h2><th>Severity</th></html>"
    session.add(fila)
    session.commit()

    resp = client.get(f"/api/reviews/{review_id}/report")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")
    assert '<html lang="es"' in resp.text
    for palabra in _PALABRAS_MARCO_VIEJO:
        assert palabra not in resp.text, palabra


@pytest.mark.skipif(
    not _informe_enlazado, reason="informe sin enlazar en services/dossiers y routers/dossiers"
)
def test_report_modo_claro_oscuro_y_auto(client: TestClient):
    _, review_id = _revision_b0(client)
    claro = client.get(f"/api/reviews/{review_id}/report", params={"modo": "claro"})
    oscuro = client.get(f"/api/reviews/{review_id}/report", params={"modo": "oscuro"})
    auto = client.get(f"/api/reviews/{review_id}/report")
    assert claro.status_code == oscuro.status_code == auto.status_code == 200
    assert claro.text != oscuro.text
    assert "prefers-color-scheme" in auto.text
    malo = client.get(f"/api/reviews/{review_id}/report", params={"modo": "sepia"})
    assert malo.status_code == 422
