"""Ingesta y privacidad, vía API con `TestClient`."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import Batch, Dataset, Project

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo" / "escenario_1"


def _crear_proyecto(client: TestClient, name: str, *, store_features: bool = True) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "reuma", "store_features": store_features},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir(
    client: TestClient,
    project_id: int,
    *,
    filename: str,
    content: bytes,
    kind: str,
    role: str,
    content_type: str = "application/json",
) -> dict:
    resp = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": (filename, content, content_type)},
        data={"kind": kind, "role": role},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _mapear(client: TestClient, dataset_id: int, mapping: dict, decisions: dict) -> dict:
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": mapping, "privacy_decisions": decisions},
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


# --- subida y detección de formato ------------------------------------------


def test_subir_feedback_baseline_detecta_formato_sin_pseudonimizar(client: TestClient):
    """Vigía no pseudonimiza. `privacy_report` es la constante fija y la
    previsualización enseña los identificadores tal como llegan en el fichero."""
    proyecto = _crear_proyecto(client, "detecta-feedback")
    contenido = (DEMO_DIR / "01_baseline_feedback.json").read_bytes()
    body = _subir(
        client,
        proyecto["id"],
        filename="01_baseline_feedback.json",
        content=contenido,
        kind="feedback",
        role="baseline",
    )
    dataset = body["dataset"]
    assert dataset["format"] == "harness_feedback"
    assert dataset["n_rows"] == 450
    assert body["suggested_mapping"]["id_col"] == "Episode_Id"
    assert body["suggested_mapping"]["label_col"] == "Has_Referral_in_Window"

    assert body["privacy_report"] == {"aplicado": False, "motivo": "sin_pseudonimizacion"}

    preview = body["preview"]
    assert preview
    assert preview[0]["Patient_Id"] not in (None, "***")


def test_subir_payload_detecta_formato_harness_payload(client: TestClient):
    proyecto = _crear_proyecto(client, "detecta-payload")
    contenido = (DEMO_DIR / "01_baseline_payload.json").read_bytes()
    body = _subir(
        client,
        proyecto["id"],
        filename="01_baseline_payload.json",
        content=contenido,
        kind="payload",
        role="baseline",
    )
    assert body["dataset"]["format"] == "harness_payload"
    assert body["dataset"]["n_rows"] == 450
    # El test añade id_col al mapeo sugerido del payload para poder emparejar
    # el feedback ingerido después (HARNESS_PAYLOAD_MAPPING no lo trae).
    assert body["suggested_mapping"]["id_col"] == "Episode_Id"


def test_mapping_sin_decisiones_de_privacidad_200(client: TestClient):
    """Ya no se exige ninguna decisión de privacidad; `privacy_decisions`
    se ignora aunque llegue vacío o con contenido."""
    proyecto = _crear_proyecto(client, "mapping-sin-decisiones")
    contenido = (DEMO_DIR / "01_baseline_feedback.json").read_bytes()
    body = _subir(
        client,
        proyecto["id"],
        filename="01_baseline_feedback.json",
        content=contenido,
        kind="feedback",
        role="baseline",
    )
    dataset_id = body["dataset"]["id"]
    mapping = body["suggested_mapping"]
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": mapping, "privacy_decisions": {}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text


# --- ingesta sin pseudonimización -----------------------------------


def test_mapear_e_ingerir_feedback_da_450_registros_con_el_id_original(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, "ingesta-feedback")
    version_id = proyecto["active_version_id"]
    contenido = (DEMO_DIR / "01_baseline_feedback.json").read_bytes()
    body = _subir(
        client,
        proyecto["id"],
        filename="01_baseline_feedback.json",
        content=contenido,
        kind="feedback",
        role="baseline",
    )
    dataset_id = body["dataset"]["id"]
    mapping = body["suggested_mapping"]
    _mapear(client, dataset_id, mapping, {})

    resultado = _ingerir(client, dataset_id, model_version_id=version_id, mode="crear")
    assert resultado["n_rows"] == 450
    assert resultado["n_labeled"] > 0
    batch_id = resultado["batch_id"]
    assert batch_id is not None

    resp = client.get(f"/api/batches/{batch_id}/records", params={"limit": 500})
    assert resp.status_code == 200
    pagina = resp.json()
    assert pagina["total"] == 450

    proyecto_bd = session.get(Project, proyecto["id"])
    assert proyecto_bd is not None
    valores_originales = json.loads((DEMO_DIR / "01_baseline_feedback.json").read_bytes())
    campos = valores_originales["fields"]
    idx_episode = campos.index("Episode_Id")
    ids_originales = {str(fila[idx_episode]) for fila in valores_originales["values"]}

    ids_devueltos = {r["external_id"] for r in pagina["items"]}
    assert ids_devueltos == ids_originales  # external_id es el valor original


def test_records_no_exponen_id_original_ni_features_sin_pedirlo(client: TestClient):
    proyecto = _crear_proyecto(client, "sin-id-original")
    version_id = proyecto["active_version_id"]
    contenido = (DEMO_DIR / "01_baseline_feedback.json").read_bytes()
    body = _subir(
        client,
        proyecto["id"],
        filename="01_baseline_feedback.json",
        content=contenido,
        kind="feedback",
        role="baseline",
    )
    dataset_id = body["dataset"]["id"]
    _mapear(
        client,
        dataset_id,
        body["suggested_mapping"],
        {"Patient_Id": "hashear", "Episode_Id": "hashear"},
    )
    resultado = _ingerir(client, dataset_id, model_version_id=version_id, mode="crear")
    batch_id = resultado["batch_id"]

    sin_features = client.get(f"/api/batches/{batch_id}/records", params={"limit": 5}).json()
    assert "features" not in sin_features["items"][0]

    con_features = client.get(
        f"/api/batches/{batch_id}/records", params={"limit": 5, "with_features": "true"}
    ).json()
    assert "features" in con_features["items"][0]
    assert con_features["items"][0]["features"] is not None
    assert "Age" in con_features["items"][0]["features"]


def test_composition_cuadra_con_recuentos_del_lote(client: TestClient):
    proyecto = _crear_proyecto(client, "composicion")
    version_id = proyecto["active_version_id"]
    contenido = (DEMO_DIR / "01_baseline_feedback.json").read_bytes()
    body = _subir(
        client,
        proyecto["id"],
        filename="01_baseline_feedback.json",
        content=contenido,
        kind="feedback",
        role="baseline",
    )
    dataset_id = body["dataset"]["id"]
    _mapear(
        client,
        dataset_id,
        body["suggested_mapping"],
        {"Patient_Id": "hashear", "Episode_Id": "hashear"},
    )
    resultado = _ingerir(client, dataset_id, model_version_id=version_id, mode="crear")
    batch_id = resultado["batch_id"]

    composicion = client.get(f"/api/batches/{batch_id}/composition").json()
    assert composicion["total"]["n"] == 450
    assert sum(g["n"] for g in composicion["groups"]) == 450

    # Recuentos de favorables por grupo,
    # coherentes con las tasas ya existentes.
    for fila in composicion["groups"]:
        assert fila["pred_favorable_n"] / fila["n"] == fila["pred_favorable_rate"]
        if fila["n_labeled"]:
            assert fila["label_favorable_n"] is not None
            assert fila["label_favorable_n"] / fila["n_labeled"] == fila["label_favorable_rate"]
        else:
            assert fila["label_favorable_n"] is None
            assert fila["label_favorable_rate"] is None


# --- payload + feedback emparejados -----------------------------------------


def test_payload_luego_feedback_actualiza_450_etiquetas_y_n_unmatched_0(client: TestClient):
    proyecto = _crear_proyecto(client, "payload-feedback")
    version_id = proyecto["active_version_id"]

    payload_bytes = (DEMO_DIR / "01_baseline_payload.json").read_bytes()
    body_payload = _subir(
        client,
        proyecto["id"],
        filename="01_baseline_payload.json",
        content=payload_bytes,
        kind="payload",
        role="baseline",
    )
    dataset_payload_id = body_payload["dataset"]["id"]
    decisiones = {"Patient_Id": "hashear", "Episode_Id": "hashear"}
    _mapear(client, dataset_payload_id, body_payload["suggested_mapping"], decisiones)
    resultado_payload = _ingerir(client, dataset_payload_id, model_version_id=version_id)
    assert resultado_payload["n_rows"] == 450
    assert resultado_payload["n_labeled"] == 0  # el payload no trae etiqueta

    feedback_bytes = (DEMO_DIR / "01_baseline_feedback.json").read_bytes()
    body_feedback = _subir(
        client,
        proyecto["id"],
        filename="01_baseline_feedback.json",
        content=feedback_bytes,
        kind="feedback",
        role="baseline",
    )
    dataset_feedback_id = body_feedback["dataset"]["id"]
    _mapear(client, dataset_feedback_id, body_feedback["suggested_mapping"], decisiones)
    resultado_feedback = _ingerir(client, dataset_feedback_id, model_version_id=version_id)

    assert resultado_feedback["batch_id"] is None
    assert resultado_feedback["n_matched"] == 450
    assert resultado_feedback["n_unmatched"] == 0

    batch = client.get(f"/api/batches/{resultado_payload['batch_id']}").json()
    assert batch["n_labeled"] == 450


def test_feedback_con_ids_desconocidos_no_empareja_y_no_crea_registros(client: TestClient):
    proyecto = _crear_proyecto(client, "feedback-desconocido")
    version_id = proyecto["active_version_id"]

    payload_bytes = (DEMO_DIR / "01_baseline_payload.json").read_bytes()
    body_payload = _subir(
        client,
        proyecto["id"],
        filename="01_baseline_payload.json",
        content=payload_bytes,
        kind="payload",
        role="baseline",
    )
    decisiones = {"Patient_Id": "hashear", "Episode_Id": "hashear"}
    _mapear(client, body_payload["dataset"]["id"], body_payload["suggested_mapping"], decisiones)
    _ingerir(client, body_payload["dataset"]["id"], model_version_id=version_id)

    feedback = json.loads((DEMO_DIR / "01_baseline_feedback.json").read_bytes())
    idx_episode = feedback["fields"].index("Episode_Id")
    for fila in feedback["values"]:
        fila[idx_episode] = f"no-existe-{fila[idx_episode]}"
    feedback_bytes = json.dumps(feedback).encode("utf-8")

    body_feedback = _subir(
        client,
        proyecto["id"],
        filename="01_baseline_feedback_desconocido.json",
        content=feedback_bytes,
        kind="feedback",
        role="baseline",
    )
    _mapear(client, body_feedback["dataset"]["id"], body_feedback["suggested_mapping"], decisiones)
    resultado = _ingerir(client, body_feedback["dataset"]["id"], model_version_id=version_id)

    assert resultado["batch_id"] is None
    assert resultado["n_matched"] == 0
    assert resultado["n_unmatched"] == 450


# --- CSV con identificadores y descartar ------------------------------------


def test_csv_con_dni_y_patient_id_en_claro_ingiere_sin_decisiones(client: TestClient):
    """Una columna `dni` y una `patient_id`
    en claro no bloquean la subida ni el mapeo; no se detectan ni se descartan."""
    proyecto = _crear_proyecto(client, "csv-sin-pseudonimizar")
    version_id = proyecto["active_version_id"]
    csv = (
        b"prediction,label,dni,patient_id,Age\n"
        b"1,1,12345678Z,pac-0001,30\n"
        b"0,0,23456789X,pac-0002,45\n"
        b"1,0,34567890Y,pac-0003,50\n"
    )
    body = _subir(
        client,
        proyecto["id"],
        filename="pacientes.csv",
        content=csv,
        kind="combined",
        role="production",
        content_type="text/csv",
    )
    assert body["privacy_report"] == {"aplicado": False, "motivo": "sin_pseudonimizacion"}
    columna_dni = next(c for c in body["dataset"]["columns"] if c["name"] == "dni")
    assert columna_dni["sample"] == "12345678Z"

    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "patient_id",
        "feature_cols": ["Age"],
        "favorable_label": 1,
    }
    _mapear(client, body["dataset"]["id"], mapping, {})
    resultado = _ingerir(client, body["dataset"]["id"], model_version_id=version_id)
    assert resultado["batch_id"] is not None
    batch_id = resultado["batch_id"]

    con_features = client.get(
        f"/api/batches/{batch_id}/records", params={"with_features": "true"}
    ).json()
    registros = con_features["items"]
    assert set(registros[0]["features"]) == {"Age"}
    assert {r["external_id"] for r in registros} == {"pac-0001", "pac-0002", "pac-0003"}


def test_ingesta_combinada_termina_con_message_lote_ingerido(client: TestClient):
    """El trabajo de una ingesta `crear` deja `message == "lote ingerido"`,
    no el último "ingiriendo registros" del bucle por lotes de 1000 filas."""
    proyecto = _crear_proyecto(client, "combinado-message-final")
    version_id = proyecto["active_version_id"]
    csv = b"id,prediction,label,Age\n1,1,1,30\n2,0,0,45\n"
    body = _subir(
        client,
        proyecto["id"],
        filename="pacientes.csv",
        content=csv,
        kind="combined",
        role="production",
        content_type="text/csv",
    )
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "feature_cols": ["Age"],
        "favorable_label": 1,
    }
    _mapear(client, body["dataset"]["id"], mapping, {})
    resp = client.post(
        f"/api/datasets/{body['dataset']['id']}/ingest",
        json={"model_version_id": version_id, "evaluate": False},
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado"
    assert job["message"] == "lote ingerido"
    assert job["result"]["batch_id"] is not None


def test_store_features_false_deja_features_json_nulo(client: TestClient):
    proyecto = _crear_proyecto(client, "sin-features", store_features=False)
    version_id = proyecto["active_version_id"]
    csv = (
        b"id,prediction,label,Age\n"
        b"1,1,1,30\n"
        b"2,0,0,45\n"
    )
    body = _subir(
        client,
        proyecto["id"],
        filename="sin_features.csv",
        content=csv,
        kind="combined",
        role="production",
        content_type="text/csv",
    )
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "feature_cols": ["Age"],
        "favorable_label": 1,
    }
    _mapear(client, body["dataset"]["id"], mapping, {})
    resultado = _ingerir(client, body["dataset"]["id"], model_version_id=version_id)
    batch_id = resultado["batch_id"]

    con_features = client.get(
        f"/api/batches/{batch_id}/records", params={"with_features": "true"}
    ).json()
    assert con_features["items"][0]["features"] is None


# --- id de mapeo sin transformar y columnas sin enmascarar ----------


def test_id_col_generico_se_guarda_tal_cual(client: TestClient):
    """El id de mapeo ya no se hashea: `external_id` es el valor
    original tanto si el id parece genérico (columna `id`) como si no."""
    proyecto = _crear_proyecto(client, "id-generico")
    version_id = proyecto["active_version_id"]
    csv = (
        b"id,prediction,label,Age\n"
        b"paciente-0001,1,1,30\n"
        b"paciente-0002,0,0,45\n"
        b"paciente-0003,1,0,50\n"
    )
    body = _subir(
        client,
        proyecto["id"],
        filename="con_id.csv",
        content=csv,
        kind="combined",
        role="production",
        content_type="text/csv",
    )
    assert body["preview"][0]["id"] == "paciente-0001"
    columna_id = next(c for c in body["dataset"]["columns"] if c["name"] == "id")
    assert columna_id["sample"] == "paciente-0001"

    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "favorable_label": 1,
    }
    _mapear(client, body["dataset"]["id"], mapping, {})
    resultado = _ingerir(client, body["dataset"]["id"], model_version_id=version_id)
    batch_id = resultado["batch_id"]

    pagina = client.get(f"/api/batches/{batch_id}/records", params={"limit": 10}).json()
    ids_originales = {"paciente-0001", "paciente-0002", "paciente-0003"}
    ids_devueltos = {r["external_id"] for r in pagina["items"]}
    assert ids_devueltos == ids_originales


def test_columns_json_no_enmascara_ninguna_columna(client: TestClient):
    """`dataset.columns` (subida y `GET /datasets/{id}`) enseña la muestra real
    de cualquier columna, DNI incluida (sin enmascarado)."""
    proyecto = _crear_proyecto(client, "columns-sin-enmascarar")
    csv = (
        b"prediction,label,DNI,Age\n"
        b"1,1,12345678Z,30\n"
        b"0,0,23456789X,45\n"
    )
    body = _subir(
        client,
        proyecto["id"],
        filename="con_dni.csv",
        content=csv,
        kind="combined",
        role="production",
        content_type="text/csv",
    )
    columna_dni = next(c for c in body["dataset"]["columns"] if c["name"] == "DNI")
    assert columna_dni["sample"] == "12345678Z"

    resp = client.get(f"/api/datasets/{body['dataset']['id']}")
    assert resp.status_code == 200
    columna_dni_get = next(c for c in resp.json()["columns"] if c["name"] == "DNI")
    assert columna_dni_get["sample"] == "12345678Z"


# --- purga del fichero en bruto tras ingerir (privacidad) --


def test_ingesta_purga_fichero_en_bruto_y_el_privado_conserva_el_id_original(
    client: TestClient, session: Session, data_dir: Path
):
    """La purga del fichero en bruto tras ingerir sigue vigente; el id ya no se
    hashea, así que el `.privado.csv` conserva el `Episode_Id` original
    (consecuencia aceptada: el operador entrega datos ya desidentificados)."""
    proyecto = _crear_proyecto(client, "purga-feedback")
    version_id = proyecto["active_version_id"]
    contenido = (DEMO_DIR / "01_baseline_feedback.json").read_bytes()
    body = _subir(
        client,
        proyecto["id"],
        filename="01_baseline_feedback.json",
        content=contenido,
        kind="feedback",
        role="baseline",
    )
    dataset_id = body["dataset"]["id"]
    _mapear(client, dataset_id, body["suggested_mapping"], {})
    _ingerir(client, dataset_id, model_version_id=version_id)

    valores_originales = json.loads((DEMO_DIR / "01_baseline_feedback.json").read_bytes())
    idx_episode = valores_originales["fields"].index("Episode_Id")
    ids_originales = {str(fila[idx_episode]) for fila in valores_originales["values"]}

    uploads_dir = data_dir / "uploads"
    ruta_original = uploads_dir / str(proyecto["id"]) / f"{dataset_id}_01_baseline_feedback.json"
    assert not ruta_original.exists()

    dataset = session.get(Dataset, dataset_id)
    assert dataset is not None
    assert dataset.raw_purged is True
    ruta_privada = Path(dataset.file_path)
    assert ruta_privada.name.endswith(".privado.csv")
    assert ruta_privada.is_file()
    texto_privado = ruta_privada.read_text(encoding="utf-8")
    assert any(id_original in texto_privado for id_original in ids_originales)


def test_raw_purged_aparece_en_get_dataset_y_en_el_evento(client: TestClient):
    proyecto = _crear_proyecto(client, "raw-purged-visible")
    version_id = proyecto["active_version_id"]
    csv = b"id,prediction,label,Age\n1,1,1,30\n2,0,0,45\n"
    body = _subir(
        client,
        proyecto["id"],
        filename="d.csv",
        content=csv,
        kind="combined",
        role="production",
        content_type="text/csv",
    )
    dataset_id = body["dataset"]["id"]
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "feature_cols": ["Age"],
        "favorable_label": 1,
    }
    _mapear(client, dataset_id, mapping, {})
    resultado = _ingerir(client, dataset_id, model_version_id=version_id)
    batch_id = resultado["batch_id"]

    resp = client.get(f"/api/datasets/{dataset_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["raw_purged"] is True

    eventos = client.get(
        "/api/events", params={"object_type": "batch", "object_id": batch_id}
    ).json()["items"]
    evento = next(e for e in eventos if e["action"] == "batch.ingerido")
    assert evento["after"]["raw_purged"] is True


def _dataset_mapeado(client: TestClient, project_id: int, name: str) -> tuple[int, Path]:
    """Sube y mapea un CSV mínimo; devuelve el id del dataset y su fichero en bruto."""
    csv = b"id,prediction,label,Age\n1,1,1,30\n2,0,0,45\n"
    body = _subir(
        client,
        project_id,
        filename=name,
        content=csv,
        kind="combined",
        role="production",
        content_type="text/csv",
    )
    dataset_id = body["dataset"]["id"]
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "feature_cols": ["Age"],
        "favorable_label": 1,
    }
    _mapear(client, dataset_id, mapping, {})
    with Session(client.app.state.engine) as s:
        ruta = Path(s.get(Dataset, dataset_id).file_path)
    assert ruta.is_file()
    return dataset_id, ruta


def _forzar_fallo_de_ingesta(monkeypatch) -> None:
    from vigia.app.services import ingest as ingest_service

    def _falla(*args, **kwargs):
        raise RuntimeError("fallo forzado de prueba")

    monkeypatch.setattr(ingest_service, "_ingest_crear", _falla)


def test_ingesta_fallida_borra_el_fichero_en_bruto_y_deja_el_dataset_en_error(
    client: TestClient, session: Session, monkeypatch
):
    """Un fallo de ingesta no puede dejar el fichero original en disco:
    se borra, el dataset queda en `error` con `raw_purged` y sin `file_path`, y
    el job termina en error."""
    proyecto = _crear_proyecto(client, "purga-fallo")
    version_id = proyecto["active_version_id"]
    dataset_id, ruta = _dataset_mapeado(client, proyecto["id"], "e.csv")
    _forzar_fallo_de_ingesta(monkeypatch)

    resp = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"model_version_id": version_id, "evaluate": False},
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "error", job
    assert job["error"] == "error interno al ingerir el fichero: el registro del servidor tiene el detalle"

    assert not ruta.exists()
    dataset = session.get(Dataset, dataset_id)
    assert dataset is not None
    assert dataset.status == "error"
    assert dataset.raw_purged is True
    assert dataset.file_path == ""

    cuerpo = client.get(f"/api/datasets/{dataset_id}").json()
    assert cuerpo["status"] == "error"
    assert cuerpo["raw_purged"] is True

    eventos = client.get(
        "/api/events", params={"object_type": "dataset", "object_id": dataset_id}
    ).json()["items"]
    evento = next(e for e in eventos if e["action"] == "dataset.ingesta_fallida")
    assert evento["actor_kind"] == "modelo"
    assert evento["after"]["error"] == "error interno al ingerir el fichero: el registro del servidor tiene el detalle"
    assert evento["after"]["raw_purged"] is True

    # el fallo no deja lote a medias
    assert session.exec(select(Batch).where(Batch.dataset_id == dataset_id)).first() is None


def test_dataset_en_error_no_se_puede_reingerir_409(
    client: TestClient, monkeypatch
):
    """Sin fichero en bruto no hay reintento posible: 409 con el motivo."""
    proyecto = _crear_proyecto(client, "reingesta-bloqueada")
    version_id = proyecto["active_version_id"]
    dataset_id, _ruta = _dataset_mapeado(client, proyecto["id"], "f.csv")
    _forzar_fallo_de_ingesta(monkeypatch)

    primera = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"model_version_id": version_id, "evaluate": False},
    )
    assert primera.json()["status"] == "error"

    monkeypatch.undo()
    segunda = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"model_version_id": version_id, "evaluate": False},
    )
    assert segunda.status_code == 409, segunda.text
    assert "vuelve a subir el fichero" in segunda.json()["detail"]


def test_ingesta_cancelada_conserva_el_fichero_en_bruto(
    client: TestClient, session: Session, monkeypatch
):
    """La cancelación (`JobCancelled`) no borra nada: el dataset se puede reintentar."""
    from vigia.app.jobs import JobCancelled
    from vigia.app.services import ingest as ingest_service

    proyecto = _crear_proyecto(client, "cancelacion-conserva")
    version_id = proyecto["active_version_id"]
    dataset_id, ruta = _dataset_mapeado(client, proyecto["id"], "g.csv")

    def _cancela(*args, **kwargs):
        raise JobCancelled()

    monkeypatch.setattr(ingest_service, "_ingest_crear", _cancela)
    client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"model_version_id": version_id, "evaluate": False},
    )

    assert ruta.is_file()
    dataset = session.get(Dataset, dataset_id)
    assert dataset is not None
    assert dataset.raw_purged is False
    assert dataset.status == "mapeado"

    monkeypatch.undo()
    resultado = _ingerir(client, dataset_id, model_version_id=version_id)
    assert resultado["batch_id"] is not None


# --- borrado -----------------------------------------------------------


def test_delete_dataset_sin_confirm_400(client: TestClient):
    proyecto = _crear_proyecto(client, "borrar-dataset")
    csv = b"prediction,label,Age\n1,1,30\n"
    body = _subir(
        client,
        proyecto["id"],
        filename="a.csv",
        content=csv,
        kind="combined",
        role="production",
        content_type="text/csv",
    )
    resp = client.delete(
        f"/api/datasets/{body['dataset']['id']}", headers=actor_headers("miguel")
    )
    assert resp.status_code == 400


def test_delete_batch_con_confirm_y_actor(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, "borrar-batch")
    version_id = proyecto["active_version_id"]
    csv = b"id,prediction,label,Age\n1,1,1,30\n2,0,0,45\n"
    body = _subir(
        client,
        proyecto["id"],
        filename="b.csv",
        content=csv,
        kind="combined",
        role="production",
        content_type="text/csv",
    )
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "feature_cols": ["Age"],
        "favorable_label": 1,
    }
    _mapear(client, body["dataset"]["id"], mapping, {})
    resultado = _ingerir(client, body["dataset"]["id"], model_version_id=version_id)
    batch_id = resultado["batch_id"]

    resp = client.request(
        "DELETE",
        f"/api/batches/{batch_id}?confirm=true",
        json={"actor": "miguel", "motivo": "lote de prueba"},
    )
    assert resp.status_code == 204
    assert session.get(Batch, batch_id) is None


def test_delete_batch_respeta_actor_kind_de_la_cabecera(client: TestClient):
    """El evento de borrado usa el `actor_kind` de `X-Vigia-Actor-Kind`, no siempre humano."""
    proyecto = _crear_proyecto(client, "borrar-batch-agente")
    version_id = proyecto["active_version_id"]
    csv = b"id,prediction,label,Age\n1,1,1,30\n2,0,0,45\n"
    body = _subir(
        client,
        proyecto["id"],
        filename="c.csv",
        content=csv,
        kind="combined",
        role="production",
        content_type="text/csv",
    )
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "feature_cols": ["Age"],
        "favorable_label": 1,
    }
    _mapear(client, body["dataset"]["id"], mapping, {})
    resultado = _ingerir(client, body["dataset"]["id"], model_version_id=version_id)
    batch_id = resultado["batch_id"]

    token = client.get("/api/settings?reveal=true").json()["mcp_token"]
    resp = client.request(
        "DELETE",
        f"/api/batches/{batch_id}?confirm=true",
        json={"actor": "mcp-agente", "motivo": "lote de prueba"},
        headers=actor_headers("mcp-agente", kind="agente", token=token),
    )
    assert resp.status_code == 204

    eventos = client.get(
        "/api/events", params={"object_type": "batch", "object_id": batch_id}
    ).json()["items"]
    borrado = next(e for e in eventos if e["action"] == "batch.borrado")
    assert borrado["actor_kind"] == "agente"


# --- etiqueta de grupo ---------------------------------------


def test_group_label_por_rangos_en_composicion_y_registros(client: TestClient):
    """El mapeo del harness (`18-35` / `36-75`) etiqueta grupo a grupo y registro
    a registro, con `otros` para los que quedan fuera de ambos rangos."""
    proyecto = _crear_proyecto(client, "etiqueta-rangos")
    version_id = proyecto["active_version_id"]
    contenido = (DEMO_DIR / "01_baseline_feedback.json").read_bytes()
    body = _subir(
        client,
        proyecto["id"],
        filename="01_baseline_feedback.json",
        content=contenido,
        kind="feedback",
        role="baseline",
    )
    dataset_id = body["dataset"]["id"]
    _mapear(
        client,
        dataset_id,
        body["suggested_mapping"],
        {"Patient_Id": "hashear", "Episode_Id": "hashear"},
    )
    batch_id = _ingerir(client, dataset_id, model_version_id=version_id, mode="crear")["batch_id"]

    composicion = client.get(f"/api/batches/{batch_id}/composition").json()
    etiquetas = {g["group_code"]: g["group_label"] for g in composicion["groups"]}
    assert etiquetas[0] == "18-35"
    assert etiquetas[1] == "36-75"
    assert all(v == "otros" for k, v in etiquetas.items() if k not in (0, 1))

    registros = client.get(f"/api/batches/{batch_id}/records", params={"limit": 100}).json()
    assert registros["items"]
    for r in registros["items"]:
        assert r["group_label"] == etiquetas[r["group_code"]]


def test_group_label_categorico(client: TestClient):
    """Mapeo categórico: cada código toma el texto de su grupo; -1 es `otros`."""
    proyecto = _crear_proyecto(client, "etiqueta-categorica")
    version_id = proyecto["active_version_id"]
    csv = b"id,prediction,label,sexo,edad\n1,1,1,mujer,30\n2,0,0,hombre,45\n3,1,0,otro,60\n"
    body = _subir(
        client,
        proyecto["id"],
        filename="cat.csv",
        content=csv,
        kind="combined",
        role="production",
        content_type="text/csv",
    )
    dataset_id = body["dataset"]["id"]
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "protected_attr_col": "sexo",
        "protected_kind": "categorical",
        "unpriv_groups": ["mujer"],
        "priv_groups": ["hombre"],
        "feature_cols": ["edad"],
        "favorable_label": 1,
    }
    _mapear(client, dataset_id, mapping, {})
    batch_id = _ingerir(client, dataset_id, model_version_id=version_id)["batch_id"]

    composicion = client.get(f"/api/batches/{batch_id}/composition").json()
    etiquetas = {g["group_code"]: g["group_label"] for g in composicion["groups"]}
    assert etiquetas == {0: "mujer", 1: "hombre", -1: "otros"}

    registros = client.get(f"/api/batches/{batch_id}/records").json()["items"]
    por_valor = {r["protected_value"]: r["group_label"] for r in registros}
    assert por_valor == {"mujer": "mujer", "hombre": "hombre", "otro": "otros"}


def test_ingesta_con_version_de_otro_modelo_da_422(client: TestClient):
    proyecto = _crear_proyecto(client, "ingesta-version-propia")
    ajeno = _crear_proyecto(client, "ingesta-version-ajena")
    dataset_id, _ruta = _dataset_mapeado(client, proyecto["id"], "f.csv")
    version_ajena = ajeno["active_version_id"]

    resp = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"model_version_id": version_ajena, "evaluate": False},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == (
        f"la versión {version_ajena} es de otro modelo: elige una versión de este modelo"
    )
