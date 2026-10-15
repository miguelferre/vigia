"""Los mensajes del MCP nombran la tool y lo que falta.

Unitarios sobre `_que_hacer` y `fallos_de_conexion`, y una prueba por stdio real
(subproceso `vigia mcp`), porque los tests en memoria no ven el bucle de eventos."""

from __future__ import annotations

import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests.mcp.test_stdio_real import _entorno, _puerto_libre, backend  # noqa: F401
from vigia.mcp.errores import MENSAJE_SIN_ARRANQUE, VigiaError, _que_hacer, fallos_de_conexion


@pytest.mark.parametrize(
    ("ruta", "parametro", "tool"),
    [
        ("/api/projects/9", "project_id", "list_projects"),
        ("/api/alerts/9", "alert_id", "get_alerts"),
        ("/api/model-versions/9/activate", "version_id", "list_versions"),
        ("/api/jobs/9", "job_id", "get_job"),
    ],
)
def test_404_nombra_el_parametro_y_la_tool(ruta, parametro, tool):
    texto = _que_hacer(404, "modelo 9 no encontrado", ruta)
    assert texto == f"el {parametro} no existe: consulta los ids vigentes con {tool}"


@pytest.mark.parametrize(
    ("detalle", "tool"),
    [
        ("El modelo tiene una sola versión: crea la versión nueva en la ficha del modelo", "create_version"),
        ("El modelo no tiene versión activa: activa una versión o elige cuál comparar.", "activate_version"),
        ("la versión no tiene baseline congelado", "freeze_baseline"),
        ("la versión activa no tiene línea base congelada", "upload_dataset"),
        ("explicabilidad no disponible: sube el modelo en ONNX", "upload_model_artifact"),
        ("no hay variables guardadas para este lote: activa «Guardar las variables»", "store_features"),
        ("la revisión aún no tiene informe: espera a que termine", "run_dossier_review"),
        ("primero hay que hacer el triaje de la alerta", "act_on_alert"),
        ("la alerta ya está cerrada", "get_alert"),
    ],
)
def test_409_nombra_la_tool_y_lo_que_falta(detalle, tool):
    texto = _que_hacer(409, detalle, "/api/projects/1/loquesea")
    assert texto is not None and tool in texto
    assert detalle not in texto  # el detalle ya va en la primera línea


def test_409_sin_pista_usa_la_tool_de_lectura_de_la_ruta():
    assert "get_alert" in (_que_hacer(409, "otra cosa", "/api/alerts/3/acknowledge") or "")
    assert "tool de lectura" in (_que_hacer(409, "otra cosa", "/api/monitors/3") or "")


def test_503_con_url_nombra_la_direccion_y_sin_url_la_carpeta():
    with pytest.raises(VigiaError) as exc, fallos_de_conexion("http://127.0.0.1:9"):
        raise RuntimeError(MENSAJE_SIN_ARRANQUE)
    assert exc.value.status_code == 503
    assert "http://127.0.0.1:9" in str(exc.value) and "carpeta de datos" not in str(exc.value)
    with pytest.raises(VigiaError) as exc, fallos_de_conexion(None):
        raise RuntimeError(MENSAJE_SIN_ARRANQUE)
    assert MENSAJE_SIN_ARRANQUE in str(exc.value)


@pytest.mark.slow
async def test_mensajes_por_stdio_real(backend: str):  # noqa: F811
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "vigia", "mcp", "--url", backend, "--actor", "claude-stdio-157"],
        env=_entorno(),
    )
    async with stdio_client(params) as (leer, escribir), ClientSession(leer, escribir) as sesion:
        await sesion.initialize()
        r = await sesion.call_tool("list_versions", {"project_id": 999999})
        texto = r.content[0].text
        assert r.isError and texto.startswith("404:")
        assert "el project_id no existe" in texto and "list_projects" in texto

        creado = await sesion.call_tool("create_project", {"name": "stdio 157", "deployment_stage": "desarrollo"})
        proyecto = creado.structuredContent or {}
        r = await sesion.call_tool("explain_global", {"version_id": proyecto["active_version_id"]})
        assert r.isError and r.content[0].text.startswith("409:")
        assert "upload_model_artifact" in r.content[0].text


@pytest.mark.slow
async def test_backend_parado_con_url_por_stdio_real():
    url = f"http://127.0.0.1:{_puerto_libre()}"  # nadie escucha
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "vigia", "mcp", "--url", url, "--actor", "claude-stdio-157"],
        env=_entorno(),
    )
    async with stdio_client(params) as (leer, escribir), ClientSession(leer, escribir) as sesion:
        await sesion.initialize()
        r = await sesion.call_tool("list_projects", {})
        texto = r.content[0].text
        assert r.isError and texto.startswith("503:")
        assert url in texto and "carpeta de datos" not in texto
