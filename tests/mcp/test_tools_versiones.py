"""Las tools de versiones, `model_version_id` en `upload_dataset`
y `get_measurements`, y `deployment_stage` obligatorio en `create_project`."""

from __future__ import annotations

CSV = (
    "id,prediction,label,Age\n"
    + "".join(f"{i},{i % 2},{(i + (i % 3 == 0)) % 2},{30 + i}\n" for i in range(1, 41))
).encode()
MAPEO = {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "feature_cols": ["Age"],
         "favorable_label": 1}


async def _proyecto(llamar_tool, sesion, nombre: str = "versiones-mcp") -> dict:
    error, proyecto = await llamar_tool(
        sesion, "create_project", {"name": nombre, "deployment_stage": "validacion"}
    )
    assert not error, proyecto
    return proyecto


async def _v2(llamar_tool, sesion, proyecto: dict) -> dict:
    error, v2 = await llamar_tool(
        sesion,
        "create_version",
        {"project_id": proyecto["id"], "label": "v2", "motivo": "reentrenado con datos nuevos"},
    )
    assert not error, v2
    return v2


async def _eventos_agente(cliente_http, project_id: int) -> list[dict]:
    resp = await cliente_http.get(
        "/api/events", params={"project_id": project_id, "actor_kind": "agente", "limit": 500}
    )
    return resp.json()["items"]


# --- list_versions y create_version ------------------------------------


