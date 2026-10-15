"""Actor de la entrada y `actor_detalle`, origen `politica_organizacion`,
`instancia` en `get_settings`, títulos de prompts y recursos, claves del mapeo,
revisión duplicada y `export_report` estructurado."""

from __future__ import annotations

import pytest

from vigia.core.schema import ColumnMapping, MappingTemplate
from vigia.mcp.client import (
    CLAVES_COLUMN_MAPPING,
    CLAVES_MAPPING_TEMPLATE,
    VigiaClient,
    _texto_detalle,
)

ACTOR = "claude-code-tests"
HUMANO = {"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"}


async def _eventos(cliente_http, project_id: int, accion: str) -> list[dict]:
    resp = await cliente_http.get(
        "/api/events", params={"project_id": project_id, "actor_kind": "agente", "limit": 500}
    )
    return [e for e in resp.json()["items"] if e["action"] == accion]


async def _monitor_calidad(cliente_http, project_id: int) -> dict:
    monitores = (await cliente_http.get(f"/api/projects/{project_id}/monitors")).json()["items"]
    return next(m for m in monitores if m["type"] == "quality")


# --- Actor de la entrada y actor_detalle --------------------------------


def test_cuerpo_actor_usa_el_de_la_entrada():
    client = VigiaClient(url="http://x", actor="claude-desktop")
    assert client.cuerpo_actor(None) == {"actor": "claude-desktop"}
    assert client.cuerpo_actor("claude-desktop") == {"actor": "claude-desktop"}
    assert client.cuerpo_actor("  ") == {"actor": "claude-desktop"}
    assert client.cuerpo_actor("Claude (por encargo del usuario)") == {
        "actor": "claude-desktop",
        "actor_detalle": "Claude (por encargo del usuario)",
    }
    largo = client.cuerpo_actor("x" * 500)
    assert len(largo["actor_detalle"]) == 200


async def test_act_on_alert_firma_con_el_actor_de_la_entrada(sesion_mcp, proyecto_demo, cliente_http, llamar_tool):
    async with sesion_mcp as sesion:
        error, res = await llamar_tool(
            sesion,
            "act_on_alert",
            {
                "alert_id": proyecto_demo["alert_id"],
                "accion": "acknowledge",
                "actor": "Claude (por encargo del usuario)",
                "motivo": "reconocida por encargo",
            },
        )
    assert not error, res
    eventos = await _eventos(cliente_http, proyecto_demo["project_id"], "alerta.reconocida")
    assert eventos, "falta el evento alerta.reconocida"
    evento = eventos[0]
    assert evento["actor_id"] == ACTOR
    assert evento["after"]["actor_detalle"] == "Claude (por encargo del usuario)"


async def test_sin_actor_no_hay_detalle_y_el_actor_es_el_de_la_entrada(
    sesion_mcp, proyecto_demo, cliente_http, llamar_tool
):
    async with sesion_mcp as sesion:
        error, res = await llamar_tool(
            sesion,
            "create_risk",
            {
                "project_id": proyecto_demo["project_id"],
                "title": "Riesgo sin actor",
                "motivo": "alta sin actor",
                "impact_level": 3,
                "probability_level": 2,
            },
        )
        assert not error, res
        error, res2 = await llamar_tool(
            sesion,
            "update_risk",
            {
                "risk_id": res["id"],
                "accion": "seguimiento",
                "motivo": "seguimiento",
                "actor": "Claude (por encargo del usuario)",
            },
        )
        assert not error, res2
    eventos = (
        await cliente_http.get(
            "/api/events", params={"project_id": proyecto_demo["project_id"], "actor_kind": "agente", "limit": 500}
        )
    ).json()["items"]
    del_riesgo = [e for e in eventos if e["object_type"] == "risk" and e["object_id"] == res["id"]]
    assert del_riesgo
    assert {e["actor_id"] for e in del_riesgo} == {ACTOR}
    con_detalle = [e for e in del_riesgo if (e["after"] or {}).get("actor_detalle")]
    sin_detalle = [e for e in del_riesgo if not (e["after"] or {}).get("actor_detalle")]
    assert len(con_detalle) == 1, "solo el update_risk con actor distinto deja actor_detalle"
    assert con_detalle[0]["after"]["actor_detalle"] == "Claude (por encargo del usuario)"
    assert sin_detalle, "el alta (sin actor) no deja actor_detalle"


