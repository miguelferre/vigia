"""Las subidas guardan la correlación del agente.

La misión por MCP dejó 39 de 50 eventos de agente sin `correlation_id`: la
subida y el mapeo de datasets, el diario de uso y los outcomes no leían la
cabecera `X-Vigia-Correlation`.
"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import Event

DEMO = Path(__file__).resolve().parents[2] / "data" / "demo"
CID = "5f1c7a52-8f0e-4a8e-9d55-0d6f2b1c3e01"


def _agente(client: TestClient) -> dict[str, str]:
    token = client.get("/api/settings?reveal=true").json()["mcp_token"]
    return actor_headers("claude-code", kind="agente", correlation=CID, token=token)


def _cid_de(session: Session, action: str) -> list[str | None]:
    return [e.correlation_id for e in session.exec(select(Event).where(Event.action == action)).all()]


def test_subidas_del_agente_guardan_la_correlacion(client: TestClient, session: Session):
    cab = _agente(client)
    proyecto = client.post(
        "/api/projects", json={"name": "t5-correlacion", "domain": "reuma"}, headers=cab
    ).json()
    pid = proyecto["id"]

    contenido = (DEMO / "escenario_1" / "01_baseline_feedback.json").read_bytes()
    resp = client.post(
        f"/api/projects/{pid}/datasets/upload",
        files={"file": ("base.json", contenido, "application/json")},
        data={"kind": "combined", "role": "baseline"},
        headers=cab,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    resp = client.put(
        f"/api/datasets/{body['dataset']['id']}/mapping",
        json={"mapping": body["suggested_mapping"]},
        headers=cab,
    )
    assert resp.status_code == 200, resp.text

    with (DEMO / "usage_logs_demo.csv").open("rb") as f:
        resp = client.post(
            f"/api/projects/{pid}/usage-logs/upload",
            files={"file": ("uso.csv", f, "text/csv")},
            headers=cab,
        )
    assert resp.status_code == 200, resp.text

    csv = "period,metric_key,value,source\n2026-01,tasa,0.8,manual\n"
    resp = client.post(
        f"/api/projects/{pid}/outcomes",
        files={"file": ("outcomes.csv", io.BytesIO(csv.encode()), "text/csv")},
        headers=cab,
    )
    assert resp.status_code == 200, resp.text

    for accion in ("dataset.subido", "dataset.mapeado", "usage_log.ingerido", "outcome.ingerido"):
        assert _cid_de(session, accion) == [CID], accion
