"""Ayudas de los tests de la comparación de versiones."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import (
    Batch,
    Evaluation,
    Measurement,
    ModelVersion,
    Monitor,
)

_t = 0


def _marca() -> str:
    global _t
    _t += 1
    return f"2026-10-01T10:{_t // 60:02d}:{_t % 60:02d}.000000+00:00"


def proyecto(client: TestClient, session: Session, nombre: str = "cmp") -> tuple[int, int]:
    resp = client.post(
        "/api/projects", json={"name": nombre, "domain": "libre"}, headers=actor_headers()
    )
    assert resp.status_code == 200, resp.text
    p = resp.json()
    return p["id"], p["active_version_id"]


def version_nueva(session: Session, project_id: int, label: str = "v2") -> int:
    v = ModelVersion(project_id=project_id, label=label)
    session.add(v)
    session.commit()
    session.refresh(v)
    return v.id


def lote(session: Session, project_id: int, version_id: int, seq: int) -> int:
    b = Batch(project_id=project_id, model_version_id=version_id, seq=seq, n_rows=100)
    session.add(b)
    session.commit()
    session.refresh(b)
    return b.id


def congelar_base(session: Session, version_id: int, batch_id: int) -> None:
    v = session.get(ModelVersion, version_id)
    v.baseline_batch_id = batch_id
    session.add(v)
    session.commit()


def medida(
    session: Session, project_id: int, version_id: int, batch_id: int, monitor: str,
    metric: str, value: float | None, *, low=None, high=None, state="ok", group=None,
    interval=(None, None), n=None, motivo=None,
) -> int:
    mon = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == monitor)
    ).first()
    ev = session.exec(
        select(Evaluation).where(
            Evaluation.monitor_id == mon.id,
            Evaluation.model_version_id == version_id,
            Evaluation.batch_id == batch_id,
        )
    ).first()
    if ev is None:
        ev = Evaluation(
            monitor_id=mon.id, project_id=project_id, model_version_id=version_id,
            batch_id=batch_id, worst_state=state, created_at=_marca(),
        )
        session.add(ev)
        session.flush()
    session.add(
        Measurement(
            evaluation_id=ev.id, project_id=project_id, monitor_type=monitor,
            metric_key=metric, value=value, interval_low=interval[0],
            interval_high=interval[1], threshold_low=low, threshold_high=high,
            state=state, group_code=group, motivo=motivo,
            extra_json={"n": n} if n is not None else None,
        )
    )
    session.commit()
    return ev.id


def escenario_dos_versiones(client: TestClient, session: Session) -> dict:
    """v1 activa, v2 activa tras activar: AUC mejora, equidad empeora, F1 igual, recall sin datos en v2."""
    pid, v1 = proyecto(client, session)
    v2 = version_nueva(session, pid)
    b1_base, b1_prod = lote(session, pid, v1, 0), lote(session, pid, v1, 1)
    b2_base, b2_prod = lote(session, pid, v2, 2), lote(session, pid, v2, 3)
    congelar_base(session, v1, b1_base)
    congelar_base(session, v2, b2_base)
    for v, base, prod, auc, eq, f1 in (
        (v1, b1_base, b1_prod, 0.70, 0.95, 0.600),
        (v2, b2_base, b2_prod, 0.80, 0.70, 0.602),
    ):
        medida(session, pid, v, base, "quality", "auc", 0.75, low=0.65)
        medida(session, pid, v, prod, "quality", "auc", auc, low=0.65, n=200)
        medida(session, pid, v, prod, "quality", "f1", f1, low=0.5)
        medida(session, pid, v, prod, "fairness", "fairness_value", eq, low=0.8, high=1.25,
               n=150)
    medida(session, pid, v1, b1_prod, "quality", "recall", 0.6, low=0.5)
    medida(session, pid, v2, b2_prod, "quality", "recall", None, low=0.5,
           state="sin_datos", motivo="sin etiquetas")
    return {"pid": pid, "v1": v1, "v2": v2, "b1": (b1_base, b1_prod), "b2": (b2_base, b2_prod)}


def fila(datos: dict, metric: str, group=None) -> dict:
    return next(
        f for f in datos["filas"] if f["metric_key"] == metric and f["group_code"] == group
    )


def comparar(client: TestClient, pid: int, **params) -> dict:
    r = client.get(f"/api/projects/{pid}/versions/compare", params=params)
    assert r.status_code == 200, r.text
    return r.json()