async def test_set_monitor_con_actor_distinto_deja_detalle(sesion_mcp, proyecto_demo, cliente_http, llamar_tool):
    monitor = await _monitor_calidad(cliente_http, proyecto_demo["project_id"])
    async with sesion_mcp as sesion:
        error, res = await llamar_tool(
            sesion,
            "set_monitor",
            {"monitor_id": monitor["id"], "actor": "otro nombre", "motivo": "prueba", "enabled": True},
        )
    assert not error, res
    eventos = (
        await cliente_http.get(
            "/api/events", params={"object_type": "monitor", "object_id": monitor["id"], "limit": 50}
        )
    ).json()["items"]
    agente = [e for e in eventos if e["actor_kind"] == "agente"]
    assert agente and agente[0]["actor_id"] == ACTOR
    assert agente[0]["after"]["actor_detalle"] == "otro nombre"


async def test_la_interfaz_humana_no_cambia(cliente_http, proyecto_demo):
    """Un cuerpo sin `actor_detalle` no deja rastro en el diario; el humano firma con su actor."""
    resp = await cliente_http.post(
        f"/api/alerts/{proyecto_demo['alert_id']}/acknowledge",
        json={"actor": "miguel", "motivo": "a mano"},
        headers=HUMANO,
    )
    assert resp.status_code in (200, 409), resp.text
    if resp.status_code == 200:
        eventos = (
            await cliente_http.get("/api/events", params={"project_id": proyecto_demo["project_id"], "limit": 500})
        ).json()["items"]
        propios = [e for e in eventos if e["actor_id"] == "miguel" and e["action"] == "alerta.reconocida"]
        assert propios and "actor_detalle" not in (propios[0]["after"] or {})


async def test_actor_detalle_demasiado_largo_da_422(cliente_http, proyecto_demo):
    resp = await cliente_http.post(
        f"/api/alerts/{proyecto_demo['alert_id']}/close",
        json={"actor": "miguel", "motivo": "m", "actor_detalle": "x" * 201},
        headers=HUMANO,
    )
    assert resp.status_code == 422


# --- Origen politica_organizacion ---------------------------------------


async def test_politica_organizacion_no_es_de_fabrica(sesion_mcp, proyecto_demo, cliente_http, llamar_tool):
    monitor = await _monitor_calidad(cliente_http, proyecto_demo["project_id"])
    base = monitor["thresholds"]["thresholds"][0]
    nuevo = {
        "metric_key": base["metric_key"],
        "kind": base["kind"],
        "value": 0.66,
        "origen": "politica_organizacion",
        "nota": "política interna de calidad",
    }
    async with sesion_mcp as sesion:
        error, res = await llamar_tool(
            sesion,
            "set_monitor",
            {"monitor_id": monitor["id"], "motivo": "política", "thresholds": {"thresholds": [nuevo]}},
        )
        assert not error, res
        error, propuesta = await llamar_tool(
            sesion, "get_threshold_proposal", {"project_id": proyecto_demo["project_id"]}
        )
    assert not error, propuesta
    guardado = (await cliente_http.get(f"/api/monitors/{monitor['id']}")).json()["thresholds"]["thresholds"][0]
    assert guardado["origen"] == "politica_organizacion"
    filas = [
        p
        for m in propuesta["monitors"]
        for p in m["propuestas"]
        if p["metric_key"] == nuevo["metric_key"] and p["kind"] == nuevo["kind"]
    ]
    assert filas
    assert filas[0]["origen_actual"] == "politica_organizacion"
    assert filas[0]["aviso"] is None


async def test_docstrings_de_origen_y_propuesta(sesion_mcp):
    async with sesion_mcp as sesion:
        tools = {t.name: t.description for t in (await sesion.list_tools()).tools}
    assert "politica_organizacion" in tools["set_monitor"]
    assert "politica_organizacion" in tools["get_threshold_proposal"]


