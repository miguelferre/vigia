"""Contenido: la guía de datos, el
glosario nuevo y la guía de uso al día."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vigia.app.services.plantillas_datos import TIPOS_PLANTILLA

try:
    from build.gen_content import _volcar
    from build.gen_content_guia_datos import generar_guia_datos

    HAY_GENERADOR = True
except ImportError:  # el árbol público no lleva el generador ni sus fuentes
    HAY_GENERADOR = False

CONTENT_DIR = Path(__file__).resolve().parents[2] / "src" / "vigia" / "content"
GUIA_DATOS_JSON = CONTENT_DIR / "guia-datos.json"
GUIA_USO_JSON = CONTENT_DIR / "guia-uso.json"
N_SECCIONES = 8

SECCIONES = [
    "linea-base",
    "lote",
    "etiquetas",
    "registro-uso",
    "outcomes",
    "multiclase",
    "regresion",
    "modelo",
]
CONCEPTOS_R6 = {
    "version",
    "linea_base_version",
    "comparacion_versiones",
    "plantilla_mapeo",
    "etapa_despliegue",
    "vista_previa",
}


@pytest.mark.skipif(
    not HAY_GENERADOR,
    reason="falta build/gen_content.py y sus fuentes en docs/, que no viajan en el árbol público",
)
def test_guia_datos_esta_regenerada():
    """`gen_content --check` cubre el fichero nuevo."""
    assert GUIA_DATOS_JSON.read_text(encoding="utf-8") == _volcar(generar_guia_datos())


def test_guia_datos_tiene_las_ocho_secciones(client):
    resp = client.get("/api/content/guia-datos")
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert N_SECCIONES == 8
    assert [s["id"] for s in cuerpo["secciones"]] == SECCIONES
    for seccion in cuerpo["secciones"]:
        assert seccion["titulo"] and seccion["para_que"] and seccion["notas"]
    assert cuerpo["aviso_sintetico"]


def test_cada_seccion_con_csv_remite_a_su_plantilla(client):
    cuerpo = client.get("/api/content/guia-datos").json()
    con_plantilla = [s for s in cuerpo["secciones"] if s["plantilla"]]
    assert [s["plantilla"] for s in con_plantilla] == list(TIPOS_PLANTILLA)
    for seccion in con_plantilla:
        assert seccion["obligatorias"]
        resp = client.get(f"/api/content/plantillas/{seccion['plantilla']}.csv")
        assert resp.status_code == 200
        assert seccion["nombre_plantilla"] in resp.headers["content-disposition"]
        cabecera = resp.text.splitlines()[0].split(",")
        # Las columnas obligatorias de la guía están en la cabecera de la plantilla
        # (la fila `crp, esr, joint_count` de variables agrupa tres columnas).
        # `prob_<clase>` (multiclase) agrupa una columna de probabilidad por clase.
        for columna in seccion["obligatorias"]:
            nombre = columna["nombre"]
            if "<clase>" in nombre:
                prefijo = nombre.split("<clase>")[0]
                assert [c for c in cabecera if c.startswith(prefijo)], (seccion["id"], nombre)
            else:
                assert nombre in cabecera, (seccion["id"], nombre)
    modelo = cuerpo["secciones"][-1]
    assert modelo["plantilla"] is None and modelo["nombre_plantilla"] is None


def test_registro_uso_de_la_guia_sale_de_su_ayuda(client):
    guia = client.get("/api/content/guia-datos").json()
    ayuda = client.get("/api/content/registro-uso").json()
    seccion = next(s for s in guia["secciones"] if s["id"] == "registro-uso")
    assert seccion["obligatorias"] == ayuda["columnas_obligatorias"]
    assert seccion["opcionales"] == ayuda["columnas_opcionales"]


def test_guia_datos_cubre_formatos_excel_clase_favorable_e_inconclusa(client):
    cuerpo = client.get("/api/content/guia-datos").json()
    formatos = cuerpo["formatos"]
    texto = json.dumps(formatos, ensure_ascii=False)
    for pieza in ("coma", "punto y coma", "UTF-8", "Windows-1252", "lista de objetos"):
        assert pieza in texto, pieza
    assert "guárdalo como CSV" in formatos["excel"]
    assert {f["formato"] for f in formatos["fechas"]} == {"aaaa-mm-dd", "dd/mm/aaaa y dd-mm-aaaa"}
    assert "xlsx" not in " ".join(
        v for k, v in formatos.items() if isinstance(v, str) and k != "excel"
    ).lower()
    favorable = cuerpo["clase_favorable"]
    assert favorable["pasos"] and favorable["ejemplos"]
    assert "persona" in favorable["pregunta"]
    inconclusa = cuerpo["codificacion_inconclusa"]
    assert "inconclusa" in inconclusa["titulo"]
    assert "significado" in " ".join(inconclusa["pasos"])
    assert "motivo" in " ".join(inconclusa["pasos"])


def test_guia_datos_usa_vocabulario_neutro_y_sin_guion_largo():
    texto = GUIA_DATOS_JSON.read_text(encoding="utf-8").lower()
    for palabra in ("paciente", "el clínico", "clínic", "derivar", "cribado"):
        assert palabra not in texto, palabra
    assert "—" not in texto


# ---------------------------------------------------------------------------
# Glosario
# ---------------------------------------------------------------------------


def test_glosario_gana_los_seis_conceptos_de_la_guia_de_datos(client):
    cuerpo = client.get("/api/content/glosario").json()
    assert CONCEPTOS_R6 <= set(cuerpo)
    for clave in CONCEPTOS_R6:
        assert cuerpo[clave]["etiqueta"] and cuerpo[clave]["definicion"]
        assert "—" not in cuerpo[clave]["definicion"]
    assert "validación" in cuerpo["etapa_despliegue"]["definicion"]
    assert "validación" in cuerpo["estado_despliegue"]["definicion"]
    assert "alertas son del modelo" in cuerpo["comparacion_versiones"]["definicion"]


# ---------------------------------------------------------------------------
# Guía de uso
# ---------------------------------------------------------------------------


def _entradas(client) -> dict[int, dict]:
    cuerpo = client.get("/api/content/guia-uso").json()
    return {e["id"]: e for e in cuerpo["entradas"]}


def test_guia_uso_entrada_1_no_promete_parquet_y_remite_a_la_guia_de_datos(client):
    entrada = _entradas(client)[1]
    texto = " ".join(entrada["pasos"])
    assert "Parquet" not in texto
    assert "CSV" in texto and "guárdalos como CSV" in texto
    assert "«Datos»" in texto and "plantillas" in texto


def test_guia_uso_sin_parquet_ni_siguiente_version(client):
    cuerpo = client.get("/api/content/guia-uso").json()
    texto = GUIA_USO_JSON.read_text(encoding="utf-8")
    assert "siguiente versión" not in texto.lower()
    assert "Parquet" not in texto
    assert all(e["estado"] is None for e in cuerpo["entradas"])


def test_guia_uso_entrada_2_pide_el_valor_favorable_y_sube_la_linea_base_despues(client):
    entrada = _entradas(client)[2]
    texto = " ".join(entrada["pasos"])
    assert "Paso «Datos»" in texto and "valor favorable" in texto
    assert "solo se leen sus columnas" in texto and "Pulsa Continuar" in texto
    assert "pestaña «Umbrales»" in texto
    assert "desarrollo, validación o producción" in texto


def test_guia_uso_tiene_las_siete_entradas_nuevas(client):
    entradas = _entradas(client)
    titulos = {i: entradas[i]["titulo"] for i in range(13, 20)}
    assert titulos == {
        13: "Versiones y comparación",
        14: "Umbrales y su origen",
        15: "Plantilla de mapeo",
        16: "Capa humana",
        17: "Auditoría",
        18: "Riesgos",
        19: "Operar Vigía con un asistente de IA",
    }
    for entrada in entradas.values():
        assert entrada["pasos"] and entrada["para_que"]


@pytest.mark.parametrize("pieza", ["39 herramientas", ".mcp.json", "claude_desktop_config.json", "vigia-mcp"])
def test_guia_uso_mcp_en_lenguaje_de_usuario_con_la_configuracion(client, pieza):
    entrada = _entradas(client)[19]
    assert pieza in " ".join(entrada["pasos"])
    assert entrada["ruta"].startswith("/")


def test_guia_uso_umbrales_lista_los_cinco_origenes(client):
    texto = " ".join(_entradas(client)[14]["pasos"])
    for origen in ("línea base", "fabricante", "criterio del responsable", "política de la organización", "fábrica"):
        assert origen in texto


def test_la_seccion_multiclase_cubre_sus_puntos(client):
    """Clases, conjunto favorable, orden de probabilidades,
    etiquetas de texto, clase nueva en la predicción y en la etiqueta."""
    cuerpo = client.get("/api/content/guia-datos").json()
    seccion = next(s for s in cuerpo["secciones"] if s["id"] == "multiclase")
    texto = " ".join(seccion["notas"] + [seccion["para_que"]]).lower()
    for punto in (
        "de 3 a 20",
        "conjunto de clases favorables",
        "mismo orden",
        "mayúsculas",
        "error",
        "no bloquea",
    ):
        assert punto in texto, punto


def test_los_textos_de_dos_valores_remiten_al_tipo_multiclase(client):
    """Los textos que decían «Dos valores» valen en binario y remiten a multiclase."""
    cuerpo = client.get("/api/content/guia-datos").json()
    dos_valores = positiva = 0
    for seccion in cuerpo["secciones"]:
        if seccion["id"] == "multiclase":
            continue
        for columna in seccion["obligatorias"] + seccion["opcionales"]:
            for campo in ("que_es", "valores"):
                texto = columna[campo]
                bajo = texto.lower()
                if "dos valores" in bajo or "clase positiva" in bajo:
                    dos_valores += "dos valores" in bajo
                    positiva += "clase positiva" in bajo
                    assert "multiclase" in bajo, (seccion["id"], columna["nombre"])
    # Cinco textos «Dos valores» (predicción en dos secciones, etiqueta en tres)
    # y dos de «clase positiva» (probabilidad en dos secciones).
    assert (dos_valores, positiva) == (5, 2)
