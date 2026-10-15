"""Tools de proyectos, datasets y monitores."""

from __future__ import annotations

from pathlib import Path


async def test_upload_dataset(tmp_path: Path, proyecto_demo, sesion_mcp, llamar_tool):
    """Única de las 17 tools sin test. Sube un CSV real (mismo formato
    mínimo que `tests/api/test_datasets.py::_dataset_mapeado`), fija su
    mapeo y comprueba que ingiere: `dataset` con su id y `ingest_job`
    terminado."""
    csv = tmp_path / "nuevo.csv"
    csv.write_bytes(b"id,prediction,label,Age\n1,1,1,30\n2,0,0,45\n")
    # `id_col` obligatorio en lotes si el modelo acepta feedback.
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "feature_cols": ["Age"],
    }

    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "upload_dataset",
            {
                "project_id": proyecto_demo["project_id"],
                "file_path": str(csv),
                "kind": "combined",
                "role": "production",
                "mapping": mapping,
            },
        )

    assert not error, resultado
    assert resultado["dataset"]["id"] > 0
    assert resultado["dataset"]["kind"] == "combined"
    assert resultado["ingest_job"]["status"] == "terminado", resultado["ingest_job"]


async def test_list_projects(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(sesion, "list_projects", {})
    assert not error
    assert resultado["total"] >= 1


async def test_create_project(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion, "create_project", {"name": "Proyecto MCP", "favorable_label": 1, "deployment_stage": "desarrollo"}
        )
    assert not error
    assert resultado["name"] == "Proyecto MCP"


async def test_create_project_con_plantilla_y_acepta_feedback(sesion_mcp, llamar_tool):
    """La tool acepta la plantilla de mapeo y `acepta_feedback`."""
    plantilla = {"favorable_label": 0, "id_col": "id", "feature_cols": ["edad"]}
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "create_project",
            {
                "name": "Proyecto MCP con plantilla",
                "deployment_stage": "validacion",
                "domain": "digestivo",
                "mapping_template": plantilla,
                "acepta_feedback": False,
                "fairness_interval_method": "ventanas",
            },
        )
    assert not error, resultado
    guardada = resultado["mapping_template_json"]
    assert guardada["favorable_label"] == 0
    assert guardada["id_col"] == "id"
    assert guardada["feature_cols"] == ["edad"]
    assert resultado["acepta_feedback"] is False
    assert resultado["versions"][0]["fairness_interval_method"] == "ventanas"


async def test_set_monitor(sesion_mcp, proyecto_demo, cliente_http, llamar_tool):
    monitores = await cliente_http.get(f"/api/projects/{proyecto_demo['project_id']}/monitors")
    monitor_id = monitores.json()["items"][0]["id"]
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "set_monitor",
            {"monitor_id": monitor_id, "actor": "claude-code-tests", "motivo": "prueba MCP", "enabled": True},
        )
    assert not error
    assert resultado["monitor"]["id"] == monitor_id


async def _monitor_calidad(cliente_http, project_id: int) -> dict:
    monitores = (await cliente_http.get(f"/api/projects/{project_id}/monitors")).json()["items"]
    return next(m for m in monitores if m["type"] == "quality")


async def test_set_monitor_fusiona_umbrales(sesion_mcp, proyecto_demo, cliente_http, llamar_tool):
    """Los umbrales nombrados cambian y los no nombrados se conservan."""
    monitor = await _monitor_calidad(cliente_http, proyecto_demo["project_id"])
    antes = monitor["thresholds"]["thresholds"]
    assert len(antes) >= 2
    nombrado, resto = antes[0], antes[1:]
    nuevo = {"metric_key": nombrado["metric_key"], "kind": nombrado["kind"], "value": 0.123,
             "origen": "criterio_clinico", "nota": "ficha"}
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "set_monitor",
            {"monitor_id": monitor["id"], "actor": "claude-code-tests", "motivo": "ficha del monitor",
             "thresholds": {"thresholds": [nuevo]}},
        )
    assert not error, resultado
    despues = (await cliente_http.get(f"/api/monitors/{monitor['id']}")).json()["thresholds"]["thresholds"]
    assert len(despues) == len(antes)
    assert despues[0] == nuevo
    assert despues[1:] == resto


async def test_set_monitor_reemplazar_umbrales(sesion_mcp, proyecto_demo, cliente_http, llamar_tool):
    """Con `reemplazar_umbrales=true` la lista es exactamente la que se manda."""
    monitor = await _monitor_calidad(cliente_http, proyecto_demo["project_id"])
    unico = {"metric_key": monitor["thresholds"]["thresholds"][0]["metric_key"], "kind": "lower_limit", "value": 0.5}
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "set_monitor",
            {"monitor_id": monitor["id"], "actor": "claude-code-tests", "motivo": "quitar umbrales",
             "thresholds": {"thresholds": [unico]}, "reemplazar_umbrales": True},
        )
    assert not error, resultado
    despues = (await cliente_http.get(f"/api/monitors/{monitor['id']}")).json()["thresholds"]["thresholds"]
    # La API sirve un umbral sin origen como de fábrica.
    assert [{k: t[k] for k in unico} for t in despues] == [unico]


async def test_set_mapping_template(sesion_mcp, proyecto_demo, cliente_http, llamar_tool):
    """La plantilla se cambia por el MCP sobre
    `PATCH /projects/{id}`, la sustituye entera y deja un evento del agente."""
    project_id = proyecto_demo["project_id"]
    plantilla = {"favorable_label": 1, "id_col": "id", "feature_cols": ["edad", "importe"]}
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "set_mapping_template",
            {
                "project_id": project_id,
                "mapping_template": plantilla,
                "actor": "claude-code-tests",
                "motivo": "rehacer el mapeo sin la columna de fecha",
            },
        )
    assert not error, resultado
    guardada = resultado["mapping_template_json"]
    assert guardada["id_col"] == "id"
    assert guardada["feature_cols"] == ["edad", "importe"]

    leida = (await cliente_http.get(f"/api/projects/{project_id}")).json()
    assert leida["mapping_template_json"]["feature_cols"] == ["edad", "importe"]
    eventos = (
        await cliente_http.get("/api/events", params={"object_type": "project", "object_id": project_id})
    ).json()["items"]
    agente = next(
        e for e in eventos if e["actor_kind"] == "agente" and e["action"] == "proyecto.plantilla_actualizada"
    )
    assert agente["actor_id"] == "claude-code-tests"


async def test_set_mapping_template_rechaza_una_plantilla_invalida(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, _resultado = await llamar_tool(
            sesion,
            "set_mapping_template",
            {
                "project_id": proyecto_demo["project_id"],
                "mapping_template": {"columna_que_no_existe": "x"},
                "actor": "claude-code-tests",
                "motivo": "plantilla con un campo desconocido",
            },
        )
    assert error
