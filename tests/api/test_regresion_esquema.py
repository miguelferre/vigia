"""Esquema y alta de una regresión.

El cerrojo de `validar_tipo_http` se quitó al integrar, con el test de despacho en verde.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, select

from tests.api import _datos_multiclase as d
from tests.api import _datos_regresion as r
from tests.api.conftest import actor_headers
from vigia.app.db import init_db, make_engine
from vigia.app.migrations import current_version, migrate, target_version
from vigia.app.models import Event, Project
from vigia.core.schema import MENSAJE_SIM_SOLO_BINARIO

HUMANO = actor_headers("miguel")


# ---------------------------------------------------------------------------
# Sin cerrojo
# ---------------------------------------------------------------------------


def test_sin_cerrojo_un_tipo_inventado_sigue_dando_422_y_no_deja_un_proyecto_a_medias(
    client: TestClient,
):
    """El cerrojo se quitó: `regression` entra y un tipo que no existe sigue fuera."""
    resp = client.post(
        "/api/projects", json={"name": "r5-inventado", "task_type": "ranking"}, headers=HUMANO
    )
    assert resp.status_code == 422
    assert "regression" in resp.text
    assert client.get("/api/projects").json()["total"] == 0


def test_con_el_cerrojo_quitado_la_regresion_se_da_de_alta(client: TestClient):
    p = r.crear_proyecto_regresion(client, "r5-alta-abierta")
    assert p["task_type"] == "regression"


# ---------------------------------------------------------------------------
# Migración 14
# ---------------------------------------------------------------------------

_COLUMNAS_14 = {
    "record": {"prediction_value", "label_value"},
    "project": {"target_unit", "favorable_ranges_json"},
    "usage_log": {"human_value", "model_value", "truth_value"},
}


def _columnas(engine, tabla: str) -> set[str]:
    with engine.connect() as conn:
        return {f[1] for f in conn.execute(text(f"PRAGMA table_info({tabla})")).fetchall()}


def test_la_migracion_14_anade_las_siete_columnas_nulas_sin_tocar_filas(tmp_path: Path):
    ruta = tmp_path / "m14.db"
    engine = make_engine(ruta)
    init_db(engine)
    with engine.begin() as conn:
        for tabla, columnas in _COLUMNAS_14.items():
            for columna in columnas:
                conn.execute(text(f"ALTER TABLE {tabla} DROP COLUMN {columna}"))
        conn.execute(text("DELETE FROM schema_version WHERE version >= 14"))
        conn.execute(
            text(
                "INSERT INTO project (name, domain, task_type, favorable_label, store_features, "
                "explain_auto, explain_method, is_demo, deployment_stage, acepta_feedback, "
                "created_at, updated_at) VALUES ('viejo', 'libre', 'multiclass', 1, 1, 1, "
                "'permutation', 0, 'desarrollo', 1, '2026-10-01', '2026-10-01')"
            )
        )
    for tabla, columnas in _COLUMNAS_14.items():
        assert not columnas & _columnas(engine, tabla)
    assert current_version(engine) == 13
    assert migrate(engine, ruta) == target_version() == 15
    for tabla, columnas in _COLUMNAS_14.items():
        assert columnas <= _columnas(engine, tabla), tabla
    with engine.connect() as conn:
        fila = conn.execute(
            text("SELECT task_type, target_unit, favorable_ranges_json FROM project")
        ).one()
    assert tuple(fila) == ("multiclass", None, None)  # task_type no se toca
    assert migrate(engine, ruta) == 15  # idempotente


def test_la_migracion_14_sobre_la_demo_completa_conserva_eventos_y_alertas(client: TestClient):
    """Una base con la demo entera migra con los mismos eventos y alertas."""
    from vigia.app.models import Alert

    resp = client.post(
        "/api/demo/runs",
        json={"scenario_key": "timeline_completo", "with_human": False},
        headers=HUMANO,
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    resp = client.post(f"/api/demo/runs/{run['id']}/play", headers=HUMANO)
    assert resp.status_code == 200 and resp.json()["status"] == "terminado", resp.text
    engine = client.app.state.engine

    def huella() -> tuple[list[tuple], list[tuple]]:
        with Session(engine) as s:
            eventos = [(e.id, e.action, e.object_id) for e in s.exec(select(Event).order_by(Event.id)).all()]
            alertas = [(a.id, a.metric_key, a.status) for a in s.exec(select(Alert).order_by(Alert.id)).all()]
        return eventos, alertas

    antes = huella()
    assert len(antes[0]) > 50 and len(antes[1]) >= 1
    with engine.begin() as conn:
        for tabla, columnas in _COLUMNAS_14.items():
            for columna in columnas:
                conn.execute(text(f"ALTER TABLE {tabla} DROP COLUMN {columna}"))
        conn.execute(text("DELETE FROM schema_version WHERE version >= 14"))
    assert current_version(engine) == 13
    assert migrate(engine, Path(engine.url.database)) == 15
    assert huella() == antes
    for tabla, columnas in _COLUMNAS_14.items():
        assert columnas <= _columnas(engine, tabla), tabla


# ---------------------------------------------------------------------------
# El alta con unidad y rango
# ---------------------------------------------------------------------------


def test_el_alta_de_regresion_fija_unidad_y_rango_y_no_tiene_clase_favorable(client: TestClient):
    p = r.crear_proyecto_regresion(client, "r5-alta-campos", rangos=[[12, None], [-5, -1]])
    assert p["favorable_label"] is None
    assert p["target_unit"] == r.UNIDAD
    assert p["favorable_ranges"] == [[-5.0, -1.0], [12.0, None]]  # ordenados por el mínimo
    assert p["classes"] is None
    leido = client.get(f"/api/projects/{p['id']}").json()
    assert leido["favorable_label"] is None and leido["target_unit"] == r.UNIDAD
    listado = client.get("/api/projects").json()["items"][0]
    assert listado["favorable_label"] is None and listado["favorable_ranges"] == p["favorable_ranges"]
    with Session(client.app.state.engine) as s:
        fila = s.get(Project, p["id"])
        assert fila.target_unit == r.UNIDAD
        assert fila.favorable_ranges_json == [[-5.0, -1.0], [12.0, None]]
        assert fila.favorable_label == 1  # la columna de compatibilidad, no se enseña
    assert p["mapping_template_json"]["target_unit"] == r.UNIDAD


def test_el_cuerpo_manda_sobre_la_plantilla(client: TestClient):
    p = r.crear_proyecto_regresion(
        client,
        "r5-alta-cuerpo-manda",
        unidad="días",
        rangos=[[1, 5]],
        mapping_template={"target_unit": "horas", "favorable_ranges": [[40, 81]]},
    )
    assert p["target_unit"] == "días" and p["favorable_ranges"] == [[1.0, 5.0]]
    assert p["mapping_template_json"]["target_unit"] == "días"


def test_la_plantilla_puede_traer_unidad_y_rango_sin_el_cuerpo(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={
            "name": "r5-alta-plantilla",
            "task_type": "regression",
            "mapping_template": {"target_unit": "días", "favorable_ranges": [[3, 14]]},
        },
        headers=HUMANO,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["target_unit"] == "días" and resp.json()["favorable_ranges"] == [[3.0, 14.0]]


@pytest.mark.parametrize(
    ("extra", "pista"),
    [
        ({"classes": ["a", "b", "c"]}, "classes"),
        ({"mapping_template": {"favorable_label": 1}}, "favorable_label"),
        ({"mapping_template": {"probability_col": "p"}}, "probability_col"),
        ({"favorable_ranges": [[5, 1]]}, "mínimo"),
        ({"favorable_ranges": [[1, 5], [4, 9]]}, "solapar"),
        ({"favorable_ranges": [[1, 2], [3, 4], [5, 6], [7, 8]]}, "intervalos"),
        ({"target_unit": "x" * 31}, "target_unit"),
    ],
)
def test_el_alta_de_regresion_rechaza_lo_que_no_es_de_regresion(
    client: TestClient, extra: dict, pista: str
):
    cuerpo = {"name": "r5-alta-rechazo", "task_type": "regression", **extra}
    resp = client.post("/api/projects", json=cuerpo, headers=HUMANO)
    assert resp.status_code == 422, resp.text
    assert pista in resp.text
    assert client.get("/api/projects").json()["total"] == 0


def test_una_clase_favorable_en_el_cuerpo_del_alta_de_regresion_da_422(client: TestClient):
    """`favorable_label` en el cuerpo del alta (no solo en la plantilla) nombra el campo. El `1`
    de compatibilidad del MCP y la ausencia del campo siguen valiendo."""
    resp = client.post(
        "/api/projects",
        json={"name": "r5-alta-favorable-0", "task_type": "regression", "favorable_label": 0},
        headers=HUMANO,
    )
    assert resp.status_code == 422, resp.text
    assert "favorable_label" in resp.text and "favorable_ranges" in resp.text
    assert client.get("/api/projects").json()["total"] == 0
    for nombre, extra in (("uno", {"favorable_label": 1}), ("ausente", {})):
        resp = client.post(
            "/api/projects",
            json={"name": f"r5-alta-favorable-{nombre}", "task_type": "regression", **extra},
            headers=HUMANO,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["favorable_label"] is None


def test_unidad_y_rango_son_solo_de_regresion(client: TestClient):
    for extra, pista in (
        ({"target_unit": "días"}, "target_unit"),
        ({"favorable_ranges": [[1, 2]]}, "favorable_ranges"),
    ):
        for tipo in ("binary", "multiclass"):
            cuerpo = {"name": f"r5-solo-reg-{tipo}", "task_type": tipo, **extra}
            if tipo == "multiclass":
                cuerpo["classes"] = ["a", "b", "c"]
            resp = client.post("/api/projects", json=cuerpo, headers=HUMANO)
            assert resp.status_code == 422, resp.text
            assert pista in resp.text


def test_regresion_con_el_modelo_simulado_da_422(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={"name": "r5-sim", "task_type": "regression", "domain": "reuma", "model_kind": "sim_logistic"},
        headers=HUMANO,
    )
    assert resp.status_code == 422
    assert MENSAJE_SIM_SOLO_BINARIO in resp.text
    p = r.crear_proyecto_regresion(client, "r5-sim-version")
    resp = client.post(
        f"/api/projects/{p['id']}/versions",
        json={"label": "v2", "model_kind": "sim_logistic", "actor": "miguel", "motivo": "probar"},
        headers=HUMANO,
    )
    assert resp.status_code == 422, resp.text


def test_el_tipo_de_regresion_no_cambia_con_patch(client: TestClient):
    p = r.crear_proyecto_regresion(client, "r5-tipo-fijo")
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={"actor": "miguel", "motivo": "probar", "task_type": "binary"},
        headers=HUMANO,
    )
    assert resp.status_code == 409
    assert "proyecto nuevo" in resp.text


def test_antes_de_congelar_el_patch_de_la_plantilla_cambia_unidad_y_rango(client: TestClient):
    p = r.crear_proyecto_regresion(client, "r5-h5-antes")
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={
            "actor": "miguel",
            "motivo": "ajustar el rango",
            "mapping_template": {"target_unit": "días", "favorable_ranges": [[3, 9]]},
        },
        headers=HUMANO,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["target_unit"] == "días"
    assert resp.json()["favorable_ranges"] == [[3.0, 9.0]]


def test_despues_de_congelar_cambiar_la_unidad_o_el_rango_da_409(client: TestClient):
    p, _t = r.linea_base_regresion(client, "r5-h5-despues", n=200)
    for plantilla in (
        {"target_unit": "días"},
        {"favorable_ranges": [[3, 9]]},
    ):
        resp = client.patch(
            f"/api/projects/{p['id']}",
            json={"actor": "miguel", "motivo": "cambiar", "mapping_template": plantilla},
            headers=HUMANO,
        )
        assert resp.status_code == 409, resp.text
        assert "proyecto nuevo" in resp.text
    leido = client.get(f"/api/projects/{p['id']}").json()
    assert leido["target_unit"] == r.UNIDAD and leido["favorable_ranges"] == [[12.0, None]]
    # Una plantilla que no dice unidad ni rango conserva los fijados.
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={"actor": "miguel", "motivo": "columnas", "mapping_template": {"feature_cols": ["x1"]}},
        headers=HUMANO,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["target_unit"] == r.UNIDAD
    assert resp.json()["favorable_ranges"] == [[12.0, None]]


def test_un_mapeo_con_otro_rango_despues_de_congelar_da_409(client: TestClient):
    p, _t = r.linea_base_regresion(client, "r5-h5-mapeo", n=200)
    sub = d.subir(client, p["id"], r.a_csv(r.filas_regresion(50, semilla=3)), rol="production")
    resp = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion(favorable_ranges=[[3, 9]]))
    assert resp.status_code == 409, resp.text
    assert d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion()).status_code == 200
    # El mismo rango, escrito igual, no es un cambio.
    ok = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion(favorable_ranges=[[12, None]]))
    assert ok.status_code == 200, ok.text


def test_sin_unidad_ni_rango_en_el_alta_se_fijan_al_congelar_desde_el_mapeo(client: TestClient):
    p = r.crear_proyecto_regresion(client, "r5-h5-congelar", unidad=None, rangos=None)
    assert p["target_unit"] is None and p["favorable_ranges"] == []
    r.subir_e_ingerir(
        client,
        p,
        r.filas_regresion(200),
        mapeo=r.mapeo_regresion(target_unit="días", favorable_ranges=[[10, 20]]),
    )
    leido = client.get(f"/api/projects/{p['id']}").json()
    assert leido["target_unit"] == "días" and leido["favorable_ranges"] == [[10.0, 20.0]]
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={"actor": "miguel", "motivo": "x", "mapping_template": {"favorable_ranges": [[1, 2]]}},
        headers=HUMANO,
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Títulos del diario
# ---------------------------------------------------------------------------


def test_los_titulos_del_diario_dicen_el_tipo_con_unidad_y_el_rango(client: TestClient):
    p = r.crear_proyecto_regresion(client, "r5-titulos", unidad="horas por semana", rangos=[[40, 81]])
    eventos = client.get("/api/events", params={"project_id": p["id"], "limit": 100}).json()["items"]
    titulos = [e["titulo"] for e in eventos]
    assert any("Tipo de tarea: regresión (unidad: horas por semana)" in t for t in titulos), titulos
    assert any("Rango favorable fijado: de 40 a 81 horas por semana" in t for t in titulos), titulos


# ---------------------------------------------------------------------------
# Titular de calidad por tipo
# ---------------------------------------------------------------------------


def test_el_titular_de_calidad_por_defecto_depende_del_tipo(client: TestClient):
    reg = r.crear_proyecto_regresion(client, "r5-titular-reg")
    assert client.get(f"/api/projects/{reg['id']}/state").json()["quality_primary_metric"] == "mean_absolute_error"
    bin_ = client.post("/api/projects", json={"name": "r5-titular-bin"}, headers=HUMANO).json()
    assert client.get(f"/api/projects/{bin_['id']}/state").json()["quality_primary_metric"] == "accuracy"
    multi = d.crear_proyecto_multiclase(client, "r5-titular-multi")
    assert client.get(f"/api/projects/{multi['id']}/state").json()["quality_primary_metric"] == "f1_measure"


def test_primary_metric_acepta_las_claves_de_calidad_del_tipo(client: TestClient):
    reg = r.crear_proyecto_regresion(client, "r5-primary-reg")
    calidad = next(m for m in reg["monitors"] if m["type"] == "quality")

    def patch(monitor: dict, clave: str):
        return client.patch(
            f"/api/monitors/{monitor['id']}",
            json={"actor": "miguel", "motivo": "titular", "config": {"primary_metric": clave}},
            headers=HUMANO,
        )

    assert patch(calidad, "root_mean_squared_error").status_code == 200
    assert client.get(f"/api/projects/{reg['id']}/state").json()["quality_primary_metric"] == "root_mean_squared_error"
    malo = patch(calidad, "accuracy")
    assert malo.status_code == 422 and "mean_absolute_error" in malo.text
    binario = client.post("/api/projects", json={"name": "r5-primary-bin"}, headers=HUMANO).json()
    cal_bin = next(m for m in binario["monitors"] if m["type"] == "quality")
    assert patch(cal_bin, "accuracy").status_code == 200
    rechazo = patch(cal_bin, "mean_absolute_error")
    assert rechazo.status_code == 422


# ---------------------------------------------------------------------------
# Monitores de fábrica por tipo
# ---------------------------------------------------------------------------


def test_los_monitores_de_fabrica_de_una_regresion(client: TestClient):
    con = r.crear_proyecto_regresion(client, "r5-fabrica-con-rango")
    sin = r.crear_proyecto_regresion(client, "r5-fabrica-sin-rango", rangos=None)

    def umbrales(p: dict, tipo: str) -> set[str]:
        m = next(m for m in p["monitors"] if m["type"] == tipo)
        return {t["metric_key"] for t in m["thresholds"]["thresholds"]}

    for p in (con, sin):
        assert umbrales(p, "quality") == set()  # Sin valores de fábrica en unidades
        deriva = umbrales(p, "drift")
        assert "feature_drift_score" in deriva
        assert "prediction_drift_score" not in deriva
        assert not deriva & {"confidence_drift_score", "model_quality_score"}
        assert umbrales(p, "cross") == set()
    assert "fairness_value" in umbrales(con, "fairness")
    assert umbrales(sin, "fairness") == set()

    # Con rango, la equidad de pertenencia y la explicabilidad son las de fábrica binarias.
    from vigia.core.thresholds import DEFAULT_EXPLAIN_THRESHOLDS, DEFAULT_FAIRNESS_THRESHOLDS

    def fabrica(p: dict, tipo: str) -> set[tuple[str, str, float]]:
        m = next(m for m in p["monitors"] if m["type"] == tipo)
        return {(t["metric_key"], t["kind"], t["value"]) for t in m["thresholds"]["thresholds"]}

    esperado_equidad = {
        (t.metric_key, t.kind, t.value) for t in DEFAULT_FAIRNESS_THRESHOLDS.thresholds if t.metric_key == "fairness_value"
    }
    assert esperado_equidad and esperado_equidad <= fabrica(con, "fairness")
    assert fabrica(con, "explain") == {(t.metric_key, t.kind, t.value) for t in DEFAULT_EXPLAIN_THRESHOLDS.thresholds}
    assert fabrica(sin, "explain") == fabrica(con, "explain")
