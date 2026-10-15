"""Plantilla de mapeo y `acepta_feedback` en el alta, método del intervalo de
equidad de la v1 y de versiones nuevas, `sim_logistic` fuera de los dominios
del simulador, aviso de línea base sin congelar, congelar al activar, la
propuesta de umbrales (con `core.calibration.proponer_umbrales` parcheado) y la sincronía de
`favorable_label` al congelar la línea base.
"""

from __future__ import annotations

from unittest import mock

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import Batch, Dataset, Event, ModelVersion, Project
from vigia.app.schemas.projects import MENSAJE_SIM_LOGISTIC
from vigia.core.calibration import PropuestaUmbral


def _crear_proyecto(client: TestClient, **kwargs) -> dict:
    body = {"name": "proyecto-r2", "domain": "libre", **kwargs}
    resp = client.post("/api/projects", json=body, headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _congelar_con_batch(client: TestClient, session: Session, project_id: int, version_id: int) -> Batch:
    batch = Batch(project_id=project_id, model_version_id=version_id, seq=0, n_rows=5)
    session.add(batch)
    session.commit()
    session.refresh(batch)
    resp = client.post(
        f"/api/model-versions/{version_id}/baseline",
        json={"batch_id": batch.id, "actor": "miguel", "motivo": "linea base"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return batch


# --- Plantilla de mapeo y acepta_feedback -----------------------------


def test_crear_proyecto_con_plantilla_y_acepta_feedback(client: TestClient, session: Session):
    plantilla = {"favorable_label": 0, "id_col": "episodio", "feature_cols": ["edad", "sexo"]}
    proyecto = _crear_proyecto(
        client, name="con-plantilla", mapping_template=plantilla, acepta_feedback=False
    )
    assert proyecto["mapping_template_json"]["favorable_label"] == 0
    assert proyecto["mapping_template_json"]["id_col"] == "episodio"
    assert proyecto["acepta_feedback"] is False

    proyecto_bd = session.get(Project, proyecto["id"])
    assert proyecto_bd is not None
    assert proyecto_bd.acepta_feedback is False


def test_patch_project_cambia_plantilla_y_deja_evento_propio(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, name="plantilla-patch")
    project_id = proyecto["id"]
    nueva_plantilla = {"favorable_label": 1, "feature_cols": ["talla"]}

    resp = client.patch(
        f"/api/projects/{project_id}",
        json={"actor": "miguel", "motivo": "fijo la plantilla", "mapping_template": nueva_plantilla},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["mapping_template_json"]["feature_cols"] == ["talla"]

    evento = session.exec(
        select(Event).where(Event.action == "proyecto.plantilla_actualizada")
    ).one()
    assert evento.after_json["mapping_template"]["feature_cols"] == ["talla"]
    assert evento.motivo == "fijo la plantilla"

    # PATCH sin mapping_template (None) no toca la plantilla ya guardada.
    resp = client.patch(
        f"/api/projects/{project_id}",
        json={"actor": "miguel", "motivo": "otro cambio", "acepta_feedback": False},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["mapping_template_json"]["feature_cols"] == ["talla"]
    assert resp.json()["acepta_feedback"] is False


# --- Método del intervalo de equidad ----------------------------------


def test_crear_proyecto_sin_metodo_pone_lote_en_la_v1(client: TestClient):
    """POST /api/projects pone "lote" en la v1 salvo que el cuerpo diga otra cosa."""
    proyecto = _crear_proyecto(client, name="metodo-por-defecto")
    assert proyecto["versions"][0]["fairness_interval_method"] == "lote"


def test_crear_proyecto_con_metodo_explicito_lo_respeta(client: TestClient):
    proyecto = _crear_proyecto(
        client, name="metodo-ventanas", fairness_interval_method="ventanas"
    )
    assert proyecto["versions"][0]["fairness_interval_method"] == "ventanas"


def test_crear_version_hereda_metodo_de_la_activa_si_no_se_pasa(client: TestClient):
    proyecto = _crear_proyecto(
        client, name="hereda-metodo", fairness_interval_method="ventanas"
    )
    resp = client.post(
        f"/api/projects/{proyecto['id']}/versions",
        json={"label": "v2", "actor": "miguel", "motivo": "nueva versión"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["fairness_interval_method"] == "ventanas"


def test_crear_version_con_metodo_explicito_no_hereda(client: TestClient):
    proyecto = _crear_proyecto(
        client, name="version-metodo-propio", fairness_interval_method="ventanas"
    )
    resp = client.post(
        f"/api/projects/{proyecto['id']}/versions",
        json={
            "label": "v2",
            "actor": "miguel",
            "motivo": "nueva versión",
            "fairness_interval_method": "lote",
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["fairness_interval_method"] == "lote"


# --- Sim_logistic fuera de los dominios del simulador -----------------


def test_crear_version_sim_logistic_fuera_de_reuma_digestivo_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="version-sim-libre", domain="libre")
    resp = client.post(
        f"/api/projects/{proyecto['id']}/versions",
        json={
            "label": "v2",
            "model_kind": "sim_logistic",
            "actor": "miguel",
            "motivo": "modelo del simulador",
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == MENSAJE_SIM_LOGISTIC


def test_crear_version_sim_logistic_en_reuma_200(client: TestClient):
    proyecto = _crear_proyecto(client, name="version-sim-reuma", domain="reuma")
    resp = client.post(
        f"/api/projects/{proyecto['id']}/versions",
        json={
            "label": "v2",
            "model_kind": "sim_logistic",
            "actor": "miguel",
            "motivo": "modelo del simulador",
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text


# --- Aviso de línea base y congelar al activar -----------


def test_get_project_avisa_si_la_version_activa_no_tiene_linea_base(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="sin-linea-base")
    project_id = proyecto["id"]

    resp = client.get(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["aviso_linea_base"] == (
        "la versión activa no tiene línea base congelada: la deriva no se evalúa"
    )

    _congelar_con_batch(client, session, project_id, proyecto["active_version_id"])

    resp = client.get(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["aviso_linea_base"] is None


def test_activar_version_congela_linea_base_con_el_id_de_un_lote(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="activar-congela-lote")
    project_id = proyecto["id"]
    v1_id = proyecto["active_version_id"]

    resp = client.post(
        f"/api/projects/{project_id}/versions",
        json={"label": "v2", "actor": "miguel", "motivo": "nueva versión"},
        headers=actor_headers("miguel"),
    )
    v2_id = resp.json()["id"]

    batch = Batch(project_id=project_id, model_version_id=v2_id, seq=0, n_rows=5)
    session.add(batch)
    session.commit()
    session.refresh(batch)

    resp = client.post(
        f"/api/model-versions/{v2_id}/activate",
        json={"actor": "miguel", "motivo": "pasa a producción", "congelar_linea_base": batch.id},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_active"] is True
    assert body["baseline_batch_id"] == batch.id
    assert body["frozen_at"] is not None

    version_bd = session.get(ModelVersion, v2_id)
    assert version_bd is not None
    assert version_bd.baseline_batch_id == batch.id

    # activar sin congelar sigue funcionando (la API lo permite).
    resp = client.post(
        f"/api/model-versions/{v1_id}/activate",
        json={"actor": "miguel", "motivo": "vuelvo a v1"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["baseline_batch_id"] is None


def test_activar_version_congelar_linea_base_con_id_de_dataset(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="activar-congela-dataset")
    project_id = proyecto["id"]
    v1_id = proyecto["active_version_id"]

    dataset = Dataset(project_id=project_id, name="lote-origen.csv")
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    batch = Batch(
        project_id=project_id, model_version_id=v1_id, seq=0, n_rows=5, dataset_id=dataset.id
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)

    resp = client.post(
        f"/api/model-versions/{v1_id}/activate",
        json={
            "actor": "miguel",
            "motivo": "pasa a producción",
            "congelar_linea_base": dataset.id,
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["baseline_batch_id"] == batch.id


def test_activar_version_congelar_linea_base_id_invalido_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="activar-congela-invalido")
    resp = client.post(
        f"/api/model-versions/{proyecto['active_version_id']}/activate",
        json={"actor": "miguel", "motivo": "x", "congelar_linea_base": 999999},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422


def test_activar_version_con_baseline_ya_congelado_409_no_activa(
    client: TestClient, session: Session
):
    """Corrección: si la versión a activar ya tiene un baseline congelado,
    `congelar_linea_base` debe dar 409 sin llegar a activarla (antes se
    confirmaba la activación y solo después fallaba `freeze_baseline`,
    dejando la versión activada de verdad pese al 409)."""
    proyecto = _crear_proyecto(client, name="activar-ya-congelado")
    project_id = proyecto["id"]
    v1_id = proyecto["active_version_id"]
    _congelar_con_batch(client, session, project_id, v1_id)

    resp = client.post(
        f"/api/projects/{project_id}/versions",
        json={"label": "v2", "actor": "miguel", "motivo": "nueva versión"},
        headers=actor_headers("miguel"),
    )
    v2_id = resp.json()["id"]
    resp = client.post(
        f"/api/model-versions/{v2_id}/activate",
        json={"actor": "miguel", "motivo": "pasa a producción"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text

    otro_batch = Batch(project_id=project_id, model_version_id=v1_id, seq=1, n_rows=5)
    session.add(otro_batch)
    session.commit()
    session.refresh(otro_batch)

    resp = client.post(
        f"/api/model-versions/{v1_id}/activate",
        json={
            "actor": "miguel",
            "motivo": "vuelvo a v1 y recongelo",
            "congelar_linea_base": otro_batch.id,
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 409, resp.text

    session.expire_all()
    proyecto_bd = session.get(Project, project_id)
    assert proyecto_bd is not None
    assert proyecto_bd.active_version_id == v2_id

    v1_bd = session.get(ModelVersion, v1_id)
    v2_bd = session.get(ModelVersion, v2_id)
    assert v1_bd is not None and v2_bd is not None
    assert v1_bd.is_active is False
    assert v2_bd.is_active is True


# --- Origen/nota del umbral y propuesta de calibración ----------------


def test_patch_monitor_conserva_origen_y_nota_de_cada_umbral(client: TestClient):
    proyecto = _crear_proyecto(client, name="umbral-origen")
    monitores = client.get(f"/api/projects/{proyecto['id']}/monitors").json()["items"]
    fairness = next(m for m in monitores if m["type"] == "fairness")

    umbrales = {
        "thresholds": [
            {
                "metric_key": "disparate_impact",
                "kind": "lower_limit",
                "value": 0.8,
                "origen": "criterio_clinico",
                "nota": "criterio del comité clínico",
            }
        ]
    }
    resp = client.patch(
        f"/api/monitors/{fairness['id']}",
        json={"actor": "miguel", "motivo": "fijo el umbral", "thresholds": umbrales},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    thr = resp.json()["monitor"]["thresholds"]["thresholds"][0]
    assert thr["origen"] == "criterio_clinico"
    assert thr["nota"] == "criterio del comité clínico"

    # Se conserva tras un GET posterior (no es solo eco del PATCH).
    resp = client.get(f"/api/monitors/{fairness['id']}")
    thr = resp.json()["thresholds"]["thresholds"][0]
    assert thr["origen"] == "criterio_clinico"
    assert thr["nota"] == "criterio del comité clínico"


def test_thresholds_proposal_409_sin_linea_base(client: TestClient):
    proyecto = _crear_proyecto(client, name="propuesta-sin-linea-base")
    resp = client.get(f"/api/projects/{proyecto['id']}/thresholds/proposal")
    assert resp.status_code == 409


def test_thresholds_proposal_con_linea_base(client: TestClient, session: Session):
    """Parchea `core.calibration.proponer_umbrales` (lo implementa B en
    paralelo): D solo comprueba que la ruta combina la propuesta con el
    umbral actual y su origen."""
    proyecto = _crear_proyecto(client, name="propuesta-con-linea-base")
    project_id = proyecto["id"]
    batch = _congelar_con_batch(client, session, project_id, proyecto["active_version_id"])

    propuestas_falsas = [
        PropuestaUmbral(
            metric_key="disparate_impact",
            kind="lower_limit",
            value=0.82,
            valor_linea_base=0.95,
            motivo=None,
        )
    ]
    with mock.patch(
        "vigia.core.calibration.proponer_umbrales", return_value=propuestas_falsas
    ) as propone:
        resp = client.get(
            f"/api/projects/{project_id}/thresholds/proposal", params={"tamano_lote": 500}
        )
    assert resp.status_code == 200, resp.text
    assert propone.call_count == 2  # fairness y quality
    body = resp.json()
    assert body["baseline_batch_id"] == batch.id
    assert body["tamano_lote"] == 500
    fairness = next(m for m in body["monitors"] if m["monitor_type"] == "fairness")
    propuesta = fairness["propuestas"][0]
    assert propuesta["metric_key"] == "disparate_impact"
    assert propuesta["value"] == 0.82
    # Sin origen guardado: se enseña como "fabrica" con su aviso.
    assert propuesta["origen_actual"] == "fabrica"
    assert propuesta["aviso"] == "umbral de fábrica: no calibrado para este modelo"


# --- Sincronía de favorable_label al congelar la línea base ------------


def test_congelar_baseline_sincroniza_favorable_label_desde_el_dataset(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="sincronia-favorable")
    project_id = proyecto["id"]
    v1_id = proyecto["active_version_id"]
    assert proyecto["mapping_template_json"] is None

    dataset = Dataset(
        project_id=project_id,
        name="linea-base.csv",
        mapping_json={"favorable_label": 0, "feature_cols": ["edad"]},
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    batch = Batch(
        project_id=project_id, model_version_id=v1_id, seq=0, n_rows=5, dataset_id=dataset.id
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)

    resp = client.post(
        f"/api/model-versions/{v1_id}/baseline",
        json={"batch_id": batch.id, "actor": "miguel", "motivo": "primera línea base"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text

    resp = client.get(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mapping_template_json"]["favorable_label"] == 0
    assert body["favorable_label"] == 0

    evento = session.exec(
        select(Event).where(Event.action == "proyecto.favorable_sincronizado")
    ).one()
    assert evento.after_json["favorable_label"] == 0


def test_congelar_baseline_no_sincroniza_si_la_plantilla_ya_tiene_favorable(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(
        client, name="sincronia-no-pisa", mapping_template={"favorable_label": 1}
    )
    project_id = proyecto["id"]
    v1_id = proyecto["active_version_id"]

    dataset = Dataset(
        project_id=project_id, name="otro.csv", mapping_json={"favorable_label": 0}
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    batch = Batch(
        project_id=project_id, model_version_id=v1_id, seq=0, n_rows=5, dataset_id=dataset.id
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)

    resp = client.post(
        f"/api/model-versions/{v1_id}/baseline",
        json={"batch_id": batch.id, "actor": "miguel", "motivo": "línea base"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text

    resp = client.get(f"/api/projects/{project_id}")
    assert resp.json()["mapping_template_json"]["favorable_label"] == 1

    assert (
        session.exec(
            select(Event).where(Event.action == "proyecto.favorable_sincronizado")
        ).first()
        is None
    )
