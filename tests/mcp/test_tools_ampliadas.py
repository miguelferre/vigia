"""Las 14 tools nuevas con el FastMCP en memoria,
los errores con «qué hacer» y la espera agotada."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from vigia.mcp.client import VigiaClient, VigiaError

USAGE_CSV = Path(__file__).resolve().parents[2] / "data" / "demo" / "usage_logs_demo.csv"

CSV_OUTCOMES = (
    "period,metric_key,value,source\n"
    "2026-01,tasa_derivacion_correcta,0.81,manual\n"
    "2026-02,tasa_derivacion_correcta,0.79,manual\n"
)


async def _eventos_agente(cliente_http, project_id: int) -> list[dict]:
    resp = await cliente_http.get(
        "/api/events", params={"project_id": project_id, "actor_kind": "agente", "limit": 500}
    )
    return resp.json()["items"]


# --- upload_usage_log ---------------------------------------------------


async def test_upload_usage_log(sesion_mcp, llamar_tool, cliente_http):
    proyecto = (await cliente_http.post(
        "/api/projects", json={"name": "uso-mcp", "domain": "reuma"},
        headers={"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"},
    )).json()
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion,
            "upload_usage_log",
            {"project_id": proyecto["id"], "file_path": str(USAGE_CSV), "valor_favorable": "refer"},
        )
    assert not error, resultado
    assert resultado["n_rows"] > 0
    assert resultado["valor_favorable"] == "refer"
    assert "comprobacion_codificacion" in resultado


async def test_upload_usage_log_exige_valor_favorable(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        error, _ = await llamar_tool(
            sesion, "upload_usage_log", {"project_id": 1, "file_path": str(USAGE_CSV)}
        )
        assert error
        error2, resultado2 = await llamar_tool(
            sesion,
            "upload_usage_log",
            {"project_id": 1, "file_path": str(USAGE_CSV), "valor_favorable": "si"},
        )
    assert error2
    assert "valor_favorable no reconocido" in str(resultado2)


# --- Alertas cruzadas ---------------------------------------------


async def test_evaluate_cross_y_get_cross_latest(sesion_mcp, proyecto_demo, llamar_tool):
    pid = proyecto_demo["project_id"]
    async with sesion_mcp as sesion:
        error, job = await llamar_tool(sesion, "evaluate_cross", {"project_id": pid})
        assert not error, job
        assert job["status"] in ("terminado", "en_curso")
        error, ultima = await llamar_tool(sesion, "get_cross_latest", {"project_id": pid})
    assert not error, ultima
    assert isinstance(ultima, dict)


async def test_evaluate_cross_sin_esperar(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, job = await llamar_tool(
            sesion, "evaluate_cross", {"project_id": proyecto_demo["project_id"], "wait": False}
        )
    assert not error, job
    assert job["kind"] == "cruzadas"


# --- Deskilling y overrides ---------------------------------------


async def test_get_deskilling(sesion_mcp, proyecto_demo, llamar_tool):
    pid = proyecto_demo["project_id"]
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(sesion, "get_deskilling", {"project_id": pid})
        assert not error, resultado
        assert "windows" in resultado and resultado["n_windows"] == 4
        error, filtrado = await llamar_tool(
            sesion, "get_deskilling", {"project_id": pid, "n_windows": 2, "subgroup": "no-existe"}
        )
    assert not error, filtrado
    assert filtrado["n_windows"] == 2
    assert filtrado["subgroup"] == "no-existe"


@pytest.mark.parametrize("by", ["subgroup", "phase", "clinician", "profesionales"])
async def test_get_overrides(sesion_mcp, proyecto_demo, llamar_tool, by):
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion, "get_overrides", {"project_id": proyecto_demo["project_id"], "by": by}
        )
    assert not error, resultado
    if by == "profesionales":
        assert "clinicians" in resultado


async def test_get_overrides_agrupacion_invalida(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion, "get_overrides", {"project_id": proyecto_demo["project_id"], "by": "persona"}
        )
    assert error
    assert "by no reconocido" in str(resultado)


# --- Outcomes -----------------------------------------------------


async def test_upload_y_get_outcomes(tmp_path, sesion_mcp, proyecto_demo, llamar_tool, cliente_http):
    pid = proyecto_demo["project_id"]
    csv = tmp_path / "outcomes.csv"
    csv.write_text(CSV_OUTCOMES, encoding="utf-8")
    antes = len(await _eventos_agente(cliente_http, pid))
    async with sesion_mcp as sesion:
        error, subida = await llamar_tool(
            sesion, "upload_outcomes", {"project_id": pid, "file_path": str(csv)}
        )
        assert not error, subida
        assert subida["n_rows"] == 2 and subida["n_creados"] == 2
        error, todos = await llamar_tool(sesion, "get_outcomes", {"project_id": pid})
        assert not error, todos
        assert len(todos["rows"]) >= 2
        error, uno = await llamar_tool(
            sesion, "get_outcomes", {"project_id": pid, "metric_key": "tasa_derivacion_correcta"}
        )
    assert not error, uno
    assert {f["metric_key"] for f in uno["rows"]} == {"tasa_derivacion_correcta"}
    assert len(await _eventos_agente(cliente_http, pid)) > antes


# --- create_dossier -----------------------------------------------------


async def test_create_dossier_manual(sesion_mcp, proyecto_demo, llamar_tool, cliente_http):
    pid = proyecto_demo["project_id"]
    antes = len(await _eventos_agente(cliente_http, pid))
    async with sesion_mcp as sesion:
        error, dossier = await llamar_tool(
            sesion,
            "create_dossier",
            {
                "project_id": pid,
                "actor": "claude-code-tests",
                "motivo": "dossier desde el MCP",
                "system_name": "Modelo de prueba",
                "domain": "reuma",
                "profile": {"uso": "triaje"},
                "experience": {"formacion": "ninguna"},
                "inventory": {"modelo": "v1"},
            },
        )
    assert not error, dossier
    assert dossier["id"] > 0
    assert len(await _eventos_agente(cliente_http, pid)) > antes


async def test_create_dossier_importa_el_json_del_paquete(tmp_path, sesion_mcp, proyecto_demo, llamar_tool):
    """Ruta `RUTA_DOSSIER_IMPORT`."""
    fichero = tmp_path / "dossier.json"
    fichero.write_text(
        json.dumps(
            {
                "system_name": "Modelo importado",
                "domain": "reuma",
                "summary": "resumen",
                "sources": [{"id": "s1", "kind": "document", "label": "Perfil", "content": "texto"}],
            }
        ),
        encoding="utf-8",
    )
    async with sesion_mcp as sesion:
        error, dossier = await llamar_tool(
            sesion,
            "create_dossier",
            {
                "project_id": proyecto_demo["project_id"],
                "actor": "claude-code-tests",
                "motivo": "importación desde el MCP",
                "dossier_path": str(fichero),
            },
        )
    assert not error, dossier
    assert dossier["id"] > 0


async def test_create_dossier_valida_las_vias(tmp_path, sesion_mcp, proyecto_demo, llamar_tool):
    base = {"project_id": proyecto_demo["project_id"], "actor": "a", "motivo": "m"}
    malo = tmp_path / "malo.json"
    malo.write_text("{no es json", encoding="utf-8")
    async with sesion_mcp as sesion:
        e1, r1 = await llamar_tool(sesion, "create_dossier", base)
        e2, r2 = await llamar_tool(
            sesion, "create_dossier", {**base, "dossier_path": "x.json", "profile": {"a": "b"}}
        )
        e3, r3 = await llamar_tool(sesion, "create_dossier", {**base, "dossier_path": str(malo)})
        e4, r4 = await llamar_tool(
            sesion, "create_dossier", {**base, "dossier_path": str(tmp_path / "no-existe.json")}
        )
    assert e1 and "falta la fuente" in str(r1)
    assert e2 and "no las dos vías" in str(r2)
    assert e3 and "no es un JSON válido" in str(r3)
    assert e4 and "no se puede leer" in str(r4)


# --- Riesgos ----------------------------------------------------


async def test_riesgos_ciclo_completo(sesion_mcp, proyecto_demo, llamar_tool, cliente_http):
    pid = proyecto_demo["project_id"]
    antes = len(await _eventos_agente(cliente_http, pid))
    async with sesion_mcp as sesion:
        error, riesgo = await llamar_tool(
            sesion,
            "create_risk",
            {
                "project_id": pid,
                "title": "Riesgo desde el MCP",
                "motivo": "alta de prueba",
                "impact_level": 3,
                "probability_level": 2,
            },
        )
        assert not error, riesgo
        rid = riesgo["id"]
        error, desde_alerta = await llamar_tool(
            sesion,
            "create_risk",
            {
                "project_id": pid,
                "title": "Riesgo de una alerta",
                "motivo": "alta desde alerta",
                "origin_alert_id": proyecto_demo["alert_id"],
            },
        )
        assert not error, desde_alerta
        assert desde_alerta["origin_alert_id"] == proyecto_demo["alert_id"]

        error, movido = await llamar_tool(
            sesion,
            "update_risk",
            {"risk_id": rid, "accion": "mover", "motivo": "sube", "impact_level": 4, "probability_level": 4},
        )
        assert not error, movido
        assert (movido["impact_level"], movido["probability_level"]) == (4, 4)

        error, seguido = await llamar_tool(
            sesion, "update_risk", {"risk_id": rid, "accion": "seguimiento", "motivo": "en vigilancia"}
        )
        assert not error, seguido
        assert seguido["status"] == "en_seguimiento"

        error, listado = await llamar_tool(
            sesion, "list_risks", {"project_id": pid, "status": "en_seguimiento"}
        )
        assert not error, listado
        assert [r["id"] for r in listado["items"]] == [rid]

        error, sin_confirmar = await llamar_tool(
            sesion, "update_risk", {"risk_id": rid, "accion": "cerrar", "motivo": "fin"}
        )
        assert error and "confirm=true" in str(sin_confirmar)
        error, cerrado = await llamar_tool(
            sesion, "update_risk", {"risk_id": rid, "accion": "cerrar", "motivo": "fin", "confirm": True}
        )
    assert not error, cerrado
    assert cerrado["status"] == "cerrado"
    eventos = await _eventos_agente(cliente_http, pid)
    assert len(eventos) >= antes + 5  # dos altas, mover, seguimiento, cerrar


async def test_update_risk_valida_parametros(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        e1, r1 = await llamar_tool(sesion, "update_risk", {"risk_id": 1, "accion": "borrar", "motivo": "m"})
        e2, r2 = await llamar_tool(sesion, "update_risk", {"risk_id": 1, "accion": "mover", "motivo": "m"})
    assert e1 and "accion no reconocida" in str(r1)
    assert e2 and "impact_level y probability_level" in str(r2)


# --- Otras tools -----------------------------------------------------------


async def test_get_threshold_proposal(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, propuesta = await llamar_tool(
            sesion, "get_threshold_proposal", {"project_id": proyecto_demo["project_id"]}
        )
    # Con línea base congelada devuelve la propuesta; sin ella, un 409 legible.
    assert (not error and isinstance(propuesta, dict)) or str(propuesta).startswith("409:")


async def test_get_alert(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, alerta = await llamar_tool(sesion, "get_alert", {"alert_id": proyecto_demo["alert_id"]})
    assert not error, alerta
    assert alerta["id"] == proyecto_demo["alert_id"]
    assert "actions" in alerta and "protocol_steps" in alerta


async def test_get_job(sesion_mcp, proyecto_demo, llamar_tool):
    batch = proyecto_demo["batches"][0]["id"]
    async with sesion_mcp as sesion:
        error, job = await llamar_tool(
            sesion, "run_evaluation", {"batch_id": batch, "wait": False}
        )
        assert not error, job
        error, estado = await llamar_tool(sesion, "get_job", {"job_id": job["id"]})
    assert not error, estado
    assert estado["id"] == job["id"]


# --- Errores ------------------------------------------------------------


async def test_error_404_empieza_por_el_codigo(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(sesion, "get_alert", {"alert_id": 999999})
    assert error
    assert str(texto).startswith("404:")
    assert "consulta los ids vigentes con get_alerts" in str(texto)


async def test_error_409_explicabilidad_sin_artefacto(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        _e, proyecto = await llamar_tool(sesion, "create_project", {"name": "sin artefacto", "deployment_stage": "desarrollo"})
        error, texto = await llamar_tool(
            sesion, "explain_global", {"version_id": proyecto["active_version_id"]}
        )
    assert error
    assert str(texto).startswith("409:")
    # Nombra la tool y lo que falta, no la frase genérica.
    assert "upload_model_artifact" in str(texto)
    assert "no aplicable ahora" not in str(texto)


async def test_error_422_revisa_el_campo(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(
            sesion,
            "create_risk",
            {"project_id": proyecto_demo["project_id"], "title": "sin niveles", "motivo": "m"},
        )
    assert error
    assert str(texto).startswith("422:")
    assert "corrige el campo que nombra el mensaje" in str(texto)


async def test_error_500_simulado(sesion_mcp, cliente_vigia, llamar_tool, monkeypatch):
    real_get = cliente_vigia.http.get

    async def get_roto(url, *args, **kwargs):
        if url.endswith("/alerts/7"):
            return httpx.Response(500, json={"detail": "fallo interno"})
        return await real_get(url, *args, **kwargs)

    monkeypatch.setattr(cliente_vigia.http, "get", get_roto)
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(sesion, "get_alert", {"alert_id": 7})
    assert error
    assert str(texto).startswith("500: fallo interno")
    assert "error de Vigía; el diario tiene el detalle" in str(texto)


async def test_raise_for_status_unidad():
    cliente = VigiaClient(url="http://x")
    with pytest.raises(VigiaError) as exc:
        await cliente._raise_for_status(
            httpx.Response(422, json={"detail": [{"loc": ["body", "title"], "msg": "campo requerido"}]})
        )
    assert exc.value.status_code == 422
    assert exc.value.detail == "title: campo requerido"
    assert str(exc.value).startswith("422: title: campo requerido")
    assert isinstance(exc.value, RuntimeError)
    with pytest.raises(VigiaError) as sin_json:
        await cliente._raise_for_status(httpx.Response(503, text="caído"))
    assert sin_json.value.que_hacer == "error de Vigía; el diario tiene el detalle"
    with pytest.raises(VigiaError) as otro:
        await cliente._raise_for_status(httpx.Response(401, json={"detail": "token"}))
    assert otro.value.que_hacer is None
    assert str(otro.value) == "401: token"


# --- Espera agotada -----------------------------------------------------


async def test_espera_agotada_devuelve_en_curso(sesion_mcp, proyecto_demo, cliente_vigia, llamar_tool, monkeypatch):
    real_get = VigiaClient.get

    async def get_lento(self, path, **kw):
        if path.startswith("/jobs/"):
            return {"id": int(path.rsplit("/", 1)[1]), "status": "en_ejecucion"}
        return await real_get(self, path, **kw)

    monkeypatch.setattr(VigiaClient, "get", get_lento)
    batch = proyecto_demo["batches"][0]["id"]
    pid = proyecto_demo["project_id"]
    async with sesion_mcp as sesion:
        e1, r1 = await llamar_tool(sesion, "run_evaluation", {"batch_id": batch, "timeout_s": 0})
        e2, r2 = await llamar_tool(sesion, "evaluate_cross", {"project_id": pid, "timeout_s": 0})
        e3, r3 = await llamar_tool(
            sesion, "explain_global", {"version_id": proyecto_demo["version_id"], "timeout_s": 0}
        )
    for error, resultado in ((e1, r1), (e2, r2), (e3, r3)):
        assert not error, resultado
        assert resultado["status"] == "en_curso"
        assert resultado["timeout"] is True
        assert resultado["aviso"] == f"sigue en curso; consulta get_job({resultado['job_id']})"


async def test_toda_tool_con_wait_acepta_timeout_s(sesion_mcp):
    async with sesion_mcp as sesion:
        tools = (await sesion.list_tools()).tools
    con_wait = {t.name: t for t in tools if "wait" in t.inputSchema.get("properties", {})}
    # lab_generate y run_scenario siempre esperan y no exponen `wait`.
    assert {"run_evaluation", "next_phase", "evaluate_cross", "upload_dataset"} <= set(con_wait)
    for nombre, tool in con_wait.items():
        assert "timeout_s" in tool.inputSchema["properties"], nombre


# --- upload_dataset con wait --------------------------------------------


async def test_upload_dataset_wait_devuelve_el_resultado_de_la_ingesta(
    tmp_path, proyecto_demo, sesion_mcp, llamar_tool
):
    csv = tmp_path / "ingesta.csv"
    csv.write_bytes(b"id,prediction,label,Age\n1,1,1,30\n2,0,0,45\n")
    mapping = {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "feature_cols": ["Age"]}
    args = {
        "project_id": proyecto_demo["project_id"],
        "file_path": str(csv),
        "kind": "combined",
        "role": "production",
        "mapping": mapping,
    }
    async with sesion_mcp as sesion:
        error, esperado = await llamar_tool(sesion, "upload_dataset", args)
        assert not error, esperado
        job = esperado["ingest_job"]
        assert job["status"] == "terminado"
        assert job["result"] is not None  # filas, avisos y errores de la ingesta
        error, sin_esperar = await llamar_tool(sesion, "upload_dataset", {**args, "wait": False})
    assert not error, sin_esperar
    assert "id" in sin_esperar["ingest_job"]


# --- informe_semanal ------------------------------------------------------


async def test_informe_semanal_incluye_cruzadas_deskilling_y_riesgos(sesion_mcp, proyecto_demo, llamar_tool):
    pid = proyecto_demo["project_id"]
    async with sesion_mcp as sesion:
        error, _ = await llamar_tool(
            sesion,
            "create_risk",
            {"project_id": pid, "title": "Riesgo del informe", "motivo": "m", "impact_level": 2, "probability_level": 2},
        )
        assert not error
        resultado = await sesion.get_prompt(
            "informe_semanal", {"project_id": str(pid), "since": "2020-01-01", "until": "2099-01-01"}
        )
    texto = resultado.messages[0].content.text
    for seccion in ("## 1. Diario de eventos", "## 2. Alertas cruzadas", "## 3. Deskilling", "## 4. Riesgos abiertos"):
        assert seccion in texto
    assert "Riesgo del informe" in texto


async def test_informe_semanal_sin_datos_no_se_cae(sesion_mcp, cliente_vigia, llamar_tool):
    async with sesion_mcp as sesion:
        _e, proyecto = await llamar_tool(sesion, "create_project", {"name": "vacío", "deployment_stage": "desarrollo"})
        resultado = await sesion.get_prompt(
            "informe_semanal",
            {"project_id": str(proyecto["id"]), "since": "2020-01-01", "until": "2099-01-01"},
        )
    texto = resultado.messages[0].content.text
    assert "## 2. Alertas cruzadas" in texto


# --- upload_dataset sin mapeo -------------------------------------------


async def test_upload_dataset_sin_mapeo_devuelve_el_error(tmp_path, sesion_mcp, llamar_tool, cliente_http):
    """El error llega antes de subir (el proyecto de demo trae plantilla y
    heredaría; este es un proyecto sin ella)."""
    proyecto = await _crear_proyecto(cliente_http)
    csv = tmp_path / "sin_mapeo.csv"
    csv.write_bytes(b"id,prediction,label,Age\n1,1,1,30\n2,0,0,45\n")
    args = {"project_id": proyecto["id"], "file_path": str(csv), "kind": "combined", "role": "production"}
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(sesion, "upload_dataset", args)
    assert error
    assert "422" in str(resultado) and "mapeo" in str(resultado)


# --- upload_dataset hereda la plantilla -----------------------------------


async def _crear_proyecto(cliente_http, **extra) -> dict:
    resp = await cliente_http.post(
        "/api/projects",
        json={"name": "plantilla-mcp", **extra},
        headers={"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


CSV_PLANTILLA = b"id,prediction,label,Age\n1,1,1,30\n2,0,0,45\n"
PLANTILLA = {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "feature_cols": ["Age"]}


async def test_upload_dataset_sin_mapping_ni_plantilla_falla_antes_de_subir(
    tmp_path, sesion_mcp, llamar_tool, cliente_http
):
    proyecto = await _crear_proyecto(cliente_http)
    csv = tmp_path / "x.csv"
    csv.write_bytes(CSV_PLANTILLA)
    args = {"project_id": proyecto["id"], "file_path": str(csv), "kind": "combined", "role": "production"}
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(sesion, "upload_dataset", args)
    assert error
    assert str(texto).startswith("422:")
    assert "mapping" in str(texto) and "set_mapping_template" in str(texto)
    # Falló antes de subir: no hay datasets ni trabajos de ingesta.
    datasets = (await cliente_http.get(f"/api/projects/{proyecto['id']}/datasets")).json()
    assert datasets["total"] == 0


async def test_upload_dataset_con_plantilla_sin_columnas_falla_antes_de_subir(
    tmp_path, sesion_mcp, llamar_tool, cliente_http
):
    proyecto = await _crear_proyecto(cliente_http, mapping_template={"favorable_label": 1})
    csv = tmp_path / "x.csv"
    csv.write_bytes(CSV_PLANTILLA)
    args = {"project_id": proyecto["id"], "file_path": str(csv), "kind": "combined", "role": "production"}
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(sesion, "upload_dataset", args)
    assert error
    assert str(texto).startswith("422:")
    assert "no fija ninguna columna" in str(texto) and "set_mapping_template" in str(texto)
    datasets = (await cliente_http.get(f"/api/projects/{proyecto['id']}/datasets")).json()
    assert datasets["total"] == 0


async def test_upload_dataset_hereda_la_plantilla_del_proyecto(
    tmp_path, sesion_mcp, llamar_tool, cliente_http
):
    proyecto = await _crear_proyecto(cliente_http, mapping_template=PLANTILLA)
    csv = tmp_path / "x.csv"
    csv.write_bytes(CSV_PLANTILLA)
    args = {"project_id": proyecto["id"], "file_path": str(csv), "kind": "combined", "role": "production"}
    async with sesion_mcp as sesion:
        error, res = await llamar_tool(sesion, "upload_dataset", args)
        assert not error, res
        assert res["mapping_origen"] == "plantilla_proyecto"
        assert res["mapping_aplicado"]["prediction_col"] == "prediction"
        assert res["mapping_aplicado"]["feature_cols"] == ["Age"]
        assert "positive_label" not in res["mapping_aplicado"]
        assert res["ingest_job"]["status"] == "terminado", res
        # Con `mapping` explícito manda el parámetro y no hay `mapping_aplicado`.
        explicito_mapping = {**PLANTILLA, "favorable_label": 1}
        error, explicito = await llamar_tool(sesion, "upload_dataset", {**args, "mapping": explicito_mapping})
    assert not error, explicito
    assert explicito["mapping_origen"] == "parametro"
    assert "mapping_aplicado" not in explicito


# --- export_report acotado ------------------------------------------------


async def test_export_report_diario_acota_con_limit(sesion_mcp, proyecto_demo, llamar_tool):
    async with sesion_mcp as sesion:
        error, corto = await llamar_tool(sesion, "export_report", {"kind": "diario", "limit": 3})
        assert not error, corto
        assert corto["limit"] == 3 and corto["devueltos"] == 3
        assert corto["truncado"] is True and corto["total"] > 3
        error, completo = await llamar_tool(sesion, "export_report", {"kind": "diario"})
        assert not error, completo
        assert completo["limit"] == 200
        assert completo["devueltos"] == len(completo["eventos"]) == min(completo["total"], 200)
        assert completo["eventos"][-3:] == corto["eventos"]
        error, html = await llamar_tool(sesion, "export_report", {"kind": "diario", "limit": 3, "format": "html"})
        assert not error, html
        assert html["truncado"] is True and html["since_aplicado"]
        assert html["total"] > 3 and html["devueltos"] >= 3
        assert "<table" in html["html"]
        error, html_entero = await llamar_tool(sesion, "export_report", {"kind": "diario", "format": "html"})
        assert not error, html_entero
        assert html_entero["truncado"] is False and html_entero["devueltos"] == html_entero["total"]
        error, malo = await llamar_tool(sesion, "export_report", {"kind": "diario", "limit": 0})
        assert error and "limit" in str(malo)
        error, formato = await llamar_tool(sesion, "export_report", {"kind": "diario", "format": "xml"})
    assert error and str(formato).startswith("422:")


# --- Aviso de calibración y claves de decide ------------------------------


@pytest.mark.parametrize(
    ("modo", "con_aviso"), [("calibracion", True), ("vigilancia", False), (None, False)]
)
async def test_evaluate_cross_avisa_solo_si_calibra(
    sesion_mcp, proyecto_demo, llamar_tool, monkeypatch, modo, con_aviso
):
    async def trabajo(self, job, wait, timeout_s=60.0):
        return {"id": job["id"], "status": "terminado", "result": {"mode": modo, "n_alerts": 0}}

    monkeypatch.setattr(VigiaClient, "seguir_job", trabajo)
    async with sesion_mcp as sesion:
        error, res = await llamar_tool(sesion, "evaluate_cross", {"project_id": proyecto_demo["project_id"]})
    assert not error, res
    assert ("aviso" in res) is con_aviso
    if con_aviso:
        assert "fija la referencia" in res["aviso"] and "evaluate_cross" in res["aviso"]


async def test_evaluate_cross_aviso_con_calibration_until_vigente_o_vencida(
    sesion_mcp, proyecto_demo, llamar_tool, monkeypatch, cliente_http
):
    async def trabajo(self, job, wait, timeout_s=60.0):
        return {"id": job["id"], "status": "terminado", "result": {"mode": "calibracion", "n_alerts": 0}}

    monkeypatch.setattr(VigiaClient, "seguir_job", trabajo)
    pid = proyecto_demo["project_id"]
    cabeceras = {"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"}
    futuro = "2999-01-01T00:00:00+00:00"
    pasado = "2000-01-01T00:00:00+00:00"
    async with sesion_mcp as sesion:
        resp = await cliente_http.patch(f"/api/projects/{pid}", json={"actor": "miguel", "motivo": "prueba", "calibration_until": futuro}, headers=cabeceras)
        assert resp.status_code == 200, resp.text
        error, vigente = await llamar_tool(sesion, "evaluate_cross", {"project_id": pid})
        assert not error, vigente
        assert "no fija todavía la referencia" in vigente["aviso"] and futuro in vigente["aviso"]
        resp = await cliente_http.patch(f"/api/projects/{pid}", json={"actor": "miguel", "motivo": "prueba", "calibration_until": pasado}, headers=cabeceras)
        assert resp.status_code == 200, resp.text
        error, vencida = await llamar_tool(sesion, "evaluate_cross", {"project_id": pid})
    assert not error, vencida
    assert "fija la referencia" in vencida["aviso"] and "no fija" not in vencida["aviso"]


async def test_evaluate_cross_con_resultado_no_dict_no_se_cae(sesion_mcp, proyecto_demo, llamar_tool, monkeypatch):
    async def trabajo(self, job, wait, timeout_s=60.0):
        return {"id": job["id"], "status": "terminado", "result": None}

    monkeypatch.setattr(VigiaClient, "seguir_job", trabajo)
    async with sesion_mcp as sesion:
        error, res = await llamar_tool(sesion, "evaluate_cross", {"project_id": proyecto_demo["project_id"]})
    assert not error, res
    assert "aviso" not in res


async def test_docstring_de_act_on_alert_lista_las_claves_de_decide(sesion_mcp):
    from vigia.app.services.alerting import ETIQUETAS_ACCION

    async with sesion_mcp as sesion:
        tools = {t.name: t for t in (await sesion.list_tools()).tools}
    descripcion = tools["act_on_alert"].description or ""
    for clave in ETIQUETAS_ACCION:
        assert f"`{clave}`" in descripcion, clave


def test_estados_finales_del_cliente_coinciden_con_el_backend():
    from vigia.app.jobs import ESTADOS_FINALES as BACKEND
    from vigia.mcp.client import ESTADOS_FINALES

    assert ESTADOS_FINALES == BACKEND
