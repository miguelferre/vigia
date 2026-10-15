"""Capa humana de regresión por el MCP.

Sin rango favorable, `upload_usage_log` da el motivo antes de subir nada. Con rango, la subida
pasa (ya no hay guardia «aún no»): el registro trae las cifras y la API valida cada celda.
"""

from __future__ import annotations

from pathlib import Path

from vigia.app.services import tarea

USAGE_CSV = Path(__file__).resolve().parents[2] / "data" / "demo" / "usage_logs_demo.csv"
HUMANO = {"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"}
SIN_RANGO = "la capa humana de regresión necesita un rango favorable"
CIFRAS = "en regresión el registro trae las cifras"

# Registro de regresión con cifras (horas): decisión del profesional, salida del modelo y verdad.
REGISTRO_CIFRAS = (
    "date,human_decision,model_output,ground_truth,clinician_pseudonym,subgroup\n"
    + "".join(
        f"2026-01-{d:02d},{h},{m},{t},prof-{d % 3},{'a' if d % 2 else 'b'}\n"
        for d, h, m, t in [
            (1, 45.5, 38.0, 44.0),
            (2, 50.0, 52.5, 49.0),
            (3, 30.0, 45.0, 33.0),
            (4, 60.0, 61.0, 59.5),
            (5, 42.0, 35.0, 41.0),
            (6, 70.0, 72.0, 71.0),
        ]
    )
)


