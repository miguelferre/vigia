"""Tipo de tarea y esquema común.

Un test por regla. Los de punta a punta multiclase (ingesta, evaluación) están en
`test_multiclase_ingesta_evaluacion.py`; aquí, lo que no depende del motor.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, select

from tests.api import _datos_multiclase as d
from tests.api.conftest import actor_headers
from vigia.app.db import init_db, make_engine
from vigia.app.migrations import current_version, migrate, target_version
from vigia.app.models import Event, Project
from vigia.app.schemas.respuestas_datos import ColumnMappingOut
from vigia.app.services.ingest import _CAMPOS_PLANTILLA
from vigia.core.schema import ColumnMapping, MappingTemplate
from vigia.mcp.errores import CLAVES_COLUMN_MAPPING, CLAVES_MAPPING_TEMPLATE


def _crear(client: TestClient, **cuerpo):
    cuerpo.setdefault("name", "r4-proyecto")
    return client.post("/api/projects", json=cuerpo, headers=actor_headers("miguel"))


# ---------------------------------------------------------------------------
# Tipo de tarea
# ---------------------------------------------------------------------------


def test_task_type_por_defecto_es_binario(client: TestClient):
    p = _crear(client, name="r4-defecto").json()
    assert p["task_type"] == "binary"
    assert p["classes"] is None
    assert p["favorable_label"] == 1


def test_alta_multiclase_guarda_tipo_clases_y_favorables(client: TestClient):
    resp = _crear(
        client,
        name="r4-multi",
        task_type="multiclass",
        classes=d.CLASES,
        mapping_template={"favorable_label": ["permitido", "spam"]},
    )
    assert resp.status_code == 200, resp.text
    p = resp.json()
    assert p["task_type"] == "multiclass"
    assert p["classes"] == d.CLASES
    # La verdad es la plantilla; el entero de compatibilidad no manda.
    assert p["favorable_label"] == ["permitido", "spam"]
    leido = client.get(f"/api/projects/{p['id']}").json()
    assert leido["classes"] == d.CLASES and leido["task_type"] == "multiclass"


def test_alta_multiclase_toma_las_clases_de_la_plantilla(client: TestClient):
    resp = _crear(
        client,
        name="r4-multi-plantilla",
        task_type="multiclass",
        mapping_template={"classes": ["a", "b", "c"], "favorable_label": ["a"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["classes"] == ["a", "b", "c"]


def test_las_clases_del_cuerpo_mandan_sobre_las_de_la_plantilla(client: TestClient):
    resp = _crear(
        client,
        name="r4-multi-manda",
        task_type="multiclass",
        classes=["x", "y", "z"],
        mapping_template={"classes": ["a", "b", "c"]},
    )
    assert resp.status_code == 200, resp.text
    p = resp.json()
    assert p["classes"] == ["x", "y", "z"]
    assert p["mapping_template_json"]["classes"] == ["x", "y", "z"]


def test_multiclase_sin_clases_vale_y_salen_de_la_linea_base(client: TestClient):
    resp = _crear(client, name="r4-multi-sin-clases", task_type="multiclass")
    assert resp.status_code == 200, resp.text
    assert resp.json()["classes"] is None
    # Y sin conjunto favorable se enseña la lista vacía, no el `1` de compatibilidad.
    assert resp.json()["favorable_label"] == []


def test_un_campo_desconocido_del_alta_da_422(client: TestClient):
    resp = _crear(client, name="r4-forbid", tipo_de_tarea="multiclase")
    assert resp.status_code == 422
    assert "tipo_de_tarea" in resp.text


def test_un_task_type_inventado_da_422(client: TestClient):
    resp = _crear(client, name="r4-inventado", task_type="ranking")
    assert resp.status_code == 422


def test_regresion_se_acepta_en_el_alta(client: TestClient):
    """Una regresión se acepta en el alta."""
    resp = _crear(client, name="r4-regresion", task_type="regression")
    assert resp.status_code == 200, resp.text
    assert resp.json()["task_type"] == "regression"
    assert client.get("/api/projects").json()["total"] == 1


def test_cambiar_el_task_type_con_patch_da_409(client: TestClient):
    p = _crear(client, name="r4-patch-tipo").json()
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={"actor": "miguel", "motivo": "probar", "task_type": "multiclass"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 409
    assert "proyecto nuevo" in resp.text
    assert client.get(f"/api/projects/{p['id']}").json()["task_type"] == "binary"


def test_repetir_el_mismo_task_type_no_es_un_cambio(client: TestClient):
    p = _crear(client, name="r4-patch-igual").json()
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={"actor": "miguel", "motivo": "probar", "task_type": "binary", "description": "ok"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["description"] == "ok"


def test_un_proyecto_existente_sigue_binario_tras_migrar(tmp_path: Path):
    engine = make_engine(tmp_path / "v.db")
    init_db(engine)
    with Session(engine) as s:
        s.add(Project(name="viejo"))
        s.commit()
    migrate(engine, tmp_path / "v.db")
    with Session(engine) as s:
        assert s.exec(select(Project)).one().task_type == "binary"


# ---------------------------------------------------------------------------
# Reglas por tipo en el alta y en la plantilla (interfaz §2.5)
# ---------------------------------------------------------------------------


def test_binario_con_tres_clases_da_422(client: TestClient):
    resp = _crear(client, name="r4-bin-3", classes=["a", "b", "c"])
    assert resp.status_code == 422
    assert "binario" in resp.text and "multiclase" in resp.text


def test_binario_con_dos_favorables_da_422_y_no_un_500(client: TestClient):
    resp = _crear(client, name="r4-bin-fav", mapping_template={"favorable_label": [0, 1]})
    assert resp.status_code == 422, resp.text
    assert "multiclase" in resp.text


def test_multiclase_con_dos_clases_da_422(client: TestClient):
    resp = _crear(client, name="r4-multi-2", task_type="multiclass", classes=["a", "b"])
    assert resp.status_code == 422
    assert "binario" in resp.text


def test_multiclase_con_mas_de_veinte_clases_da_422(client: TestClient):
    resp = _crear(
        client, name="r4-multi-21", task_type="multiclass", classes=[f"c{i}" for i in range(21)]
    )
    assert resp.status_code == 422


def test_multiclase_con_todas_las_clases_favorables_da_422(client: TestClient):
    resp = _crear(
        client,
        name="r4-multi-todas",
        task_type="multiclass",
        classes=["a", "b", "c"],
        mapping_template={"favorable_label": ["a", "b", "c"]},
    )
    assert resp.status_code == 422
    assert "al menos una" in resp.text


def test_favorable_fuera_de_las_clases_da_422(client: TestClient):
    resp = _crear(
        client,
        name="r4-multi-fuera",
        task_type="multiclass",
        classes=["a", "b", "c"],
        mapping_template={"favorable_label": ["z"]},
    )
    assert resp.status_code == 422
    assert "no está entre las clases" in resp.text


def test_probabilidad_de_una_sola_columna_escalar_en_multiclase_da_422(client: TestClient):
    """La regla vive en el mapeo de cada fichero: la plantilla no fija el formato."""
    p = _crear(client, name="r4-multi-prob", task_type="multiclass", classes=["a", "b", "c"]).json()
    contenido = b"id,prediction,label,p\n1,a,a,0.5\n2,b,b,0.5\n"
    sub = d.subir(client, p["id"], contenido, rol="production")
    resp = d.mapear(
        client,
        sub["dataset"]["id"],
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "probability_col": "p"},
    )
    assert resp.status_code == 422
    assert "una columna por clase" in resp.text


def test_probability_cols_de_otra_longitud_que_classes_da_422(client: TestClient):
    resp = _crear(
        client,
        name="r4-multi-longitud",
        task_type="multiclass",
        classes=["a", "b", "c"],
        mapping_template={"probability_cols": ["pa", "pb"]},
    )
    assert resp.status_code == 422
    assert "una columna por clase" in resp.text


def test_el_patch_de_plantilla_se_valida_por_tipo(client: TestClient):
    p = _crear(client, name="r4-patch-plantilla").json()
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={
            "actor": "miguel",
            "motivo": "probar",
            "mapping_template": {"favorable_label": [0, 1]},
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422
    assert "multiclase" in resp.text


def test_el_patch_de_plantilla_fija_las_clases_del_proyecto_una_vez(client: TestClient):
    p = _crear(client, name="r4-patch-clases", task_type="multiclass").json()
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={
            "actor": "miguel",
            "motivo": "declarar clases",
            "mapping_template": {"classes": ["a", "b", "c"], "favorable_label": ["a"]},
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["classes"] == ["a", "b", "c"]
    # Después no se pueden contradecir.
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={
            "actor": "miguel",
            "motivo": "cambiar",
            "mapping_template": {"classes": ["x", "y", "z"]},
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422
    assert "no coinciden" in resp.text


def test_el_put_del_mapeo_valida_por_tipo(client: TestClient):
    p = _crear(client, name="r4-put-tipo").json()
    sub = d.subir(client, p["id"], b"id,prediction,label\n1,0,0\n2,1,1\n", rol="production")
    resp = d.mapear(
        client,
        sub["dataset"]["id"],
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": [0, 1]},
    )
    assert resp.status_code == 422
    assert "multiclase" in resp.text


# ---------------------------------------------------------------------------
# Los seis sitios del mismo conjunto de claves
# ---------------------------------------------------------------------------


def test_los_seis_sitios_comparten_el_conjunto_de_claves():
    plantilla = set(MappingTemplate.model_fields)
    mapeo = set(ColumnMapping.model_fields)
    assert set(_CAMPOS_PLANTILLA) == plantilla
    assert set(CLAVES_MAPPING_TEMPLATE) == plantilla
    assert set(CLAVES_COLUMN_MAPPING) == mapeo
    assert set(ColumnMappingOut.model_fields) == mapeo
    assert {"classes", "probability_cols"} <= plantilla & mapeo
    assert "positive_label" not in plantilla | mapeo | set(_CAMPOS_PLANTILLA)


def test_positive_label_no_esta_en_el_openapi(client: TestClient):
    esquemas = client.app.openapi()["components"]["schemas"]
    for nombre in ("MappingTemplate", "ColumnMapping", "ColumnMappingOut"):
        assert "positive_label" not in esquemas[nombre]["properties"], nombre


# ---------------------------------------------------------------------------
# Positive_label
# ---------------------------------------------------------------------------


def _plantilla_cruda(client: TestClient, proyecto_id: int, plantilla: dict) -> None:
    with Session(client.app.state.engine) as s:
        p = s.get(Project, proyecto_id)
        p.mapping_template_json = plantilla
        s.add(p)
        s.commit()


def _eventos(client: TestClient, accion: str) -> list[Event]:
    with Session(client.app.state.engine) as s:
        return list(s.exec(select(Event).where(Event.action == accion)).all())


def test_positive_label_nulo_se_relee_sin_error(client: TestClient):
    p = _crear(client, name="r4-pos-nulo").json()
    _plantilla_cruda(client, p["id"], {"favorable_label": 1, "positive_label": None})
    sub = d.subir(client, p["id"], b"id,prediction,label\n1,0,0\n2,1,1\n", rol="production")
    resp = d.mapear(
        client,
        sub["dataset"]["id"],
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id"},
    )
    assert resp.status_code == 200, resp.text
    assert _eventos(client, "proyecto.positive_label_ignorado") == []
    with Session(client.app.state.engine) as s:
        assert "positive_label" not in s.get(Project, p["id"]).mapping_template_json


def test_positive_label_con_valor_da_un_aviso_una_vez_y_se_quita(client: TestClient):
    p = _crear(client, name="r4-pos-valor").json()
    _plantilla_cruda(client, p["id"], {"favorable_label": 1, "positive_label": 0})
    sub = d.subir(client, p["id"], b"id,prediction,label\n1,0,0\n2,1,1\n", rol="production")
    mapeo = {"prediction_col": "prediction", "label_col": "label", "id_col": "id"}
    assert d.mapear(client, sub["dataset"]["id"], mapeo).status_code == 200
    avisos = _eventos(client, "proyecto.positive_label_ignorado")
    assert len(avisos) == 1
    assert avisos[0].before_json == {"positive_label": 0}
    # Una segunda relectura ya no lo repite.
    assert d.mapear(client, sub["dataset"]["id"], mapeo).status_code == 200
    assert len(_eventos(client, "proyecto.positive_label_ignorado")) == 1
    with Session(client.app.state.engine) as s:
        assert "positive_label" not in s.get(Project, p["id"]).mapping_template_json


def test_actualizar_la_plantilla_con_positive_label_guardado_deja_el_aviso(client: TestClient):
    p = _crear(client, name="r4-pos-patch").json()
    _plantilla_cruda(client, p["id"], {"favorable_label": 1, "positive_label": 1})
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={"actor": "miguel", "motivo": "actualizar", "mapping_template": {"favorable_label": 1, "id_col": "id"}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert len(_eventos(client, "proyecto.positive_label_ignorado")) == 1
    assert "positive_label" not in resp.json()["mapping_template_json"]


def test_el_aviso_de_positive_label_tiene_titulo_en_espanol(client: TestClient):
    p = _crear(client, name="r4-pos-titulo").json()
    _plantilla_cruda(client, p["id"], {"favorable_label": 1, "positive_label": 1})
    sub = d.subir(client, p["id"], b"id,prediction,label\n1,0,0\n", rol="production")
    d.mapear(client, sub["dataset"]["id"], {"prediction_col": "prediction", "label_col": "label", "id_col": "id"})
    eventos = client.get("/api/events", params={"project_id": p["id"], "limit": 200}).json()["items"]
    titulos = [e["titulo"] for e in eventos if e["action"] == "proyecto.positive_label_ignorado"]
    assert titulos and "positive_label" in titulos[0] and "ignora" in titulos[0]


# ---------------------------------------------------------------------------
# Migración 13
# ---------------------------------------------------------------------------

_COLUMNAS_13 = {
    "record": ["prediction_class", "label_class", "probabilities_json"],
    "project": ["classes_json"],
    "usage_log": ["human_class", "model_class", "truth_class"],
}
# Las siete de la migración 14; el esquema de la 12 tampoco las tiene.
_COLUMNAS_14 = {
    "record": ["prediction_value", "label_value"],
    "project": ["target_unit", "favorable_ranges_json"],
    "usage_log": ["human_value", "model_value", "truth_value"],
}


def _quitar_columnas_13_y_14(conn) -> None:
    """Deja el esquema como lo dejaba la versión 12 (sin las columnas de la 13 y la 14)."""
    for columnas_por_tabla in (_COLUMNAS_14, _COLUMNAS_13):
        for tabla, columnas in columnas_por_tabla.items():
            for columna in columnas:
                conn.execute(text(f"ALTER TABLE {tabla} DROP COLUMN {columna}"))
    conn.execute(text("DELETE FROM schema_version WHERE version >= 13"))


def _columnas(engine, tabla: str) -> set[str]:
    with engine.connect() as conn:
        return {f[1] for f in conn.execute(text(f"PRAGMA table_info({tabla})")).fetchall()}


def test_la_migracion_13_anade_las_siete_columnas_nulas(tmp_path: Path):
    ruta = tmp_path / "m13.db"
    engine = make_engine(ruta)
    init_db(engine)
    # Esquema tal como lo dejaba la versión 12: sin las siete columnas.
    with engine.begin() as conn:
        _quitar_columnas_13_y_14(conn)
        conn.execute(
            text(
                "INSERT INTO project (name, domain, task_type, favorable_label, store_features, "
                "explain_auto, explain_method, is_demo, deployment_stage, acepta_feedback, "
                "created_at, updated_at) VALUES ('viejo', 'libre', 'binary', 1, 1, 1, "
                "'permutation', 0, 'desarrollo', 1, '2026-10-01', '2026-10-01')"
            )
        )
    for tabla, columnas in _COLUMNAS_13.items():
        assert not set(columnas) & _columnas(engine, tabla)
    assert current_version(engine) == 12
    assert migrate(engine, ruta) == target_version() == 15
    for tabla, columnas in _COLUMNAS_13.items():
        assert set(columnas) <= _columnas(engine, tabla), tabla
    with engine.connect() as conn:
        fila = conn.execute(text("SELECT task_type, classes_json FROM project")).one()
    assert tuple(fila) == ("binary", None)
    # Idempotente.
    assert migrate(engine, ruta) == 15


def test_una_base_parcial_sin_las_tablas_no_rompe(tmp_path: Path):
    ruta = tmp_path / "parcial.db"
    engine = make_engine(ruta)
    from vigia.app.migrations import _migracion_13

    with engine.begin() as conn:
        _migracion_13(conn)  # ninguna tabla existe: no toca nada


# ---------------------------------------------------------------------------
# La favorable de texto en binario
# ---------------------------------------------------------------------------


def test_favorable_de_texto_en_binario_se_enseña_como_texto(client: TestClient):
    resp = _crear(client, name="r4-favorable-si", mapping_template={"favorable_label": "Sí"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["favorable_label"] == "Sí"
    leido = client.get(f"/api/projects/{resp.json()['id']}").json()
    assert leido["favorable_label"] == "Sí"
    listado = client.get("/api/projects").json()["items"][0]
    assert listado["favorable_label"] == "Sí"


def test_la_favorable_sincronizada_con_la_linea_base_de_texto_se_lee_de_la_plantilla(
    client: TestClient,
):
    p = _crear(client, name="r4-favorable-sync").json()
    filas = "id,prediction,label\n" + "\n".join(
        f"{i},{'Sí' if i % 2 else 'No'},{'Sí' if i % 3 else 'No'}" for i in range(40)
    )
    sub = d.subir(client, p["id"], filas.encode(), rol="baseline")
    resp = d.mapear(
        client,
        sub["dataset"]["id"],
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": "Sí"},
    )
    assert resp.status_code == 200, resp.text
    trabajo = d.ingerir(client, sub["dataset"]["id"], p["active_version_id"])
    assert trabajo["status"] == "terminado", trabajo
    assert client.get(f"/api/projects/{p['id']}").json()["favorable_label"] == "Sí"


# ---------------------------------------------------------------------------
# Títulos del diario
# ---------------------------------------------------------------------------


def _titulos(client: TestClient, proyecto_id: int, accion: str) -> list[str]:
    eventos = client.get("/api/events", params={"project_id": proyecto_id, "limit": 500}).json()["items"]
    return [e["titulo"] for e in eventos if e["action"] == accion]


def test_el_alta_multiclase_deja_el_tipo_en_el_titulo(client: TestClient):
    p = _crear(client, name="r4-titulo-alta", task_type="multiclass", classes=["a", "b", "c"]).json()
    titulos = _titulos(client, p["id"], "proyecto.creado")
    assert titulos and "Tipo de tarea: multiclase" in titulos[0]


def test_el_alta_binaria_no_cambia_el_titulo(client: TestClient):
    p = _crear(client, name="r4-titulo-bin").json()
    titulos = _titulos(client, p["id"], "proyecto.creado")
    assert titulos == ["Proyecto «r4-titulo-bin» creado"]


def test_varias_favorables_se_nombran_en_plural():
    from vigia.app.events_titulos import _titulo_favorable

    assert _titulo_favorable(["A", "B"]) == "Clases favorables fijadas: A, B"
    assert _titulo_favorable(["A"]) == "Clase favorable del modelo fijada en «A»"
    assert _titulo_favorable(1) == "Clase favorable del modelo fijada en «1»"


# ---------------------------------------------------------------------------
# La métrica principal de calidad depende del tipo
# ---------------------------------------------------------------------------


def test_la_metrica_principal_por_defecto_depende_del_tipo(client: TestClient):
    binario = _crear(client, name="r4-metrica-bin").json()
    multi = _crear(client, name="r4-metrica-multi", task_type="multiclass").json()
    assert client.get(f"/api/projects/{binario['id']}/state").json()["quality_primary_metric"] == "accuracy"
    assert client.get(f"/api/projects/{multi['id']}/state").json()["quality_primary_metric"] == "f1_measure"


def test_una_metrica_principal_fijada_manda_tambien_en_multiclase(client: TestClient):
    multi = _crear(client, name="r4-metrica-fijada", task_type="multiclass").json()
    calidad = next(m for m in multi["monitors"] if m["type"] == "quality")
    resp = client.patch(
        f"/api/monitors/{calidad['id']}",
        json={"actor": "miguel", "motivo": "fijar", "config": {"primary_metric": "accuracy"}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert client.get(f"/api/projects/{multi['id']}/state").json()["quality_primary_metric"] == "accuracy"


def test_la_ingesta_valida_el_mapeo_resuelto_y_no_da_500(client: TestClient):
    """Cuarto punto de entrada (interfaz §2.5): un mapeo guardado que ya no cumple las
    reglas del tipo (aquí, dos favorables en binario, escrito a mano en la base) falla
    la ingesta con el mensaje en español, no con un 500."""
    from vigia.app.models import Dataset

    p = _crear(client, name="r4-ingesta-valida").json()
    sub = d.subir(client, p["id"], b"id,prediction,label\n1,0,0\n2,1,1\n", rol="production")
    d.mapear(
        client,
        sub["dataset"]["id"],
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": 1},
    )
    with Session(client.app.state.engine) as s:
        ds = s.get(Dataset, sub["dataset"]["id"])
        ds.mapping_json = {**ds.mapping_json, "favorable_label": [0, 1]}
        s.add(ds)
        s.commit()
    resp = client.post(
        f"/api/datasets/{sub['dataset']['id']}/ingest",
        json={"model_version_id": p["active_version_id"], "evaluate": False},
    )
    assert resp.status_code < 500, resp.text
    cuerpo = resp.json()
    assert cuerpo.get("status") == "error" and "multiclase" in (cuerpo.get("error") or ""), cuerpo


# ---------------------------------------------------------------------------
# Bordes del alta, positive_label entrante y la 13 sobre la demo
# ---------------------------------------------------------------------------


def test_multiclase_acepta_tres_y_veinte_clases(client: TestClient):
    for k in (3, 20):
        resp = _crear(
            client, name=f"r4-multi-{k}", task_type="multiclass", classes=[f"c{i}" for i in range(k)]
        )
        assert resp.status_code == 200, (k, resp.text)
        assert len(resp.json()["classes"]) == k


def test_un_positive_label_nuevo_en_el_patch_deja_el_aviso(client: TestClient):
    p = _crear(client, name="r4-pos-patch-nuevo").json()
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={
            "actor": "miguel",
            "motivo": "plantilla",
            "mapping_template": {"favorable_label": 1, "positive_label": "permitido", "id_col": "id"},
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    avisos = _eventos(client, "proyecto.positive_label_ignorado")
    assert len(avisos) == 1 and avisos[0].before_json == {"positive_label": "permitido"}
    assert "positive_label" not in resp.json()["mapping_template_json"]
    # Sin positive_label en el cuerpo, no hay aviso nuevo.
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={"actor": "miguel", "motivo": "otra vez", "mapping_template": {"favorable_label": 1, "id_col": "id"}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert len(_eventos(client, "proyecto.positive_label_ignorado")) == 1


def test_la_migracion_13_sobre_la_demo_completa_conserva_eventos_y_alertas(client: TestClient):
    """Una base con la demo entera migra con los mismos eventos y
    alertas. La base se deja con el esquema de la 12 quitando las siete columnas."""
    from vigia.app.models import Alert

    resp = client.post(
        "/api/demo/runs",
        json={"scenario_key": "timeline_completo", "with_human": False},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    resp = client.post(f"/api/demo/runs/{run['id']}/play", headers=actor_headers("miguel"))
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
        _quitar_columnas_13_y_14(conn)
    assert current_version(engine) == 12
    assert migrate(engine, Path(engine.url.database)) == 15
    assert huella() == antes
    for tabla, columnas in _COLUMNAS_13.items():
        assert set(columnas) <= _columnas(engine, tabla), tabla