async def test_list_versions(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        proyecto = await _proyecto(llamar_tool, sesion)
        error, lista = await llamar_tool(sesion, "list_versions", {"project_id": proyecto["id"]})
    assert not error, lista
    assert set(lista) == {"project_id", "active_version_id", "versions"}
    assert lista["active_version_id"] == proyecto["active_version_id"]
    (v1,) = lista["versions"]
    assert v1["is_active"] is True
    for clave in ("baseline_batch_id", "artifact_kind", "label"):
        assert clave in v1


async def test_create_version_deja_evento_del_agente(sesion_mcp, llamar_tool, cliente_http):
    async with sesion_mcp as sesion:
        proyecto = await _proyecto(llamar_tool, sesion)
        v2 = await _v2(llamar_tool, sesion, proyecto)
        _e, lista = await llamar_tool(sesion, "list_versions", {"project_id": proyecto["id"]})
    assert v2["label"] == "v2" and v2["is_active"] is False
    assert [v["label"] for v in lista["versions"]] == ["v1", "v2"]
    eventos = await _eventos_agente(cliente_http, proyecto["id"])
    assert any(e["object_type"] == "model_version" and e["object_id"] == v2["id"] for e in eventos)


# --- upload_dataset en una versión no activa --------------------------


async def test_upload_dataset_en_v2_sin_activarla_y_congelar_linea_base(
    sesion_mcp, llamar_tool, cliente_http, tmp_path
):
    csv = tmp_path / "base-v2.csv"
    csv.write_bytes(CSV)
    async with sesion_mcp as sesion:
        proyecto = await _proyecto(llamar_tool, sesion)
        v2 = await _v2(llamar_tool, sesion, proyecto)
        error, subida = await llamar_tool(
            sesion,
            "upload_dataset",
            {
                "project_id": proyecto["id"],
                "file_path": str(csv),
                "kind": "combined",
                "role": "baseline",
                "mapping": MAPEO,
                "model_version_id": v2["id"],
            },
        )
        assert not error, subida
        assert subida["ingest_job"]["status"] == "terminado", subida
        batch_id = subida["ingest_job"]["result"]["batch_id"]
        lote = (await cliente_http.get(f"/api/batches/{batch_id}")).json()
        assert lote["model_version_id"] == v2["id"]
        solo_v2 = (
            await cliente_http.get(
                f"/api/projects/{proyecto['id']}/batches", params={"model_version_id": v2["id"]}
            )
        ).json()
        assert [b["id"] for b in solo_v2["items"]] == [batch_id]
        _e, lista = await llamar_tool(sesion, "list_versions", {"project_id": proyecto["id"]})
        assert lista["active_version_id"] == proyecto["active_version_id"]  # v2 sigue sin activar

        # La ingesta de la línea base ya la congela en la v2.
        assert next(v for v in lista["versions"] if v["id"] == v2["id"])["baseline_batch_id"] == batch_id
        error, texto = await llamar_tool(
            sesion,
            "freeze_baseline",
            {"version_id": v2["id"], "batch_id": batch_id, "motivo": "otra vez"},
        )
        assert error and texto.startswith("409:") and "Qué hacer" in texto

        # Una v3 con un lote de producción: freeze_baseline lo congela como línea base.
        error, v3 = await llamar_tool(
            sesion, "create_version", {"project_id": proyecto["id"], "label": "v3", "motivo": "prueba"}
        )
        assert not error, v3
        error, lote3 = await llamar_tool(
            sesion,
            "upload_dataset",
            {
                "project_id": proyecto["id"],
                "file_path": str(csv),
                "kind": "combined",
                "role": "production",
                "mapping": MAPEO,
                "model_version_id": v3["id"],
            },
        )
        assert not error, lote3
        lote3_id = lote3["ingest_job"]["result"]["batch_id"]
        error, congelada = await llamar_tool(
            sesion,
            "freeze_baseline",
            {"version_id": v3["id"], "batch_id": lote3_id, "motivo": "línea base de la v3"},
        )
        assert not error, congelada
        assert congelada["baseline_batch_id"] == lote3_id and congelada["frozen_at"]

        # Por el MCP: la serie de medidas filtrada por versión.
        error, evaluada = await llamar_tool(sesion, "run_evaluation", {"batch_id": batch_id})
        assert not error, evaluada
        error, de_v2 = await llamar_tool(
            sesion,
            "get_measurements",
            {
                "project_id": proyecto["id"],
                "monitor_type": "quality",
                "metric_key": "accuracy",
                "model_version_id": v2["id"],
            },
        )
        assert not error, de_v2
        error, de_v1 = await llamar_tool(
            sesion,
            "get_measurements",
            {
                "project_id": proyecto["id"],
                "monitor_type": "quality",
                "metric_key": "accuracy",
                "model_version_id": proyecto["active_version_id"],
            },
        )
        assert not error, de_v1
    assert de_v1["total"] == 0
    assert de_v2["total"] > 0
    assert all(p["model_version_id"] == v2["id"] for p in de_v2["items"])
    eventos = await _eventos_agente(cliente_http, proyecto["id"])
    assert any(e["action"].startswith("model_version.") or e["object_type"] == "model_version"
               for e in eventos)


async def test_activate_version_con_motivo(sesion_mcp, llamar_tool, cliente_http):
    async with sesion_mcp as sesion:
        proyecto = await _proyecto(llamar_tool, sesion)
        v2 = await _v2(llamar_tool, sesion, proyecto)
        error, activada = await llamar_tool(
            sesion, "activate_version", {"version_id": v2["id"], "motivo": "pasa a producción"}
        )
        assert not error, activada
        _e, lista = await llamar_tool(sesion, "list_versions", {"project_id": proyecto["id"]})
    assert activada["is_active"] is True
    assert lista["active_version_id"] == v2["id"]
    eventos = await _eventos_agente(cliente_http, proyecto["id"])
    activacion = next(e for e in eventos if e["action"] == "version.activada")
    assert activacion["actor_id"] == "claude-code-tests"


# --- deployment_stage obligatorio -------------------------------------


async def test_create_project_sin_etapa_da_error_legible(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(sesion, "create_project", {"name": "sin etapa"})
    assert error
    assert "deployment_stage" in str(texto) and "pregunta al usuario" in str(texto)


async def test_create_project_no_admite_demo_y_admite_las_tres_etapas(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(
            sesion, "create_project", {"name": "demo", "deployment_stage": "demo"}
        )
        assert error and "demo" in str(texto)
        for etapa in ("desarrollo", "validacion", "produccion"):
            error, proyecto = await llamar_tool(
                sesion, "create_project", {"name": f"etapa {etapa}", "deployment_stage": etapa}
            )
            assert not error, proyecto
            assert proyecto["deployment_stage"] == etapa
