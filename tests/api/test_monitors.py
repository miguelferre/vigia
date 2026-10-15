"""PATCH de monitores y bloqueo de min_records."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api.conftest import actor_headers
from tests.api.test_alerts import _alertas, _preparar_con_evento
from vigia.app.models import Event, ModelVersion


def _crear_proyecto(client: TestClient, name: str = "reuma-piloto", domain: str = "reuma") -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": domain},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _monitor(proyecto: dict, tipo: str) -> dict:
    return next(m for m in proyecto["monitors"] if m["type"] == tipo)


def test_list_monitors_devuelve_los_cinco(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-listado")
    resp = client.get(f"/api/projects/{proyecto['id']}/monitors")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert {m["type"] for m in body["items"]} == {
        "fairness",
        "quality",
        "drift",
        "explain",
        "cross",
    }


def test_get_monitor_por_id(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-uno")
    fairness = _monitor(proyecto, "fairness")
    resp = client.get(f"/api/monitors/{fairness['id']}")
    assert resp.status_code == 200
    assert resp.json()["type"] == "fairness"


def test_patch_monitor_sin_motivo_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-sin-motivo")
    quality = _monitor(proyecto, "quality")
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={"actor": "miguel", "enabled": False},
    )
    assert resp.status_code == 422


def test_patch_monitor_sin_actor_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-sin-actor")
    quality = _monitor(proyecto, "quality")
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={"motivo": "prueba", "enabled": False},
    )
    assert resp.status_code == 422


def test_patch_monitor_deshabilita_y_registra_evento(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="p-deshabilita")
    quality = _monitor(proyecto, "quality")
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={"actor": "miguel", "motivo": "pausa temporal", "enabled": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["monitor"]["enabled"] is False
    assert body["event_id"] is not None

    evento = session.get(Event, body["event_id"])
    assert evento.action == "monitor.configurado"
    assert evento.motivo == "pausa temporal"
    assert evento.before_json == {"enabled": True}
    assert evento.after_json == {"enabled": False}


def test_patch_config_invalida_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-config-mala")
    quality = _monitor(proyecto, "quality")
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={
            "actor": "miguel",
            "motivo": "prueba",
            "config": {"min_feedback": "no-es-un-numero"},
        },
    )
    assert resp.status_code == 422


def test_patch_thresholds_invalidos_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-thresholds-malos")
    quality = _monitor(proyecto, "quality")
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={
            "actor": "miguel",
            "motivo": "prueba",
            "thresholds": {"thresholds": [{"metric_key": "accuracy", "kind": "no-existe", "value": 1}]},
        },
    )
    assert resp.status_code == 422


def test_cambiar_min_records_sin_laboratorio_409(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-min-records-bloqueado")
    fairness = _monitor(proyecto, "fairness")
    resp = client.patch(
        f"/api/monitors/{fairness['id']}",
        json={
            "actor": "miguel",
            "motivo": "quiero bajar la ventana",
            "config": {**fairness["config"], "min_records": 50},
        },
    )
    assert resp.status_code == 409


def test_cambiar_min_records_con_laboratorio_y_sim_logistic_actualiza_version(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="p-laboratorio")
    # Sustituimos la versión activa por una sim_logistic para poder tocar la ventana.
    resp = client.post(
        f"/api/projects/{proyecto['id']}/versions",
        json={"label": "sim", "model_kind": "sim_logistic", "actor": "miguel", "motivo": "laboratorio"},
    )
    assert resp.status_code == 200, resp.text
    version_sim = resp.json()
    resp = client.post(
        f"/api/model-versions/{version_sim['id']}/activate",
        json={"actor": "miguel", "motivo": "activar sim para laboratorio"},
    )
    assert resp.status_code == 200, resp.text

    fairness = _monitor(proyecto, "fairness")
    resp = client.patch(
        f"/api/monitors/{fairness['id']}",
        json={
            "actor": "miguel",
            "motivo": "ventana de laboratorio más pequeña",
            "laboratorio": True,
            "config": {**fairness["config"], "min_records": 50},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["monitor"]["config"]["min_records"] == 50

    version_bd = session.get(ModelVersion, version_sim["id"])
    assert version_bd.fairness_window_n == 50

    evento = session.get(Event, body["event_id"])
    assert evento.after_json["fairness_window_n"] == 50


def test_patch_config_parcial_conserva_los_campos_no_enviados(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="p-config-parcial")
    fairness = _monitor(proyecto, "fairness")

    resp = client.patch(
        f"/api/monitors/{fairness['id']}",
        json={
            "actor": "miguel",
            "motivo": "ajustar mínimos de grupo",
            "config": {**fairness["config"], "min_group": 99, "min_positives": 7},
        },
    )
    assert resp.status_code == 200, resp.text

    resp = client.patch(
        f"/api/monitors/{fairness['id']}",
        json={
            "actor": "miguel",
            "motivo": "ajustar el paso de ventana",
            "config": {"window_step": 3},
        },
    )
    assert resp.status_code == 200, resp.text
    config = resp.json()["monitor"]["config"]
    assert config["window_step"] == 3
    assert config["min_group"] == 99
    assert config["min_positives"] == 7

    # Con min_records ya bajado por laboratorio, un PATCH parcial sin relación
    # con la ventana no debe interpretarse como un intento de tocarlo.
    resp = client.post(
        f"/api/projects/{proyecto['id']}/versions",
        json={"label": "sim", "model_kind": "sim_logistic", "actor": "miguel", "motivo": "laboratorio"},
    )
    assert resp.status_code == 200, resp.text
    version_sim = resp.json()
    resp = client.post(
        f"/api/model-versions/{version_sim['id']}/activate",
        json={"actor": "miguel", "motivo": "activar sim para laboratorio"},
    )
    assert resp.status_code == 200, resp.text

    resp = client.patch(
        f"/api/monitors/{fairness['id']}",
        json={
            "actor": "miguel",
            "motivo": "bajar la ventana en laboratorio",
            "laboratorio": True,
            "config": {**fairness["config"], "min_records": 50},
        },
    )
    assert resp.status_code == 200, resp.text

    resp = client.patch(
        f"/api/monitors/{fairness['id']}",
        json={
            "actor": "miguel",
            "motivo": "ajustar min_group sin tocar la ventana",
            "config": {"min_group": 30},
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["monitor"]["config"]["min_group"] == 30


def test_patch_protocolo(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-protocolo")
    cross = _monitor(proyecto, "cross")
    resp = client.patch(
        f"/api/monitors/{cross['id']}",
        json={"actor": "miguel", "motivo": "afinar protocolo", "protocolo_md": "Nuevo protocolo."},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["monitor"]["protocolo_md"] == "Nuevo protocolo."


def test_get_monitor_trae_el_protocolo_con_los_cinco_hitos_de_la_plantilla(client: TestClient):
    """Un monitor recién creado enseña la plantilla de
    `content/protocolo-hitos.json`, sin responsable ni plazo."""
    proyecto = _crear_proyecto(client, name="p-protocolo-plantilla")
    quality = _monitor(proyecto, "quality")
    resp = client.get(f"/api/monitors/{quality['id']}")
    assert resp.status_code == 200
    protocol = resp.json()["protocol"]
    assert [h["key"] for h in protocol] == [
        "deteccion",
        "triaje",
        "investigacion",
        "decision",
        "seguimiento",
    ]
    assert [h["titulo"] for h in protocol] == [
        "Detección",
        "Triaje",
        "Investigación",
        "Decisión",
        "Seguimiento",
    ]
    assert all(h["responsable"] is None for h in protocol)
    assert all(h["plazo_dias"] is None for h in protocol)


def test_patch_protocol_valido_lo_guarda_y_deja_el_evento(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, name="p-protocolo-valido")
    quality = _monitor(proyecto, "quality")
    protocol_antes = quality["protocol"]
    nuevo_protocol = [dict(h) for h in protocol_antes]
    nuevo_protocol[1] = {
        **nuevo_protocol[1],
        "titulo": "Triaje urgente",
        "entregables": [*nuevo_protocol[1]["entregables"], "Aviso al clínico"],
        "responsable": "Clara",
        "plazo_dias": 2,
    }
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={
            "actor": "miguel",
            "motivo": "afinar el hito de triaje",
            "protocol": nuevo_protocol,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    protocol_guardado = body["monitor"]["protocol"]
    assert protocol_guardado[1]["titulo"] == "Triaje urgente"
    assert "Aviso al clínico" in protocol_guardado[1]["entregables"]
    assert protocol_guardado[1]["responsable"] == "Clara"
    assert protocol_guardado[1]["plazo_dias"] == 2
    assert protocol_guardado[0]["titulo"] == "Detección"  # el resto no se toca

    evento = session.get(Event, body["event_id"])
    assert evento.action == "monitor.configurado"
    assert evento.before_json["protocol"] == protocol_antes
    assert evento.after_json["protocol"] == protocol_guardado


def test_patch_protocol_con_cuatro_hitos_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-protocolo-incompleto")
    quality = _monitor(proyecto, "quality")
    protocol_incompleto = quality["protocol"][:4]  # falta "seguimiento"
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={"actor": "miguel", "motivo": "prueba", "protocol": protocol_incompleto},
    )
    assert resp.status_code == 422


def test_patch_protocol_con_claves_desordenadas_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-protocolo-desordenado")
    quality = _monitor(proyecto, "quality")
    protocol_desordenado = list(reversed(quality["protocol"]))
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={"actor": "miguel", "motivo": "prueba", "protocol": protocol_desordenado},
    )
    assert resp.status_code == 422


def test_patch_protocol_con_plazo_dias_negativo_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-protocolo-plazo-malo")
    quality = _monitor(proyecto, "quality")
    protocol = [dict(h) for h in quality["protocol"]]
    protocol[0]["plazo_dias"] = -1
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={"actor": "miguel", "motivo": "prueba", "protocol": protocol},
    )
    assert resp.status_code == 422


def test_patch_que_no_toca_protocol_lo_conserva(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-protocolo-intacto")
    quality = _monitor(proyecto, "quality")
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={"actor": "miguel", "motivo": "solo cambio la activación", "enabled": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["monitor"]["protocol"] == quality["protocol"]


# --- Hitos extra del protocolo --------------


def test_patch_protocol_con_hito_extra_aparece_informativo_en_la_alerta(client: TestClient):
    """Un hito extra intercalado tras «Decisión»: 200, se ve en `GET
    /monitors/{id}` y, en la alerta abierta de ese monitor, en
    `protocol_steps` con `status: "informativo"` en su posición."""
    proyecto, _ = _preparar_con_evento(client)
    fairness = _monitor(proyecto, "fairness")
    protocol = [dict(h) for h in fairness["protocol"]]
    hito_extra = {
        "key": "comunicar_servicio",
        "titulo": "Comunicar al servicio",
        "descripcion": "Avisar al servicio clínico afectado.",
        "entregables": ["Aviso registrado"],
        "responsable": None,
        "plazo_dias": None,
    }
    protocol.insert(4, hito_extra)  # tras "decision", antes de "seguimiento"

    resp = client.patch(
        f"/api/monitors/{fairness['id']}",
        json={"actor": "miguel", "motivo": "añadir hito de comunicación", "protocol": protocol},
    )
    assert resp.status_code == 200, resp.text
    protocol_guardado = resp.json()["monitor"]["protocol"]
    assert [h["key"] for h in protocol_guardado] == [
        "deteccion", "triaje", "investigacion", "decision",
        "comunicar_servicio", "seguimiento",
    ]

    alert_id = next(
        a for a in _alertas(client, proyecto["id"], status="abierta") if a["monitor_type"] == "fairness"
    )["id"]
    detalle = client.get(f"/api/alerts/{alert_id}").json()
    pasos = detalle["protocol_steps"]
    assert [p["key"] for p in pasos] == [
        "deteccion", "triaje", "investigacion", "decision",
        "comunicar_servicio", "seguimiento",
    ]
    extra = next(p for p in pasos if p["key"] == "comunicar_servicio")
    assert extra["status"] == "informativo"
    assert extra["target_date"] is None
    assert extra["titulo"] == "Comunicar al servicio"


def test_patch_protocol_quitando_un_hito_estandar_422_con_faltan(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-h13-quitar-estandar")
    quality = _monitor(proyecto, "quality")
    protocol_sin_seguimiento = [h for h in quality["protocol"] if h["key"] != "seguimiento"]
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={"actor": "miguel", "motivo": "prueba", "protocol": protocol_sin_seguimiento},
    )
    assert resp.status_code == 422
    assert "faltan" in resp.json()["detail"]


def test_patch_protocol_hito_extra_con_key_de_acciones_alerta_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="p-h13-key-accion")
    quality = _monitor(proyecto, "quality")
    protocol = [*quality["protocol"], {
        "key": "escalar",  # ya está en ACCIONES_ALERTA
        "titulo": "Escalar",
        "descripcion": "",
        "entregables": [],
        "responsable": None,
        "plazo_dias": None,
    }]
    resp = client.patch(
        f"/api/monitors/{quality['id']}",
        json={"actor": "miguel", "motivo": "prueba", "protocol": protocol},
    )
    assert resp.status_code == 422


def test_investigar_y_decidir_con_hitos_extra_no_cambia_alert_stage(client: TestClient):
    """Un hito extra nunca mueve la etapa, con o sin él en el
    protocolo la secuencia investigate -> decide deriva la misma etapa."""
    proyecto, _ = _preparar_con_evento(client)
    fairness = _monitor(proyecto, "fairness")
    protocol = [*fairness["protocol"], {
        "key": "hito_extra_etapa",
        "titulo": "Hito informativo",
        "descripcion": "",
        "entregables": [],
        "responsable": None,
        "plazo_dias": None,
    }]
    resp = client.patch(
        f"/api/monitors/{fairness['id']}",
        json={"actor": "miguel", "motivo": "añadir hito informativo", "protocol": protocol},
    )
    assert resp.status_code == 200, resp.text

    alert_id = next(
        a for a in _alertas(client, proyecto["id"], status="abierta") if a["monitor_type"] == "fairness"
    )["id"]
    resp = client.post(f"/api/alerts/{alert_id}/acknowledge", json={"actor": "clara", "motivo": "reviso"})
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/api/alerts/{alert_id}/investigate",
        json={"actor": "clara", "motivo": "reviso a fondo", "hallazgos": "consistente con el evento"},
    )
    assert resp.status_code == 200, resp.text
    detalle = client.get(f"/api/alerts/{alert_id}").json()
    assert detalle["stage"] == "en_investigacion"

    resp = client.post(
        f"/api/alerts/{alert_id}/decide",
        json={"actor": "clara", "motivo": "se contiene", "acciones": [{"key": "contener_subgrupo"}]},
    )
    assert resp.status_code == 200, resp.text
    detalle = client.get(f"/api/alerts/{alert_id}").json()
    assert detalle["stage"] == "en_seguimiento"
    pasos = {p["key"]: p["status"] for p in detalle["protocol_steps"]}
    assert pasos["hito_extra_etapa"] == "informativo"


def test_settings_for_incluye_el_umbral_de_explain(client: TestClient, session: Session):
    """El PATCH de `explain` debe llegar al motor: `settings_for` construye
    `MonitorSettings.thresholds` con la clave `"explain"`, no solo con
    fairness/quality/drift. Sin ella, `core.engine.evaluate_batch` cae
    siempre al valor por defecto (`DEFAULT_EXPLAIN_THRESHOLDS`, 0,50) vía
    `settings.thresholds.get("explain", ...)`, ignorando cualquier PATCH.
    """
    from vigia.app.models import ModelVersion, Project
    from vigia.app.services.monitors import settings_for

    proyecto = _crear_proyecto(client, name="p-explain-umbral")
    explain = _monitor(proyecto, "explain")

    resp = client.patch(
        f"/api/monitors/{explain['id']}",
        json={
            "actor": "miguel",
            "motivo": "calibrar el umbral de explicabilidad",
            "thresholds": {
                "thresholds": [
                    {"metric_key": "explain_stability_ndcg", "kind": "lower_limit", "value": 0.9}
                ]
            },
        },
    )
    assert resp.status_code == 200, resp.text

    project = session.get(Project, proyecto["id"])
    version = session.get(ModelVersion, project.active_version_id)
    settings = settings_for(session, project, version)

    assert "explain" in settings.thresholds
    assert settings.thresholds["explain"].limits("explain_stability_ndcg") == (0.9, None)


def test_patch_monitor_404(client: TestClient):
    resp = client.patch(
        "/api/monitors/999999",
        json={"actor": "miguel", "motivo": "prueba"},
    )
    assert resp.status_code == 404
