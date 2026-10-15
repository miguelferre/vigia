"""Esquemas y plantillas compartidos: `AlertStatus` con `retirada`, origen de
la alerta y títulos del diario."""

from __future__ import annotations

import typing

from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api.conftest import actor_headers
from vigia.app.events_titulos import ACCIONES_CON_PLANTILLA, titulo_evento
from vigia.app.models import Alert, Batch, Event, Measurement, ModelVersion, Project
from vigia.app.schemas.cross import CrossLatestOut, CrossRuleOut
from vigia.app.schemas.respuestas_alertas import Alert as AlertOut
from vigia.app.schemas.respuestas_base import AlertStatus
from vigia.app.services.human_layer import _cross_rules_from_measurements
from vigia.core.schema import MappingTemplate


def _crear_proyecto(client: TestClient, name: str, **extra) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "reuma", **extra},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir(client: TestClient, project_id: int, contenido: bytes) -> dict:
    resp = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": ("datos.csv", contenido, "text/csv")},
        data={"kind": "combined", "role": "production"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- alertas: estado retirada y origen -------------------------


def test_alert_status_acepta_retirada():
    assert "retirada" in typing.get_args(AlertStatus.__value__)
    assert {"origin_batch_id", "origin_batch_seq", "origin_phase_label"} <= set(
        AlertOut.model_fields
    )


def test_la_alerta_sale_con_su_lote_de_origen_y_retirada(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, "origen-alerta")
    version_id = proyecto["active_version_id"]
    lote = Batch(
        project_id=proyecto["id"],
        model_version_id=version_id,
        seq=3,
        phase_label="Pacientes nuevos",
    )
    session.add(lote)
    session.flush()
    viva = Alert(
        project_id=proyecto["id"],
        monitor_type="quality",
        metric_key="accuracy",
        title="viva",
        origin_batch_id=lote.id,
    )
    retirada = Alert(
        project_id=proyecto["id"],
        monitor_type="quality",
        metric_key="f1",
        title="retirada",
        status="retirada",
        retired_reason="lote 3 borrado",
        origin_batch_id=9999,  # lote que ya no existe
    )
    session.add(viva)
    session.add(retirada)
    session.commit()

    detalle = client.get(f"/api/alerts/{viva.id}").json()
    assert detalle["origin_batch_id"] == lote.id
    assert detalle["origin_batch_seq"] == 3
    assert detalle["origin_phase_label"] == "Pacientes nuevos"

    lista = {
        a["id"]: a for a in client.get(f"/api/projects/{proyecto['id']}/alerts").json()["items"]
    }
    assert lista[viva.id]["origin_batch_seq"] == 3
    borrada = lista[retirada.id] if retirada.id in lista else client.get(
        f"/api/alerts/{retirada.id}"
    ).json()
    assert borrada["status"] == "retirada"
    assert borrada["retired_reason"] == "lote 3 borrado"
    assert borrada["origin_batch_id"] == 9999
    assert borrada["origin_batch_seq"] is None
    assert borrada["origin_phase_label"] is None


# --- títulos del diario ----------------------------------------


def test_titulos_alerta_retirada_y_linea_base_automatica():
    assert "alerta.retirada" in ACCIONES_CON_PLANTILLA
    retirada = Event(
        id=1,
        action="alerta.retirada",
        object_type="alert",
        object_id=8,
        motivo="lote 3 borrado",
    )
    assert titulo_evento(retirada) == "Alerta 8 retirada: lote 3 borrado"
    manual = Event(
        id=2,
        action="version.baseline_congelado",
        object_type="model_version",
        object_id=7,
        after_json={"baseline_batch_id": 4},
    )
    assert titulo_evento(manual) == "Línea base congelada en el lote 4"
    automatico = Event(
        id=3,
        action="version.baseline_congelado",
        object_type="model_version",
        object_id=7,
        after_json={"baseline_batch_id": 4, "automatico": True},
    )
    assert titulo_evento(automatico) == "Línea base congelada automáticamente en el lote 4"


# --- Cross/latest sin datos ------------------------------------------


def test_cross_latest_sin_datos_es_200_con_estado_explicito(client: TestClient):
    proyecto = _crear_proyecto(client, "cross-sin-datos")
    resp = client.get(f"/api/projects/{proyecto['id']}/cross/latest")
    assert resp.status_code == 200
    cuerpo = resp.json()
    assert cuerpo["estado"] == "sin_datos"
    assert cuerpo["rules"] == []
    assert cuerpo["evaluation_id"] is None
    assert cuerpo["evaluated_at"] is None
    assert cuerpo["worst_state"] == "sin_datos"


# --- Motivo y n en las reglas cruzadas --------------------------------


def test_regla_cruzada_lleva_motivo_y_n():
    assert {"motivo", "n"} <= set(CrossRuleOut.model_fields)
    assert "estado" in CrossLatestOut.model_fields
    medida = Measurement(
        evaluation_id=1,
        metric_key="human_review_zero",
        value=0.0,
        state="aviso",
        motivo="ningún profesional ha corregido al modelo en 412 decisiones",
        extra_json={"n": 412, "n_override": 0},
    )
    sin_extra = Measurement(evaluation_id=1, metric_key="cx4_deskilling", value=1.0, state="ok")
    reglas = _cross_rules_from_measurements([medida, sin_extra])
    assert reglas[0]["n"] == 412
    assert "412 decisiones" in reglas[0]["motivo"]
    assert reglas[1]["n"] is None and reglas[1]["motivo"] is None
    for r in reglas:
        CrossRuleOut(**r)


# --- Plantilla en la subida y columnas del modelo ---------------


def test_la_plantilla_admite_prediccion_probabilidad_y_etiqueta():
    p = MappingTemplate(prediction_col="pred", probability_col="prob", label_col="y")
    assert p.model_dump(mode="json")["label_col"] == "y"
    assert MappingTemplate().prediction_col is None


def test_la_subida_trae_la_sugerencia_con_la_plantilla(client: TestClient):
    proyecto = _crear_proyecto(
        client,
        "e07-subida",
        mapping_template={
            "favorable_label": 0,
            "id_col": "id",
            "prediction_col": "salida",
            "probability_col": "prob_modelo",
            "label_col": "real",
        },
    )
    cuerpo = _subir(
        client,
        proyecto["id"],
        b"id,prediction,label,salida,prob_modelo,real\n1,0,0,0,0.2,0\n2,1,1,1,0.9,1\n",
    )
    sugerido = cuerpo["dataset"]["suggested_mapping"]
    assert sugerido["favorable_label"] == 0
    assert sugerido["id_col"] == "id"
    assert sugerido["prediction_col"] == "salida"
    assert sugerido["probability_col"] == "prob_modelo"
    assert sugerido["label_col"] == "real"
    assert cuerpo["suggested_mapping"] == sugerido


def test_la_columna_de_la_plantilla_que_el_fichero_no_trae_no_se_sugiere(client: TestClient):
    proyecto = _crear_proyecto(
        client,
        "e08-columna-ausente",
        mapping_template={"prediction_col": "salida_vieja", "label_col": "real_viejo"},
    )
    cuerpo = _subir(
        client, proyecto["id"], b"id,prediction,label\n1,0,0\n2,1,1\n"
    )
    sugerido = cuerpo["dataset"]["suggested_mapping"]
    assert sugerido["prediction_col"] == "prediction"
    assert sugerido["label_col"] == "label"


def test_la_linea_base_congelada_rellena_las_columnas_de_la_plantilla(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, "e08-sincroniza")
    cuerpo = _subir(
        client, proyecto["id"], b"id,prediction,prob,label\n1,0,0.2,0\n2,1,0.9,1\n"
    )
    dataset_id = cuerpo["dataset"]["id"]
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={
            "mapping": {
                "prediction_col": "prediction",
                "probability_col": "prob",
                "label_col": "label",
                "id_col": "id",
                "favorable_label": 1,
            }
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    lote = Batch(
        project_id=proyecto["id"],
        model_version_id=proyecto["active_version_id"],
        dataset_id=dataset_id,
        seq=0,
        n_rows=2,
    )
    session.add(lote)
    session.commit()
    resp = client.post(
        f"/api/model-versions/{proyecto['active_version_id']}/baseline",
        json={"batch_id": lote.id, "actor": "miguel", "motivo": "linea base"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    session.expire_all()
    plantilla = session.get(Project, proyecto["id"]).mapping_template_json
    assert plantilla["prediction_col"] == "prediction"
    assert plantilla["probability_col"] == "prob"
    assert plantilla["label_col"] == "label"
    assert plantilla["favorable_label"] == 1
    assert session.get(ModelVersion, proyecto["active_version_id"]).frozen_at is not None