async def _regresion(cliente_http, nombre: str, **extra) -> dict:
    resp = await cliente_http.post(
        "/api/projects",
        json={"name": nombre, "domain": "libre", "task_type": "regression", **extra},
        headers=HUMANO,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_el_registro_de_uso_de_una_regresion_sin_rango_da_el_motivo(
    sesion_mcp, llamar_tool, cliente_http
):
    proyecto = await _regresion(cliente_http, "uso-regresion-sin-rango", target_unit="horas")
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(
            sesion, "upload_usage_log", {"project_id": proyecto["id"], "file_path": str(USAGE_CSV)}
        )
    assert error
    assert SIN_RANGO in str(texto)
    assert "valor_favorable" not in str(texto)


async def test_con_rango_la_subida_del_registro_pasa_y_no_hay_guardia_aun_no(
    sesion_mcp, llamar_tool, cliente_http, tmp_path
):
    """La guardia «aún no está disponible» desaparece: con rango, la tool sube las cifras sin
    `valor_favorable`."""
    proyecto = await _regresion(
        cliente_http, "uso-regresion-con-rango", target_unit="horas", favorable_ranges=[[40, 81]]
    )
    fichero = tmp_path / "uso_cifras.csv"
    fichero.write_text(REGISTRO_CIFRAS, encoding="utf-8")
    async with sesion_mcp as sesion:
        error, resultado = await llamar_tool(
            sesion, "upload_usage_log", {"project_id": proyecto["id"], "file_path": str(fichero)}
        )
    assert not error, resultado
    assert "aún no está disponible" not in str(resultado)
    assert resultado["n_rows"] == 6


async def test_con_rango_un_registro_con_refer_da_el_texto_de_cifras(
    sesion_mcp, llamar_tool, cliente_http
):
    """El registro binario en un proyecto de regresión con rango no pasa: el 422 de la API
    dice que el registro trae las cifras."""
    proyecto = await _regresion(
        cliente_http, "uso-regresion-refer", target_unit="horas", favorable_ranges=[[40, 81]]
    )
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(
            sesion, "upload_usage_log", {"project_id": proyecto["id"], "file_path": str(USAGE_CSV)}
        )
    assert error
    assert CIFRAS in str(texto)


async def test_con_rango_un_valor_favorable_pasado_da_el_texto_de_cifras_sin_llegar_a_la_api(
    sesion_mcp, llamar_tool, cliente_http, tmp_path
):
    """En regresión la tool no manda `valor_favorable`; si la persona lo pasa, la tool da el
    texto de la guardia antes de subir (también si el valor es raro: el de un modelo binario no aplica)."""
    proyecto = await _regresion(
        cliente_http, "uso-regresion-valor", target_unit="horas", favorable_ranges=[[40, 81]]
    )
    fichero = tmp_path / "uso_cifras.csv"
    fichero.write_text(REGISTRO_CIFRAS, encoding="utf-8")
    async with sesion_mcp as sesion:
        for valor in ("refer", "alto"):
            error, texto = await llamar_tool(
                sesion,
                "upload_usage_log",
                {"project_id": proyecto["id"], "file_path": str(fichero), "valor_favorable": valor},
            )
            assert error, valor
            assert CIFRAS in str(texto), valor
            assert "valor_favorable no reconocido" not in str(texto), valor


async def test_un_valor_favorable_raro_en_regresion_sin_rango_da_el_motivo_de_la_guardia(
    sesion_mcp, llamar_tool, cliente_http
):
    """Sin rango, la guardia dice su motivo antes que un `valor_favorable` raro (que es de un
    modelo binario)."""
    proyecto = await _regresion(cliente_http, "uso-regresion-valor-raro")
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(
            sesion,
            "upload_usage_log",
            {"project_id": proyecto["id"], "file_path": str(USAGE_CSV), "valor_favorable": "alto"},
        )
    assert error
    assert SIN_RANGO in str(texto)
    assert "valor_favorable no reconocido" not in str(texto)


async def test_get_overrides_cambios_llama_a_la_tabla_de_cambios(
    sesion_mcp, llamar_tool, cliente_http, tmp_path
):
    """`by="cambios"` lee `GET /overrides/cambios`: en regresión con rango, las categorías son
    «dentro del rango» y «fuera del rango» y la tabla es cuadrada."""
    proyecto = await _regresion(
        cliente_http, "cambios-regresion", target_unit="horas", favorable_ranges=[[40, 81]]
    )
    fichero = tmp_path / "uso_cifras.csv"
    fichero.write_text(REGISTRO_CIFRAS, encoding="utf-8")
    async with sesion_mcp as sesion:
        error, _ = await llamar_tool(
            sesion, "upload_usage_log", {"project_id": proyecto["id"], "file_path": str(fichero)}
        )
        assert not error
        error, tabla = await llamar_tool(
            sesion, "get_overrides", {"project_id": proyecto["id"], "by": "cambios"}
        )
    assert not error, tabla
    assert tabla["task_type"] == "regression"
    assert tabla["categorias"] == ["dentro del rango", "fuera del rango"]
    assert len(tabla["filas"]) == 2
    assert all(len(f["celdas"]) == 2 for f in tabla["filas"])
    # Contenido: seis decisiones repartidas en dos filas quedan por debajo de la celda mínima
    #: las tasas son nulas y los `n` se conservan.
    assert tabla["min_n"] > max(f["n"] for f in tabla["filas"])
    assert sum(f["n"] for f in tabla["filas"]) == 6
    assert tabla["n_sin_decision"] == 0
    for fila in tabla["filas"]:
        assert fila["tasa_cambio"] is None
        assert all(c["tasa"] is None and c["n"] >= 0 for c in fila["celdas"])
    assert sum(c["n"] for f in tabla["filas"] for c in f["celdas"]) == 6


async def test_get_overrides_cambios_sin_rango_da_el_motivo(sesion_mcp, llamar_tool, cliente_http):
    proyecto = await _regresion(cliente_http, "cambios-regresion-sin-rango", target_unit="horas")
    async with sesion_mcp as sesion:
        error, tabla = await llamar_tool(
            sesion, "get_overrides", {"project_id": proyecto["id"], "by": "cambios"}
        )
    assert not error, tabla
    assert tabla["filas"] == []
    assert SIN_RANGO in str(tabla["motivo"])


async def test_get_overrides_acepta_cambios_y_rechaza_otro_valor(sesion_mcp, llamar_tool, cliente_http):
    proyecto = await _regresion(cliente_http, "cambios-valor", target_unit="horas")
    async with sesion_mcp as sesion:
        error, texto = await llamar_tool(
            sesion, "get_overrides", {"project_id": proyecto["id"], "by": "semana"}
        )
    assert error
    assert "cambios" in str(texto)


def test_el_texto_sin_rango_del_mcp_es_el_de_la_api():
    """El MCP repite el texto de la guardia sin rango (no importa `app.services`); si
    cambia en la API y no aquí, este test lo dice."""
    from vigia.core.schema import MOTIVO_CAPA_HUMANA_SIN_RANGO
    from vigia.mcp import tools_humano

    assert tools_humano.MOTIVO_REGRESION_SIN_RANGO == MOTIVO_CAPA_HUMANA_SIN_RANGO
    assert tools_humano.TEXTO_SIN_RANGO == tarea.texto_guardia_capa_humana(sin_rango=True)
    assert not hasattr(tools_humano, "MENSAJE_REGISTRO_USO_REGRESION")
    assert not hasattr(tools_humano, "TEXTO_AUN_NO")


def test_el_texto_de_valor_favorable_en_regresion_del_mcp_es_el_de_la_api():
    """El MCP repite el 422 de la API para `valor_favorable` en regresión."""
    from vigia.app.services import human_layer
    from vigia.mcp import tools_humano

    assert tools_humano.TEXTO_VALOR_FAVORABLE_EN_REGRESION == human_layer.MENSAJE_VALOR_FAVORABLE_REGRESION
    assert CIFRAS in tools_humano.TEXTO_VALOR_FAVORABLE_EN_REGRESION


async def test_get_overrides_cambios_en_binario_trae_n_tasa_y_las_dos_categorias(
    sesion_mcp, llamar_tool, cliente_http
):
    """`by="cambios"` también sirve en clasificación binaria: categorías `refer` y `no-refer`."""
    resp = await cliente_http.post(
        "/api/projects", json={"name": "cambios-binario", "domain": "libre"}, headers=HUMANO
    )
    assert resp.status_code == 200, resp.text
    proyecto = resp.json()
    async with sesion_mcp as sesion:
        error, subida = await llamar_tool(
            sesion,
            "upload_usage_log",
            {"project_id": proyecto["id"], "file_path": str(USAGE_CSV), "valor_favorable": "refer"},
        )
        assert not error, subida
        error, tabla = await llamar_tool(
            sesion, "get_overrides", {"project_id": proyecto["id"], "by": "cambios"}
        )
    assert not error, tabla
    assert tabla["task_type"] == "binary"
    assert sorted(tabla["categorias"]) == ["no-refer", "refer"]
    assert tabla["min_n"] >= 1
    for fila in tabla["filas"]:
        assert fila["n"] >= 0 and "tasa_cambio" in fila
        for celda in fila["celdas"]:
            assert "n" in celda and "tasa" in celda
            if fila["n"] >= tabla["min_n"]:
                assert celda["tasa"] is not None
