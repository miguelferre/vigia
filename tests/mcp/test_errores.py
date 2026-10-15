"""«qué hacer» por patrón de ruta, 409 y 422 sin repetir el detalle,
y un backend parado como `VigiaError` con `MENSAJE_SIN_ARRANQUE`."""

from __future__ import annotations

import pytest

from vigia.mcp.client import MENSAJE_SIN_ARRANQUE, VigiaClient, VigiaError, _que_hacer


@pytest.mark.parametrize(
    ("ruta", "tool"),
    [
        ("/api/projects/9", "list_projects"),
        ("/api/projects/9/alerts", "get_alerts"),
        ("/api/alerts/9", "get_alerts"),
        ("/api/projects/9/risks", "list_risks"),
        ("/api/risks/9", "list_risks"),
        ("/api/model-versions/9/activate", "list_versions"),
        ("/api/jobs/9", "get_job"),
        ("/api/projects/9/versions/compare", "list_projects o list_versions"),
    ],
)
def test_404_nombra_la_tool_de_listado_segun_la_ruta(ruta, tool):
    texto = _que_hacer(404, "no existe", ruta)
    assert texto is not None and tool in texto


def test_404_de_una_ruta_sin_listado_conserva_el_texto_generico():
    assert _que_hacer(404, "no existe", "/api/monitors/9") == "comprueba el id con la tool de listado"
    assert _que_hacer(404, "no existe") == "comprueba el id con la tool de listado"


def test_409_y_422_no_repiten_el_detalle():
    detalle = "texto único del detalle de la API"
    for codigo in (409, 422):
        texto = _que_hacer(codigo, detalle, "/api/projects/1")
        assert texto and detalle not in texto


def test_409_de_baseline_ya_congelado_no_pide_la_linea_base():
    """«Ya tiene un baseline congelado» no recibe la pista de «falta la línea base»."""
    texto = _que_hacer(409, "la versión ya tiene un baseline congelado", "/api/model-versions/3/baseline")
    assert texto and "falta la línea base" not in texto
    assert "ya tiene su línea base" in texto
    # El 409 de verdad de «falta» conserva su pista.
    assert "falta la línea base" in _que_hacer(409, "el proyecto no tiene baseline congelado", "/api/projects/1")


async def test_404_por_ruta_de_extremo_a_extremo(sesion_mcp, llamar_tool):
    casos = [
        ("get_alert", {"alert_id": 999999}, "get_alerts"),
        ("get_job", {"job_id": 999999}, "get_job"),
        ("list_versions", {"project_id": 999999}, "list_projects"),
        ("list_risks", {"project_id": 999999}, "list_risks"),
        ("activate_version", {"version_id": 999999, "motivo": "prueba"}, "list_versions"),
    ]
    async with sesion_mcp as sesion:
        for nombre, args, tool in casos:
            error, texto = await llamar_tool(sesion, nombre, args)
            assert error, nombre
            assert str(texto).startswith("404:"), (nombre, texto)
            assert f"con {tool}" in str(texto), (nombre, texto)


async def test_409_dice_el_paso_siguiente(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        _e, proyecto = await llamar_tool(
            sesion, "create_project", {"name": "sin artefacto", "deployment_stage": "desarrollo"}
        )
        error, texto = await llamar_tool(
            sesion, "explain_global", {"version_id": proyecto["active_version_id"]}
        )
    assert error and str(texto).startswith("409:")
    # El 409 nombra la tool y lo que falta, no una frase genérica.
    assert "Qué hacer: sube el modelo ejecutable de la versión con upload_model_artifact" in str(texto)
    primera, _, resto = str(texto).partition("\nQué hacer: ")
    assert primera.removeprefix("409: ") not in resto


async def test_422_dice_el_paso_siguiente(sesion_mcp, llamar_tool):
    async with sesion_mcp as sesion:
        _e, proyecto = await llamar_tool(
            sesion, "create_project", {"name": "etiqueta vacía", "deployment_stage": "desarrollo"}
        )
        error, texto = await llamar_tool(
            sesion,
            "create_version",
            {"project_id": proyecto["id"], "label": "   ", "motivo": "prueba"},
        )
    assert error and str(texto).startswith("422:"), texto
    assert "\nQué hacer: " in str(texto)
    primera, _, resto = str(texto).partition("\nQué hacer: ")
    assert primera.removeprefix("422: ") not in resto


async def test_backend_parado_sale_como_vigia_error():
    client = VigiaClient(url="http://127.0.0.1:1", actor="prueba")
    try:
        with pytest.raises(VigiaError) as exc:
            await client.get("/projects")
    finally:
        await client.aclose()
    # Con `--url` el texto nombra la dirección, no una carpeta de datos.
    assert "http://127.0.0.1:1" in str(exc.value)
    assert exc.value.status_code == 503


async def test_bootstrap_sin_lock_sale_como_vigia_error(tmp_path):
    client = VigiaClient(data_dir=tmp_path, actor="prueba")
    with pytest.raises(VigiaError) as exc:
        await client.bootstrap()
    assert MENSAJE_SIN_ARRANQUE in str(exc.value)
    with pytest.raises(VigiaError):
        await client.post("/projects", json={})