# --- Instancia en get_settings ------------------------------------------


async def test_get_settings_trae_la_instancia(sesion_mcp, llamar_tool, data_dir):
    async with sesion_mcp as sesion:
        error, res = await llamar_tool(sesion, "get_settings", {})
    assert not error, res
    assert "mcp_token" in res or "puerto" in res or res  # los ajustes de siempre siguen ahí
    instancia = res["instancia"]
    assert set(instancia) == {"url_base", "puerto_en_uso", "data_dir", "version"}
    assert instancia["url_base"] == "http://vigia"
    assert instancia["puerto_en_uso"] == 8765  # `app.state.port` del fixture
    assert instancia["data_dir"] == str(data_dir)
    assert instancia["version"]


def test_base_url_publica():
    assert VigiaClient(url="http://127.0.0.1:8123/").base_url == "http://127.0.0.1:8123"


# --- Títulos con tilde ----------------------------------------------------


async def test_prompts_y_recursos_llevan_titulo_con_tilde(sesion_mcp):
    async with sesion_mcp as sesion:
        prompts = {p.name: p.title for p in (await sesion.list_prompts()).prompts}
        recursos = {str(r.uri): r.title for r in (await sesion.list_resources()).resources}
        plantillas = {t.uriTemplate: t.title for t in (await sesion.list_resource_templates()).resourceTemplates}
    assert prompts["diagnostico_de_alerta"] == "Análisis de alerta"
    assert all(prompts.values()), prompts
    assert recursos["presentacion://"] == "Presentación"
    assert recursos["guia://uso"] == "Guía de uso"
    assert all(recursos.values()), recursos
    assert all(plantillas.values()), plantillas


# --- Claves del mapeo ------------------------------------------------------


def test_claves_de_mapeo_coinciden_con_los_modelos():
    assert set(CLAVES_MAPPING_TEMPLATE) == set(MappingTemplate.model_fields)
    assert set(CLAVES_COLUMN_MAPPING) == set(ColumnMapping.model_fields)


def test_ejemplos_de_los_docstrings_son_validos():
    MappingTemplate.model_validate(
        {
            "id_col": "patient_id",
            "prediction_col": "pred",
            "label_col": "y",
            "feature_cols": ["edad", "crp"],
            "protected_attr_col": "edad",
            "protected_kind": "numeric_ranges",
            "unpriv_groups": [[65, 120]],
            "priv_groups": [[0, 64]],
        }
    )
    ColumnMapping.model_validate(
        {"prediction_col": "pred", "label_col": "y", "id_col": "id", "feature_cols": ["edad", "crp"]}
    )


def test_extra_forbidden_lista_las_claves_validas():
    detalle = [
        {"type": "extra_forbidden", "loc": ["body", "mapping_template", "foo"], "msg": "Extra inputs are not permitted"}
    ]
    texto = _texto_detalle(detalle)
    assert "mapping_template.foo" in texto
    assert "claves válidas de mapping_template:" in texto
    assert all(c in texto for c in CLAVES_MAPPING_TEMPLATE)
    detalle_mapeo = [{"type": "extra_forbidden", "loc": ["body", "mapping", "positive_label"], "msg": "x"}]
    assert "claves válidas de mapping: " in _texto_detalle(detalle_mapeo)
    otro = [{"type": "extra_forbidden", "loc": ["body", "otra", "cosa"], "msg": "x"}]
    assert "claves válidas" not in _texto_detalle(otro)
    solo_tipo = [{"type": "missing", "loc": ["body", "mapping_template", "id_col"], "msg": "x"}]
    assert "claves válidas" not in _texto_detalle(solo_tipo)


