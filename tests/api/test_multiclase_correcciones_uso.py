"""Arreglos del backend: la comprobación de codificación en multiclase."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api import _datos_multiclase as d
from tests.api.conftest import actor_headers
from tests.api.test_human_multiclase import _crear, _diario, _subir
from vigia.app.models import Event

MOTIVO = "no aplica en multiclase: el registro trae nombres de clase validados contra las clases del modelo"


def test_multiclase_no_comprueba_la_codificacion_y_dice_por_que(client: TestClient, session: Session):
    proyecto = _crear(client, "a-223-uso")
    resp = _subir(client, proyecto["id"], _diario(300))
    assert resp.status_code == 200, resp.text
    comp = resp.json()["comprobacion_codificacion"]
    assert comp["estado"] == "inconcluso"
    assert comp["r"] is None and comp["p"] is None
    assert comp["n"] == 300
    assert comp["motivo"] == MOTIVO
    evento = session.exec(select(Event).where(Event.action == "usage_log.ingerido")).all()[-1]
    assert evento.after_json["comprobacion_codificacion"]["motivo"] == MOTIVO


def test_multiclase_con_lotes_tampoco_da_r(client: TestClient):
    """Con lotes de producción, el código viejo daba `r` (proporción de salidas favorables
    de la semana, p. ej. 0,75) y un `coherente` que no comprobaba nada."""
    proyecto, _s, _t = d.linea_base_multiclase(client, "a-223-lotes", n=300)
    # Usa las clases de `d.CLASES`; el diario lleva sus nombres de clase.
    filas = ["date,human_decision,model_output,ground_truth"]
    for i in range(250):
        clase = d.CLASES[i % 5]
        filas.append(f"2026-01-{1 + i % 28:02d},{clase},{clase},{clase}")
    resp = client.post(
        f"/api/projects/{proyecto['id']}/usage-logs/upload",
        files={"file": ("uso.csv", ("\n".join(filas) + "\n").encode(), "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    comp = resp.json()["comprobacion_codificacion"]
    assert comp["r"] is None and comp["estado"] == "inconcluso"
    assert comp["motivo"].startswith("no aplica en multiclase")


def test_binario_sigue_comprobando(client: TestClient):
    from pathlib import Path

    usage = Path(__file__).resolve().parents[2] / "data" / "demo" / "usage_logs_demo.csv"
    p = client.post("/api/projects", json={"name": "a-223-bin", "domain": "libre"}, headers=actor_headers("miguel"))
    assert p.status_code == 200, p.text
    resp = client.post(
        f"/api/projects/{p.json()['id']}/usage-logs/upload",
        files={"file": ("uso.csv", usage.read_bytes(), "text/csv")},
        data={"valor_favorable": "refer"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    comp = resp.json()["comprobacion_codificacion"]
    assert comp["r"] is not None  # sin lotes, `inconcluso` por falta de lotes, pero con `r`
    assert "no aplica en multiclase" not in (comp["motivo"] or "")
