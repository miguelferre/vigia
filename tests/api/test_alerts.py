"""Alertas, vía API con `TestClient`."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo" / "escenario_1"


def _crear_proyecto(client: TestClient, name: str = "reuma-alertas") -> dict:
    resp = client.post(
        "/api/projects",
        # Números de referencia: método de ventanas, no por lote.
        json={"name": name, "domain": "reuma", "fairness_interval_method": "ventanas"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir_y_mapear(client: TestClient, project_id: int, filename: str, *, role: str) -> dict:
    contenido = (DEMO_DIR / filename).read_bytes()
    resp = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": (filename, contenido, "application/json")},
        data={"kind": "combined", "role": role},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    dataset = body["dataset"]
    mapping = body["suggested_mapping"]
    resp = client.put(
        f"/api/datasets/{dataset['id']}/mapping",
        json={"mapping": mapping},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ingerir(client: TestClient, dataset_id: int, **body) -> dict:
    body.setdefault("evaluate", False)
    resp = client.post(f"/api/datasets/{dataset_id}/ingest", json=body)
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    return job["result"]


def _evaluar(client: TestClient, batch_id: int, trigger: str = "manual") -> dict:
    resp = client.post(f"/api/batches/{batch_id}/evaluate", json={"trigger": trigger})
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    return job["result"]


def _alertas(
    client: TestClient,
    project_id: int,
    status: str | None = None,
    severity: str | None = None,
) -> list[dict]:
    params = {}
    if status:
        params["status"] = status
    if severity:
        params["severity"] = severity
    resp = client.get(f"/api/projects/{project_id}/alerts", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _preparar_con_evento(client: TestClient) -> tuple[dict, dict]:
    """Proyecto con el baseline E1 congelado y el evento E1 ingerido y evaluado."""
    proyecto = _crear_proyecto(client)
    baseline_ds = _subir_y_mapear(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    _ingerir(client, baseline_ds["id"])
    # Ingerir la línea base ya la congela; no hay POST /baseline que hacer.

    evento_ds = _subir_y_mapear(client, proyecto["id"], "02_evento_feedback.json", role="production")
    resultado_evento = _ingerir(client, evento_ds["id"])
    _evaluar(client, resultado_evento["batch_id"])
    return proyecto, resultado_evento


# --- aparición de alertas -----------------------------------------------------


def test_evento_e1_abre_alertas_fairness_alta_y_media(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    abiertas = _alertas(client, proyecto["id"], status="abierta")
    por_metrica = {a["metric_key"]: a for a in abiertas}

    assert "false_negative_rate_difference" in por_metrica
    assert por_metrica["false_negative_rate_difference"]["severity"] == "alta"
    assert por_metrica["false_negative_rate_difference"]["monitor_type"] == "fairness"

    assert "fairness_value" in por_metrica
    assert por_metrica["fairness_value"]["severity"] == "media"

    # una única fila abierta por (proyecto, monitor, métrica, grupo)
    claves = [(a["monitor_type"], a["metric_key"], a["group_code"]) for a in abiertas]
    assert len(claves) == len(set(claves))


def test_titulo_legible_con_etiqueta_de_metrica_y_grupo_del_mapeo(client: TestClient):
    """FNRD (sin `group_code` propio) usa la etiqueta del grupo del mapeo (`18-35`)
    y la etiqueta en español de `METRIC_LABELS`, con el valor y el umbral en el título."""
    proyecto, _ = _preparar_con_evento(client)
    abiertas = _alertas(client, proyecto["id"], status="abierta")
    fnrd = next(a for a in abiertas if a["metric_key"] == "false_negative_rate_difference")
    assert "Diferencia de tasa de falsos negativos" in fnrd["title"]
    assert "18-35" in fnrd["title"]
    assert "umbral" in fnrd["title"]


def test_recovery_pasa_a_en_observacion_sin_cerrar(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)

    recovery_ds = _subir_y_mapear(client, proyecto["id"], "03_recovery_feedback.json", role="production")
    resultado_recovery = _ingerir(client, recovery_ds["id"])
    _evaluar(client, resultado_recovery["batch_id"])

    todas = _alertas(client, proyecto["id"])
    fnrd = next(a for a in todas if a["metric_key"] == "false_negative_rate_difference")
    assert fnrd["status"] == "en_observacion"
    assert fnrd["observation_count"] == 1
    assert fnrd["reopen_count"] == 0
    # El motor mueve `status` a `en_observacion`, pero la etapa solo cuenta hitos
    # humanos: sin triaje sigue «detectada» (antes salía «en_seguimiento» con
    # «1 de 5 hitos»). El triaje se admite también desde `en_observacion`
    # y conserva el `status` del motor.
    assert fnrd["stage"] == "detectada"
    resp = client.post(
        f"/api/alerts/{fnrd['id']}/acknowledge", json={"actor": "clara", "motivo": "triaje tardío"}
    )
    assert resp.status_code == 200, resp.text
    triada = resp.json()
    assert triada["status"] == "en_observacion"
    assert triada["stage"] == "en_observacion"
    assert triada["history"][-1]["hito"] == "triaje"
    assert triada["history"][-1]["to"] == "en_observacion"
    detalle = client.get(f"/api/alerts/{fnrd['id']}").json()
    pasos = {p["key"]: p["status"] for p in detalle["protocol_steps"]}
    assert pasos["triaje"] == "done"
    assert pasos["investigacion"] == "current"
    resp = client.post(
        f"/api/alerts/{fnrd['id']}/acknowledge", json={"actor": "clara", "motivo": "otra vez"}
    )
    assert resp.status_code == 409


def test_reingerir_el_evento_reabre_la_misma_fila(client: TestClient):
    proyecto, _resultado_evento = _preparar_con_evento(client)

    recovery_ds = _subir_y_mapear(client, proyecto["id"], "03_recovery_feedback.json", role="production")
    resultado_recovery = _ingerir(client, recovery_ds["id"])
    _evaluar(client, resultado_recovery["batch_id"])

    otro_evento_ds = _subir_y_mapear(client, proyecto["id"], "02_evento_feedback.json", role="production")
    resultado_otro_evento = _ingerir(client, otro_evento_ds["id"])
    _evaluar(client, resultado_otro_evento["batch_id"])

    todas = _alertas(client, proyecto["id"])
    fnrd_filas = [a for a in todas if a["metric_key"] == "false_negative_rate_difference"]
    assert len(fnrd_filas) == 1
    fnrd = fnrd_filas[0]
    assert fnrd["status"] == "abierta"
    assert fnrd["reopen_count"] == 1

    abiertas_no_cerradas = [
        a
        for a in todas
        if a["metric_key"] == "false_negative_rate_difference" and a["status"] != "cerrada"
    ]
    assert len(abiertas_no_cerradas) == 1


# --- acciones humanas: actor y motivo obligatorios ---------------------------


def test_acknowledge_actions_y_close_exigen_actor_y_motivo_y_dejan_evento_humano(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    abiertas = _alertas(client, proyecto["id"], status="abierta")
    alerta = next(a for a in abiertas if a["metric_key"] == "false_negative_rate_difference")
    alert_id = alerta["id"]

    resp = client.post(f"/api/alerts/{alert_id}/acknowledge", json={"actor": "", "motivo": "reviso"})
    assert resp.status_code == 422

    resp = client.post(
        f"/api/alerts/{alert_id}/acknowledge", json={"actor": "clara", "motivo": "reviso la alerta"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "reconocida"

    resp = client.post(
        f"/api/alerts/{alert_id}/actions",
        json={"action": "no-existe", "actor": "clara", "motivo": "x"},
    )
    assert resp.status_code == 422

    resp = client.post(
        f"/api/alerts/{alert_id}/actions",
        json={"action": "escalar", "actor": "clara", "motivo": "se escala a responsable clínico"},
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(f"/api/alerts/{alert_id}/close", json={"actor": "clara", "motivo": ""})
    assert resp.status_code == 422

    resp = client.post(
        f"/api/alerts/{alert_id}/close", json={"actor": "clara", "motivo": "resuelto tras revisión"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cerrada"

    resp = client.get(f"/api/alerts/{alert_id}")
    assert resp.status_code == 200, resp.text
    detalle = resp.json()
    assert len(detalle["actions"]) == 1
    assert detalle["actions"][0]["action"] == "escalar"
    assert detalle["actions"][0]["actor"] == "clara"

    resp = client.get(
        "/api/events",
        params={"actor_kind": "humano", "object_type": "alert", "object_id": alert_id},
    )
    assert resp.status_code == 200, resp.text
    eventos = resp.json()["items"]
    acciones = {e["action"] for e in eventos}
    assert {"alerta.reconocida", "alerta.accion", "alerta.cerrada"} <= acciones
    for e in eventos:
        assert e["actor_kind"] == "humano"
        assert e["actor_id"] == "clara" or e["action"] != "alerta.cerrada"


def test_catalogo_de_acciones(client: TestClient):
    resp = client.get("/api/alerts/catalog")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["items"]
    acciones = {i["action"] for i in items}
    assert "contener_subgrupo" in acciones
    assert "nota" in acciones
    # La decisión sin medidas, última entrada del catálogo (8 -> 9).
    assert "seguir_vigilando" in acciones
    assert body["total"] == len(items) == 9
    for i in items:
        assert i["label"]


# --- casos añadidos ------------------------------------------------------------


def test_titulo_con_numeros_en_formato_espanol(client: TestClient):
    """Hueco 9b: valor y umbrales del título llevan coma decimal y tres decimales;
    ningún punto decimal (la UI enseña «0,631», no «0.631»)."""
    proyecto, _ = _preparar_con_evento(client)
    abiertas = _alertas(client, proyecto["id"], status="abierta")
    assert abiertas

    fnrd = next(a for a in abiertas if a["metric_key"] == "false_negative_rate_difference")
    assert "0,631" in fnrd["title"]
    assert "umbral" in fnrd["title"]
    for a in abiertas:
        assert "." not in a["title"], a["title"]
        assert "," in a["title"], a["title"]

    # el rango del grupo no cambia de formato
    assert "18-35" in fnrd["title"]


def test_titulo_recalcula_la_etiqueta_al_servir_sin_migrar_la_fila(client: TestClient, session: Session):
    """El título se fijaba solo al abrir la alerta, así
    que una alerta que sigue abierta mucho tiempo se quedaba con el wording
    viejo si `content/metricas-ayuda.json` o `METRIC_LABELS` cambiaban
    después. Se recalcula la etiqueta al servir (`alert_to_dict`), sin tocar
    `title` en la base."""
    from vigia.app.models import Alert

    proyecto = _crear_proyecto(client, name="reuma-titulo-stale")
    fila = Alert(
        project_id=proyecto["id"],
        monitor_type="fairness",
        metric_key="false_negative_rate_difference",
        group_code="18-35",
        severity="media",
        status="abierta",
        title="DI x 100 en 18-35: 0,631 (umbral >= 0,600)",
    )
    session.add(fila)
    session.commit()
    session.refresh(fila)
    titulo_en_bd = fila.title

    detalle = client.get(f"/api/alerts/{fila.id}").json()
    assert "Diferencia de tasa de falsos negativos" in detalle["title"]
    assert "0,631" in detalle["title"]
    assert "umbral >= 0,600" in detalle["title"]

    session.refresh(fila)
    assert fila.title == titulo_en_bd  # la fila no se ha tocado, solo lo servido


def test_historial_trae_actor_kind_en_las_entradas_nuevas(client: TestClient):
    """Cada entrada nueva de `history_json` trae
    `actor_kind`, para que el frontend no tenga que adivinar el carril por el
    prefijo del actor (una acción del MCP se pintaba como humana)."""
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    detalle = client.get(f"/api/alerts/{alert_id}").json()
    assert detalle["history"][0]["actor_kind"] == "modelo"

    resp = client.post(f"/api/alerts/{alert_id}/acknowledge", json={"actor": "clara", "motivo": "reviso"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["history"][-1]["actor_kind"] == "humano"


def test_filtro_por_severidad(client: TestClient):
    """Hueco 6: `severity` acepta lista separada por comas, como `status`."""
    proyecto, _ = _preparar_con_evento(client)
    todas = _alertas(client, proyecto["id"])
    severidades = {a["severity"] for a in todas}
    assert {"alta", "media"} <= severidades

    altas = _alertas(client, proyecto["id"], severity="alta")
    assert altas
    assert {a["severity"] for a in altas} == {"alta"}
    assert len(altas) < len(todas)

    medias = _alertas(client, proyecto["id"], severity="media")
    assert medias
    assert {a["severity"] for a in medias} == {"media"}

    ambas = _alertas(client, proyecto["id"], severity="alta,media")
    assert len(ambas) == len(altas) + len(medias)

    # combinado con el filtro por estado
    abiertas_altas = _alertas(client, proyecto["id"], status="abierta", severity="alta")
    assert {(a["status"], a["severity"]) for a in abiertas_altas} == {("abierta", "alta")}


def test_severidad_desconocida_422(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    resp = client.get(f"/api/projects/{proyecto['id']}/alerts", params={"severity": "urgente"})
    assert resp.status_code == 422, resp.text
    assert "urgente" in resp.json()["detail"]
    assert "alta" in resp.json()["detail"]


def test_filtro_por_monitor_type(client: TestClient):
    """`monitor_type` filtra como `severity`, lista separada por comas."""
    proyecto, _ = _preparar_con_evento(client)
    todas = _alertas(client, proyecto["id"])
    tipos_presentes = {a["monitor_type"] for a in todas}
    assert "fairness" in tipos_presentes

    resp = client.get(
        f"/api/projects/{proyecto['id']}/alerts", params={"monitor_type": "fairness"}
    )
    assert resp.status_code == 200, resp.text
    fairness = resp.json()["items"]
    assert fairness
    assert {a["monitor_type"] for a in fairness} == {"fairness"}
    assert len(fairness) < len(todas) or tipos_presentes == {"fairness"}

    resp = client.get(
        f"/api/projects/{proyecto['id']}/alerts", params={"monitor_type": "quality"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


def test_monitor_type_desconocido_422(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    resp = client.get(
        f"/api/projects/{proyecto['id']}/alerts", params={"monitor_type": "inventado"}
    )
    assert resp.status_code == 422, resp.text
    assert "inventado" in resp.json()["detail"]


# --- Título con las 45 etiquetas de content/metricas-ayuda.json ----------


def test_titulo_de_alerta_ya_no_depende_del_diccionario_de_8_metricas(
    client: TestClient, session: Session
):
    """`gini_coefficient` y `disparate_impact` no estaban en `METRIC_LABELS` (8
    entradas); ahora el título sale de las 45 etiquetas del contenido."""
    from vigia.app.models import Evaluation, Monitor, Project
    from vigia.app.services import alerting

    proyecto = _crear_proyecto(client, name="reuma-titulos-h3")
    project = session.get(Project, proyecto["id"])
    assert project is not None
    monitor_calidad = session.exec(
        select(Monitor).where(Monitor.project_id == project.id, Monitor.type == "quality")
    ).first()
    monitor_equidad = session.exec(
        select(Monitor).where(Monitor.project_id == project.id, Monitor.type == "fairness")
    ).first()
    assert monitor_calidad is not None and monitor_equidad is not None

    evaluacion_calidad = Evaluation(
        monitor_id=monitor_calidad.id,
        project_id=project.id,
        model_version_id=project.active_version_id,
        trigger="manual",
    )
    session.add(evaluacion_calidad)
    session.flush()
    alertas_calidad = alerting.sync_candidates(
        session,
        project,
        monitor_calidad,
        evaluacion_calidad,
        [
            {
                "metric_key": "gini_coefficient",
                "state": "alerta",
                "value": 0.1,
                "threshold_low": 0.6,
                "threshold_high": None,
            }
        ],
    )
    session.commit()
    assert alertas_calidad
    assert "Coeficiente de Gini" in alertas_calidad[0].title

    evaluacion_equidad = Evaluation(
        monitor_id=monitor_equidad.id,
        project_id=project.id,
        model_version_id=project.active_version_id,
        trigger="manual",
    )
    session.add(evaluacion_equidad)
    session.flush()
    alertas_equidad = alerting.sync_candidates(
        session,
        project,
        monitor_equidad,
        evaluacion_equidad,
        [
            {
                "metric_key": "disparate_impact",
                "state": "alerta",
                "value": 0.2,
                "threshold_low": 0.8,
                "threshold_high": None,
            }
        ],
    )
    session.commit()
    assert alertas_equidad
    assert "Impacto dispar" in alertas_equidad[0].title


# --- Lote derivado de `last_evaluation_id` ------------------------------


def test_alerta_trae_batch_id_seq_y_phase_label_del_lote_evaluado(client: TestClient):
    proyecto, resultado_evento = _preparar_con_evento(client)
    lote = client.get(f"/api/batches/{resultado_evento['batch_id']}").json()

    abiertas = _alertas(client, proyecto["id"], status="abierta")
    assert abiertas
    for a in abiertas:
        assert a["batch_id"] == lote["id"]
        assert a["batch_seq"] == lote["seq"]
        assert a["batch_phase_label"] == lote["phase_label"]

    # mismo dato en el detalle (`GET /alerts/{id}`, resuelto sin lista).
    detalle = client.get(f"/api/alerts/{abiertas[0]['id']}").json()
    assert detalle["batch_id"] == lote["id"]
    assert detalle["batch_seq"] == lote["seq"]


def test_alerta_sin_evaluacion_tiene_lote_a_null(client: TestClient, session: Session):
    from vigia.app.models import Alert, Project

    proyecto = _crear_proyecto(client, name="reuma-alertas-sin-eval")
    project = session.get(Project, proyecto["id"])
    fila = Alert(
        project_id=project.id,
        monitor_type="fairness",
        metric_key="fairness_value",
        severity="media",
        status="abierta",
        title="sin evaluación",
    )
    session.add(fila)
    session.commit()

    resp = client.get(f"/api/projects/{proyecto['id']}/alerts")
    assert resp.status_code == 200, resp.text
    alerta = next(a for a in resp.json()["items"] if a["id"] == fila.id)
    assert alerta["batch_id"] is None
    assert alerta["batch_seq"] is None
    assert alerta["batch_phase_label"] is None


# --- Acción en lote sobre alertas ----------------------------------------


def test_bulk_close_salta_la_ya_cerrada_y_comparte_correlation_id(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    abiertas = _alertas(client, proyecto["id"], status="abierta")
    ids = [a["id"] for a in abiertas]
    assert len(ids) >= 2

    resp = client.post(f"/api/alerts/{ids[0]}/close", json={"actor": "clara", "motivo": "cerrada antes"})
    assert resp.status_code == 200, resp.text

    resp = client.post(
        f"/api/projects/{proyecto['id']}/alerts/bulk",
        json={"alert_ids": ids, "action": "close", "actor": "clara", "motivo": "cierre en lote"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] == len(ids) - 1
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["alert_id"] == ids[0]
    assert "cerrada" in body["skipped"][0]["reason"]

    for alert_id in ids[1:]:
        detalle = client.get(f"/api/alerts/{alert_id}").json()
        assert detalle["status"] == "cerrada"

    eventos = client.get(
        "/api/events",
        params={"object_type": "alert", "actor_kind": "humano", "project_id": proyecto["id"], "limit": 500},
    ).json()["items"]
    cierres_del_lote = [e for e in eventos if e["action"] == "alerta.cerrada" and e["motivo"] == "cierre en lote"]
    assert len(cierres_del_lote) == len(ids) - 1
    correlaciones = {e["correlation_id"] for e in cierres_del_lote}
    assert len(correlaciones) == 1
    assert None not in correlaciones


def test_bulk_alerta_de_otro_proyecto_o_inexistente_se_salta(client: TestClient, session: Session):
    from vigia.app.models import Alert

    proyecto_a, _ = _preparar_con_evento(client)
    proyecto_b = _crear_proyecto(client, name="reuma-alertas-b")
    alerta_b = Alert(
        project_id=proyecto_b["id"],
        monitor_type="fairness",
        metric_key="fairness_value",
        severity="media",
        status="abierta",
        title="de otro proyecto",
    )
    session.add(alerta_b)
    session.commit()

    alert_id_a = _alertas(client, proyecto_a["id"], status="abierta")[0]["id"]

    resp = client.post(
        f"/api/projects/{proyecto_a['id']}/alerts/bulk",
        json={
            "alert_ids": [alert_id_a, alerta_b.id, 999999],
            "action": "acknowledge",
            "actor": "clara",
            "motivo": "reviso el lote",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] == 1
    razones = {s["alert_id"]: s["reason"] for s in body["skipped"]}
    assert "otro proyecto" in razones[alerta_b.id]
    assert "no existe" in razones[999999]


def test_bulk_con_accion_del_catalogo_aplica_a_todas(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    ids = [a["id"] for a in _alertas(client, proyecto["id"], status="abierta")]

    resp = client.post(
        f"/api/projects/{proyecto['id']}/alerts/bulk",
        json={"alert_ids": ids, "action": "escalar", "actor": "clara", "motivo": "escalado en lote"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] == len(ids)
    assert body["skipped"] == []
    for alert_id in ids:
        detalle = client.get(f"/api/alerts/{alert_id}").json()
        assert any(a["action"] == "escalar" for a in detalle["actions"])


def test_bulk_accion_no_reconocida_422(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    resp = client.post(
        f"/api/projects/{proyecto['id']}/alerts/bulk",
        json={"alert_ids": [alert_id], "action": "no-existe", "actor": "clara", "motivo": "x"},
    )
    assert resp.status_code == 422, resp.text


def test_bulk_motivo_vacio_422(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    resp = client.post(
        f"/api/projects/{proyecto['id']}/alerts/bulk",
        json={"alert_ids": [alert_id], "action": "acknowledge", "actor": "clara", "motivo": ""},
    )
    assert resp.status_code == 422, resp.text


def test_bulk_lista_vacia_422(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    resp = client.post(
        f"/api/projects/{proyecto['id']}/alerts/bulk",
        json={"alert_ids": [], "action": "acknowledge", "actor": "clara", "motivo": "x"},
    )
    assert resp.status_code == 422, resp.text


# --- Hitos del protocolo --------------------------------------------------


def test_protocol_steps_alerta_recien_abierta(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]

    detalle = client.get(f"/api/alerts/{alert_id}").json()
    pasos = {p["key"]: p["status"] for p in detalle["protocol_steps"]}
    assert pasos == {
        "deteccion": "done",
        "triaje": "current",
        "investigacion": "pending",
        "decision": "pending",
        "seguimiento": "pending",
    }
    assert all(p["target_date"] is None for p in detalle["protocol_steps"])
    assert [p["key"] for p in detalle["protocol_steps"]] == [
        "deteccion", "triaje", "investigacion", "decision", "seguimiento",
    ]


def test_protocol_steps_en_observacion_tras_reconocer(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    fnrd = next(
        a
        for a in _alertas(client, proyecto["id"], status="abierta")
        if a["metric_key"] == "false_negative_rate_difference"
    )
    resp = client.post(f"/api/alerts/{fnrd['id']}/acknowledge", json={"actor": "clara", "motivo": "reviso"})
    assert resp.status_code == 200, resp.text

    recovery_ds = _subir_y_mapear(client, proyecto["id"], "03_recovery_feedback.json", role="production")
    resultado_recovery = _ingerir(client, recovery_ds["id"])
    _evaluar(client, resultado_recovery["batch_id"])

    detalle = client.get(f"/api/alerts/{fnrd['id']}").json()
    assert detalle["status"] == "en_observacion"
    pasos = {p["key"]: p["status"] for p in detalle["protocol_steps"]}
    assert pasos["deteccion"] == "done"
    assert pasos["triaje"] == "done"
    assert pasos["investigacion"] == "current"
    assert pasos["decision"] == "pending"
    # Sin decisión, el seguimiento queda
    # `pending` aunque ya haya una medida posterior de vuelta a `ok` (antes
    # salía marcado como si estuviera en curso).
    assert pasos["seguimiento"] == "pending"
    assert sum(1 for s in pasos.values() if s == "done") == 2


def test_protocol_steps_cerrada_decision_hecha(client: TestClient):
    """Cerrar ya no completa investigación ni decisión (se derivan de
    `alerta.investigada`/`alerta.decidida`, no del cierre); cerrar sin haber
    decidido deja esos dos hitos `pending` y el seguimiento sin nada que
    seguir."""
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    resp = client.post(f"/api/alerts/{alert_id}/close", json={"actor": "clara", "motivo": "resuelto"})
    assert resp.status_code == 200, resp.text

    detalle = client.get(f"/api/alerts/{alert_id}").json()
    pasos = {p["key"]: p["status"] for p in detalle["protocol_steps"]}
    assert pasos["deteccion"] == "done"
    assert pasos["triaje"] == "done"
    assert pasos["investigacion"] == "pending"
    assert pasos["decision"] == "pending"
    assert pasos["seguimiento"] == "pending"


def test_protocol_steps_seguimiento_done_tras_decision_y_medidas_ok(client: TestClient, session: Session):
    """Con la decisión registrada (acknowledge -> investigate ->
    decide, no el cierre) y las dos últimas medidas posteriores de la misma
    métrica y grupo en `ok`, el seguimiento pasa a `done`."""
    from vigia.app.models import Measurement

    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    resp = client.post(f"/api/alerts/{alert_id}/acknowledge", json={"actor": "clara", "motivo": "reviso"})
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/api/alerts/{alert_id}/investigate",
        json={"actor": "clara", "motivo": "reviso a fondo", "hallazgos": "consistente con el evento"},
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/api/alerts/{alert_id}/decide",
        json={"actor": "clara", "motivo": "se contiene", "acciones": [{"key": "contener_subgrupo"}]},
    )
    assert resp.status_code == 200, resp.text
    fnrd = client.get(f"/api/alerts/{alert_id}").json()

    # Dos medidas sintéticas posteriores a la apertura, mismo monitor/métrica/
    # grupo que la alerta, reusando una evaluación real ya existente para la
    # FK: `_estados_posteriores` solo mira `Measurement.state`, no de qué
    # evaluación cuelga.
    for _ in range(2):
        session.add(
            Measurement(
                evaluation_id=fnrd["last_evaluation_id"],
                project_id=proyecto["id"],
                monitor_type=fnrd["monitor_type"],
                metric_key=fnrd["metric_key"],
                group_code=fnrd["group_code"],
                value=0.0,
                state="ok",
            )
        )
    session.commit()

    detalle = client.get(f"/api/alerts/{alert_id}").json()
    pasos = {p["key"]: p["status"] for p in detalle["protocol_steps"]}
    assert pasos["decision"] == "done"
    assert pasos["seguimiento"] == "done"


def test_protocol_steps_triaje_hecho_solo_con_accion_del_catalogo(client: TestClient):
    """`act()` no toca `history_json`, solo `alert_action`: `_triaje_hecho`
    tiene que mirar también esa tabla, no solo el historial."""
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    resp = client.post(
        f"/api/alerts/{alert_id}/actions",
        json={"action": "nota", "actor": "clara", "motivo": "primera revisión"},
    )
    assert resp.status_code == 200, resp.text

    detalle = client.get(f"/api/alerts/{alert_id}").json()
    assert detalle["status"] == "abierta"  # `act()` no cambia el estado de la alerta
    pasos = {p["key"]: p["status"] for p in detalle["protocol_steps"]}
    assert pasos["triaje"] == "done"
    assert pasos["investigacion"] == "current"


def test_pasos_protocolo_puros_casos_sinteticos():
    """`_pasos` es una función pura, se prueba sin sesión ni API."""
    from vigia.app.services.protocol_steps import _pasos

    recien_abierta = {
        p["key"]: p["status"]
        for p in _pasos(
            cerrada=False,
            triaje_hecho=False,
            investigacion_hecha=False,
            decision_hecha=False,
            estado_seguimiento="pending",
        )
    }
    assert recien_abierta == {
        "deteccion": "done",
        "triaje": "current",
        "investigacion": "pending",
        "decision": "pending",
        "seguimiento": "pending",
    }

    triada_sin_cerrar = {
        p["key"]: p["status"]
        for p in _pasos(
            cerrada=False,
            triaje_hecho=True,
            investigacion_hecha=False,
            decision_hecha=False,
            estado_seguimiento="current",
        )
    }
    assert triada_sin_cerrar["triaje"] == "done"
    assert triada_sin_cerrar["investigacion"] == "current"
    assert triada_sin_cerrar["decision"] == "pending"

    investigada_sin_cerrar = {
        p["key"]: p["status"]
        for p in _pasos(
            cerrada=False,
            triaje_hecho=True,
            investigacion_hecha=True,
            decision_hecha=False,
            estado_seguimiento="pending",
        )
    }
    assert investigada_sin_cerrar["investigacion"] == "done"
    assert investigada_sin_cerrar["decision"] == "current"

    decidida = {
        p["key"]: p["status"]
        for p in _pasos(
            cerrada=False,
            triaje_hecho=True,
            investigacion_hecha=True,
            decision_hecha=True,
            estado_seguimiento="current",
        )
    }
    assert decidida["investigacion"] == "done"
    assert decidida["decision"] == "done"
    assert decidida["seguimiento"] == "current"

    # Cerrar ya no completa nada por sí solo; sin investigar ni decidir,
    # cerrada deja esos dos hitos `pending` (no `current`: en una alerta
    # cerrada ningún hito queda `current`) y el seguimiento tal cual llega.
    cerrada_sin_decidir = {
        p["key"]: p["status"]
        for p in _pasos(
            cerrada=True,
            triaje_hecho=True,
            investigacion_hecha=False,
            decision_hecha=False,
            estado_seguimiento="pending",
        )
    }
    assert cerrada_sin_decidir["triaje"] == "done"
    assert cerrada_sin_decidir["investigacion"] == "pending"
    assert cerrada_sin_decidir["decision"] == "pending"

    # sin triaje no hay cierre posible en la práctica, pero la función es pura
    # y no lo impide: documenta que triaje manda sobre investigación, y que
    # `cerrada` nunca deja un hito `current`.
    sin_triaje_pero_cerrada = {
        p["key"]: p["status"]
        for p in _pasos(
            cerrada=True,
            triaje_hecho=False,
            investigacion_hecha=False,
            decision_hecha=False,
            estado_seguimiento="pending",
        )
    }
    assert sin_triaje_pero_cerrada["triaje"] == "pending"
    assert sin_triaje_pero_cerrada["investigacion"] == "pending"
    assert sin_triaje_pero_cerrada["decision"] == "pending"


def test_estado_seguimiento_puro_casos_sinteticos():
    """`_estado_seguimiento`, también pura, con listas sintéticas de
    estados. El seguimiento depende primero de si la decisión está hecha."""
    from vigia.app.services.protocol_steps import _estado_seguimiento

    # sin decisión, `pending` siempre, aunque ya haya medidas de vuelta a `ok`.
    assert _estado_seguimiento(False, []) == "pending"
    assert _estado_seguimiento(False, ["ok", "ok"]) == "pending"

    # con la decisión hecha, la regla de siempre sobre las medidas posteriores.
    assert _estado_seguimiento(True, []) == "current"
    assert _estado_seguimiento(True, ["aviso"]) == "current"
    assert _estado_seguimiento(True, ["alerta", "aviso"]) == "current"
    assert _estado_seguimiento(True, ["aviso", "ok"]) == "current"  # una sola `ok` no basta
    assert _estado_seguimiento(True, ["ok", "ok"]) == "done"
    assert _estado_seguimiento(True, ["alerta", "ok", "ok"]) == "done"  # las dos últimas, no todas
    assert _estado_seguimiento(True, ["ok", "aviso"]) == "current"  # la última no es `ok`


# --- Alerta por hitos, investigate/decide y `stage` ----------


def test_stage_detectada_en_alerta_recien_abierta(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    detalle = client.get(f"/api/alerts/{alert_id}").json()
    assert detalle["stage"] == "detectada"


def test_flujo_completo_por_hitos_investigate_y_decide(client: TestClient):
    """Acknowledge (triaje) -> investigate -> decide, con `stage` en
    cada paso, el historial hablando en hitos, `protocol_steps` al día y los
    eventos `alerta.investigada`/`alerta.decidida` encadenados a los
    `alerta.accion` de `decide` por el mismo `correlation_id`."""
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]

    resp = client.post(f"/api/alerts/{alert_id}/acknowledge", json={"actor": "clara", "motivo": "reviso"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["stage"] == "en_observacion"

    resp = client.post(
        f"/api/alerts/{alert_id}/investigate",
        json={"actor": "clara", "motivo": "reviso a fondo", "hallazgos": "el lote viene manipulado"},
    )
    assert resp.status_code == 200, resp.text
    investigada = resp.json()
    assert investigada["stage"] == "en_investigacion"
    assert investigada["status"] == "reconocida"  # investigate no cambia `status`

    resp = client.post(
        f"/api/alerts/{alert_id}/decide",
        json={
            "actor": "clara",
            "motivo": "se contiene el subgrupo",
            "acciones": [
                {"key": "contener_subgrupo", "notes": "aviso al clínico"},
                {"key": "escalar"},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    decidida = resp.json()
    assert decidida["stage"] == "en_seguimiento"
    assert decidida["status"] == "reconocida"  # decide tampoco cambia `status`

    detalle = client.get(f"/api/alerts/{alert_id}").json()
    entrada_investigacion = next(h for h in detalle["history"] if h["hito"] == "investigacion")
    assert entrada_investigacion["detalle"] == "el lote viene manipulado"
    entrada_decision = next(h for h in detalle["history"] if h["hito"] == "decision")
    assert entrada_decision["detalle"] == "Contener el subgrupo · Escalar"
    entrada_triaje = next(h for h in detalle["history"] if h["hito"] == "triaje")
    assert entrada_triaje["to"] == "reconocida"

    pasos = {p["key"]: p["status"] for p in detalle["protocol_steps"]}
    assert pasos["triaje"] == "done"
    assert pasos["investigacion"] == "done"
    assert pasos["decision"] == "done"
    assert pasos["seguimiento"] == "current"

    assert len(detalle["actions"]) == 2
    assert {a["action"] for a in detalle["actions"]} == {"contener_subgrupo", "escalar"}
    nota_contener = next(a for a in detalle["actions"] if a["action"] == "contener_subgrupo")
    assert nota_contener["motivo"] == "aviso al clínico"
    nota_escalar = next(a for a in detalle["actions"] if a["action"] == "escalar")
    assert nota_escalar["motivo"] == "se contiene el subgrupo"  # sin `notes` propio, cae al motivo general

    eventos = client.get(
        "/api/events",
        params={"actor_kind": "humano", "object_type": "alert", "object_id": alert_id, "limit": 100},
    ).json()["items"]
    investigada_evt = next(e for e in eventos if e["action"] == "alerta.investigada")
    assert investigada_evt["after"]["hallazgos"] == "el lote viene manipulado"
    decidida_evt = next(e for e in eventos if e["action"] == "alerta.decidida")
    assert decidida_evt["after"]["acciones"] == ["contener_subgrupo", "escalar"]
    cid = decidida_evt["correlation_id"]
    assert cid is not None
    acciones_evt = [e for e in eventos if e["action"] == "alerta.accion"]
    assert len(acciones_evt) == 2
    assert all(e["correlation_id"] == cid for e in acciones_evt)


def test_investigate_sin_triaje_409(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    resp = client.post(
        f"/api/alerts/{alert_id}/investigate",
        json={"actor": "clara", "motivo": "x", "hallazgos": "y"},
    )
    assert resp.status_code == 409, resp.text
    assert "triaje" in resp.json()["detail"]


def test_investigate_repetida_409(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    client.post(f"/api/alerts/{alert_id}/acknowledge", json={"actor": "clara", "motivo": "reviso"})
    resp = client.post(
        f"/api/alerts/{alert_id}/investigate",
        json={"actor": "clara", "motivo": "x", "hallazgos": "y"},
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/api/alerts/{alert_id}/investigate",
        json={"actor": "clara", "motivo": "x", "hallazgos": "otra vez"},
    )
    assert resp.status_code == 409, resp.text
    assert "investigación" in resp.json()["detail"]


def test_investigate_alerta_cerrada_409(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    client.post(f"/api/alerts/{alert_id}/close", json={"actor": "clara", "motivo": "resuelto"})
    resp = client.post(
        f"/api/alerts/{alert_id}/investigate",
        json={"actor": "clara", "motivo": "x", "hallazgos": "y"},
    )
    assert resp.status_code == 409, resp.text


def test_decide_sin_investigacion_409(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    client.post(f"/api/alerts/{alert_id}/acknowledge", json={"actor": "clara", "motivo": "reviso"})
    resp = client.post(
        f"/api/alerts/{alert_id}/decide",
        json={"actor": "clara", "motivo": "x", "acciones": [{"key": "escalar"}]},
    )
    assert resp.status_code == 409, resp.text
    assert "investigación" in resp.json()["detail"]


def test_decide_repetida_409(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    client.post(f"/api/alerts/{alert_id}/acknowledge", json={"actor": "clara", "motivo": "reviso"})
    client.post(
        f"/api/alerts/{alert_id}/investigate",
        json={"actor": "clara", "motivo": "x", "hallazgos": "y"},
    )
    resp = client.post(
        f"/api/alerts/{alert_id}/decide",
        json={"actor": "clara", "motivo": "x", "acciones": [{"key": "escalar"}]},
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/api/alerts/{alert_id}/decide",
        json={"actor": "clara", "motivo": "x", "acciones": [{"key": "nota"}]},
    )
    assert resp.status_code == 409, resp.text
    assert "decisión" in resp.json()["detail"]


def test_decide_acciones_vacia_422(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    client.post(f"/api/alerts/{alert_id}/acknowledge", json={"actor": "clara", "motivo": "reviso"})
    client.post(
        f"/api/alerts/{alert_id}/investigate",
        json={"actor": "clara", "motivo": "x", "hallazgos": "y"},
    )
    resp = client.post(
        f"/api/alerts/{alert_id}/decide",
        json={"actor": "clara", "motivo": "x", "acciones": []},
    )
    assert resp.status_code == 422, resp.text


def test_decide_clave_desconocida_422(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    client.post(f"/api/alerts/{alert_id}/acknowledge", json={"actor": "clara", "motivo": "reviso"})
    client.post(
        f"/api/alerts/{alert_id}/investigate",
        json={"actor": "clara", "motivo": "x", "hallazgos": "y"},
    )
    resp = client.post(
        f"/api/alerts/{alert_id}/decide",
        json={"actor": "clara", "motivo": "x", "acciones": [{"key": "no-existe"}]},
    )
    assert resp.status_code == 422, resp.text


def test_stage_cerrada_tras_cerrar(client: TestClient):
    proyecto, _ = _preparar_con_evento(client)
    alert_id = _alertas(client, proyecto["id"], status="abierta")[0]["id"]
    resp = client.post(f"/api/alerts/{alert_id}/close", json={"actor": "clara", "motivo": "resuelto"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["stage"] == "cerrada"

    detalle = client.get(f"/api/alerts/{alert_id}").json()
    assert detalle["stage"] == "cerrada"


def test_protocol_steps_con_textos_del_monitor(client: TestClient, session: Session):
    """`protocol_steps` trae los textos de `Monitor.protocol_json`, no
    solo la plantilla fija; el resto de hitos, que el monitor no ha tocado,
    sigue viniendo de la plantilla."""
    from vigia.app.content_loader import protocolo_hitos_plantilla
    from vigia.app.models import Monitor, Project

    proyecto, _ = _preparar_con_evento(client)
    project = session.get(Project, proyecto["id"])
    assert project is not None
    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == project.id, Monitor.type == "fairness")
    ).first()
    assert monitor is not None

    protocolo = protocolo_hitos_plantilla()
    for hito in protocolo:
        if hito["key"] == "triaje":
            hito["titulo"] = "Triaje clínico"
            hito["responsable"] = "Enfermería"
            hito["plazo_dias"] = 2
    monitor.protocol_json = protocolo
    session.add(monitor)
    session.commit()

    alert_id = next(
        a for a in _alertas(client, proyecto["id"], status="abierta") if a["monitor_type"] == "fairness"
    )["id"]
    detalle = client.get(f"/api/alerts/{alert_id}").json()
    pasos = {p["key"]: p for p in detalle["protocol_steps"]}
    assert pasos["triaje"]["titulo"] == "Triaje clínico"
    assert pasos["triaje"]["responsable"] == "Enfermería"
    assert pasos["triaje"]["plazo_dias"] == 2
    # el resto del protocolo, no tocado a mano, sigue trayendo su texto.
    assert pasos["deteccion"]["titulo"] == "Detección"
    assert pasos["decision"]["entregables"]
    assert all(p["target_date"] is None for p in pasos.values())
