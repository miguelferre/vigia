"""Reproductor de demo, laboratorio y explicabilidad."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import (
    Batch,
    Dataset,
    DemoRun,
    Event,
    Explanation,
    ModelVersion,
    Project,
    UsageLog,
)
from vigia.core.engine import run_scenario
from vigia.core.schema import State


def _crear_run(
    client: TestClient, scenario_key: str, *, source: str = "canned", with_human: bool = False
) -> dict:
    resp = client.post(
        "/api/demo/runs",
        json={"scenario_key": scenario_key, "source": source, "with_human": with_human},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _play(client: TestClient, run_id: int) -> dict:
    resp = client.post(f"/api/demo/runs/{run_id}/play", headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    return job


def test_scenarios_listados_incluyen_los_tres_guiones(client: TestClient):
    resp = client.get("/api/demo/scenarios")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    claves = {s["key"] for s in body["items"]}
    assert claves == {"timeline_completo", "consejeria_regional", "caso_digestivo"}


def test_scenarios_incluyen_lab_params_por_fase(client: TestClient):
    """§3.4: `lab_params` por fase, con la misma inspección de firma que valida
    el laboratorio; `age_mean`/`age_std` ya registrados, `accuracy_target`
    sigue sin estarlo (hueco documentado, no en la firma del generador).
    Siete fases, `b2..b5` con el mismo generador que `b1`."""
    resp = client.get("/api/demo/scenarios")
    guiones = {s["key"]: s for s in resp.json()["items"]}
    fases = {f["key"]: f for f in guiones["caso_digestivo"]["phases"]}
    assert set(fases) == {"b1", "b2", "b3", "b4", "b5", "e1_evento", "e1_recovery"}
    lab_params_baseline = {
        "seed",
        "n_total",
        "frac_young",
        "age_mean",
        "age_std",
        "temperature",
    }
    for clave in ("b1", "b2", "b3", "b4", "b5"):
        assert set(fases[clave]["lab_params"]) == lab_params_baseline, clave
    assert set(fases["e1_evento"]["lab_params"]) == {
        "seed",
        "n_total",
        "frac_young",
        "bias_additive",
        "age_mean",
        "age_std",
        "temperature",
    }
    assert set(fases["e1_recovery"]["lab_params"]) == {"seed", "n_total", "frac_young"}
    assert "accuracy_target" not in fases["e1_evento"]["lab_params"]


def test_timeline_completo_reproduce_9_fases_iguales_al_motor_en_memoria(
    client: TestClient, session: Session
):
    run = _crear_run(client, "timeline_completo")
    job = _play(client, run["id"])
    run_final = job["result"]
    assert run_final["status"] == "terminada"
    resumenes = run_final["result"]
    assert len(resumenes) == 9

    for resumen in resumenes:
        assert resumen["matches_expected"], resumen
        assert all(resumen["matches_expected"].values()), resumen

    reports = run_scenario("timeline_completo")
    assert len(reports) == len(resumenes)
    for reporte, resumen in zip(reports, resumenes, strict=True):
        assert resumen["phase_key"] == reporte.phase_key
        estados_motor = {k: v.value for k, v in reporte.states.items()}
        # Las cinco baselines llevan explain_global=True
        # y las demás fases obtienen la explicación automática (explain_auto
        # por defecto), así que la API añade "explain" al estado de todas;
        # run_scenario en memoria no calcula explicabilidad (es de servicio,
        # no de motor: core/engine.py no la dispara nunca), así que esa clave
        # no aparece nunca en estados_motor.
        estados_api = dict(resumen["states"])
        assert "explain" in estados_api, resumen
        estados_api.pop("explain", None)
        assert estados_api == estados_motor

    project = session.get(Project, run["project_id"])
    assert project is not None
    assert project.is_demo is True

    batches = session.exec(
        select(Batch).where(Batch.project_id == project.id).order_by(Batch.seq)  # type: ignore[arg-type]
    ).all()
    assert len(batches) == 9
    e2_batches = [b for b in batches if b.phase_label in ("e2_evento", "e2_recovery")]
    assert len(e2_batches) == 2
    for b in e2_batches:
        assert b.orden_manipulado is True
        assert b.motivo_manipulacion

    v2 = session.exec(
        select(ModelVersion).where(ModelVersion.project_id == project.id, ModelVersion.label == "v2")
    ).first()
    assert v2 is not None
    assert v2.is_active is True
    assert v2.baseline_batch_id is not None
    assert v2.frozen_at is not None


def test_consejeria_regional_reproduce_6_fases(client: TestClient):
    run = _crear_run(client, "consejeria_regional")
    job = _play(client, run["id"])
    resumenes = job["result"]["result"]
    assert len(resumenes) == 6
    for resumen in resumenes:
        assert all(resumen["matches_expected"].values()), resumen


def test_play_deja_rastro_humano_de_solicitud_antes_de_las_fases_de_sistema(client: TestClient):
    """`play` registra un evento `humano` de solicitud antes de las fases,
    que van como `sistema`."""
    run = _crear_run(client, "consejeria_regional")
    _play(client, run["id"])

    eventos = client.get(
        "/api/events",
        params={"object_type": "demo_run", "object_id": run["id"], "limit": 500},
    ).json()["items"]
    acciones_humano = {e["action"] for e in eventos if e["actor_kind"] == "humano"}
    acciones_sistema = {e["action"] for e in eventos if e["actor_kind"] == "sistema"}
    assert "demo.avance_solicitado" in acciones_humano
    assert "demo.fase_reproducida" in acciones_sistema

    solicitud = next(e for e in eventos if e["action"] == "demo.avance_solicitado")
    assert solicitud["actor_id"] == "miguel"
    assert solicitud["after"]["solicitud"] == "play"
    assert solicitud["after"]["phase_key"]  # la primera fase del guion, todavía pendiente
    assert solicitud["titulo"] and "avance_solicitado" not in solicitud["titulo"]


def test_next_fase_a_fase_equivalente_a_play(client: TestClient):
    run_a = _crear_run(client, "timeline_completo", source="generate")
    job_a = _play(client, run_a["id"])
    resumenes_play = job_a["result"]["result"]

    run_b = _crear_run(client, "timeline_completo", source="generate")
    resumenes_next = []
    for _ in range(9):
        resp = client.post(f"/api/demo/runs/{run_b['id']}/next", headers=actor_headers("miguel"))
        assert resp.status_code == 200, resp.text
        job = resp.json()
        assert job["status"] == "terminado", job
        resumenes_next.append(job["result"])

    assert len(resumenes_next) == len(resumenes_play)
    for a, b in zip(resumenes_play, resumenes_next, strict=True):
        assert a["phase_key"] == b["phase_key"]
        assert a["states"] == b["states"]
        assert a["matches_expected"] == b["matches_expected"]


def test_reset_deja_el_proyecto_virgen(client: TestClient, session: Session):
    run = _crear_run(client, "timeline_completo")
    _play(client, run["id"])

    resp = client.post(
        f"/api/demo/runs/{run['id']}/reset",
        json={"actor": "miguel", "motivo": "reiniciar demo", "confirm": True},
    )
    assert resp.status_code == 200, resp.text
    run_reiniciado = resp.json()
    assert run_reiniciado["id"] == run["id"]
    assert run_reiniciado["current_phase"] == 0
    assert run_reiniciado["status"] == "lista"
    assert run_reiniciado["result"] == []

    project = session.get(Project, run["project_id"])
    assert project is not None
    batches = session.exec(select(Batch).where(Batch.project_id == project.id)).all()
    assert batches == []

    demo_runs = session.exec(select(DemoRun).where(DemoRun.project_id == project.id)).all()
    assert len(demo_runs) == 1
    assert demo_runs[0].id == run["id"]


def test_reset_respeta_actor_kind_de_la_cabecera(client: TestClient):
    """El evento `demo.reiniciada` usa el `actor_kind` de `X-Vigia-Actor-Kind`."""
    run = _crear_run(client, "timeline_completo")
    _play(client, run["id"])

    token = client.get("/api/settings?reveal=true").json()["mcp_token"]
    resp = client.post(
        f"/api/demo/runs/{run['id']}/reset",
        json={"actor": "mcp-agente", "motivo": "reiniciar demo", "confirm": True},
        headers=actor_headers("mcp-agente", kind="agente", token=token),
    )
    assert resp.status_code == 200, resp.text
    run_reiniciado = resp.json()

    eventos = client.get(
        "/api/events", params={"object_type": "demo_run", "object_id": run_reiniciado["id"]}
    ).json()["items"]
    reiniciada = next(e for e in eventos if e["action"] == "demo.reiniciada")
    assert reiniciada["actor_kind"] == "agente"


def test_reset_sin_confirm_da_400(client: TestClient):
    run = _crear_run(client, "timeline_completo")
    resp = client.post(
        f"/api/demo/runs/{run['id']}/reset",
        json={"actor": "miguel", "motivo": "reiniciar demo"},
    )
    assert resp.status_code == 400


def test_with_human_produce_usage_log_y_evaluacion_cross_por_fase(
    client: TestClient, session: Session
):
    run = _crear_run(client, "timeline_completo", with_human=True)
    job = _play(client, run["id"])
    resumenes = job["result"]["result"]
    assert len(resumenes) == 9
    for resumen in resumenes:
        assert "cross_alerts" in resumen

    project = session.get(Project, run["project_id"])
    assert project is not None
    usage_rows = session.exec(select(UsageLog).where(UsageLog.project_id == project.id)).all()
    assert len(usage_rows) > 0

    reports = run_scenario("timeline_completo", with_human=True, human_seed=0)
    assert reports[0].cross is not None
    assert reports[0].cross.mode == "calibracion"
    e2_recovery = next(r for r in reports if r.phase_key == "e2_recovery")
    assert e2_recovery.cross is not None
    assert e2_recovery.cross.mode == "calibracion"


def _cross_evaluations(client: TestClient, project_id: int) -> list[dict]:
    """Evaluaciones `cross` del proyecto en orden de creación: exactamente una por fase.
    El reproductor evalúa el lote con `with_cross=False` e inserta
    el diario de uso de la fase antes de lanzar las cruzadas, así que no hay evaluación
    espuria sobre el uso acumulado de la fase anterior.
    """
    resp = client.get(f"/api/projects/{project_id}/evaluations", params={"monitor_type": "cross"})
    assert resp.status_code == 200, resp.text
    items = sorted(resp.json()["items"], key=lambda e: e["id"])
    detalles = []
    for it in items:
        r = client.get(f"/api/evaluations/{it['id']}")
        assert r.status_code == 200, r.text
        detalles.append(r.json())
    return detalles


def _valores_por_prefijo(measurements: list[dict], prefijo: str) -> dict[str | None, float | None]:
    return {m["group_code"]: m["value"] for m in measurements if m["metric_key"].startswith(prefijo)}


def _valor_metrica(measurements: list[dict], metric_key: str) -> float | None:
    for m in measurements:
        if m["metric_key"] == metric_key:
            return m["value"]
    return None


@pytest.mark.parametrize("scenario_key", ["timeline_completo", "consejeria_regional"])
def test_cruzadas_del_reproductor_coinciden_con_run_scenario(client: TestClient, scenario_key: str):
    """Paridad de las cruzadas del reproductor (API) con `run_scenario` en memoria,
    misma semilla humana (0): por fase, el modo (`calibracion`/`vigilancia`), el
    conjunto de reglas con estado `alerta` (`rule`, `group`) y los valores z de
    `cx1_override_z`/`cx6_override_z` por grupo y `cx5_chi2_p` (tolerancia 1e-6)
    coinciden exactamente, y hay exactamente una evaluación cross por fase (§7.7).
    """
    run = _crear_run(client, scenario_key, with_human=True)
    job = _play(client, run["id"])
    fases_api = job["result"]["result"]

    cross_evals = _cross_evaluations(client, run["project_id"])
    assert len(cross_evals) == len(fases_api), (
        f"{len(cross_evals)} evaluaciones cross vs {len(fases_api)} fases"
    )

    reports = run_scenario(scenario_key, with_human=True, human_seed=0)
    assert len(reports) == len(fases_api)

    for fase_api, ce, reporte in zip(fases_api, cross_evals, reports, strict=True):
        cross_mem = reporte.cross
        assert cross_mem is not None, fase_api["phase_key"]
        assert fase_api["phase_key"] == reporte.phase_key

        assert ce["result"]["mode"] == cross_mem.mode, fase_api["phase_key"]

        reglas_api = {(a["rule"], a["group"]) for a in ce["result"]["alerts"]}
        reglas_mem = {(a.rule, a.group) for a in cross_mem.alerts}
        assert reglas_api == reglas_mem, fase_api["phase_key"]
        # el resumen de la fase en el run expone exactamente las mismas alertas
        assert fase_api["cross_alerts"] == ce["result"]["alerts"], fase_api["phase_key"]

        measurements_mem = [m.model_dump(mode="json") for m in cross_mem.measurements]

        for prefijo in ("cx1_override_z:", "cx6_override_z:"):
            valores_api = _valores_por_prefijo(ce["measurements"], prefijo)
            valores_mem = _valores_por_prefijo(measurements_mem, prefijo)
            assert valores_api.keys() == valores_mem.keys(), (fase_api["phase_key"], prefijo)
            for grupo, valor in valores_api.items():
                if valor is None:
                    assert valores_mem[grupo] is None, (fase_api["phase_key"], prefijo, grupo)
                else:
                    assert valores_mem[grupo] == pytest.approx(valor, abs=1e-6), (
                        fase_api["phase_key"],
                        prefijo,
                        grupo,
                    )

        p5_api = _valor_metrica(ce["measurements"], "cx5_chi2_p")
        p5_mem = _valor_metrica(measurements_mem, "cx5_chi2_p")
        if p5_api is None:
            assert p5_mem is None, fase_api["phase_key"]
        else:
            assert p5_mem == pytest.approx(p5_api, abs=1e-6), fase_api["phase_key"]


def test_batch_pertenece_a_fase_esperada_y_evento_activa_v2(client: TestClient, session: Session):
    run = _crear_run(client, "timeline_completo")
    _play(client, run["id"])

    project = session.get(Project, run["project_id"])
    assert project is not None
    from vigia.app.models import Event

    eventos = session.exec(
        select(Event).where(Event.project_id == project.id, Event.action == "version.activada")
    ).all()
    assert len(eventos) >= 1


def test_estados_fairness_e1_evento_marca_matches_expected(client: TestClient):
    run = _crear_run(client, "timeline_completo")
    job = _play(client, run["id"])
    resumenes = job["result"]["result"]
    e1_evento = next(r for r in resumenes if r["phase_key"] == "e1_evento")
    assert e1_evento["states"]["fairness"] in (State.alerta.value, State.inestable.value)
    assert e1_evento["matches_expected"]["fairness"] is True


def test_eventos_de_next_comparten_correlacion_y_job_id(client: TestClient, session: Session):
    """§4: todos los eventos de un job de demo comparten correlación (incluidos
    `dataset.subido`, `dataset.mapeado` y `version.baseline_congelado`, que los
    servicios de otros carriles no etiquetan por sí solos)."""
    run = _crear_run(client, "timeline_completo")
    resp = client.post(f"/api/demo/runs/{run['id']}/next", headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    correlation_id = job["correlation_id"]
    assert correlation_id

    from vigia.app.models import Event

    project_id = run["project_id"]
    eventos = session.exec(
        select(Event).where(Event.project_id == project_id).order_by(Event.id)
    ).all()
    acciones_esperadas = {
        "dataset.subido",
        "dataset.mapeado",
        "version.baseline_congelado",
        "batch.ingerido",
        "evaluacion.completada",
        "demo.fase_reproducida",
    }
    encontradas = {e.action for e in eventos if e.action in acciones_esperadas}
    assert encontradas == acciones_esperadas, encontradas

    sin_correlacion = [
        (e.action, e.correlation_id, e.job_id)
        for e in eventos
        if e.action in acciones_esperadas and (e.correlation_id != correlation_id or e.job_id != job["id"])
    ]
    assert sin_correlacion == []


def test_fase_con_explain_global_deja_explicacion_guardada(client: TestClient, session: Session):
    """`consejeria_regional` marca `explain_global` en sus
    cinco baselines; el reproductor dispara `explain_global` en esas fases. La
    fase restante no declara `explain_global`, pero con `explain_auto` activado
    por defecto obtiene igualmente su explicación automática (nunca dos
    explicaciones para el mismo lote: una u otra, no las dos)."""
    run = _crear_run(client, "consejeria_regional")
    job = _play(client, run["id"])
    resumenes = job["result"]["result"]
    assert len(resumenes) == 6

    baselines = [r for r in resumenes if r["phase_key"].startswith("b")]
    assert len(baselines) == 5
    assert all(r["explain_calculado"] is True for r in baselines)

    evento = next(r for r in resumenes if r["phase_key"] == "e1_evento")
    assert evento["explain_calculado"] is True

    explicaciones = session.exec(
        select(Explanation).where(Explanation.project_id == run["project_id"])
    ).all()
    assert len(explicaciones) == 6
    assert all(e.kind == "global_permutation" for e in explicaciones)
    assert all(e.available for e in explicaciones)


def _lab(
    client: TestClient,
    run_id: int,
    *,
    phase_key: str = "e1_evento",
    params: dict | None = None,
    seed: int | None = 1001,
    actor: str = "miguel",
    motivo: str | None = "calibrar el umbral de FNRD",
) -> dict:
    body: dict = {"phase_key": phase_key, "params": params if params is not None else {}, "actor": actor}
    if seed is not None:
        body["seed"] = seed
    if motivo is not None:
        body["motivo"] = motivo
    return client.post(f"/api/demo/runs/{run_id}/lab", json=body)


def test_lab_no_avanza_el_guion(client: TestClient):
    run = _crear_run(client, "timeline_completo", source="generate")
    resp = _lab(client, run["id"], params={"bias_additive": 1.5})
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "terminado", job
    assert job["result"]["phase_key"] == "e1_evento"
    assert job["result"]["params"]["bias_additive"] == 1.5

    run_tras_lab = client.get(f"/api/demo/runs/{run['id']}").json()
    assert run_tras_lab["current_phase"] == 0
    assert run_tras_lab["status"] == "lista"
    assert run_tras_lab["result"] == []


def test_lab_fase_desconocida_da_404(client: TestClient):
    run = _crear_run(client, "timeline_completo")
    resp = _lab(client, run["id"], phase_key="no_existe")
    assert resp.status_code == 404, resp.text


def test_lab_parametro_desconocido_da_422_con_el_nombre(client: TestClient):
    run = _crear_run(client, "timeline_completo")
    resp = _lab(client, run["id"], params={"parametro_inventado": 1})
    assert resp.status_code == 422, resp.text
    assert "parametro_inventado" in resp.text


def test_lab_sin_motivo_da_422(client: TestClient):
    run = _crear_run(client, "timeline_completo")
    resp = _lab(client, run["id"], motivo=None)
    assert resp.status_code == 422, resp.text


def test_lab_bias_additive_sube_fnrd(client: TestClient):
    """Caso de aceptación del checklist de demo: subir
    `bias_additive` sube el FNRD frente a la misma fase sin ese parámetro."""

    def _fnrd(bias: float) -> float:
        run = _crear_run(client, "timeline_completo", source="generate")
        resp = _lab(client, run["id"], params={"bias_additive": bias})
        assert resp.status_code == 200, resp.text
        job = resp.json()
        assert job["status"] == "terminado", job
        batch_id = job["result"]["batch_id"]
        evals = client.get(
            f"/api/projects/{run['project_id']}/evaluations",
            params={"batch_id": batch_id, "monitor_type": "fairness"},
        ).json()["items"]
        assert len(evals) == 1, evals
        detalle = client.get(f"/api/evaluations/{evals[0]['id']}").json()
        valor = _valor_metrica(detalle["measurements"], "false_negative_rate_difference")
        assert valor is not None
        return valor

    fnrd_con_sesgo = _fnrd(1.5)
    fnrd_sin_sesgo = _fnrd(0.0)
    assert fnrd_con_sesgo > fnrd_sin_sesgo


# --- POST /demo/runs con project_id ------------------


def _crear_proyecto(client: TestClient, name: str, *, model_kind: str = "sim_logistic") -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "digestivo", "model_kind": model_kind},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_monitores_por_defecto_coinciden_con_los_umbrales_del_guion(client: TestClient):
    """`create_project` no cambia para la demo atada ("los monitores se
    dejan como están"): sus umbrales por defecto son los que usa
    el guion de la demo (pasos 3, 4, 8, 9, 10, 11 y 13)."""
    proyecto = _crear_proyecto(client, "monitores-por-defecto")
    monitores = {m["type"]: m for m in proyecto["monitors"]}
    assert set(monitores) == {"fairness", "quality", "drift", "explain", "cross"}

    def _umbral(monitor_type: str, metric_key: str) -> float:
        umbrales = monitores[monitor_type]["thresholds"]["thresholds"]
        return next(u["value"] for u in umbrales if u["metric_key"] == metric_key)

    assert _umbral("fairness", "false_negative_rate_difference") == 0.55
    assert _umbral("fairness", "fairness_value") == 20.0
    assert _umbral("quality", "accuracy") == 0.80
    assert _umbral("drift", "confidence_drift_score") == 0.30
    assert _umbral("drift", "feature_drift_score") == 0.15


def test_create_run_con_project_id_ata_proyecto_sin_lotes_en_fase_0(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client, "digestivo-sin-lotes")
    resp = client.post(
        "/api/demo/runs",
        json={"scenario_key": "caso_digestivo", "project_id": proyecto["id"]},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert run["project_id"] == proyecto["id"]
    assert run["current_phase"] == 0

    proyecto_bd = session.get(Project, proyecto["id"])
    assert proyecto_bd is not None
    assert proyecto_bd.is_demo is True
    assert proyecto_bd.deployment_stage == "demo"
    version = session.get(ModelVersion, proyecto_bd.active_version_id)
    assert version is not None
    assert version.fairness_window_n == 200  # min_records de caso_digestivo, sin lotes previos

    # Sin lotes, `_attach_project` también fija los umbrales de
    # calidad del guion (antes solo lo hacía `_crear_proyecto_demo`).
    monitores = client.get(f"/api/projects/{proyecto['id']}").json()["monitors"]
    monitor_calidad = next(m for m in monitores if m["type"] == "quality")
    umbral_accuracy = next(
        u["value"]
        for u in monitor_calidad["thresholds"]["thresholds"]
        if u["metric_key"] == "accuracy"
    )
    assert umbral_accuracy == 0.75  # caso_digestivo, frente al 0.80 por defecto

    eventos = client.get(
        "/api/events", params={"object_type": "demo_run", "object_id": run["id"]}
    ).json()["items"]
    creada = next(e for e in eventos if e["action"] == "demo.run_creada")
    assert creada["after"]["project_id"] == proyecto["id"]
    assert creada["after"]["attached"] is True


def test_create_run_con_project_id_desconocido_da_404(client: TestClient):
    resp = client.post(
        "/api/demo/runs",
        json={"scenario_key": "caso_digestivo", "project_id": 999999},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 404, resp.text


def test_create_run_con_project_id_sin_modelo_simulado_da_422(client: TestClient):
    proyecto = _crear_proyecto(client, "digestivo-modelo-real", model_kind="external_files")
    resp = client.post(
        "/api/demo/runs",
        json={"scenario_key": "caso_digestivo", "project_id": proyecto["id"]},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422, resp.text
    assert "la demo necesita un modelo simulado" in resp.text


def test_create_run_con_project_id_reproduccion_ya_existente_da_409(client: TestClient):
    proyecto = _crear_proyecto(client, "digestivo-doble-run")
    primero = client.post(
        "/api/demo/runs",
        json={"scenario_key": "caso_digestivo", "project_id": proyecto["id"]},
        headers=actor_headers("miguel"),
    )
    assert primero.status_code == 200, primero.text
    segundo = client.post(
        "/api/demo/runs",
        json={"scenario_key": "caso_digestivo", "project_id": proyecto["id"]},
        headers=actor_headers("miguel"),
    )
    assert segundo.status_code == 409, segundo.text


def test_create_run_con_project_id_lote_baseline_sin_produccion_arranca_en_fase_1(
    client: TestClient, session: Session
):
    """El lote con papel `baseline` (el de su dataset) lo subió el
    usuario: la reproducción arranca en la fase 1, ese lote se etiqueta `b1`
    y `fairness_window_n` no se toca (la versión ya estaba configurada)."""
    proyecto = _crear_proyecto(client, "digestivo-baseline-manual")
    proyecto_bd = session.get(Project, proyecto["id"])
    assert proyecto_bd is not None
    version = session.get(ModelVersion, proyecto_bd.active_version_id)
    assert version is not None
    version.fairness_window_n = 55
    session.add(version)

    dataset = Dataset(project_id=proyecto["id"], name="línea base manual", kind="combined", role="baseline")
    session.add(dataset)
    session.flush()
    batch = Batch(
        project_id=proyecto["id"],
        dataset_id=dataset.id,
        model_version_id=version.id,
        seq=0,
        n_rows=10,
    )
    session.add(batch)
    session.commit()
    batch_id = batch.id
    version_id = version.id

    resp = client.post(
        "/api/demo/runs",
        json={"scenario_key": "caso_digestivo", "project_id": proyecto["id"]},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    # El atado ya no se queda en la fase 1 (solo b1 adoptado);
    # reproduce b2..b5 enlatados antes de responder.
    assert resp.json()["current_phase"] == 5

    session.expire_all()
    batch_recargado = session.get(Batch, batch_id)
    assert batch_recargado is not None
    assert batch_recargado.phase_label == "b1"
    version_recargada = session.get(ModelVersion, version_id)
    assert version_recargada is not None
    assert version_recargada.fairness_window_n == 55


# --- GET /demo/scenarios/{key}/files/{phase} (§3.3) ---------------------------


def test_scenario_file_b1_es_csv_combinado_reconocible_sin_intervencion(client: TestClient):
    resp = client.get("/api/demo/scenarios/caso_digestivo/files/b1")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    # Literal fijo por contrato: no depende de la fase pedida.
    assert 'filename="caso-digestivo-linea-base.csv"' in resp.headers["content-disposition"]

    filas = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(filas) == 450
    columnas = set(filas[0])
    assert {"id", "timestamp", "prediction", "probability", "label"} <= columnas
    # Las columnas clínicas viajan con su nombre original; el mapeo
    # automático las detectaría como atributo protegido sin grupos (rompería
    # el guardado), así que el formulario no usa ese mapeo sugerido para este
    # CSV: precarga `upload_mapping` (comprobado más abajo).
    assert "Age" in columnas
    assert "Sex" in columnas
    assert filas[0]["prediction"] in ("0", "1")
    assert filas[0]["label"] in ("0", "1")
    float(filas[0]["probability"])  # no lanza: es un escalar

    # El formulario precargado sube con `upload_mapping` (§3.3), no con el
    # mapeo sugerido: sin intervención manual, ingiere sin error y deja el
    # atributo protegido con sus grupos (18 a 35 frente a 36 a 75).
    guiones = client.get("/api/demo/scenarios").json()["items"]
    mapeo = next(s for s in guiones if s["key"] == "caso_digestivo")["upload_mapping"]
    assert mapeo["protected_attr_col"] == "Age"
    assert mapeo["unpriv_groups"] == [[18, 35]]
    assert mapeo["priv_groups"] == [[36, 75]]

    proyecto = client.post(
        "/api/projects",
        json={"name": "b1-mapeo-precargado", "domain": "digestivo", "model_kind": "sim_logistic"},
        headers=actor_headers("miguel"),
    ).json()
    subida = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("b1.csv", resp.content, "text/csv")},
        data={"kind": "combined", "role": "baseline"},
        headers=actor_headers("miguel"),
    )
    assert subida.status_code == 200, subida.text
    dataset_id = subida.json()["dataset"]["id"]

    guardado = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": mapeo},
        headers=actor_headers("miguel"),
    )
    assert guardado.status_code == 200, guardado.text
    assert guardado.json()["mapping"]["protected_attr_col"] == "Age"
    assert guardado.json()["mapping"]["unpriv_groups"] == [[18, 35]]

    ingesta = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"evaluate": True},
        headers=actor_headers("miguel"),
    )
    assert ingesta.status_code == 200, ingesta.text
    assert ingesta.json()["status"] == "terminado", ingesta.json()


def test_scenario_file_nombre_fijo_no_depende_del_guion(client: TestClient):
    """§3.3: el literal es fijo. `timeline_completo` reutiliza la misma fase
    `b1` (mismo enlatado que `caso_digestivo`, scenarios.py) y responde 200
    con el mismo nombre de fichero; no hay forma de distinguir el guion
    pedido por el `Content-Disposition`."""
    resp = client.get("/api/demo/scenarios/timeline_completo/files/b1")
    assert resp.status_code == 200, resp.text
    assert 'filename="caso-digestivo-linea-base.csv"' in resp.headers["content-disposition"]


def test_scenario_file_fase_desconocida_da_404(client: TestClient):
    resp = client.get("/api/demo/scenarios/caso_digestivo/files/no_existe")
    assert resp.status_code == 404, resp.text


def test_scenario_file_guion_desconocido_da_404(client: TestClient):
    resp = client.get("/api/demo/scenarios/no_existe/files/b1")
    assert resp.status_code == 404, resp.text


def test_scenario_file_cachea_por_clave_y_fase():
    from vigia.app.services import demo_files

    demo_files._combined_csv_cached.cache_clear()
    a = demo_files.combined_csv_bytes("caso_digestivo", "b1")
    b = demo_files.combined_csv_bytes("caso_digestivo", "b1")
    assert a == b
    assert demo_files._combined_csv_cached.cache_info().hits >= 1


# --- Extremo a extremo: línea base real + project_id (criterio de cierre 3) --


def test_e2e_linea_base_real_atada_con_project_id_reproduce_e1_evento(client: TestClient, session: Session):
    """Descarga el CSV de `b1`, lo sube como combinado/línea base con el mapeo
    precargado del formulario real (`upload_mapping`; no el mapeo
    sugerido genérico), ata la reproducción con `project_id` y comprueba que
    arranca en la fase 1 y que `next` reproduce `e1_evento` con
    `matches_expected` verdadero."""
    csv_resp = client.get("/api/demo/scenarios/caso_digestivo/files/b1")
    assert csv_resp.status_code == 200, csv_resp.text

    proyecto = _crear_proyecto(client, "digestivo-e2e-b1")
    project_id = proyecto["id"]

    subida = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": ("caso-digestivo-b1.csv", csv_resp.content, "text/csv")},
        data={"kind": "combined", "role": "baseline"},
        headers=actor_headers("miguel"),
    )
    assert subida.status_code == 200, subida.text
    cuerpo_subida = subida.json()
    dataset_id = cuerpo_subida["dataset"]["id"]
    # El mapeo sugerido genérico (`_suggest_mapping`) detecta `Age` por
    # nombre, pero sin rangos: guardarlo tal cual fallaría por el validador
    # de `ColumnMapping` (grupos vacíos con protected_attr_col fijado). El
    # formulario real no lo usa para este CSV, precarga `upload_mapping`.
    assert cuerpo_subida["suggested_mapping"]["protected_attr_col"] == "Age"
    assert cuerpo_subida["suggested_mapping"]["unpriv_groups"] == []
    sin_grupos = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": cuerpo_subida["suggested_mapping"]},
        headers=actor_headers("miguel"),
    )
    assert sin_grupos.status_code == 422, sin_grupos.text

    guiones = client.get("/api/demo/scenarios").json()["items"]
    mapeo_precargado = next(s for s in guiones if s["key"] == "caso_digestivo")["upload_mapping"]
    assert mapeo_precargado["prediction_col"] == "prediction"
    assert mapeo_precargado["label_col"] == "label"
    # Con intervención mínima (el usuario confirma lo precargado, no lo
    # adivina): el atributo protegido y sus grupos ya llegan declarados.
    assert mapeo_precargado["protected_attr_col"] == "Age"
    assert mapeo_precargado["unpriv_groups"] == [[18, 35]]
    assert mapeo_precargado["priv_groups"] == [[36, 75]]

    mapeo = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": mapeo_precargado},
        headers=actor_headers("miguel"),
    )
    assert mapeo.status_code == 200, mapeo.text

    ingesta = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"evaluate": True},
        headers=actor_headers("miguel"),
    )
    assert ingesta.status_code == 200, ingesta.text
    assert ingesta.json()["status"] == "terminado", ingesta.json()
    baseline_batch_id = ingesta.json()["result"]["batch_id"]

    # La ingesta de un dataset con rol `baseline` congela la línea base
    # sola (motivo automático); un POST /baseline posterior da 409.
    congelado = client.post(
        f"/api/model-versions/{proyecto['active_version_id']}/baseline",
        json={"batch_id": baseline_batch_id, "actor": "miguel", "motivo": "línea base (e2e)"},
        headers=actor_headers("miguel"),
    )
    assert congelado.status_code == 409, congelado.text

    atada = client.post(
        "/api/demo/runs",
        json={"scenario_key": "caso_digestivo", "project_id": project_id},
        headers=actor_headers("miguel"),
    )
    assert atada.status_code == 200, atada.text
    run = atada.json()
    assert run["project_id"] == project_id
    # El atado ya reproduce b2..b5 enlatados, no solo adopta b1.
    assert run["current_phase"] == 5
    assert len(run["result"]) == 5
    # La versión llegó ya congelada; el motivo del guion se conserva en el
    # evento de la fase 0 en vez de perderse.
    session.expire_all()
    motivos = [
        e.motivo
        for e in session.exec(select(Event).where(Event.action == "demo.fase_reproducida")).all()
        if e.motivo
    ]
    assert any("caso_digestivo" in m and "ya llegó congelada" in m for m in motivos), motivos

    siguiente = client.post(f"/api/demo/runs/{run['id']}/next", headers=actor_headers("miguel"))
    assert siguiente.status_code == 200, siguiente.text
    job = siguiente.json()
    assert job["status"] == "terminado", job
    resumen = job["result"]
    assert resumen["phase_key"] == "e1_evento"
    assert resumen["matches_expected"], resumen
    assert all(resumen["matches_expected"].values()), resumen

    # Cifras del guion de la demo: no solo el estado
    # grueso de `matches_expected`, los valores exactos reproducidos en vivo
    # (ingesta real, no `run_scenario` en memoria) sobre `caso_digestivo`.
    medidas: dict[str, float | None] = {}
    evaluaciones = client.get(
        f"/api/projects/{project_id}/evaluations", params={"batch_id": resumen["batch_id"]}
    )
    assert evaluaciones.status_code == 200, evaluaciones.text
    items_evaluacion = evaluaciones.json()["items"]
    assert items_evaluacion, "el lote de e1_evento no tiene evaluaciones"
    for item in items_evaluacion:
        detalle = client.get(f"/api/evaluations/{item['id']}")
        assert detalle.status_code == 200, detalle.text
        for medida in detalle.json()["measurements"]:
            medidas[medida["metric_key"]] = medida["value"]

    assert medidas["accuracy"] == pytest.approx(0.860, abs=0.001)
    assert medidas["false_negative_rate_difference"] == pytest.approx(0.631, abs=0.001)
    assert medidas["fairness_value"] == pytest.approx(19.50, abs=0.01)
    assert medidas["confidence_drift_score"] == pytest.approx(0.370, abs=0.001)
    # `feature_drift_score` (KS de la edad, paso 13): con `Age` intacta
    # y mapeada vía `upload_mapping` (protegida y como característica), la
    # línea base sube con sus propios valores de edad, así que el ranking de
    # deriva por característica reproduce el mismo máximo que el guion sin
    # atar (`test_caso_digestivo_reproduce_cifras_de_guion_demo_en_e1_evento`).
    assert medidas["feature_drift_score"] == pytest.approx(0.189, abs=5e-4)

    # Composición del paso 14: proporción de 18 a 35 años en línea base y en
    # el lote de casos nuevos, calculada sobre los mismos CSV que sirve
    # §3.3 (más directo que recorrer `group_code` del lote ingerido).
    def _pct_18_35(csv_bytes: bytes) -> float:
        filas_csv = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8"))))
        jovenes = sum(1 for f in filas_csv if 18 <= float(f["Age"]) <= 35)
        return 100 * jovenes / len(filas_csv)

    csv_evento = client.get("/api/demo/scenarios/caso_digestivo/files/e1_evento")
    assert csv_evento.status_code == 200, csv_evento.text
    assert _pct_18_35(csv_resp.content) == pytest.approx(14.9, abs=0.05)
    assert _pct_18_35(csv_evento.content) == pytest.approx(32.9, abs=0.05)


def _subir_linea_base_real(client: TestClient, project_id: int, *, evaluate: bool) -> int:
    """Sube el CSV de `b1` como combinado/línea base con `upload_mapping` y lo
    ingiere; devuelve el `batch_id`. No congela la línea base: eso lo hace el
    atado (`demo_adoptar`)."""
    csv_resp = client.get("/api/demo/scenarios/caso_digestivo/files/b1")
    assert csv_resp.status_code == 200, csv_resp.text
    subida = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": ("caso-digestivo-b1.csv", csv_resp.content, "text/csv")},
        data={"kind": "combined", "role": "baseline"},
        headers=actor_headers("miguel"),
    )
    assert subida.status_code == 200, subida.text
    dataset_id = subida.json()["dataset"]["id"]
    guiones = client.get("/api/demo/scenarios").json()["items"]
    mapeo = next(s for s in guiones if s["key"] == "caso_digestivo")["upload_mapping"]
    guardado = client.put(
        f"/api/datasets/{dataset_id}/mapping", json={"mapping": mapeo}, headers=actor_headers("miguel")
    )
    assert guardado.status_code == 200, guardado.text
    ingesta = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"evaluate": evaluate},
        headers=actor_headers("miguel"),
    )
    assert ingesta.status_code == 200, ingesta.text
    assert ingesta.json()["status"] == "terminado", ingesta.json()
    return ingesta.json()["result"]["batch_id"]


def test_atar_adopta_la_linea_base_del_usuario_como_fase_0(client: TestClient, session: Session):
    """Demo guiada, paso 2: el usuario sube la línea base sin evaluar y
    el atado completa lo que la fase 0 hace tras ingerir: congela la línea
    base, calcula la explicación global (`_B1.explain_global`), evalúa el lote
    ya con la línea base fijada (deriva `ok`, no `sin_datos`) y deja el
    resumen en `result[0]` con `phase_key="b1"`, como si la hubiera
    reproducido `next`. El atado también reproduce `b2..b5`
    enlatados (mismos datos que `b1`, así que salen los mismos estados) y deja
    `result[0..4]`; `current_phase` queda en 5. El umbral de exactitud
    del proyecto pasa a 0,75 antes de evaluar, así que `b1` (0,880) sale en
    `ok`, no en `aviso`. Después `next` reproduce `e1_evento` igual que en el
    E2E de arriba."""
    proyecto = _crear_proyecto(client, "digestivo-adoptar-b1")
    project_id = proyecto["id"]
    batch_id = _subir_linea_base_real(client, project_id, evaluate=False)

    atada = client.post(
        "/api/demo/runs",
        json={"scenario_key": "caso_digestivo", "project_id": project_id},
        headers=actor_headers("miguel"),
    )
    assert atada.status_code == 200, atada.text
    run = atada.json()
    assert run["current_phase"] == 5
    assert run["status"] == "en_curso"
    assert len(run["result"]) == 5
    resumen = run["result"][0]
    assert resumen["phase_key"] == "b1"
    assert resumen["batch_id"] == batch_id
    assert resumen["adoptado"] is True
    assert resumen["explain_calculado"] is True
    assert resumen["states"]["quality"] == "ok"
    assert resumen["states"]["drift"] == "ok"
    assert resumen["states"]["fairness"] == "ok"
    assert all(resumen["matches_expected"].values()), resumen

    assert [r["phase_key"] for r in run["result"]] == ["b1", "b2", "b3", "b4", "b5"]
    for r in run["result"][1:]:
        assert r.get("adoptado") is None  # solo b1 lleva la marca de adopción
        assert r["states"]["quality"] == "ok"
        assert r["states"]["drift"] == "ok"
        assert r["states"]["fairness"] == "ok"
        assert all(r["matches_expected"].values()), r

    session.expire_all()
    version = session.get(ModelVersion, proyecto["active_version_id"])
    assert version is not None
    assert version.baseline_batch_id == batch_id
    assert version.frozen_at is not None
    assert (
        session.exec(select(Explanation).where(Explanation.batch_id == batch_id)).first()
        is not None
    )

    monitores = client.get(f"/api/projects/{project_id}/monitors").json()["items"]
    calidad = next(m for m in monitores if m["type"] == "quality")
    umbrales = {t["metric_key"]: t["value"] for t in calidad["thresholds"]["thresholds"]}
    # Los cinco umbrales del guion, elegidos para que
    # las 13 métricas de calidad den `ok` en las siete fases de `caso_digestivo`.
    assert umbrales["accuracy"] == pytest.approx(0.75)
    assert umbrales["area_under_roc"] == pytest.approx(0.70)
    assert umbrales["true_positive_rate"] == pytest.approx(0.65)
    assert umbrales["recall"] == pytest.approx(0.65)
    assert umbrales["gini_coefficient"] == pytest.approx(0.50)
    eventos_monitor = client.get(
        "/api/events", params={"object_type": "monitor", "object_id": calidad["id"]}
    ).json()["items"]
    configurado = next(e for e in eventos_monitor if e["action"] == "monitor.configurado")
    assert "calidad en correcto" in (configurado["motivo"] or "")

    siguiente = client.post(f"/api/demo/runs/{run['id']}/next", headers=actor_headers("miguel"))
    assert siguiente.status_code == 200, siguiente.text
    evento = siguiente.json()["result"]
    assert evento["phase_key"] == "e1_evento"
    assert all(evento["matches_expected"].values()), evento
    # El agregado de calidad también queda en
    # correcto en e1_evento (antes "aviso" por AUC/recall/gini con sus
    # umbrales por defecto).
    assert evento["states"]["quality"] == "ok", evento
    detalle = client.get(f"/api/demo/runs/{run['id']}").json()
    assert [r["phase_key"] for r in detalle["result"]] == [
        "b1",
        "b2",
        "b3",
        "b4",
        "b5",
        "e1_evento",
    ]


def test_atar_con_linea_base_ingerida_con_evaluate_true_no_la_evalua_dos_veces(client: TestClient):
    """Aunque el usuario deje marcado «evaluar al terminar», la ingesta
    de la línea base ni la evalúa (queda congelada y sin evaluaciones); el
    atado la evalúa una sola vez, ya con el umbral de exactitud del guion
 y con la línea base congelada (la deriva ya no sale `sin_datos`).
    `b2..b5` se reproducen y evalúan con 0,75, así que salen en `ok`."""
    proyecto = _crear_proyecto(client, "digestivo-adoptar-evaluada")
    project_id = proyecto["id"]
    batch_id = _subir_linea_base_real(client, project_id, evaluate=True)
    antes = client.get(f"/api/projects/{project_id}/evaluations", params={"batch_id": batch_id})
    assert antes.json()["items"] == []

    atada = client.post(
        "/api/demo/runs",
        json={"scenario_key": "caso_digestivo", "project_id": project_id},
        headers=actor_headers("miguel"),
    )
    assert atada.status_code == 200, atada.text
    run = atada.json()
    assert run["current_phase"] == 5
    assert len(run["result"]) == 5
    resumen = run["result"][0]
    assert resumen["phase_key"] == "b1"
    assert resumen["states"]["drift"] != "sin_datos"
    despues = client.get(f"/api/projects/{project_id}/evaluations", params={"batch_id": batch_id})
    tipos = [e["monitor_type"] for e in despues.json()["items"]]
    assert tipos and len(tipos) == len(set(tipos))

    for r in run["result"][1:]:
        assert r["states"]["quality"] == "ok"
        assert all(r["matches_expected"].values()), r


def test_caso_digestivo_reproduce_cifras_de_guion_demo_en_e1_evento(client: TestClient):
    """Las cifras del guion de la demo (FNRD 0,631,
    DI 19,50, exactitud 0,860, confianza 0,370, KS 0,189) salen en `e1_evento`
    contra `b1`, reproducidas en vivo sobre `caso_digestivo` (ingesta real vía
    `play`, no `run_scenario` en memoria). Guion sin atar (`_crear_proyecto_demo`):
    a diferencia del E2E con `project_id` de arriba, `next` también ingiere
    `b1` con el mapeo del harness, así que `Age` llega intacta y el ranking de
    deriva por característica (`feature_drift_score`) es comprobable aquí.
    Siete fases (`b1..b5` antes de `e1_evento`); reverificado
    con el motor en memoria (`run_scenario`, sin API) que las cinco líneas
    base no mueven ninguna de estas cifras: `fairness_value`/`accuracy` los
    da siempre el propio lote (450 filas, muy por encima de `min_records`
    y de `label_min_records`), no el histórico. `prediction_drift_score`
    sale 0,082 (sobre el umbral 0,080 de `drift`)."""
    run = _crear_run(client, "caso_digestivo")
    job = _play(client, run["id"])
    resumenes = job["result"]["result"]
    assert len(resumenes) == 7
    assert [r["phase_key"] for r in resumenes] == [
        "b1",
        "b2",
        "b3",
        "b4",
        "b5",
        "e1_evento",
        "e1_recovery",
    ]
    resumen = resumenes[5]
    assert resumen["phase_key"] == "e1_evento"

    medidas: dict[str, float | None] = {}
    evaluaciones = client.get(
        f"/api/projects/{run['project_id']}/evaluations", params={"batch_id": resumen["batch_id"]}
    )
    assert evaluaciones.status_code == 200, evaluaciones.text
    items_evaluacion = evaluaciones.json()["items"]
    assert items_evaluacion, "el lote de e1_evento no tiene evaluaciones"
    for item in items_evaluacion:
        detalle = client.get(f"/api/evaluations/{item['id']}")
        assert detalle.status_code == 200, detalle.text
        for medida in detalle.json()["measurements"]:
            medidas[medida["metric_key"]] = medida["value"]

    assert medidas["accuracy"] == pytest.approx(0.860, abs=0.001)
    assert medidas["false_negative_rate_difference"] == pytest.approx(0.631, abs=0.001)
    assert medidas["fairness_value"] == pytest.approx(19.50, abs=0.01)
    assert medidas["confidence_drift_score"] == pytest.approx(0.370, abs=0.001)
    # `feature_drift_score` es el máximo del KS/JS de las 41 características
    # (`core/drift.py::feature_drift_score`); la edad encabeza el ranking
    # (paso 13), así que el máximo es su KS.
    assert medidas["feature_drift_score"] == pytest.approx(0.189, abs=5e-4)
    assert medidas["prediction_drift_score"] == pytest.approx(0.082, abs=1e-3)
    # El agregado de calidad también queda en
    # correcto en e1_evento por este camino (sin project_id).
    assert resumen["states"]["quality"] == "ok", resumen


def test_umbrales_calidad_demo_se_aplican_sin_project_id_y_dejan_todo_ok(client: TestClient):
    """`_crear_proyecto_demo` (camino sin
    `project_id`) también fija `scenario.umbrales_calidad`, antes de que se
    reproduzca ninguna fase; las siete fases de `caso_digestivo` quedan en
    `ok` en calidad, igual que por el camino atado."""
    run = _crear_run(client, "caso_digestivo")

    monitores = client.get(f"/api/projects/{run['project_id']}/monitors").json()["items"]
    calidad = next(m for m in monitores if m["type"] == "quality")
    umbrales = {t["metric_key"]: t["value"] for t in calidad["thresholds"]["thresholds"]}
    assert umbrales["accuracy"] == pytest.approx(0.75)
    assert umbrales["area_under_roc"] == pytest.approx(0.70)
    assert umbrales["true_positive_rate"] == pytest.approx(0.65)
    assert umbrales["recall"] == pytest.approx(0.65)
    assert umbrales["gini_coefficient"] == pytest.approx(0.50)

    job = _play(client, run["id"])
    resumenes = job["result"]["result"]
    assert len(resumenes) == 7
    for r in resumenes:
        assert r["states"]["quality"] == "ok", r


def test_umbrales_calidad_demo_no_se_tocan_en_timeline_completo(client: TestClient):
    """Los guiones antiguos no declaran `umbrales_calidad`: el monitor de
    calidad del proyecto se queda con los umbrales por defecto."""
    run = _crear_run(client, "timeline_completo")
    monitores = client.get(f"/api/projects/{run['project_id']}/monitors").json()["items"]
    calidad = next(m for m in monitores if m["type"] == "quality")
    umbral_accuracy = next(
        t for t in calidad["thresholds"]["thresholds"] if t["metric_key"] == "accuracy"
    )
    assert umbral_accuracy["value"] == pytest.approx(0.80)


def test_caso_digestivo_lotes_fechados_una_semana_aparte(client: TestClient):
    """Al ingerir cada fase, `Batch.created_at` queda fechado
    `hoy - semanas_atras` (`b1` seis semanas atrás … `e1_recovery` hoy);
    `b1` queda al menos cinco semanas antes que `e1_evento` (con un margen de
    un día para el tiempo real que tarda la reproducción)."""
    run = _crear_run(client, "caso_digestivo")
    _play(client, run["id"])

    lotes = client.get(f"/api/projects/{run['project_id']}/batches").json()["items"]
    por_fase = {b["phase_label"]: datetime.fromisoformat(b["created_at"]) for b in lotes}
    assert set(por_fase) == {"b1", "b2", "b3", "b4", "b5", "e1_evento", "e1_recovery"}

    orden = ["b1", "b2", "b3", "b4", "b5", "e1_evento", "e1_recovery"]
    fechas = [por_fase[k] for k in orden]
    assert fechas == sorted(fechas), "las fechas simuladas siguen el orden de las fases"

    diferencia = fechas[-1] - fechas[0]
    assert diferencia >= timedelta(weeks=6) - timedelta(days=1)

    # Los eventos del diario, en cambio, conservan la hora real: recientes, no de hace
    # semanas.
    eventos = client.get(
        "/api/events", params={"object_type": "demo_run", "object_id": run["id"], "limit": 500}
    ).json()["items"]
    ahora = datetime.now(UTC)
    for e in eventos:
        ts = datetime.fromisoformat(e["ts"])
        assert ahora - ts < timedelta(minutes=10), e


def test_caso_digestivo_alerts_series_por_dia_tiene_siete_tramos(client: TestClient):
    """Verifica en vivo (§5 del encargo) que la fecha simulada por fase
    separa los lotes en la agregación diaria de `GET /projects/{id}/alerts/series`:
    con siete fases fechadas una semana aparte, salen siete tramos con lote."""
    run = _crear_run(client, "caso_digestivo")
    _play(client, run["id"])

    serie = client.get(
        f"/api/projects/{run['project_id']}/alerts/series", params={"granularity": "day"}
    )
    assert serie.status_code == 200, serie.text
    tramos = [t for t in serie.json()["items"] if t.get("n_batches", 0) > 0]
    assert len(tramos) == 7, serie.json()
