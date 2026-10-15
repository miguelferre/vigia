"""Capa humana mínima: diario de uso y alertas cruzadas."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import Alert, Dataset, Evaluation, ModelVersion, Monitor, Project, UsageLog
from vigia.app.services.alerting import sync_candidates

USAGE_CSV = Path(__file__).resolve().parents[2] / "data" / "demo" / "usage_logs_demo.csv"
DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo" / "escenario_1"


def _crear_proyecto(client: TestClient, name: str = "reuma-humano") -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "reuma"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir_usage_log(client: TestClient, project_id: int) -> dict:
    with USAGE_CSV.open("rb") as f:
        resp = client.post(
            f"/api/projects/{project_id}/usage-logs/upload",
            files={"file": ("usage_logs_demo.csv", f, "text/csv")},
            headers=actor_headers("miguel"),
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_subir_usage_log_sin_subgroup_ni_clinician_ingiere_filas(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client)
    body = _subir_usage_log(client, proyecto["id"])
    assert body["n_rows"] > 0
    assert body["dataset_id"] is not None

    dataset = session.get(Dataset, body["dataset_id"])
    assert dataset is not None
    assert dataset.kind == "usage_log"
    assert dataset.status == "ingerido"
    assert Path(dataset.file_path).is_file()

    filas = session.exec(
        select(UsageLog).where(UsageLog.project_id == proyecto["id"])
    ).all()
    assert len(filas) == body["n_rows"]
    assert filas[0].human_decision in (0, 1)
    assert filas[0].subgroup is None
    assert filas[0].clinician_pseudonym is None


def test_cross_evaluate_calibra_la_primera_vez_y_vigila_despues(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="reuma-cross")
    _subir_usage_log(client, proyecto["id"])

    resp = client.post(f"/api/projects/{proyecto['id']}/cross/evaluate", headers=actor_headers())
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado"
    assert job["result"]["mode"] == "calibracion"

    version = session.get(ModelVersion, proyecto["active_version_id"])
    assert version is not None
    assert version.cross_reference_json is not None
    assert version.cross_reference_json.get("n") > 0

    evaluaciones = session.exec(
        select(Evaluation).where(Evaluation.project_id == proyecto["id"])
    ).all()
    assert len(evaluaciones) == 1
    assert evaluaciones[0].result_json["mode"] == "calibracion"

    resp = client.post(f"/api/projects/{proyecto['id']}/cross/evaluate", headers=actor_headers())
    assert resp.status_code == 200, resp.text
    job2 = resp.json()
    assert job2["result"]["mode"] == "vigilancia"

    evaluaciones = session.exec(
        select(Evaluation).where(Evaluation.project_id == proyecto["id"])
    ).all()
    assert len(evaluaciones) == 2


def test_export_usage_csv_empieza_por_cabecera_required_columns(client: TestClient):
    proyecto = _crear_proyecto(client, name="reuma-export")
    _subir_usage_log(client, proyecto["id"])

    resp = client.get(f"/api/projects/{proyecto['id']}/usage-logs/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    primera_linea = resp.text.splitlines()[0]
    assert primera_linea.startswith("date,human_decision,model_output,ground_truth")
    # al menos una fila de datos, con las etiquetas del harness (no enteros).
    segunda_linea = resp.text.splitlines()[1]
    assert "refer" in segunda_linea or "no-refer" in segunda_linea


def test_cross_alert_no_disparada_pasa_a_en_observacion(client: TestClient, session: Session):
    """Una alerta cruzada abierta cuya regla deja de disparar pasa a `en_observacion`."""
    proyecto = _crear_proyecto(client, name="reuma-en-observacion")
    project = session.get(Project, proyecto["id"])
    assert project is not None
    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == project.id, Monitor.type == "cross")
    ).first()
    assert monitor is not None
    version = session.get(ModelVersion, project.active_version_id)
    assert version is not None

    evaluacion_previa = Evaluation(
        monitor_id=monitor.id,
        project_id=project.id,
        model_version_id=version.id,
        trigger="manual",
        window_json={},
        config_snapshot_json={},
        app_version="test",
        core_version="test",
        status="ok",
        worst_state="alerta",
        result_json={},
    )
    session.add(evaluacion_previa)
    session.flush()

    alerta = Alert(
        project_id=project.id,
        monitor_type="cross",
        metric_key="cx6_override_z:A",
        group_code="A",
        severity="alta",
        status="abierta",
        title="CX-6 en A: 0.900 (0.050)",
        last_evaluation_id=evaluacion_previa.id,
        last_value=0.9,
        history_json=[{"ts": "t0", "from": None, "to": "abierta", "evaluation_id": evaluacion_previa.id}],
    )
    session.add(alerta)
    session.flush()

    evaluacion_actual = Evaluation(
        monitor_id=monitor.id,
        project_id=project.id,
        model_version_id=version.id,
        trigger="manual",
        window_json={},
        config_snapshot_json={},
        app_version="test",
        core_version="test",
        status="ok",
        worst_state="ok",
        result_json={},
    )
    session.add(evaluacion_actual)
    session.flush()

    # La regla no ha disparado en esta pasada: candidato en `ok`, sin alerta asociada.
    candidato = {"metric_key": "cx6_override_z:A", "group_code": "A", "state": "ok", "value": None}
    sync_candidates(session, project, monitor, evaluacion_actual, [candidato])
    session.flush()
    session.refresh(alerta)

    assert alerta.status == "en_observacion"
    assert alerta.observation_count == 1
    assert alerta.last_evaluation_id == evaluacion_actual.id
    assert alerta.history_json[-1]["to"] == "en_observacion"
    assert alerta.history_json[-1]["evaluation_id"] == evaluacion_actual.id

    # Una segunda pasada que tampoco dispara no debe reincrementar el contador:
    # la alerta ya está en observación.
    sync_candidates(session, project, monitor, evaluacion_actual, [candidato])
    session.refresh(alerta)
    assert alerta.observation_count == 1


# --- Fecha del diario de uso -----------------------------------


def test_subir_usage_log_con_fecha_dd_mm_aaaa_se_normaliza_a_iso(
    client: TestClient, session: Session
):
    """Fecha española `dd/mm/aaaa`: se normaliza a ISO en la subida; `GET /deskilling` no da 500 después."""
    proyecto = _crear_proyecto(client, name="reuma-fecha-dd-mm-aaaa")
    csv_bytes = (
        b"date,human_decision,model_output,ground_truth\n"
        b"05/01/2026,refer,refer,refer\n"
        b"12/01/2026,no-refer,no-refer,no-refer\n"
    )
    resp = client.post(
        f"/api/projects/{proyecto['id']}/usage-logs/upload",
        files={"file": ("f18_dd_mm_aaaa.csv", csv_bytes, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text

    filas = session.exec(
        select(UsageLog).where(UsageLog.project_id == proyecto["id"]).order_by(UsageLog.id)
    ).all()
    assert [f.date for f in filas] == ["2026-01-05", "2026-01-12"]

    resp_desk = client.get(f"/api/projects/{proyecto['id']}/deskilling")
    assert resp_desk.status_code == 200, resp_desk.text
    assert resp_desk.json()["filas_excluidas_fecha"] == 0


def test_subir_usage_log_con_fecha_dd_guion_mm_guion_aaaa_se_normaliza_a_iso(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, name="reuma-fecha-dd-guion-mm-guion-aaaa")
    csv_bytes = (
        b"date,human_decision,model_output,ground_truth\n"
        b"05-01-2026,refer,refer,refer\n"
    )
    resp = client.post(
        f"/api/projects/{proyecto['id']}/usage-logs/upload",
        files={"file": ("fecha_guiones.csv", csv_bytes, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    filas = session.exec(
        select(UsageLog).where(UsageLog.project_id == proyecto["id"])
    ).all()
    assert filas[0].date == "2026-01-05"


def test_subir_usage_log_con_fecha_no_reconocida_da_422_con_la_fila(client: TestClient):
    proyecto = _crear_proyecto(client, name="reuma-fecha-invalida")
    csv_bytes = (
        b"date,human_decision,model_output,ground_truth\n"
        b"2026-01-05,refer,refer,refer\n"
        b"2026/13/40,refer,refer,refer\n"
    )
    resp = client.post(
        f"/api/projects/{proyecto['id']}/usage-logs/upload",
        files={"file": ("fecha_mala.csv", csv_bytes, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422, resp.text
    assert "fila 2" in resp.text


def test_subir_usage_log_con_record_seq_no_numerico_da_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="reuma-record-seq-invalido")
    csv_bytes = (
        b"date,human_decision,model_output,ground_truth,record_seq\n"
        b"2026-01-05,refer,refer,refer,doce\n"
    )
    resp = client.post(
        f"/api/projects/{proyecto['id']}/usage-logs/upload",
        files={"file": ("malo.csv", csv_bytes, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422, resp.text


def test_subir_usage_log_con_record_seq_decimal_se_acepta(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, name="reuma-record-seq-decimal")
    csv_bytes = (
        b"date,human_decision,model_output,ground_truth,record_seq\n"
        b"2026-01-05,refer,refer,refer,12.0\n"
    )
    resp = client.post(
        f"/api/projects/{proyecto['id']}/usage-logs/upload",
        files={"file": ("bueno.csv", csv_bytes, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    filas = session.exec(
        select(UsageLog).where(UsageLog.project_id == proyecto["id"])
    ).all()
    assert filas[0].record_seq == 12


# --- fórmula de `model_alert_groups` (§9.1) ----------------------------------


def _subir_mapear_e_ingerir(client: TestClient, project_id: int, filename: str, *, role: str) -> dict:
    """Sube, mapea (hasheando todo lo marcado) e ingiere un fichero del harness."""
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
    resp = client.put(
        f"/api/datasets/{dataset['id']}/mapping",
        json={"mapping": body["suggested_mapping"]},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/api/datasets/{dataset['id']}/ingest", json={"evaluate": True})
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    return job["result"]


def test_model_alert_groups_vacio_sin_evaluacion_de_fairness(client: TestClient, session: Session):
    resp = client.post(
        "/api/projects",
        json={"name": "libre-sin-fairness", "domain": "libre"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    project = session.get(Project, resp.json()["id"])
    assert project is not None

    from vigia.app.services.human_layer import _model_alert_groups

    assert _model_alert_groups(session, project) == set()


def test_model_alert_groups_formula_18_35_sin_depender_del_dominio(client: TestClient, session: Session):
    """§9.1: con una evaluación de fairness en alerta el conjunto es `{"18-35"}`, sin
    referencia al dominio del proyecto (aquí `libre`, no `reuma`)."""
    resp = client.post(
        "/api/projects",
        json={"name": "libre-con-fairness", "domain": "libre"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    proyecto = resp.json()
    project = session.get(Project, proyecto["id"])
    assert project is not None

    _subir_mapear_e_ingerir(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    # Ingerir la línea base ya la congela; no hay POST /baseline que hacer.
    _subir_mapear_e_ingerir(client, proyecto["id"], "02_evento_feedback.json", role="production")

    session.expire_all()
    from vigia.app.services.human_layer import _model_alert_groups

    assert _model_alert_groups(session, project) == {"18-35"}


def test_cross_evaluate_sin_version_activa_409(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, name="reuma-sin-activa")
    from vigia.app.models import Project

    p = session.get(Project, proyecto["id"])
    assert p is not None
    p.active_version_id = None
    session.add(p)
    session.commit()

    resp = client.post(f"/api/projects/{proyecto['id']}/cross/evaluate", headers=actor_headers())
    assert resp.status_code == 409


# --- GET /projects/{id}/deskilling -------------------------------


def test_deskilling_sin_diario_da_sin_datos_con_motivo(client: TestClient):
    proyecto = _crear_proyecto(client, name="reuma-deskilling-vacio")
    resp = client.get(f"/api/projects/{proyecto['id']}/deskilling")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sin_datos"] is True
    assert body["motivo"] == "sin diario de uso"
    assert body["windows"] == []
    assert body["signal"] is None


def test_deskilling_con_diario_devuelve_windows_y_respeta_n_windows(client: TestClient):
    proyecto = _crear_proyecto(client, name="reuma-deskilling-con-diario")
    _subir_usage_log(client, proyecto["id"])

    resp = client.get(f"/api/projects/{proyecto['id']}/deskilling?n_windows=3")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sin_datos"] is False
    assert body["motivo"] is None
    assert body["n_windows"] == 3
    assert len(body["windows"]) == 3
    assert body["model_version_id"] == proyecto["active_version_id"]
    assert body["min_n"] == 30
    assert body["eps"] == 0.02
    assert body["package_version"]
    assert body["signal"]["fired"] in (True, False)
    assert "reason" in body["signal"]
    assert body["filas_excluidas_fecha"] == 0


def test_deskilling_con_version_de_otro_proyecto_da_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="reuma-deskilling-a")
    _subir_usage_log(client, proyecto["id"])
    otro = _crear_proyecto(client, name="reuma-deskilling-b")

    resp = client.get(
        f"/api/projects/{proyecto['id']}/deskilling",
        params={"model_version_id": otro["active_version_id"]},
    )
    assert resp.status_code == 422, resp.text


def test_deskilling_n_windows_fuera_de_rango_da_422(client: TestClient):
    proyecto = _crear_proyecto(client, name="reuma-deskilling-rango")
    _subir_usage_log(client, proyecto["id"])

    resp = client.get(f"/api/projects/{proyecto['id']}/deskilling?n_windows=13")
    assert resp.status_code == 422, resp.text


# --- Semántica de `refer` documentada --------------------------

_TEXTO_REFER_D155 = (
    "refer (o 1) es la decisión favorable para la persona afectada, en el "
    "mismo sentido que la etiqueta favorable del modelo"
)


def test_openapi_documenta_la_semantica_de_refer_en_la_subida(client: TestClient):
    """El texto exacto vive en
    TRES sitios del OpenAPI, cada uno comprobado por
    separado: la descripción de la operación (docstring de `upload_usage_log`,
    `routers/human.py`), la `description` del campo `file` del `requestBody`
    (`File(description=_REFER_DESCRIPTION)`) y la `description` del schema de
    respuesta (`UsageLogUploadResponse`, `schemas/human.py`). Antes de la
    corrección solo aparecía en el segundo: el docstring de la ruta lo
    parafraseaba con comillas invertidas alrededor de `refer`/`1` (rompía el
    texto exacto) y `UsageLogUploadResponse` no lo llevaba en ningún sitio;
    una comprobación `in` sobre el JSON entero seguía en verde con una sola
    coincidencia, así que aquí se localiza cada una por su ruta en el
    documento en vez de buscar en el texto completo."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200, resp.text
    spec = resp.json()

    operacion = spec["paths"]["/api/projects/{project_id}/usage-logs/upload"]["post"]
    assert _TEXTO_REFER_D155 in operacion["description"], "descripción de la operación"

    upload_body_schema = spec["components"]["schemas"][
        "Body_upload_usage_log_api_projects__project_id__usage_logs_upload_post"
    ]
    file_description = upload_body_schema["properties"]["file"]["description"]
    assert _TEXTO_REFER_D155 in file_description, "description del campo file"

    response_schema = spec["components"]["schemas"]["UsageLogUploadResponse"]
    assert _TEXTO_REFER_D155 in response_schema["description"], "schema de respuesta"
