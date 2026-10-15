"""Proyectos: creación, versiones, reinicio y estado."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import Batch, Event, ModelVersion, Monitor, Project
from vigia.core.thresholds import DEFAULT_FAIRNESS_THRESHOLDS


def _crear_proyecto(client: TestClient, name: str = "reuma-piloto", domain: str = "reuma") -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": domain},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- creación ---------------------------------------------------------------


def test_crear_proyecto_deja_version_v1_activa_y_cinco_monitores(client: TestClient):
    proyecto = _crear_proyecto(client)
    assert proyecto["domain"] == "reuma"
    assert len(proyecto["versions"]) == 1
    v1 = proyecto["versions"][0]
    assert v1["label"] == "v1"
    assert v1["is_active"] is True
    assert proyecto["active_version_id"] == v1["id"]

    tipos = {m["type"] for m in proyecto["monitors"]}
    assert tipos == {"fairness", "quality", "drift", "explain", "cross"}
    for monitor in proyecto["monitors"]:
        assert monitor["enabled"] is True
        assert monitor["protocolo_md"]

    fairness = next(m for m in proyecto["monitors"] if m["type"] == "fairness")
    umbrales_esperados = DEFAULT_FAIRNESS_THRESHOLDS.model_dump(mode="json")
    # Los umbrales nunca tocados salen con `origen: "fabrica"` explícito.
    umbrales_esperados["thresholds"] = [
        {**t, "origen": "fabrica"} for t in umbrales_esperados["thresholds"]
    ]
    assert fairness["thresholds"] == umbrales_esperados
    assert fairness["config"]["min_records"] == 200


def test_crear_proyecto_no_expone_hmac_salt(client: TestClient):
    proyecto = _crear_proyecto(client, name="sin-salt")
    assert "hmac_salt" not in proyecto
    assert all("hmac_salt" not in v for v in proyecto["versions"])


def test_crear_proyecto_domain_invalido_422(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={"name": "x", "domain": "no-existe"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422


def test_crear_proyecto_nombre_solo_espacios_422(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={"name": "   ", "domain": "libre"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422


def test_crear_proyecto_nombre_duplicado_409(client: TestClient):
    _crear_proyecto(client, name="duplicado")
    resp = client.post(
        "/api/projects", json={"name": "duplicado", "domain": "libre"}, headers=actor_headers()
    )
    assert resp.status_code == 409


# --- versiones, activación y baseline ---------------------------------------


def test_crear_version_activar_y_congelar_baseline_dejan_eventos_con_before_after(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="con-version")
    project_id = proyecto["id"]
    v1_id = proyecto["active_version_id"]

    resp = client.post(
        f"/api/projects/{project_id}/versions",
        json={
            "label": "v2",
            "model_kind": "sim_logistic",
            "actor": "miguel",
            "motivo": "nueva versión de modelo",
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    v2 = resp.json()
    assert v2["fairness_window_n"] == 200
    assert v2["is_active"] is False

    resp = client.post(
        f"/api/model-versions/{v2['id']}/activate",
        json={"actor": "miguel", "motivo": "pasa a producción"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is True

    evento_activacion = session.exec(
        select(Event).where(Event.action == "version.activada")
    ).one()
    assert evento_activacion.before_json == {"active_version_id": v1_id}
    assert evento_activacion.after_json == {"active_version_id": v2["id"]}
    assert evento_activacion.actor_id == "miguel"
    assert evento_activacion.motivo == "pasa a producción"

    proyecto_bd = session.get(Project, project_id)
    assert proyecto_bd is not None
    assert proyecto_bd.active_version_id == v2["id"]

    # Crea a mano un lote de esa versión para congelar su baseline.
    batch = Batch(project_id=project_id, model_version_id=v2["id"], seq=0, n_rows=10)
    session.add(batch)
    session.commit()
    session.refresh(batch)

    resp = client.post(
        f"/api/model-versions/{v2['id']}/baseline",
        json={"batch_id": batch.id, "actor": "miguel", "motivo": "primer lote estable"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["baseline_batch_id"] == batch.id
    assert body["frozen_at"] is not None

    evento_baseline = session.exec(
        select(Event).where(Event.action == "version.baseline_congelado")
    ).one()
    assert evento_baseline.before_json == {"baseline_batch_id": None, "frozen_at": None}
    assert evento_baseline.after_json["baseline_batch_id"] == batch.id
    assert evento_baseline.motivo == "primer lote estable"

    # Congelar de nuevo sin laboratorio -> 409.
    resp = client.post(
        f"/api/model-versions/{v2['id']}/baseline",
        json={"batch_id": batch.id, "actor": "miguel", "motivo": "otra vez"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 409


def test_congelar_baseline_sin_motivo_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="sin-motivo")
    resp = client.post(
        f"/api/model-versions/{proyecto['active_version_id']}/baseline",
        json={"batch_id": 1, "actor": "miguel", "motivo": ""},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422


# --- reinicio y borrado -------------------------------------------------


def test_reset_deja_el_proyecto_virgen_y_conserva_monitores(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, name="para-reiniciar")
    project_id = proyecto["id"]
    v1_id = proyecto["active_version_id"]

    batch = Batch(project_id=project_id, model_version_id=v1_id, seq=0, n_rows=5)
    session.add(batch)
    session.commit()
    session.refresh(batch)
    client.post(
        f"/api/model-versions/{v1_id}/baseline",
        json={"batch_id": batch.id, "actor": "miguel", "motivo": "baseline inicial"},
        headers=actor_headers("miguel"),
    )

    resp = client.post(
        f"/api/projects/{project_id}/reset",
        json={"actor": "miguel", "motivo": "limpiar para relanzar la demo", "confirm": True},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"]["batches"] == 1

    assert session.exec(select(Batch).where(Batch.project_id == project_id)).all() == []
    monitores = session.exec(select(Monitor).where(Monitor.project_id == project_id)).all()
    assert len(monitores) == 5
    versiones = session.exec(select(ModelVersion).where(ModelVersion.project_id == project_id)).all()
    assert len(versiones) == 1
    assert versiones[0].baseline_batch_id is None
    assert versiones[0].frozen_at is None

    evento = session.exec(select(Event).where(Event.action == "proyecto.reiniciado")).one()
    assert evento.before_json["batches"] == 1


def test_reset_sin_confirm_400(client: TestClient):
    proyecto = _crear_proyecto(client, name="reset-sin-confirm")
    resp = client.post(
        f"/api/projects/{proyecto['id']}/reset",
        json={"actor": "miguel", "motivo": "x", "confirm": False},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 400


def test_delete_sin_confirm_400_y_con_confirm_204(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, name="para-borrar")
    project_id = proyecto["id"]

    resp = client.delete(f"/api/projects/{project_id}", headers=actor_headers("miguel"))
    assert resp.status_code == 400

    resp = client.delete(
        f"/api/projects/{project_id}?confirm=true", headers=actor_headers("miguel")
    )
    assert resp.status_code == 204
    assert session.get(Project, project_id) is None
    # Los eventos del proyecto borrado se conservan (sin FK a project).
    eventos = session.exec(select(Event).where(Event.project_id == project_id)).all()
    assert any(e.action == "proyecto.creado" for e in eventos)


# --- estado y PATCH -----------------------------------------------------


def test_project_state_refleja_alertas_y_ultimo_lote(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, name="con-estado")
    project_id = proyecto["id"]
    v1_id = proyecto["active_version_id"]
    batch = Batch(project_id=project_id, model_version_id=v1_id, seq=0, n_rows=3)
    session.add(batch)
    session.commit()

    resp = client.get(f"/api/projects/{project_id}/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["alerts_open_total"] == 0
    assert body["last_batch"]["id"] == batch.id
    # con un único lote, línea base y último lote coinciden.
    assert body["first_batch"]["id"] == batch.id
    assert len(body["monitors"]) == 5


def test_project_state_first_batch_es_el_seq_minimo(client: TestClient, session: Session):
    """`first_batch` es el lote de `seq` mínimo, no el último
    ingerido; así el cuadro deduce la línea base sin pedir hasta 500 lotes."""
    proyecto = _crear_proyecto(client, name="con-varios-lotes")
    project_id = proyecto["id"]
    v1_id = proyecto["active_version_id"]
    base = Batch(
        project_id=project_id, model_version_id=v1_id, seq=0, phase_label="b0", n_rows=3
    )
    evento = Batch(
        project_id=project_id, model_version_id=v1_id, seq=1, phase_label="e1_evento", n_rows=5
    )
    session.add(base)
    session.add(evento)
    session.commit()

    resp = client.get(f"/api/projects/{project_id}/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_batch"]["id"] == evento.id
    assert body["first_batch"]["id"] == base.id
    assert body["first_batch"]["seq"] == 0
    assert body["first_batch"]["phase_label"] == "b0"


def test_patch_project_actualiza_nombre_y_motivo_obligatorio(client: TestClient):
    proyecto = _crear_proyecto(client, name="nombre-viejo")
    project_id = proyecto["id"]

    resp = client.patch(
        f"/api/projects/{project_id}",
        json={"actor": "miguel", "motivo": "", "name": "nombre-nuevo"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422

    resp = client.patch(
        f"/api/projects/{project_id}",
        json={"actor": "miguel", "motivo": "corrijo el nombre", "name": "nombre-nuevo"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "nombre-nuevo"


def test_patch_project_clear_calibration_vacia_la_fecha(client: TestClient):
    """`calibration_until=None` es "no tocar"; `clear_calibration=True` la vacía."""
    proyecto = _crear_proyecto(client, name="calibracion")
    project_id = proyecto["id"]
    cuerpo = {"actor": "miguel", "motivo": "fijo calibración", "calibration_until": "2026-12-31"}
    resp = client.patch(f"/api/projects/{project_id}", json=cuerpo, headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["calibration_until"] == "2026-12-31"

    cuerpo = {"actor": "miguel", "motivo": "sin cambios", "calibration_until": None}
    resp = client.patch(f"/api/projects/{project_id}", json=cuerpo, headers=actor_headers("miguel"))
    assert resp.status_code == 200
    assert resp.json()["calibration_until"] == "2026-12-31"

    cuerpo = {"actor": "miguel", "motivo": "termina la calibración", "clear_calibration": True}
    resp = client.patch(f"/api/projects/{project_id}", json=cuerpo, headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["calibration_until"] is None


# --- Descripción del proyecto y resumen de la lista ---------------------


def test_patch_project_description_con_motivo_y_evento(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, name="con-descripcion")
    project_id = proyecto["id"]
    assert proyecto["description"] is None

    resp = client.patch(
        f"/api/projects/{project_id}",
        json={"actor": "miguel", "motivo": "documento el despliegue", "description": "Piloto reuma"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["description"] == "Piloto reuma"

    evento = session.exec(
        select(Event)
        .where(Event.object_type == "project", Event.action == "proyecto.actualizado")
        .order_by(Event.id.desc())  # type: ignore[attr-defined]
    ).first()
    assert evento is not None
    assert evento.motivo == "documento el despliegue"
    assert evento.after_json["description"] == "Piloto reuma"
    assert evento.before_json["description"] is None

    # `description=None` es "no tocar" (mismo convenio que `calibration_until`).
    resp = client.patch(
        f"/api/projects/{project_id}",
        json={"actor": "miguel", "motivo": "sin cambios"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["description"] == "Piloto reuma"

    resp = client.patch(
        f"/api/projects/{project_id}",
        json={"actor": "miguel", "motivo": "quito la descripción", "clear_description": True},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["description"] is None


def test_lista_de_proyectos_sin_summary_no_lo_incluye(client: TestClient):
    _crear_proyecto(client, name="sin-resumen")
    resp = client.get("/api/projects")
    assert resp.status_code == 200, resp.text
    item = next(p for p in resp.json()["items"] if p["name"] == "sin-resumen")
    assert item.get("summary") is None


def test_lista_de_proyectos_con_summary_cuadra_con_alertas_abiertas(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="con-resumen", domain="reuma")
    project_id = proyecto["id"]

    from vigia.app.models import Alert, Batch, Evaluation, Monitor

    batch = Batch(
        project_id=project_id,
        model_version_id=proyecto["active_version_id"],
        seq=0,
        n_rows=5,
    )
    session.add(batch)
    session.commit()

    monitor_equidad = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == "fairness")
    ).first()
    evaluacion = Evaluation(
        monitor_id=monitor_equidad.id,
        project_id=project_id,
        model_version_id=proyecto["active_version_id"],
        trigger="manual",
        worst_state="alerta",
    )
    session.add(evaluacion)
    session.flush()
    session.add(
        Alert(
            project_id=project_id,
            monitor_type="fairness",
            metric_key="fairness_value",
            severity="alta",
            status="abierta",
            title="alerta de prueba",
        )
    )
    session.add(
        Alert(
            project_id=project_id,
            monitor_type="fairness",
            metric_key="disparate_impact",
            severity="media",
            status="en_observacion",
            title="otra alerta",
        )
    )
    session.commit()

    resp = client.get("/api/projects", params={"summary": True})
    assert resp.status_code == 200, resp.text
    item = next(p for p in resp.json()["items"] if p["id"] == project_id)
    resumen = item["summary"]
    assert resumen is not None

    abiertas = client.get(
        f"/api/projects/{project_id}/alerts",
        params={"status": "abierta,en_observacion,reconocida"},
    ).json()["items"]
    esperado = {"alta": 0, "media": 0, "baja": 0}
    for a in abiertas:
        esperado[a["severity"]] += 1
    assert resumen["alerts_open_by_severity"] == esperado
    assert resumen["worst_state"] == "alerta"
    assert resumen["first_batch_at"] is not None
    assert resumen["last_evaluation_at"] is not None
    assert resumen["active_version_label"] == "v1"


# --- Delta del KPI frente al lote anterior (last_batch/previous_batch) --


def test_summary_con_un_solo_lote_previous_batch_es_null(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, name="con-un-lote", domain="reuma")
    project_id = proyecto["id"]

    from vigia.app.models import Evaluation

    monitor_calidad = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == "quality")
    ).first()
    batch = Batch(
        project_id=project_id, model_version_id=proyecto["active_version_id"], seq=0, n_rows=10
    )
    session.add(batch)
    session.commit()
    evaluacion = Evaluation(
        monitor_id=monitor_calidad.id,
        project_id=project_id,
        model_version_id=proyecto["active_version_id"],
        batch_id=batch.id,
        trigger="manual",
        worst_state="ok",
    )
    session.add(evaluacion)
    session.commit()

    resp = client.get("/api/projects", params={"summary": True})
    assert resp.status_code == 200, resp.text
    item = next(p for p in resp.json()["items"] if p["id"] == project_id)
    resumen = item["summary"]
    assert resumen["last_batch"] is not None
    assert resumen["last_batch"]["batch_id"] == batch.id
    assert resumen["previous_batch"] is None


def test_summary_last_batch_y_previous_batch_con_metrics_y_estados(
    client: TestClient, session: Session
):
    """Los dos últimos lotes con evaluación, `metrics` con la métrica
    principal de cada uno de los cuatro monitores (calidad, explicabilidad,
    equidad y deriva) que evaluaron ese lote, y
    `alerts_opened`/`monitors_in_alert`/`states_by_monitor` por lote."""
    proyecto = _crear_proyecto(client, name="con-dos-lotes", domain="reuma")
    project_id = proyecto["id"]
    version_id = proyecto["active_version_id"]

    from vigia.app.models import Alert, Evaluation, Measurement

    monitor_calidad = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == "quality")
    ).first()
    monitor_explain = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == "explain")
    ).first()
    monitor_equidad = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == "fairness")
    ).first()
    monitor_deriva = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == "drift")
    ).first()

    batch_1 = Batch(
        project_id=project_id, model_version_id=version_id, seq=0, phase_label="b1", n_rows=100
    )
    batch_2 = Batch(
        project_id=project_id, model_version_id=version_id, seq=1, phase_label="e1_evento", n_rows=120
    )
    session.add(batch_1)
    session.add(batch_2)
    session.commit()

    # Lote 1 (el anterior): calidad en alerta, sin evaluación de explicabilidad.
    eval_calidad_1 = Evaluation(
        monitor_id=monitor_calidad.id,
        project_id=project_id,
        model_version_id=version_id,
        batch_id=batch_1.id,
        trigger="manual",
        worst_state="alerta",
    )
    session.add(eval_calidad_1)
    session.flush()
    session.add(
        Measurement(
            evaluation_id=eval_calidad_1.id,
            project_id=project_id,
            monitor_type="quality",
            metric_key="accuracy",
            value=0.55,
            threshold_low=0.80,
            state="alerta",
        )
    )
    session.add(
        Alert(
            project_id=project_id,
            monitor_type="quality",
            metric_key="accuracy",
            group_code=None,
            severity="alta",
            status="abierta",
            title="calidad baja",
            history_json=[
                {
                    "ts": "2026-01-01T00:00:00.000000+00:00",
                    "from": None,
                    "to": "abierta",
                    "evaluation_id": eval_calidad_1.id,
                    "value": 0.55,
                    "actor": "vigia.core 0.1.0",
                    "motivo": None,
                }
            ],
        )
    )

    # Lote 2 (el último): calidad y explicabilidad, las dos en `ok`.
    eval_calidad_2 = Evaluation(
        monitor_id=monitor_calidad.id,
        project_id=project_id,
        model_version_id=version_id,
        batch_id=batch_2.id,
        trigger="manual",
        worst_state="ok",
    )
    session.add(eval_calidad_2)
    session.flush()
    session.add(
        Measurement(
            evaluation_id=eval_calidad_2.id,
            project_id=project_id,
            monitor_type="quality",
            metric_key="accuracy",
            value=0.91,
            threshold_low=0.80,
            state="ok",
        )
    )
    eval_explain_2 = Evaluation(
        monitor_id=monitor_explain.id,
        project_id=project_id,
        model_version_id=version_id,
        batch_id=batch_2.id,
        trigger="manual",
        worst_state="ok",
    )
    session.add(eval_explain_2)
    session.flush()
    session.add(
        Measurement(
            evaluation_id=eval_explain_2.id,
            project_id=project_id,
            monitor_type="explain",
            metric_key="explain_stability_ndcg",
            value=0.75,
            threshold_low=0.50,
            state="ok",
        )
    )
    eval_equidad_2 = Evaluation(
        monitor_id=monitor_equidad.id,
        project_id=project_id,
        model_version_id=version_id,
        batch_id=batch_2.id,
        trigger="manual",
        worst_state="ok",
    )
    session.add(eval_equidad_2)
    session.flush()
    session.add(
        Measurement(
            evaluation_id=eval_equidad_2.id,
            project_id=project_id,
            monitor_type="fairness",
            metric_key="fairness_value",
            value=1.05,
            threshold_high=1.25,
            state="ok",
        )
    )
    eval_deriva_2 = Evaluation(
        monitor_id=monitor_deriva.id,
        project_id=project_id,
        model_version_id=version_id,
        batch_id=batch_2.id,
        trigger="manual",
        worst_state="ok",
    )
    session.add(eval_deriva_2)
    session.flush()
    session.add(
        Measurement(
            evaluation_id=eval_deriva_2.id,
            project_id=project_id,
            monitor_type="drift",
            metric_key="feature_drift_score",
            value=0.10,
            threshold_high=0.30,
            state="ok",
        )
    )
    session.commit()

    resp = client.get("/api/projects", params={"summary": True})
    assert resp.status_code == 200, resp.text
    item = next(p for p in resp.json()["items"] if p["id"] == project_id)
    resumen = item["summary"]

    last_batch = resumen["last_batch"]
    previous_batch = resumen["previous_batch"]
    assert last_batch is not None
    assert previous_batch is not None
    assert last_batch["batch_id"] != previous_batch["batch_id"]
    assert last_batch["batch_id"] == batch_2.id
    assert last_batch["seq"] == 1
    assert last_batch["phase_label"] == "e1_evento"
    assert previous_batch["batch_id"] == batch_1.id

    assert previous_batch["alerts_opened"] == 1
    assert previous_batch["monitors_in_alert"] == 1
    assert previous_batch["monitors_total"] == 1
    assert previous_batch["states_by_monitor"]["quality"] == "alerta"
    # `explain` ya no sale en `states_by_monitor`
    # (ninguna pantalla lo pinta); su métrica sigue en `metrics`, más abajo.
    assert "explain" not in previous_batch["states_by_monitor"]
    assert last_batch["alerts_opened"] == 0
    assert last_batch["monitors_in_alert"] == 0
    assert last_batch["states_by_monitor"]["quality"] == "ok"
    assert "explain" not in last_batch["states_by_monitor"]

    metricas_last = {m["metric_key"]: m for m in last_batch["metrics"]}
    assert set(metricas_last) == {
        "accuracy",
        "explain_stability_ndcg",
        "fairness_value",
        "feature_drift_score",
    }
    assert metricas_last["accuracy"]["monitor_type"] == "quality"
    assert metricas_last["accuracy"]["value"] == pytest.approx(0.91)
    assert metricas_last["accuracy"]["threshold_kind"] == "lower"
    assert metricas_last["accuracy"]["threshold_value"] == pytest.approx(0.80)
    assert metricas_last["accuracy"]["state"] == "ok"
    assert metricas_last["explain_stability_ndcg"]["state"] == "ok"
    assert metricas_last["fairness_value"]["monitor_type"] == "fairness"
    assert metricas_last["fairness_value"]["value"] == pytest.approx(1.05)
    assert metricas_last["feature_drift_score"]["monitor_type"] == "drift"
    assert metricas_last["feature_drift_score"]["value"] == pytest.approx(0.10)

    # el lote anterior no tiene evaluación de explicabilidad: se omite.
    metricas_previous = {m["metric_key"]: m for m in previous_batch["metrics"]}
    assert set(metricas_previous) == {"accuracy"}
    assert metricas_previous["accuracy"]["state"] == "alerta"


def test_summary_un_monitor_sin_datos_no_oscurece_a_los_que_evaluaron(
    client: TestClient, session: Session
):
    """La primera explicación de una versión deja `explain` en `sin_datos`;
    el peor estado del proyecto sigue siendo el de los monitores con
    datos, y solo es «sin datos» cuando ninguno los tiene."""
    proyecto = _crear_proyecto(client, name="sin-datos-parcial", domain="reuma")
    project_id = proyecto["id"]
    from vigia.app.models import Evaluation

    monitores = {
        m.type: m for m in session.exec(select(Monitor).where(Monitor.project_id == project_id)).all()
    }
    assert "fairness" in monitores and "explain" in monitores
    for tipo, estado in (("fairness", "ok"), ("explain", "sin_datos")):
        session.add(
            Evaluation(
                monitor_id=monitores[tipo].id,
                project_id=project_id,
                model_version_id=proyecto["active_version_id"],
                trigger="manual",
                worst_state=estado,
            )
        )
    session.commit()

    resp = client.get("/api/projects", params={"summary": True})
    assert resp.status_code == 200, resp.text
    item = next(p for p in resp.json()["items"] if p["id"] == project_id)
    assert item["summary"]["worst_state"] == "ok"


# --- Estado de despliegue del proyecto --------------------------


def test_crear_proyecto_con_deployment_stage_produccion(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={"name": "en-produccion", "domain": "reuma", "deployment_stage": "produccion"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deployment_stage"] == "produccion"


def test_crear_proyecto_deployment_stage_por_defecto_desarrollo(client: TestClient):
    proyecto = _crear_proyecto(client, name="sin-estado-explicito")
    assert proyecto["deployment_stage"] == "desarrollo"


def test_patch_project_deployment_stage_invalido_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="estado-invalido")
    resp = client.patch(
        f"/api/projects/{proyecto['id']}",
        json={"actor": "miguel", "motivo": "pruebo un valor malo", "deployment_stage": "en_pausa"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422


def test_patch_project_deployment_stage_lo_cambia_y_lo_registra(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, name="pasa-a-produccion")
    resp = client.patch(
        f"/api/projects/{proyecto['id']}",
        json={"actor": "miguel", "motivo": "entra en producción", "deployment_stage": "produccion"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deployment_stage"] == "produccion"

    evento = session.exec(
        select(Event)
        .where(Event.action == "proyecto.actualizado", Event.object_id == proyecto["id"])
        .order_by(Event.id.desc())
    ).first()
    assert evento.after_json["deployment_stage"] == "produccion"
    assert evento.before_json["deployment_stage"] == "desarrollo"


def test_summary_incluye_deployment_stage_y_alerts_open_by_monitor_a_cero(client: TestClient):
    """`deployment_stage` en la fila y `alerts_open_by_monitor` con las
    cuatro claves a cero cuando el proyecto no tiene alertas.

    Sin `explain`: no tiene tarjeta en el
    cuadro, así que no sale en el desglose por monitor."""
    proyecto = _crear_proyecto(client, name="resumen-sin-alertas")
    resp = client.get("/api/projects", params={"summary": True})
    assert resp.status_code == 200, resp.text
    item = next(p for p in resp.json()["items"] if p["id"] == proyecto["id"])
    assert item["deployment_stage"] == "desarrollo"
    assert item["summary"]["alerts_open_by_monitor"] == {
        "fairness": {"alta": 0, "media": 0, "baja": 0},
        "quality": {"alta": 0, "media": 0, "baja": 0},
        "drift": {"alta": 0, "media": 0, "baja": 0},
        "cross": {"alta": 0, "media": 0, "baja": 0},
    }


# --- Resumen por monitor sobre la demo -----------------------


def _reproducir_timeline_completo(client: TestClient) -> dict:
    resp = client.post(
        "/api/demo/runs",
        json={"scenario_key": "timeline_completo", "with_human": False},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    resp = client.post(f"/api/demo/runs/{run['id']}/play", headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.text
    return run


def test_checks_by_state_y_alerts_open_by_monitor_con_la_demo(client: TestClient, session: Session):
    """`checks_by_state` de `timeline_completo`, con la demo ya reproducida.

    Desviación frente a lo esperado:
    se esperaba «calidad con 6 comprobaciones en alerta en el lote #9»
    (numeración 1-indexada de las 9 fases). Con la demo real, el lote #9
    (`seq=8`, el último, todo en `ok`: recupera antes de terminar el guion) no
    tiene ninguna en alerta; las 6 en alerta están en el lote anterior, `seq=7`
    (`previous_batch`, la octava fase). El test comprueba ambos lotes con sus
    cifras reales."""
    run = _reproducir_timeline_completo(client)
    project_id = run["project_id"]

    resp = client.get("/api/projects", params={"summary": True})
    assert resp.status_code == 200, resp.text
    item = next(p for p in resp.json()["items"] if p["id"] == project_id)
    resumen = item["summary"]
    last_batch = resumen["last_batch"]
    previous_batch = resumen["previous_batch"]
    assert last_batch["seq"] == 8  # noveno lote, `seq` de 0
    assert previous_batch["seq"] == 7

    checks_last = last_batch["checks_by_state"]
    checks_previous = previous_batch["checks_by_state"]
    # Sin `explain`: no tiene tarjeta en el
    # cuadro, así que no sale en `checks_by_state` (su métrica sigue en
    # `BatchKpi.metrics`, sin cambios).
    assert set(checks_last) == {"fairness", "quality", "drift", "cross"}
    assert checks_last["quality"]["alerta"] == 0
    assert checks_previous["quality"]["alerta"] == 6
    # CX-2 y CX-4 se suman a CX-1/5/6 vía Alert y
    # CX-3 se cuenta aparte desde Measurement: seis reglas cruzadas.
    # `human_review_zero` se cuenta igual que CX-3, séptima comprobación.
    assert sum(checks_last["cross"].values()) == 7
    assert sum(checks_previous["cross"].values()) == 7

    from vigia.app.models import Evaluation, Measurement

    def _n_medidas_calidad(batch_id: int) -> int:
        eval_calidad = session.exec(
            select(Evaluation.id)
            .where(Evaluation.project_id == project_id, Evaluation.batch_id == batch_id)
            .join(Monitor, Monitor.id == Evaluation.monitor_id)
            .where(Monitor.type == "quality")
        ).first()
        return len(
            session.exec(select(Measurement).where(Measurement.evaluation_id == eval_calidad)).all()
        )

    assert sum(checks_last["quality"].values()) == _n_medidas_calidad(last_batch["batch_id"])
    assert sum(checks_previous["quality"].values()) == _n_medidas_calidad(previous_batch["batch_id"])

    for tipo in ("fairness", "quality", "drift", "cross"):
        assert tipo in resumen["alerts_open_by_monitor"]
    assert "explain" not in resumen["alerts_open_by_monitor"]


def test_checks_by_state_cross_no_cuenta_alertas_abiertas_en_calibracion(
    client: TestClient, session: Session
):
    """Si la última evaluación cruzada está en calibración
    (`Evaluation.result_json["mode"] == "calibracion"`), la tarjeta de
    cruzadas del cuadro no debe sumar la severidad de una alerta CX-1 que
    siga abierta de una versión anterior: cuenta como `ok`, no `alerta`."""
    from vigia.app.models import Alert, Evaluation

    proyecto = _crear_proyecto(client, name="cruzadas-en-calibracion", domain="libre")
    project_id = proyecto["id"]
    version_id = proyecto["active_version_id"]
    monitor_cross = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == "cross")
    ).first()
    monitor_calidad = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == "quality")
    ).first()

    # Un lote cualquiera, para que el proyecto aparezca en `_batches_kpi`
    # (las evaluaciones `cross` nunca llevan `batch_id`).
    batch = Batch(project_id=project_id, model_version_id=version_id, seq=0, n_rows=10)
    session.add(batch)
    session.flush()
    session.add(
        Evaluation(
            monitor_id=monitor_calidad.id,
            project_id=project_id,
            model_version_id=version_id,
            batch_id=batch.id,
            trigger="manual",
            worst_state="ok",
        )
    )

    # Alerta CX-1 abierta de antes de calibrar.
    session.add(
        Alert(
            project_id=project_id,
            monitor_type="cross",
            metric_key="CX-1",
            severity="alta",
            status="abierta",
            title="CX-1 de una versión anterior",
        )
    )

    # La evaluación cruzada más reciente ya está en calibración.
    session.add(
        Evaluation(
            monitor_id=monitor_cross.id,
            project_id=project_id,
            model_version_id=version_id,
            batch_id=None,
            trigger="manual",
            worst_state="ok",
            result_json={"mode": "calibracion"},
        )
    )
    session.commit()

    resp = client.get("/api/projects", params={"summary": True})
    assert resp.status_code == 200, resp.text
    item = next(p for p in resp.json()["items"] if p["id"] == project_id)
    checks_cross = item["summary"]["last_batch"]["checks_by_state"]["cross"]
    assert checks_cross["alerta"] == 0
    assert checks_cross["ok"] == 7


def test_checks_by_state_cross_cuenta_human_review_zero_en_aviso(client: TestClient, session: Session):
    """`human_review_zero` nunca abre `Alert`; si la última evaluación
    cruzada la tiene en `aviso`, `checks_by_state["cross"]` la cuenta como una
    comprobación en `aviso` (siete en total). Una evaluación cruzada anterior con
    la señal en `aviso` no cuenta: solo manda la más reciente."""
    from vigia.app.models import Evaluation, Measurement

    proyecto = _crear_proyecto(client, name="cruzadas-revision-cero", domain="libre")
    project_id = proyecto["id"]
    version_id = proyecto["active_version_id"]
    monitor_cross = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == "cross")
    ).first()
    monitor_calidad = session.exec(
        select(Monitor).where(Monitor.project_id == project_id, Monitor.type == "quality")
    ).first()
    batch = Batch(project_id=project_id, model_version_id=version_id, seq=0, n_rows=10)
    session.add(batch)
    session.flush()
    session.add(
        Evaluation(
            monitor_id=monitor_calidad.id,
            project_id=project_id,
            model_version_id=version_id,
            batch_id=batch.id,
            trigger="manual",
            worst_state="ok",
        )
    )

    def _evaluacion_cross(estado: str, cuando: str) -> None:
        evaluacion = Evaluation(
            monitor_id=monitor_cross.id,
            project_id=project_id,
            model_version_id=version_id,
            batch_id=None,
            trigger="manual",
            worst_state=estado,
            created_at=cuando,
        )
        session.add(evaluacion)
        session.flush()
        session.add(
            Measurement(
                evaluation_id=evaluacion.id,
                project_id=project_id,
                monitor_type="cross",
                metric_key="human_review_zero",
                value=0.0 if estado == "aviso" else 0.12,
                state=estado,
            )
        )

    def _checks() -> dict[str, int]:
        resp = client.get("/api/projects", params={"summary": True})
        assert resp.status_code == 200, resp.text
        item = next(p for p in resp.json()["items"] if p["id"] == project_id)
        return item["summary"]["last_batch"]["checks_by_state"]["cross"]

    _evaluacion_cross("aviso", "2026-09-01T10:00:00+00:00")
    session.commit()
    checks = _checks()
    assert sum(checks.values()) == 7
    assert checks["aviso"] == 1
    assert checks["ok"] == 6

    _evaluacion_cross("ok", "2026-09-02T10:00:00+00:00")
    session.commit()
    checks = _checks()
    assert checks["aviso"] == 0
    assert checks["ok"] == 7

