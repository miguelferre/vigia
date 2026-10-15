"""Ciclo de vida del proyecto: el recorrido completo (crear, subir línea base,
mapear, ingerir, aplicar umbrales, evaluar, subir un lote, borrarlo)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import Alert, Batch, Evaluation, Event, ModelVersion

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo" / "escenario_1"


def _crear_proyecto(client: TestClient, name: str, **extra) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "reuma", "fairness_interval_method": "ventanas", **extra},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir(client: TestClient, project_id: int, filename: str, *, role: str) -> dict:
    resp = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": (filename, (DEMO_DIR / filename).read_bytes(), "application/json")},
        data={"kind": "combined", "role": role},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _mapear(client: TestClient, subida: dict) -> dict:
    resp = client.put(
        f"/api/datasets/{subida['dataset']['id']}/mapping",
        json={"mapping": subida["suggested_mapping"]},
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


def _evaluar(client: TestClient, batch_id: int) -> dict:
    resp = client.post(f"/api/batches/{batch_id}/evaluate", json={"trigger": "manual"})
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    return job["result"]


def _alertas(client: TestClient, project_id: int, **params) -> list[dict]:
    resp = client.get(f"/api/projects/{project_id}/alerts", params={"limit": 200, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _borrar_lote(client: TestClient, batch_id: int):
    return client.request(
        "DELETE",
        f"/api/batches/{batch_id}",
        params={"confirm": "true"},
        json={"actor": "miguel", "motivo": "lote equivocado"},
        headers=actor_headers("miguel"),
    )


def _linea_base_y_evento(client: TestClient, name: str) -> tuple[dict, dict, dict]:
    """Proyecto con la línea base ingerida (se congela sola) y el evento
    ingerido y evaluado: devuelve proyecto, resultado de la línea base y del evento."""
    proyecto = _crear_proyecto(client, name)
    base = _subir(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    _mapear(client, base)
    r_base = _ingerir(client, base["dataset"]["id"])
    evento = _subir(client, proyecto["id"], "02_evento_feedback.json", role="production")
    _mapear(client, evento)
    r_evento = _ingerir(client, evento["dataset"]["id"])
    _evaluar(client, r_evento["batch_id"])
    return proyecto, r_base, r_evento


# --- Línea base congelada al ingerir, sin evaluar ----------------


def test_ingerir_la_linea_base_la_congela_sola_y_no_la_evalua(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, "c10-1-congela")
    base = _subir(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    _mapear(client, base)
    # `evaluate=true` llega, pero la línea base no se evalúa.
    resultado = _ingerir(client, base["dataset"]["id"], evaluate=True)
    assert resultado["evaluated"] is False
    assert resultado["evaluate_motivo"].startswith("la línea base no se evalúa al ingerirla")
    assert resultado["baseline_congelado_automatico"] is True

    version = session.get(ModelVersion, proyecto["active_version_id"])
    session.refresh(version)
    assert version.frozen_at is not None
    assert version.baseline_batch_id == resultado["batch_id"]
    assert session.exec(select(Evaluation).where(Evaluation.batch_id == resultado["batch_id"])).first() is None

    evento = session.exec(
        select(Event).where(Event.action == "version.baseline_congelado", Event.project_id == proyecto["id"])
    ).one()
    assert evento.actor_kind == "sistema"
    assert evento.after_json["automatico"] is True
    assert "automático" in (evento.motivo or "")
    assert not _alertas(client, proyecto["id"])


def test_la_propuesta_de_umbrales_funciona_desde_que_esta_congelada(client: TestClient):
    proyecto = _crear_proyecto(client, "c10-2-propuesta")
    base = _subir(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    _mapear(client, base)
    sin_base = client.get(f"/api/projects/{proyecto['id']}/thresholds/proposal")
    assert sin_base.status_code == 409
    _ingerir(client, base["dataset"]["id"])
    con_base = client.get(f"/api/projects/{proyecto['id']}/thresholds/proposal")
    assert con_base.status_code == 200, con_base.text
    assert con_base.json()["monitors"]


def test_una_segunda_linea_base_no_cambia_la_congelada_y_avisa(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client, "c10-1-segunda")
    primera = _subir(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    _mapear(client, primera)
    r1 = _ingerir(client, primera["dataset"]["id"])
    segunda = _subir(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    _mapear(client, segunda)
    r2 = _ingerir(client, segunda["dataset"]["id"])
    assert r2["baseline_congelado_automatico"] is False
    assert any("ya tiene una línea base congelada" in a for a in r2["avisos"])
    version = session.get(ModelVersion, proyecto["active_version_id"])
    session.refresh(version)
    assert version.baseline_batch_id == r1["batch_id"]


def test_evaluar_la_linea_base_a_mano_sigue_funcionando(client: TestClient):
    proyecto = _crear_proyecto(client, "c10-2-evalua-a-mano")
    base = _subir(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    _mapear(client, base)
    resultado = _ingerir(client, base["dataset"]["id"])
    _evaluar(client, resultado["batch_id"])


def test_un_lote_de_produccion_con_evaluate_true_si_se_evalua(client: TestClient):
    proyecto = _crear_proyecto(client, "c10-2-produccion")
    base = _subir(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    _mapear(client, base)
    _ingerir(client, base["dataset"]["id"])
    evento = _subir(client, proyecto["id"], "02_evento_feedback.json", role="production")
    _mapear(client, evento)
    resultado = _ingerir(client, evento["dataset"]["id"], evaluate=True)
    assert resultado["evaluated"] is True


# --- Origen y retirada de alertas ---------------------------------


def test_la_alerta_nace_con_su_lote_de_origen_y_el_historial_lo_cita(client: TestClient):
    proyecto, _base, evento = _linea_base_y_evento(client, "c10-5-origen")
    alertas = _alertas(client, proyecto["id"])
    assert alertas
    for a in alertas:
        assert a["origin_batch_id"] == evento["batch_id"]
        assert a["origin_batch_seq"] is not None
        detalle = client.get(f"/api/alerts/{a['id']}").json()
        assert detalle["history"][0]["batch_id"] == evento["batch_id"]


def test_la_alerta_conserva_su_origen_cuando_un_lote_posterior_la_actualiza(client: TestClient):
    proyecto, _base, evento = _linea_base_y_evento(client, "c10-5-origen-estable")
    otro = _subir(client, proyecto["id"], "02_evento_feedback.json", role="production")
    _mapear(client, otro)
    r_otro = _ingerir(client, otro["dataset"]["id"])
    _evaluar(client, r_otro["batch_id"])
    for a in _alertas(client, proyecto["id"]):
        assert a["origin_batch_id"] == evento["batch_id"]
        assert a["batch_id"] == r_otro["batch_id"]
        detalle = client.get(f"/api/alerts/{a['id']}").json()
        assert detalle["history"][-1]["batch_id"] == r_otro["batch_id"]


def test_borrar_el_lote_retira_las_alertas_que_nacieron_en_el(client: TestClient, session: Session):
    proyecto, _base, evento = _linea_base_y_evento(client, "c10-3-retira")
    antes = _alertas(client, proyecto["id"])
    assert antes
    lote_seq = session.exec(select(Batch).where(Batch.id == evento["batch_id"])).one().seq
    resp = _borrar_lote(client, evento["batch_id"])
    assert resp.status_code == 204, resp.text

    # Fuera de la lista por defecto, en la de `status=retirada`.
    assert _alertas(client, proyecto["id"]) == []
    retiradas = _alertas(client, proyecto["id"], status="retirada")
    assert {a["id"] for a in retiradas} == {a["id"] for a in antes}
    for a in retiradas:
        assert a["status"] == "retirada"
        assert a["retired_reason"] == f"lote {lote_seq} borrado"
        assert a["origin_batch_id"] == evento["batch_id"]
        assert a["origin_batch_seq"] is None  # el lote ya no existe
        detalle = client.get(f"/api/alerts/{a['id']}").json()
        assert detalle["history"][-1]["to"] == "retirada"
        assert detalle["history"][-1]["motivo"] == a["retired_reason"]
        # Las entradas que citaban su evaluación salen marcadas como borradas.
        marcadas = [h for h in detalle["history"] if h["evaluacion_borrada"]]
        assert marcadas and all(h["batch_id"] == evento["batch_id"] for h in marcadas)
    eventos = session.exec(select(Event).where(Event.action == "alerta.retirada")).all()
    assert len(eventos) == len(antes)
    assert "lote" in eventos[0].motivo and "borrado" in eventos[0].motivo


def test_la_alerta_retirada_sale_de_recuentos_y_da_409_en_las_acciones(client: TestClient):
    proyecto, _base, evento = _linea_base_y_evento(client, "c10-3-recuentos")
    alerta_id = _alertas(client, proyecto["id"])[0]["id"]
    abiertas_antes = client.get(f"/api/projects/{proyecto['id']}").json()["counts"]["alerts_open"]
    assert abiertas_antes > 0
    assert _borrar_lote(client, evento["batch_id"]).status_code == 204
    assert client.get(f"/api/projects/{proyecto['id']}").json()["counts"]["alerts_open"] == 0
    # La retirada tampoco cuenta en la rejilla ni en la serie de alertas.
    resumen = next(
        p for p in client.get("/api/projects", params={"summary": True}).json()["items"]
        if p["id"] == proyecto["id"]
    )["summary"]
    assert sum(resumen["alerts_open_by_severity"].values()) == 0
    serie = client.get(
        f"/api/projects/{proyecto['id']}/alerts/series", params={"granularity": "batch"}
    )
    assert serie.status_code == 200, serie.text
    assert sum(serie.json()["cross_unbatched"].values()) == 0


    cuerpo = {"actor": "miguel", "motivo": "prueba"}
    for ruta, extra in (
        ("acknowledge", {}),
        ("investigate", {"hallazgos": "sin hallazgos"}),
        ("close", {}),
        ("decide", {"acciones": [{"key": "seguir_vigilando"}]}),
        ("actions", {"action": "nota"}),
    ):
        resp = client.post(f"/api/alerts/{alerta_id}/{ruta}", json={**cuerpo, **extra})
        assert resp.status_code == 409, (ruta, resp.text)
    resp = client.put(
        f"/api/alerts/{alerta_id}/protocol",
        json={**cuerpo, "protocolo_md": "nuevo"},
    )
    assert resp.status_code == 409, resp.text


def test_borrar_un_lote_posterior_recoloca_la_ultima_evaluacion_de_las_demas(
    client: TestClient, session: Session
):
    proyecto, _base, evento = _linea_base_y_evento(client, "c10-3-recoloca")
    antes = {a["id"]: a for a in _alertas(client, proyecto["id"])}
    otro = _subir(client, proyecto["id"], "02_evento_feedback.json", role="production")
    _mapear(client, otro)
    r_otro = _ingerir(client, otro["dataset"]["id"])
    _evaluar(client, r_otro["batch_id"])
    assert all(a["batch_id"] == r_otro["batch_id"] for a in _alertas(client, proyecto["id"]))

    assert _borrar_lote(client, r_otro["batch_id"]).status_code == 204
    despues = _alertas(client, proyecto["id"])
    assert {a["id"] for a in despues} == set(antes)  # ninguna retirada
    for a in despues:
        assert a["status"] == antes[a["id"]]["status"]
        assert a["batch_id"] == evento["batch_id"]
    assert not _alertas(client, proyecto["id"], status="retirada")
    session.expire_all()
    for fila in session.exec(select(Alert).where(Alert.project_id == proyecto["id"])).all():
        assert session.get(Evaluation, fila.last_evaluation_id) is not None


def test_una_alerta_nueva_tras_retirar_no_reabre_la_retirada(client: TestClient):
    proyecto, _base, evento = _linea_base_y_evento(client, "c10-3-no-reabre")
    ids_viejos = {a["id"] for a in _alertas(client, proyecto["id"])}
    assert _borrar_lote(client, evento["batch_id"]).status_code == 204
    nuevo = _subir(client, proyecto["id"], "02_evento_feedback.json", role="production")
    _mapear(client, nuevo)
    r_nuevo = _ingerir(client, nuevo["dataset"]["id"])
    _evaluar(client, r_nuevo["batch_id"])
    activas = _alertas(client, proyecto["id"])
    assert activas
    assert not ({a["id"] for a in activas} & ids_viejos)
    assert {a["id"] for a in _alertas(client, proyecto["id"], status="retirada")} == ids_viejos
    assert all(a["origin_batch_id"] == r_nuevo["batch_id"] for a in activas)


# --- recorrido completo ----------------------------------------------------


def test_recorrido_crear_linea_base_umbrales_evaluar_lote_y_borrarlo(client: TestClient):
    proyecto = _crear_proyecto(client, "u1-recorrido")
    pid = proyecto["id"]

    # Subir la línea base, mapearla e ingerirla: se congela, no se evalúa.
    base = _subir(client, pid, "01_baseline_feedback.json", role="baseline")
    _mapear(client, base)
    r_base = _ingerir(client, base["dataset"]["id"], evaluate=True)
    assert r_base["evaluated"] is False and r_base["baseline_congelado_automatico"] is True
    assert client.get(f"/api/projects/{pid}/thresholds/proposal").status_code == 200

    # Aplicar umbrales (sin cambios de valor) y evaluar la línea base a mano.
    calidad = next(m for m in client.get(f"/api/projects/{pid}").json()["monitors"] if m["type"] == "quality")
    resp = client.patch(
        f"/api/monitors/{calidad['id']}",
        json={
            "actor": "miguel",
            "motivo": "umbrales del alta",
            "thresholds": {
                "thresholds": [
                    {"metric_key": "accuracy", "kind": "lower_limit", "value": 0.7, "origen": "criterio_clinico"}
                ]
            },
        },
    )
    assert resp.status_code == 200, resp.text
    _evaluar(client, r_base["batch_id"])
    assert _alertas(client, pid) == []

    # Subir un lote, evaluarlo y borrarlo.
    evento = _subir(client, pid, "02_evento_feedback.json", role="production")
    _mapear(client, evento)
    r_evento = _ingerir(client, evento["dataset"]["id"])
    _evaluar(client, r_evento["batch_id"])
    abiertas = _alertas(client, pid)
    assert abiertas
    assert _borrar_lote(client, r_evento["batch_id"]).status_code == 204
    assert _alertas(client, pid) == []
    assert {a["id"] for a in _alertas(client, pid, status="retirada")} == {a["id"] for a in abiertas}

    # Los ids no se reutilizan: el lote nuevo tiene id y evaluaciones nuevas.
    nuevo = _subir(client, pid, "02_evento_feedback.json", role="production")
    _mapear(client, nuevo)
    r_nuevo = _ingerir(client, nuevo["dataset"]["id"])
    assert r_nuevo["batch_id"] > r_evento["batch_id"]
    assert nuevo["dataset"]["id"] > evento["dataset"]["id"]
    _evaluar(client, r_nuevo["batch_id"])
    activas = _alertas(client, pid)
    assert activas
    assert all(a["id"] > max(x["id"] for x in abiertas) for a in activas)
    assert all(a["origin_batch_id"] == r_nuevo["batch_id"] for a in activas)


def test_los_ids_de_evaluacion_no_se_reutilizan_tras_borrar_el_ultimo_lote(
    client: TestClient, session: Session
):
    proyecto, _base, evento = _linea_base_y_evento(client, "c10-4-ids")
    ids_borrados = {
        e.id for e in session.exec(select(Evaluation).where(Evaluation.batch_id == evento["batch_id"])).all()
    }
    assert ids_borrados
    assert _borrar_lote(client, evento["batch_id"]).status_code == 204
    otro = _subir(client, proyecto["id"], "02_evento_feedback.json", role="production")
    _mapear(client, otro)
    r_otro = _ingerir(client, otro["dataset"]["id"])
    _evaluar(client, r_otro["batch_id"])
    session.expire_all()
    ids_nuevos = {
        e.id for e in session.exec(select(Evaluation).where(Evaluation.batch_id == r_otro["batch_id"])).all()
    }
    assert ids_nuevos and not (ids_nuevos & ids_borrados)
    assert min(ids_nuevos) > max(ids_borrados)


# --- Título vigente ------------------------------------------------------


def test_el_titulo_se_reescribe_con_el_ultimo_valor_y_el_umbral_vigente(client: TestClient):
    proyecto, _base, evento = _linea_base_y_evento(client, "c10-6-titulo")
    alerta = next(
        a for a in _alertas(client, proyecto["id"]) if a["metric_key"] == "false_negative_rate_difference"
    )
    assert "umbral <= 0,550" in alerta["title"]
    equidad = next(m for m in client.get(f"/api/projects/{proyecto['id']}").json()["monitors"] if m["type"] == "fairness")
    resp = client.patch(
        f"/api/monitors/{equidad['id']}",
        json={
            "actor": "miguel",
            "motivo": "más estricto",
            "thresholds": {
                "thresholds": [
                    {
                        "metric_key": "false_negative_rate_difference",
                        "kind": "upper_limit",
                        "value": 0.07,
                        "origen": "criterio_clinico",
                    }
                ]
            },
        },
    )
    assert resp.status_code == 200, resp.text
    # PATCH no toca títulos: se ajustan en la siguiente evaluación.
    sin_tocar = client.get(f"/api/alerts/{alerta['id']}").json()
    assert "umbral <= 0,550" in sin_tocar["title"]
    _evaluar(client, evento["batch_id"])
    tocada = client.get(f"/api/alerts/{alerta['id']}").json()
    assert "umbral <= 0,070" in tocada["title"]
    assert "umbral <= 0,550" not in tocada["title"]


def test_borrar_un_lote_recalcula_el_titulo_con_el_valor_y_el_umbral_de_la_evaluacion_anterior(
    client: TestClient,
):
    """La alerta recolocada tras borrar un lote no se queda con el umbral del lote borrado."""
    proyecto, _base, _evento = _linea_base_y_evento(client, "c10-3-titulo")
    alerta = next(
        a for a in _alertas(client, proyecto["id"]) if a["metric_key"] == "false_negative_rate_difference"
    )
    titulo_inicial = alerta["title"]
    assert "umbral <= 0,550" in titulo_inicial
    equidad = next(m for m in client.get(f"/api/projects/{proyecto['id']}").json()["monitors"] if m["type"] == "fairness")
    resp = client.patch(
        f"/api/monitors/{equidad['id']}",
        json={
            "actor": "miguel",
            "motivo": "más estricto",
            "thresholds": {
                "thresholds": [
                    {
                        "metric_key": "false_negative_rate_difference",
                        "kind": "upper_limit",
                        "value": 0.07,
                        "origen": "criterio_clinico",
                    }
                ]
            },
        },
    )
    assert resp.status_code == 200, resp.text
    otro = _subir(client, proyecto["id"], "02_evento_feedback.json", role="production")
    _mapear(client, otro)
    r_otro = _ingerir(client, otro["dataset"]["id"])
    _evaluar(client, r_otro["batch_id"])
    con_lote = client.get(f"/api/alerts/{alerta['id']}").json()
    assert "umbral <= 0,070" in con_lote["title"]

    assert _borrar_lote(client, r_otro["batch_id"]).status_code == 204
    despues = client.get(f"/api/alerts/{alerta['id']}").json()
    assert despues["status"] == alerta["status"]
    assert despues["title"] == titulo_inicial
    assert "umbral <= 0,070" not in despues["title"]


# --- Favorable validado --------------------------------------------------

_CSV_BINARIO = b"id,pred,prob,y,sexo\n1,0,0.2,0,F\n2,1,0.9,1,M\n3,1,0.7,0,F\n4,0,0.1,0,M\n"


def _mapeo_csv(**extra) -> dict:
    return {
        "prediction_col": "pred",
        "probability_col": "prob",
        "label_col": "y",
        "id_col": "id",
        "protected_attr_col": "sexo",
        "protected_kind": "categorical",
        "priv_groups": ["M"],
        "unpriv_groups": ["F"],
        **extra,
    }


def _subir_csv(client: TestClient, project_id: int, contenido: bytes) -> dict:
    resp = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": ("datos.csv", contenido, "text/csv")},
        data={"kind": "combined", "role": "production"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_favorable_que_no_esta_en_la_etiqueta_da_422_con_los_valores(client: TestClient):
    proyecto = _crear_proyecto(client, "c10-7-favorable-inexistente")
    dataset_id = _subir_csv(client, proyecto["id"], _CSV_BINARIO)["dataset"]["id"]
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": _mapeo_csv(favorable_label=-1)},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422, resp.text
    detalle = resp.json()["detail"]
    assert "-1" in detalle and "valores encontrados: 0, 1" in detalle


def test_favorable_valido_o_con_alias_pasa(client: TestClient):
    proyecto = _crear_proyecto(client, "c10-7-favorable-valido")
    dataset_id = _subir_csv(client, proyecto["id"], _CSV_BINARIO)["dataset"]["id"]
    for favorable in (1, 0, "sí"):
        resp = client.put(
            f"/api/datasets/{dataset_id}/mapping",
            json={"mapping": _mapeo_csv(favorable_label=favorable)},
            headers=actor_headers("miguel"),
        )
        assert resp.status_code == 200, (favorable, resp.text)


def test_favorable_texto_ausente_lista_hasta_diez_valores(client: TestClient):
    filas = "\n".join(f"{i},{i % 2},0.5,clase{i},F" for i in range(15))
    proyecto = _crear_proyecto(client, "c10-7-diez-valores")
    dataset_id = _subir_csv(client, proyecto["id"], ("id,pred,prob,y,sexo\n" + filas + "\n").encode())["dataset"]["id"]
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": _mapeo_csv(favorable_label="maligno")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422, resp.text
    detalle = resp.json()["detail"]
    assert "clase0" in detalle and "clase9" in detalle
    assert "clase10" not in detalle and "5 más" in detalle


def test_lote_solo_con_negativos_y_favorable_binario_no_da_422(client: TestClient):
    proyecto = _crear_proyecto(client, "c10-7-solo-negativos")
    contenido = b"id,pred,prob,y,sexo\n1,0,0.2,0,F\n2,0,0.1,0,M\n"
    dataset_id = _subir_csv(client, proyecto["id"], contenido)["dataset"]["id"]
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": _mapeo_csv(favorable_label=1)},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text


# --- Umbral de fábrica explícito -----------------------------------------


def test_los_umbrales_nunca_tocados_salen_con_origen_fabrica(client: TestClient):
    proyecto = _crear_proyecto(client, "c10-8-fabrica")
    detalle = client.get(f"/api/projects/{proyecto['id']}").json()
    for monitor in detalle["monitors"]:
        for umbral in (monitor["thresholds"] or {}).get("thresholds", []):
            assert umbral["origen"] == "fabrica", (monitor["type"], umbral)
    calidad = next(m for m in detalle["monitors"] if m["type"] == "quality")
    assert calidad["thresholds"]["thresholds"]
    directo = client.get(f"/api/monitors/{calidad['id']}").json()
    assert all(u["origen"] == "fabrica" for u in directo["thresholds"]["thresholds"])

    resp = client.patch(
        f"/api/monitors/{calidad['id']}",
        json={
            "actor": "miguel",
            "motivo": "criterio clínico",
            "thresholds": {
                "thresholds": [
                    {"metric_key": "accuracy", "kind": "lower_limit", "value": 0.7, "origen": "criterio_clinico"}
                ]
            },
        },
    )
    assert resp.status_code == 200, resp.text
    tocado = client.get(f"/api/monitors/{calidad['id']}").json()["thresholds"]["thresholds"]
    assert tocado[0]["origen"] == "criterio_clinico"


# --- El historial trae lote y `evaluacion_borrada` ------------------


def test_el_historial_trae_lote_y_no_marca_borrada_una_evaluacion_viva(client: TestClient, session: Session):
    proyecto, _base, evento = _linea_base_y_evento(client, "c10-4-hist-viva")
    seq = session.exec(select(Batch).where(Batch.id == evento["batch_id"])).one().seq
    for a in _alertas(client, proyecto["id"]):
        entrada = client.get(f"/api/alerts/{a['id']}").json()["history"][0]
        assert entrada["batch_id"] == evento["batch_id"]
        assert entrada["batch_seq"] == seq
        assert entrada["evaluacion_borrada"] is False


def test_una_entrada_antigua_sin_marcas_sale_borrada_si_su_evaluacion_ya_no_existe(
    client: TestClient, session: Session
):
    proyecto, _base, evento = _linea_base_y_evento(client, "c10-4-hist-antigua")
    alertas = _alertas(client, proyecto["id"])
    assert alertas
    # Historial de antes de este cambio: sin `batch_id` ni marcas; la evaluación
    # citada se borra por debajo (el lote va con sus evaluaciones).
    for fila in session.exec(select(Alert).where(Alert.project_id == proyecto["id"])).all():
        fila.history_json = [
            {k: v for k, v in e.items() if k not in ("batch_id", "batch_seq", "evaluacion_borrada")}
            for e in fila.history_json
        ]
        session.add(fila)
    session.commit()
    for ev in session.exec(select(Evaluation).where(Evaluation.batch_id == evento["batch_id"])).all():
        session.delete(ev)
    session.commit()
    for a in alertas:
        entrada = client.get(f"/api/alerts/{a['id']}").json()["history"][0]
        assert entrada["evaluacion_borrada"] is True
        assert entrada["batch_seq"] is None
