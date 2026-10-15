"""El contenido de la regresión (plantilla, guía de datos, ayuda de las
métricas, bloque `regresion`, glosario y guía de uso) y el título de sus alertas.

Lee el contenido servido por la API y el JSON versionado, sin el generador: corre también
en el árbol público. Datos sintéticos de `_datos_regresion` para el título de la alerta.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.api import _datos_regresion as r
from vigia.app.content_loader import metric_label
from vigia.core.schema import CLAVES_EQUIDAD_ERROR, CLAVES_REGRESION

CAMPOS = ("que_mide", "como_se_lee", "formula", "formula_vars", "umbral_por_defecto")
PROHIBIDO = ("paciente", "el clínico", "clínic", "derivar", "cribado", "—")


def _efectivo(entrada: dict[str, Any]) -> dict[str, Any]:
    """El bloque que ve un proyecto de regresión: un campo nulo hereda el de la entrada."""
    efectivo = {campo: entrada.get(campo) for campo in CAMPOS}
    for campo, valor in (entrada.get("regresion") or {}).items():
        if valor is not None:
            efectivo[campo] = valor
    return efectivo


def _metricas(client: TestClient) -> dict[str, Any]:
    resp = client.get("/api/content/metricas")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Plantilla y guía de datos
# ---------------------------------------------------------------------------


def test_la_plantilla_regresion_se_sirve_por_el_router_de_contenido(client: TestClient):
    resp = client.get("/api/content/plantillas/regresion.csv")
    assert resp.status_code == 200, resp.text
    assert "plantilla-regresion-sintetico.csv" in resp.headers["content-disposition"]
    cabecera = resp.text.splitlines()[0].split(",")
    assert "prediction" in cabecera and "label" in cabecera
    assert not [c for c in cabecera if c.startswith("prob")]


def test_la_unidad_de_la_plantilla_es_la_que_cita_la_guia_de_datos(client: TestClient):
    from vigia.app.services.plantillas_datos import UNIDAD_PLANTILLA_REGRESION

    guia = client.get("/api/content/guia-datos").json()
    seccion = next(s for s in guia["secciones"] if s["id"] == "regresion")
    texto = " ".join([seccion.get("descripcion") or "", *seccion["notas"]])
    assert UNIDAD_PLANTILLA_REGRESION in texto


def test_la_guia_de_datos_tiene_la_seccion_de_regresion(client: TestClient):
    guia = client.get("/api/content/guia-datos").json()
    seccion = next(s for s in guia["secciones"] if s["id"] == "regresion")
    assert seccion["plantilla"] == "regresion"
    assert [c["nombre"] for c in seccion["obligatorias"]] == ["id", "prediction", "label"]
    notas = " ".join(seccion["notas"])
    for pieza in (
        "unidad de la salida",
        "de uno a tres intervalos",
        "después no cambia",  # Fijo tras congelar
        "Sin rango",  # qué cambia sin rango
        "error de cada grupo",
        "human_decision",  # formato del registro de uso con cifras
        "model_output",
        "ground_truth",
        "sin unidad",
    ):
        assert pieza in notas, pieza
    for columna in seccion["obligatorias"]:
        assert "clase" not in columna["que_es"].lower()


def test_la_clase_favorable_de_la_guia_remite_al_rango_en_regresion(client: TestClient):
    guia = client.get("/api/content/guia-datos").json()
    pasos = " ".join(guia["clase_favorable"]["pasos"])
    assert "regresión" in pasos and "rango favorable" in pasos


# ---------------------------------------------------------------------------
# Las nueve claves
# ---------------------------------------------------------------------------


def test_las_nueve_claves_de_regresion_tienen_entrada_completa(client: TestClient):
    metricas = _metricas(client)
    assert len(CLAVES_REGRESION) == 9
    for clave in CLAVES_REGRESION:
        entrada = metricas[clave]
        for campo in ("monitor", "etiqueta", "que_mide", "formula", "como_se_lee", "nota"):
            assert entrada[campo], (clave, campo)
        assert entrada["umbral_por_defecto"] == {}, clave  # sin valor de fábrica
        assert "regresion" not in entrada and "multiclase" not in entrada, clave
        texto = " ".join(str(entrada[c]) for c in ("que_mide", "como_se_lee", "nota"))
        assert not any(p in texto.lower() for p in PROHIBIDO), clave
    con_umbral = [c for c in CLAVES_REGRESION if c not in ("mean_squared_error", "median_absolute_error")]
    for clave in con_umbral:
        assert "línea base" in metricas[clave]["nota"], clave
    for clave in ("mean_squared_error", "median_absolute_error"):
        assert "sin umbral" in metricas[clave]["nota"], clave


def test_el_sesgo_medio_dice_el_signo_con_palabras(client: TestClient):
    """Negativo es infraestimar."""
    for clave in ("mean_error", "mean_error_difference"):
        texto = _metricas(client)[clave]["como_se_lee"]
        assert "negativo" in texto and "infraestima" in texto, clave
    assert "positivo" in _metricas(client)["mean_error"]["como_se_lee"]


def test_las_claves_de_regresion_no_mueven_el_recuento_del_motor(client: TestClient):
    """`CLAVES_MOTOR == 43` no cambia; las nueve van aparte (el recuento exacto lo
    comprueba `test_content.py` con el generador). Aquí, que ninguna de las 43 anteriores
    se llama como una de regresión."""
    metricas = _metricas(client)
    assert len(metricas) == 43 + 3 + 7 + 9  # motor, excepciones, cruzadas (con human_review_zero) y regresión
    assert set(CLAVES_EQUIDAD_ERROR) <= set(CLAVES_REGRESION)


# ---------------------------------------------------------------------------
# Bloque `regresion`
# ---------------------------------------------------------------------------


def test_la_deriva_de_la_prediccion_dice_ks_y_sin_umbral_de_fabrica(client: TestClient):
    entrada = _metricas(client)["prediction_drift_score"]
    efectivo = _efectivo(entrada)
    assert "Kolmogorov-Smirnov" in efectivo["formula"]
    assert efectivo["umbral_por_defecto"] == {}
    assert efectivo["formula_vars"] == []
    assert "línea base" in efectivo["como_se_lee"] and "sin unidad" in efectivo["como_se_lee"]
    # Binario y multiclase conservan lo suyo.
    assert entrada["umbral_por_defecto"], "binario conserva su umbral de fábrica"
    assert entrada["multiclase"]["umbral_por_defecto"] == {}
    assert "Kolmogorov" not in entrada["formula"]


def test_la_deriva_de_las_variables_dice_la_misma_escala_que_la_prediccion(client: TestClient):
    entrada = _metricas(client)["feature_drift_score"]
    efectivo = _efectivo(entrada)
    assert "misma escala" in efectivo["como_se_lee"] and "sin unidad" in efectivo["como_se_lee"]
    # Solo cambia la lectura: lo demás se hereda de la entrada.
    assert efectivo["que_mide"] == entrada["que_mide"]
    assert efectivo["umbral_por_defecto"] == entrada["umbral_por_defecto"]


def test_las_de_equidad_dicen_que_sin_rango_la_medida_sale_sin_datos(client: TestClient):
    metricas = _metricas(client)
    equidad = [c for c, e in metricas.items() if e["monitor"] == "fairness" and c not in CLAVES_REGRESION]
    assert len(equidad) == 19
    for clave in equidad:
        efectivo = _efectivo(metricas[clave])
        texto = f"{efectivo['que_mide']} {efectivo['como_se_lee']}"
        assert "sin datos" in texto or "no tiene rango favorable" in texto, clave
    # Las tres de error de grupo no dependen del rango: no dicen que salgan sin datos.
    for clave in CLAVES_EQUIDAD_ERROR:
        assert "regresion" not in metricas[clave] or "sin datos" not in (
            metricas[clave]["regresion"].get("como_se_lee") or ""
        ), clave


def test_las_diecinueve_de_equidad_dicen_rango_favorable_y_el_caso_sin_rango(client: TestClient):
    metricas = _metricas(client)
    equidad = [c for c, e in metricas.items() if e["monitor"] == "fairness" and c not in CLAVES_REGRESION]
    assert len(equidad) == 19
    for clave in equidad:
        assert "regresion" in metricas[clave], clave
        efectivo = _efectivo(metricas[clave])
        assert "rango favorable" in efectivo["que_mide"], clave
        # Las que tienen umbral dicen qué pasa sin rango.
        if metricas[clave]["umbral_por_defecto"]:
            assert "no tiene rango favorable" in efectivo["como_se_lee"], clave
    # El texto de binario y multiclase no se toca.
    assert "rango favorable" not in metricas["disparate_impact"]["que_mide"]
    assert "rango favorable" not in metricas["disparate_impact"]["multiclase"]["que_mide"]


def test_la_explicabilidad_dice_aumento_del_error_y_la_estabilidad_no_cambia_de_umbral(
    client: TestClient,
):
    entrada = _metricas(client)["explain_stability_ndcg"]
    efectivo = _efectivo(entrada)
    assert "RMSE" in efectivo["que_mide"]
    assert efectivo["umbral_por_defecto"] == {"limite_inferior": 0.5}


def test_el_bloque_efectivo_no_cuela_claves_tecnicas_en_texto_llano(client: TestClient):
    for clave, entrada in _metricas(client).items():
        if "regresion" not in entrada:
            continue
        efectivo = _efectivo(entrada)
        for variable in efectivo["formula_vars"] or []:
            for campo in ("que_mide", "como_se_lee"):
                assert variable.lower() not in (efectivo[campo] or "").lower(), (clave, campo)
        texto = " ".join(str(v or "") for v in (entrada["regresion"] or {}).values() if isinstance(v, str))
        assert not any(p in texto.lower() for p in PROHIBIDO), clave


# ---------------------------------------------------------------------------
# Glosario y guía de uso
# ---------------------------------------------------------------------------


def test_el_glosario_gana_rango_residuo_sesgo_y_unidad(client: TestClient):
    glosario = client.get("/api/content/glosario").json()
    for clave in ("rango_favorable", "residuo", "sesgo_medio", "unidad_salida"):
        assert glosario[clave]["etiqueta"] and glosario[clave]["definicion"], clave
        assert not any(p in glosario[clave]["definicion"].lower() for p in PROHIBIDO), clave
    assert "de uno a tres intervalos" in glosario["rango_favorable"]["definicion"]
    assert "regresión" in glosario["etiqueta_favorable"]["definicion"]
    assert "regresión" in glosario["plantilla_mapeo"]["definicion"]


def test_la_guia_de_uso_dice_los_tres_tipos_el_limite_y_la_tabla_de_cambios(client: TestClient):
    entradas = client.get("/api/content/guia-uso").json()["entradas"]
    primera = next(e for e in entradas if e["id"] == 1)
    texto = " ".join(primera["pasos"])
    assert "dos clases" in texto and "multiclase" in texto and "regresión" in texto
    assert "La regresión no está todavía" not in texto
    capa_humana = next(e for e in entradas if e["titulo"] == "Capa humana")
    pasos = " ".join(capa_humana["pasos"])
    limite = next(p for p in capa_humana["pasos"] if p.startswith("En regresión, un cambio"))
    assert "no cruza el corte del rango" in limite and "no cuenta como override" in limite
    assert "diferencia media" in limite and "no tiene umbral" in limite
    # La tabla de cambios en los tres tipos.
    assert "refer y no-refer" in pasos and "cada clase" in pasos and "dentro o fuera del rango" in pasos
    # La lectura del deskilling sigue presente.
    assert any(p.startswith("Cómo se lee el deskilling") for p in capa_humana["pasos"])


# ---------------------------------------------------------------------------
# Ayuda de la equidad con pocas filas
# ---------------------------------------------------------------------------


def test_las_medidas_de_error_por_grupo_dicen_que_un_grupo_pequeno_lleva_solo_n_y_motivo(
    client: TestClient,
):
    metricas = _metricas(client)
    for clave in CLAVES_EQUIDAD_ERROR:
        texto = metricas[clave]["como_se_lee"]
        assert "mínimo por grupo" in texto and "número de filas y el motivo" in texto, clave


# ---------------------------------------------------------------------------
# El título de la alerta usa la etiqueta, no la clave cruda
# ---------------------------------------------------------------------------


def test_el_titulo_de_las_alertas_de_regresion_sale_con_su_etiqueta(client: TestClient):
    for clave in CLAVES_REGRESION:
        assert metric_label(clave), clave
    p, _t = r.linea_base_regresion(client, "r5-titulo-etiqueta", n=500)
    r.subir_e_ingerir(
        client, p, r.filas_regresion(400, semilla=21, desplazar_grupo_b=3.0, prefijo="b"),
        rol="production", evaluar=True,
    )
    alertas = client.get(f"/api/projects/{p['id']}/alerts").json()["items"]
    de_regresion = [a for a in alertas if a["metric_key"] in CLAVES_REGRESION]
    assert de_regresion, [a["metric_key"] for a in alertas]
    for alerta in de_regresion:
        assert alerta["metric_key"] not in alerta["title"], alerta["title"]
        assert alerta["title"].startswith(metric_label(alerta["metric_key"])), alerta["title"]
    # Y los eventos del diario de las alertas no llevan la clave cruda. (El evento de umbrales
    # aplicados desde la línea base lista claves crudas, un defecto conocido.)
    eventos = client.get("/api/events", params={"project_id": p["id"], "limit": 200}).json()["items"]
    de_alertas = [e["titulo"] for e in eventos if e["action"].startswith("alerta.")]
    assert de_alertas
    for titulo in de_alertas:
        assert not any(clave in titulo for clave in CLAVES_REGRESION), titulo