async def test_set_mapping_template_con_clave_ajena_lista_las_validas(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(
            sesion,
            "set_mapping_template",
            {
                "project_id": proyecto_demo["project_id"],
                "mapping_template": {"columna_que_no_existe": "x"},
                "motivo": "clave ajena",
            },
        )
    assert error
    assert str(texto).startswith("422")
    assert "claves válidas de mapping_template" in str(texto)


async def test_docstrings_de_mapeo_y_etapa(sesion_mcp):
    async with sesion_mcp as sesion:
        tools = {t.name: t.description for t in (await sesion.list_tools()).tools}
    for nombre in ("create_project", "set_mapping_template"):
        assert all(c in tools[nombre] for c in CLAVES_MAPPING_TEMPLATE), nombre
    assert all(c in tools["upload_dataset"] for c in CLAVES_COLUMN_MAPPING)
    assert "produccion" in tools["create_project"] and "desarrollo" in tools["create_project"]
    for valor in ("baseline", "production", "combined", "payload", "feedback"):
        assert valor in tools["upload_dataset"]
    assert "create_risk" in tools["act_on_alert"] and "NO crea" in tools["act_on_alert"]


# --- Revisión duplicada ------------------------------------------------------


async def test_run_dossier_review_avisa_de_una_revision_previa(sesion_mcp, proyecto_demo, cliente_http, llamar_tool):
    creado = await cliente_http.post(
        f"/api/projects/{proyecto_demo['project_id']}/dossiers",
        json={"actor": "miguel", "motivo": "dossier", "profile": {"objetivo": "prueba"}},
        headers=HUMANO,
    )
    assert creado.status_code == 200, creado.text
    dossier_id = creado.json()["id"]
    args = {"dossier_id": dossier_id, "motivo": "revisión", "approach": "b0"}

    async def revisiones() -> list[dict]:
        return (await cliente_http.get(f"/api/dossiers/{dossier_id}")).json()["reviews"]

    async with sesion_mcp as sesion:
        error, primera = await llamar_tool(sesion, "run_dossier_review", args)
        assert not error, primera
        assert primera.get("status") != "ya_existe"
        assert len(await revisiones()) == 1
        error, segunda = await llamar_tool(sesion, "run_dossier_review", args)
        assert not error, segunda
        assert segunda["status"] == "ya_existe"
        assert segunda["revision"]["approach"] == "b0"
        assert "forzar" in segunda["aviso"]
        assert len(await revisiones()) == 1
        error, forzada = await llamar_tool(sesion, "run_dossier_review", {**args, "forzar": True})
        assert not error, forzada
        assert forzada.get("status") != "ya_existe"
        assert len(await revisiones()) == 2


# --- export_report estructurado y project_id ---------------------------------


async def test_export_report_devuelve_objeto_estructurado(sesion_mcp, proyecto_demo):
    async with sesion_mcp as sesion:
        crudo = await sesion.call_tool("export_report", {"kind": "diario", "limit": 3})
    assert not crudo.isError
    assert crudo.structuredContent is not None
    assert crudo.structuredContent["devueltos"] == 3
    assert isinstance(crudo.structuredContent["eventos"], list)


async def test_export_report_acota_por_proyecto(sesion_mcp, proyecto_demo, cliente_http, llamar_tool):
    otro = (
        await cliente_http.post("/api/projects", json={"name": "ajeno", "domain": "libre"}, headers=HUMANO)
    ).json()
    async with sesion_mcp as sesion:
        error, todo = await llamar_tool(sesion, "export_report", {"kind": "diario", "limit": 500})
        assert not error, todo
        error, acotado = await llamar_tool(
            sesion, "export_report", {"kind": "diario", "limit": 500, "project_id": proyecto_demo["project_id"]}
        )
        assert not error, acotado
        error, del_otro = await llamar_tool(
            sesion, "export_report", {"kind": "diario", "limit": 500, "project_id": otro["id"]}
        )
        assert not error, del_otro
    assert acotado["total"] < todo["total"]
    assert del_otro["total"] < acotado["total"]
    ids = {e["project_id"] for e in acotado["eventos"]}
    assert ids <= {proyecto_demo["project_id"], None}


@pytest.mark.parametrize("campo", ["role", "kind"])
async def test_upload_dataset_lista_role_y_kind(sesion_mcp, campo):
    async with sesion_mcp as sesion:
        tools = {t.name: t.description for t in (await sesion.list_tools()).tools}
    assert f"`{campo}`" in tools["upload_dataset"]
