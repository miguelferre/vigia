"""Alertas vivas y filtros de versión."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api.comparacion_util import (
    comparar,
    escenario_dos_versiones,
    lote,
    medida,
    proyecto,
    version_nueva,
)
from vigia.app.models import Alert


def test_alerta_viva_en_observacion_sigue_con_v2(client: TestClient, session: Session):
    pid, v1 = proyecto(client, session)
    v2 = version_nueva(session, pid)
    b1, b2 = lote(session, pid, v1, 0), lote(session, pid, v2, 1)
    ev1 = medida(session, pid, v1, b1, "fairness", "fairness_value", 1.9, high=1.25,
                 state="alerta", group="g1")
    # La alerta se abrió con v1, pasó a observación y su `last_evaluation_id` no se movió.
    medida(session, pid, v2, b2, "fairness", "fairness_value", 1.8, high=1.25,
           state="alerta", group="g1")
    session.add(
        Alert(project_id=pid, monitor_type="fairness", metric_key="fairness_value",
              group_code="g1", status="en_observacion", title="Equidad g1",
              last_evaluation_id=ev1)
    )
    # Alerta cuya última señal es de v1: en v2 la métrica ya está bien.
    medida(session, pid, v1, b1, "quality", "auc", 0.5, low=0.65, state="alerta")
    medida(session, pid, v2, b2, "quality", "auc", 0.8, low=0.65)
    session.add(
        Alert(project_id=pid, monitor_type="quality", metric_key="auc", status="abierta",
              title="AUC bajo")
    )
    session.add(
        Alert(project_id=pid, monitor_type="drift", metric_key="feature_drift_score",
              status="abierta", title="Sin señal")
    )
    session.add(
        Alert(project_id=pid, monitor_type="quality", metric_key="auc", status="cerrada",
              title="cerrada")
    )
    session.commit()
    vivas = comparar(client, pid, a=v1, b=v2)["alertas_vivas"]
    por_titulo = {a["title"]: a for a in vivas}
    assert set(por_titulo) == {"Equidad g1", "AUC bajo", "Sin señal"}
    assert por_titulo["Equidad g1"]["model_version_id"] == v2
    assert por_titulo["Equidad g1"]["version_label"] == "v2"
    assert por_titulo["AUC bajo"]["model_version_id"] == v1
    assert por_titulo["Sin señal"]["model_version_id"] is None
    assert por_titulo["Sin señal"]["motivo"]


def test_alerta_cruzada_se_casa_por_prefijo_y_exige_estado(
    client: TestClient, session: Session
):
    pid, v1 = proyecto(client, session)
    v2 = version_nueva(session, pid)
    b1, b2 = lote(session, pid, v1, 0), lote(session, pid, v2, 1)
    medida(session, pid, v1, b1, "cross", "cx1_override_z:g1", 3.1, state="alerta", group="g1")
    medida(session, pid, v2, b2, "cross", "cx1_override_z:g1", 2.9, state="alerta", group="g1")
    # CX-6 sin ninguna medida en alerta: sin versión, aunque haya historial.
    medida(session, pid, v2, b2, "cross", "cx6_override_z:g1", 0.2, state="ok", group="g1")
    for regla in ("CX-1", "CX-6"):
        session.add(
            Alert(project_id=pid, monitor_type="cross", metric_key=regla, group_code="g1",
                  status="en_observacion", title=regla, history_json=[{"evaluation_id": 1}])
        )
    session.commit()
    por_titulo = {a["title"]: a for a in comparar(client, pid, a=v1, b=v2)["alertas_vivas"]}
    assert por_titulo["CX-1"]["model_version_id"] == v2
    assert por_titulo["CX-6"]["model_version_id"] is None and por_titulo["CX-6"]["motivo"]


def test_filtros_model_version_id(client: TestClient, session: Session):
    e = escenario_dos_versiones(client, session)
    pid, v1, v2 = e["pid"], e["v1"], e["v2"]
    base = f"/api/projects/{pid}"
    todos = client.get(f"{base}/timeline", params={"monitor_type": "quality", "metric_key": "auc"}).json()["items"]
    assert {p["model_version_id"] for p in todos} == {v1, v2}
    solo2 = client.get(
        f"{base}/timeline", params={"monitor_type": "quality", "metric_key": "auc", "model_version_id": v2}
    ).json()["items"]
    assert solo2 and {p["model_version_id"] for p in solo2} == {v2}
    ev = client.get(f"{base}/evaluations", params={"model_version_id": v1, "limit": 100}).json()
    assert ev["total"] > 0 and {i["model_version_id"] for i in ev["items"]} == {v1}
    lotes = client.get(f"{base}/batches", params={"model_version_id": v2}).json()
    assert lotes["total"] == 2 and {b["model_version_id"] for b in lotes["items"]} == {v2}
    assert client.get(f"{base}/batches").json()["total"] == 4
