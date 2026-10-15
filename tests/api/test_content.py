"""Tests de /api/content/metricas, /api/content/glosario,
/api/content/presentacion, /api/content/demo y /api/content/guia-uso."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from build.gen_content import (
        CLAVES_MOTOR,
        EXCEPCIONES_SIN_EQUIVALENTE,
        generar,
    )

    HAY_GENERADOR = (Path(__file__).resolve().parents[2] / "docs" / "ui-4").is_dir()
except ImportError:  # el árbol público no lleva el generador ni sus fuentes
    HAY_GENERADOR = False

requiere_generador = pytest.mark.skipif(
    not HAY_GENERADOR,
    reason="falta build/gen_content.py y sus fuentes en docs/, que no viajan en el árbol público",
)

# Recuentos que fijan los JSON versionados (antes salían del generador).
N_DOMINIO_DEMO = 39
N_PASOS_DEMO = 29
N_DIAPOSITIVAS = 10
N_ENTRADAS_GUIA_USO = 19

REPO_ROOT = Path(__file__).resolve().parents[2]
METRICAS_JSON = REPO_ROOT / "src" / "vigia" / "content" / "metricas-ayuda.json"
GLOSARIO_JSON = REPO_ROOT / "src" / "vigia" / "content" / "glosario.json"
TEXTOS_PANTALLA_JSON = REPO_ROOT / "src" / "vigia" / "content" / "textos-pantalla.json"
PROTOCOLO_HITOS_JSON = REPO_ROOT / "src" / "vigia" / "content" / "protocolo-hitos.json"
PRESENTACION_JSON = REPO_ROOT / "src" / "vigia" / "content" / "presentacion.json"
DEMO_JSON = REPO_ROOT / "src" / "vigia" / "content" / "demo-digestivo.json"
GUIA_USO_JSON = REPO_ROOT / "src" / "vigia" / "content" / "guia-uso.json"
CONTENT_DIR = REPO_ROOT / "src" / "vigia" / "content"
PASOS_PROTOCOLO = ("deteccion", "triaje", "investigacion", "decision", "seguimiento")


@requiere_generador
def test_las_43_medidas_del_motor_tienen_entrada(client):
    """Las 43 medidas que publica el motor
    (`Measurement.metric_key` real, no el listado del markdown) tienen su
    entrada en `metricas-ayuda.json`, servido por la API. Son 42
    más `explain_stability_ndcg`, con monitor
    `explain`, fórmula y umbral por defecto."""
    assert len(CLAVES_MOTOR) == 43
    cuerpo = client.get("/api/content/metricas").json()
    faltan = [clave for clave in CLAVES_MOTOR if clave not in cuerpo]
    assert not faltan, f"sin entrada de ayuda: {faltan}"
    for clave in CLAVES_MOTOR:
        entrada = cuerpo[clave]
        assert entrada["que_mide"], f"{clave} sin 'qué mide'"
        assert entrada["etiqueta"], f"{clave} sin etiqueta"
    estabilidad = cuerpo["explain_stability_ndcg"]
    assert estabilidad["monitor"] == "explain"
    assert estabilidad["formula"]
    assert estabilidad["umbral_por_defecto"] == {"limite_inferior": 0.5}


@requiere_generador
def test_las_metricas_sin_equivalente_local_llevan_excepcion_declarada(client):
    """Las tres métricas con umbral pero sin `Measurement` real
    no cuentan para las 42, pero llevan su excepción con motivo, no un hueco."""
    assert set(EXCEPCIONES_SIN_EQUIVALENTE) == {
        "model_quality_score",
        "input_metadata_drift_score",
        "output_metadata_drift_score",
    }
    cuerpo = client.get("/api/content/metricas").json()
    for clave, motivo in EXCEPCIONES_SIN_EQUIVALENTE.items():
        assert clave not in CLAVES_MOTOR
        assert cuerpo[clave]["nota"] == motivo
        assert cuerpo[clave]["formula"] is None


@requiere_generador
def test_json_versionado_coincide_con_lo_generado():
    """Puerta de regresión (igual que build/contraste.py para la paleta): si
    alguien edita a mano metricas-ayuda.json, el glosario, los textos de
    pantalla, el protocolo por hitos o los tres JSON de presentación, demo y guía sin regenerar,
    este test lo detecta."""
    metricas, glosario, textos_pantalla, protocolo_hitos, presentacion, demo, guia_uso = generar()
    assert json.loads(METRICAS_JSON.read_text(encoding="utf-8")) == metricas
    assert json.loads(GLOSARIO_JSON.read_text(encoding="utf-8")) == glosario
    assert json.loads(TEXTOS_PANTALLA_JSON.read_text(encoding="utf-8")) == textos_pantalla
    assert json.loads(PROTOCOLO_HITOS_JSON.read_text(encoding="utf-8")) == protocolo_hitos
    assert json.loads(PRESENTACION_JSON.read_text(encoding="utf-8")) == presentacion
    assert json.loads(DEMO_JSON.read_text(encoding="utf-8")) == demo
    assert json.loads(GUIA_USO_JSON.read_text(encoding="utf-8")) == guia_uso


def test_get_metricas_devuelve_solo_las_claves_declaradas(client):
    """`response_model` con `extra='forbid'`: un campo nuevo en el JSON que
    el schema no declare hace fallar la validación de FastAPI, no cuela."""
    resp = client.get("/api/content/metricas")
    assert resp.status_code == 200
    entrada = resp.json()["CX-2"]  # sin los bloques opcionales `multiclase` ni `regresion`
    assert set(entrada) == {
        "monitor",
        "etiqueta",
        "que_mide",
        "formula",
        "formula_vars",
        "como_se_lee",
        "umbral_por_defecto",
        "nota",
    }


@requiere_generador
def test_metricas_ayuda_sin_claves_tecnicas_en_texto_llano():
    """Ninguna entrada de `metricas-ayuda.json` cuela una variable técnica de
    `formula_vars` (p. ej. `rate_unpriv`, `details.confusion.tp`) dentro de
    `que_mide` ni `como_se_lee`: esos dos campos son el texto llano ante un
    usuario sin formación técnica; `formula` y
    `formula_vars` sí pueden llevar esas claves, son el detalle técnico de
    la fórmula instanciable."""
    metricas, _glosario, _textos_pantalla, _protocolo_hitos, _p, _d, _g = generar()
    for clave, entrada in metricas.items():
        variables = entrada.get("formula_vars") or []
        for campo in ("que_mide", "como_se_lee"):
            texto = (entrada.get(campo) or "").lower()
            for variable in variables:
                # una ruta con puntos (`details.confusion.tp`) o un
                # metric_key hermano (`rate_unpriv`): ninguno de los dos
                # debe aparecer literal en el texto llano.
                assert variable.lower() not in texto, (
                    f"{clave}.{campo} contiene la clave técnica {variable!r}"
                )


@requiere_generador
def test_glosario_tiene_las_claves_nuevas_de_vocabulario_y_cruzadas():
    """Entradas nuevas del glosario: vocabulario
    de la interfaz, los cuatro carriles del diario, CX-1/5/6 y explicabilidad."""
    _metricas, glosario, _textos_pantalla, _protocolo_hitos, _p, _d, _g = generar()
    esperadas = {
        "lote",
        "linea_base",
        "evaluacion",
        "etiqueta_lote",
        "protocolo",
        "fase_dataset",
        "tipo_dataset",
        "trabajo",
        "carril_humano",
        "carril_agente",
        "carril_modelo",
        "carril_sistema",
        "cx1",
        "cx5",
        "cx6",
        "explicacion_global",
        "explicacion_local",
        "metodo_permutacion",
        "metodo_shap",
        "importancia_caracteristica",
    }
    assert esperadas <= set(glosario)
    for clave in esperadas:
        assert glosario[clave]["etiqueta"]
        assert glosario[clave]["definicion"]


@requiere_generador
def test_textos_pantalla_tiene_las_cinco_secciones():
    """`textos-pantalla.json` cubre las cinco secciones y sus claves."""
    from build.gen_content import SECCIONES_TEXTOS_PANTALLA

    _metricas, _glosario, textos_pantalla, _protocolo_hitos, _p, _d, _g = generar()
    assert set(textos_pantalla) == set(SECCIONES_TEXTOS_PANTALLA)
    for seccion, claves in SECCIONES_TEXTOS_PANTALLA.items():
        assert set(textos_pantalla[seccion]) == set(claves)
        for clave in claves:
            assert textos_pantalla[seccion][clave]


def test_get_glosario_cubre_los_conceptos_de_la_spec(client):
    """Grupo supervisado, grupo de referencia, ventana, muestra
    mínima, intervalo, los cinco estados, valor frágil, orden manipulado."""
    resp = client.get("/api/content/glosario")
    assert resp.status_code == 200
    cuerpo = resp.json()
    esperados = {
        "grupo_supervisado",
        "grupo_referencia",
        "ventana",
        "muestra_minima",
        "intervalo",
        "estado_ok",
        "estado_aviso",
        "estado_alerta",
        "estado_inestable",
        "estado_sin_datos",
        "valor_fragil",
        "orden_manipulado",
    }
    assert esperados <= set(cuerpo)
    for clave in esperados:
        assert cuerpo[clave]["etiqueta"]
        assert cuerpo[clave]["definicion"]


def test_vocabulario_de_grupos_no_usa_unpriv_ni_priv_como_palabra(client):
    """'unpriv'/'priv' no aparecen en ningún texto visible como
    vocabulario (etiqueta de métrica y de concepto). `glosario.json` sí puede
    citar el término antiguo dentro de `grupo_supervisado`/`grupo_referencia`
    a modo de mapeo de columnas (criterio 5: "incluye el mapeo de columnas"),
    y `que_mide` puede citar una ruta de API literal
    (`details.counts.n_unpriv`): esas dos claves no cambian,
    solo el vocabulario de interfaz. `que_mide` sí se revisa contra la forma
    larga "privilegiado"/"no privilegiado", que nunca es una cita de API y
    sería una regresión de vocabulario si apareciera.
    """
    metricas = client.get("/api/content/metricas").json()
    glosario = client.get("/api/content/glosario").json()
    for entrada in metricas.values():
        for campo in ("etiqueta", "nota"):
            texto = entrada.get(campo) or ""
            assert "unpriv" not in texto
            assert "priv" not in texto.lower()
        assert "privilegiad" not in (entrada.get("que_mide") or "").lower()
    excluidos_por_citar_claves_de_api = ("grupo_supervisado", "grupo_referencia", "valor_fragil")
    for clave, entrada in glosario.items():
        if clave in excluidos_por_citar_claves_de_api:
            continue
        assert "unpriv" not in entrada["definicion"]
        assert "privilegiad" not in entrada["definicion"].lower()
        assert entrada["etiqueta"] not in ("unpriv", "priv")


def test_get_demo_devuelve_los_29_pasos_sin_huecos(client):
    """Los 29 pasos, id 0 a 28,
    sin huecos ni duplicados y sin paso opcional («Tras las medidas»). Incluye los
    pasos de deskilling y de riesgo."""
    assert N_PASOS_DEMO == 29
    cuerpo = client.get("/api/content/demo").json()
    ids = [paso["id"] for paso in cuerpo["pasos"]]
    assert ids == list(range(N_PASOS_DEMO))
    assert not any(paso["opcional"] for paso in cuerpo["pasos"])


def test_get_demo_guion_apunta_al_caso_digestivo_con_capa_humana(client):
    """El guion es `caso_digestivo` con dominio
    `digestivo` y con la capa humana del simulador encendida, que es lo que
    hace que el diario de uso exista y las seis reglas cruzadas se evalúen
    (el paso 21 ya no escribe una anotación de mentira)."""
    cuerpo = client.get("/api/content/demo").json()
    assert cuerpo["guion"] == {
        "scenario_key": "caso_digestivo",
        "domain": "digestivo",
        "with_human": True,
    }


def test_get_demo_fases_tiene_las_ocho_claves(client):
    """La línea base pasa de una
    fase a cinco semanas (`b1` a `b5`), con etiqueta y descripción cada una."""
    cuerpo = client.get("/api/content/demo").json()
    assert set(cuerpo["fases"]) == {
        "b1",
        "b2",
        "b3",
        "b4",
        "b5",
        "e1_evento",
        "e1_recovery",
        "lab:*",
    }
    for fase in cuerpo["fases"].values():
        assert fase["etiqueta"]
        assert fase["descripcion"]


def test_get_demo_dominio_tiene_los_39_pares_del_capitulo_d(client):
    """El diccionario de dominio, movido al guion de la demo,
    sigue cubriendo los 39 códigos de `vigia.sim.model.DIAGNOSIS_MAPPING`
    (capítulo L), cada uno con su etiqueta clínica del capítulo D."""
    from vigia.sim.model import DIAGNOSIS_MAPPING

    cuerpo = client.get("/api/content/demo").json()
    dominio = cuerpo["dominio"]
    assert len(dominio) == N_DOMINIO_DEMO
    assert set(dominio) == set(DIAGNOSIS_MAPPING)
    for etiqueta in dominio.values():
        assert etiqueta


def test_get_demo_las_cifras_verificadas_van_tal_cual(client):
    """Las cifras del guion que se verificaron sobre
    `caso_digestivo` y que, según la nota del guion, no dependen del número
    de semanas de línea base: FNRD 0,631/0,55/alerta (paso 13), impacto
    dispar 19,50/20,0/inestable (paso 14), deriva de confianza 0,370/0,30
    (paso 15), deriva de característica 0,189/0,15/alerta (paso 17),
    composición 32,9 (paso 18), exactitud 0,860/ok tras el evento (paso 12,
    en correcto con el umbral 0,75 de la demo, ya no en aviso) y FNRD
    0,282/ok tras las medidas (paso 24). Aparecen en el `dato` de su paso
    sin redondeo adicional y sin nota de verificación pendiente."""
    pasos = {p["id"]: p for p in client.get("/api/content/demo").json()["pasos"]}
    assert pasos[13]["dato"] == {
        "metric_key": "false_negative_rate_difference",
        "esperado": 0.631,
        "umbral": 0.55,
        "estado": "alerta",
        "verificacion": None,
    }
    assert pasos[14]["dato"] == {
        "metric_key": "fairness_value",
        "esperado": 19.50,
        "umbral": 20.0,
        "estado": "inestable",
        "verificacion": None,
    }
    # El paso 15 es el cálculo de la diferencia de falsos
    # negativos; los siguientes corren un puesto.
    assert pasos[15]["dato"] == {
        "metric_key": "false_negative_rate_difference",
        "esperado": 0.631,
        "umbral": 0.55,
        "estado": "alerta",
        "verificacion": None,
    }
    assert pasos[16]["dato"]["esperado"] == 0.370
    assert pasos[16]["dato"]["umbral"] == 0.30
    assert pasos[16]["dato"]["verificacion"] is None
    assert pasos[18]["dato"] == {
        "metric_key": "feature_drift_score",
        "esperado": 0.189,
        "umbral": 0.15,
        "estado": "alerta",
        "verificacion": None,
    }
    assert pasos[19]["dato"]["esperado"] == 32.9
    assert pasos[19]["dato"]["verificacion"] is None
    assert pasos[12]["dato"]["esperado"] == 0.860
    assert pasos[12]["dato"]["umbral"] == 0.75
    assert pasos[12]["dato"]["estado"] == "ok"
    assert pasos[12]["dato"]["verificacion"] is None
    # El paso opcional «Tras las medidas» (0,282) sale del
    # guion; el 28 es el laboratorio, sin dato.
    # El paso 3 tampoco lleva dato, la métrica no se ve en la pestaña
    # Monitores.
    assert pasos[28]["destino"]["ancla"] == "laboratorio"
    assert pasos[28]["dato"]["metric_key"] is None
    assert pasos[3]["dato"]["metric_key"] is None


def test_get_demo_las_cifras_de_la_linea_base_de_cinco_semanas_estan_cerradas(client):
    """Las cifras de las cinco
    semanas de línea base (pasos 4 a 7 y 9) y la estabilidad de la
    explicación tras el evento (paso 20) se reprodujeron en vivo el
    2026-09-16 sobre las siete fases de `caso_digestivo` y el guion las lleva
    cerradas: sin notas «(a verificar)» en ningún dato ni en la prosa."""
    pasos = {p["id"]: p for p in client.get("/api/content/demo").json()["pasos"]}
    esperados = {4: 0.88, 5: 0.305, 6: 0.88, 7: 0.0, 9: 1.0, 20: 0.984}
    for id_paso, valor in esperados.items():
        assert pasos[id_paso]["dato"]["esperado"] == pytest.approx(valor), id_paso
        assert pasos[id_paso]["dato"]["verificacion"] is None, id_paso
    assert pasos[4]["dato"]["umbral"] == 0.75
    assert pasos[5]["dato"]["umbral"] == 0.55
    assert pasos[6]["dato"]["umbral"] == 0.75
    assert pasos[7]["dato"]["umbral"] == 0.30
    assert pasos[20]["dato"]["umbral"] == 0.50
    for paso in pasos.values():
        assert paso["dato"]["verificacion"] is None, paso["id"]
        assert "a verificar" not in (paso["frase"] or ""), paso["id"]
    assert "0,082" in pasos[16]["frase"]  # el monitor de deriva


def test_get_demo_no_reivindica_edad_excluida(client):
    """Regla 1 del guion (del vault): el harness usa la edad
    como característica, así que ningún texto visible dice que está
    excluida como predictor."""
    cuerpo = client.get("/api/content/demo").json()
    textos = [p["frase"] for p in cuerpo["pasos"]]
    textos += [p["hace"] for p in cuerpo["pasos"] if p["hace"]]
    for texto in textos:
        assert "excluida como predictor" not in texto.lower()
        assert "edad excluida" not in texto.lower()


def test_get_demo_paso_27_menciona_el_modo_sin_evento(client):
    """Regla 2 del guion: D-EII-008, el modo sin evento detonante, se
    menciona en el paso de cierre (paso 27)."""
    cuerpo = client.get("/api/content/demo").json()
    paso_27 = next(p for p in cuerpo["pasos"] if p["id"] == 27)
    assert "cribado periódico" in paso_27["frase"] or "disparo automático" in paso_27["frase"]


def test_get_demo_paso_21_abre_las_cruzadas_y_no_escribe_en_el_diario(client):
    """El paso 21 deja de escribir
    una anotación en el diario y pasa a enseñar la alerta
    cruzada real del grupo de 18 a 35 años."""
    cuerpo = client.get("/api/content/demo").json()
    paso = next(p for p in cuerpo["pasos"] if p["id"] == 21)
    assert paso["destino"] == {"ruta": "/capa-humana", "ancla": "cruzadas"}
    assert "CX-1" in paso["hace"]
    assert "diario" not in paso["hace"].lower()
    assert paso["dato"]["metric_key"] is None


def test_get_demo_pasos_25_y_26_son_deskilling_y_riesgo(client):
    """Los dos pasos nuevos van
    entre el protocolo (24) y el cierre del caso (27), con destino a la capa
    humana y a la matriz de riesgos."""
    cuerpo = client.get("/api/content/demo").json()
    pasos = {p["id"]: p for p in cuerpo["pasos"]}
    assert pasos[25]["destino"] == {"ruta": "/capa-humana", "ancla": "deskilling"}
    assert pasos[26]["destino"] == {"ruta": "/riesgos", "ancla": "matriz"}
    for id_paso in (25, 26):
        assert pasos[id_paso]["tipo"] == "paso"
        assert pasos[id_paso]["fase_minima"] == 6
        assert pasos[id_paso]["dato"]["metric_key"] is None


def test_get_presentacion_diapositiva_5_tiene_el_contrafactual(client):
    """El contrafactual con/sin vigilancia que
    vivía en el `cierre` de la demo (paso 19 antiguo) pasa a la diapositiva 5.
    Las cifras (decenas con vigilancia,
    cientos o miles sin ella) viven solo en el esquema: las viñetas no
    repiten el diagrama y cuentan qué es vigilar."""
    cuerpo = client.get("/api/content/presentacion").json()
    diapositiva_5 = next(d for d in cuerpo["diapositivas"] if d["id"] == 5)
    diagrama = diapositiva_5["diagrama"]
    assert "decenas" in diagrama
    assert "cientos" in diagrama or "miles" in diagrama
    puntos = " ".join(diapositiva_5["puntos"])
    assert "decenas" not in puntos
    # «Gobernar de forma activa», con el tiempo de detección.
    assert "detección" in puntos


def test_get_demo_devuelve_solo_las_claves_declaradas(client):
    """`response_model` con `extra='forbid'`: un campo nuevo en el JSON que
    el schema no declare hace fallar la validación de FastAPI, no cuela."""
    cuerpo = client.get("/api/content/demo").json()
    assert set(cuerpo) == {"guion", "fases", "pasos", "laboratorio", "dominio"}
    assert set(cuerpo["guion"]) == {"scenario_key", "domain", "with_human"}
    fase = next(iter(cuerpo["fases"].values()))
    assert set(fase) == {"etiqueta", "descripcion"}
    paso = cuerpo["pasos"][0]
    assert set(paso) == {
        "id",
        "tipo",
        "opcional",
        "kicker",
        "titulo",
        "frase",
        "hace",
        "ve",
        "destino",
        "dato",
        "fase_minima",
        "capacidad",
    }
    assert set(paso["destino"]) == {"ruta", "ancla"}
    assert set(paso["dato"]) == {"metric_key", "esperado", "umbral", "estado", "verificacion"}
    assert set(cuerpo["laboratorio"]) == {"parametros"}
    parametro = cuerpo["laboratorio"]["parametros"][0]
    assert set(parametro) == {"clave", "etiqueta", "min", "max", "paso", "por_defecto"}


def test_get_presentacion_devuelve_las_10_diapositivas_sin_huecos(client):
    """10 diapositivas (la antigua 8 se quita y las siguientes se renumeran):
    id 1 a 10, sin huecos, cada una con `puntos`."""
    assert N_DIAPOSITIVAS == 10
    cuerpo = client.get("/api/content/presentacion").json()
    ids = [dia["id"] for dia in cuerpo["diapositivas"]]
    assert ids == list(range(1, N_DIAPOSITIVAS + 1))
    diapositiva = cuerpo["diapositivas"][0]
    assert set(diapositiva) == {
        "id",
        "kicker",
        "titulo",
        "puntos",
        "frase",
        "diagrama",
        "fuente",
        "consultado",
        "estado",
        "notas",
    }


def test_get_presentacion_diapositivas_tienen_de_2_a_4_puntos(client):
    """Cada diapositiva lleva de 2 a 4 viñetas cortas, sin punto
    final."""
    cuerpo = client.get("/api/content/presentacion").json()
    for dia in cuerpo["diapositivas"]:
        puntos = dia["puntos"]
        tope = 5 if dia["id"] == 10 else 4  # La 10 enumera los pasos de la demo
        assert 2 <= len(puntos) <= tope, f"diapositiva {dia['id']}: {len(puntos)} puntos"
        for punto in puntos:
            assert punto, f"diapositiva {dia['id']}: viñeta vacía"
            assert not punto.endswith("."), f"diapositiva {dia['id']}: viñeta con punto final"


def test_get_presentacion_diapositiva_3_sin_fuente_ni_doi_en_notas(client):
    """La diapositiva 3 no cita fuente en pantalla ni DOI clínicos en las notas."""
    cuerpo = client.get("/api/content/presentacion").json()
    diapositiva_3 = next(d for d in cuerpo["diapositivas"] if d["id"] == 3)
    assert diapositiva_3["fuente"] == []
    assert "doi.org" not in diapositiva_3["notas"]
    assert "Fuentes verificadas" not in diapositiva_3["notas"]


def test_get_presentacion_fuente_no_vacia_en_diapositiva_6(client):
    """La diapositiva 6 (marco legal) sigue citando fuente externa con URL,
    verificada: el Reglamento de IA. La Estrategia de IA del SNS (eIASNS) y el
    MDR salieron de la presentación al quitar lo clínico."""
    cuerpo = client.get("/api/content/presentacion").json()
    diapositiva_6 = next(d for d in cuerpo["diapositivas"] if d["id"] == 6)
    fuente = diapositiva_6["fuente"]
    assert fuente
    for entrada in fuente:
        assert set(entrada) == {"texto", "url"}
        assert entrada["texto"]
    assert any(entrada["url"] for entrada in fuente)
    assert any("2024/1689" in entrada["texto"] for entrada in fuente)
    assert not any("eIASNS" in e["texto"] or "MDR" in e["texto"] for e in fuente)
    assert diapositiva_6["consultado"] == "2026-09-16"


def test_get_guia_uso_devuelve_las_19_entradas_sin_huecos(client):
    """La guía de uso tiene 19 entradas,
    sin huecos."""
    assert N_ENTRADAS_GUIA_USO == 19  # 12 de base más siete
    cuerpo = client.get("/api/content/guia-uso").json()
    ids = [entrada["id"] for entrada in cuerpo["entradas"]]
    assert ids == list(range(1, N_ENTRADAS_GUIA_USO + 1))
    entrada = cuerpo["entradas"][0]
    assert set(entrada) == {
        "id",
        "titulo",
        "para_que",
        "pasos",
        "ruta",
        "captura",
        "ver_tambien",
        "estado",
    }
    assert entrada["pasos"]


def test_get_guia_uso_ver_tambien_son_claves_validas_y_ruta_empieza_por_barra(client):
    """`ver_tambien` pierde el sufijo «(nueva)» y solo referencia claves
    reales del glosario; `ruta` es siempre un enlace interno."""
    glosario = client.get("/api/content/glosario").json()
    cuerpo = client.get("/api/content/guia-uso").json()
    for entrada in cuerpo["entradas"]:
        assert entrada["ruta"].startswith("/")
        for clave in entrada["ver_tambien"]:
            assert "(nueva)" not in clave
            assert clave in glosario, f"guía {entrada['id']}: ver_tambien desconocida {clave!r}"


def test_glosario_tiene_las_entradas_de_protocolo_y_riesgos(client):
    """Cinco entradas más sobre las 37 anteriores (protocolo por hitos y los
    tres conceptos que preparan la matriz de riesgos)."""
    cuerpo = client.get("/api/content/glosario").json()
    nuevas = {"hito", "entregable", "riesgo", "impacto", "probabilidad"}
    assert nuevas <= set(cuerpo)
    for clave in nuevas:
        assert cuerpo[clave]["etiqueta"]
        assert cuerpo[clave]["definicion"]


def test_glosario_tiene_las_entradas_de_metrica_principal_y_explicacion_automatica(client):
    """Dos conceptos más sobre los 42 anteriores. Un tercero,
    "datos_desidentificados", se retiró: Vigía ya no pseudonimiza ni detecta columnas
    identificadoras."""
    cuerpo = client.get("/api/content/glosario").json()
    nuevas = {"metrica_principal", "explicacion_automatica"}
    assert nuevas <= set(cuerpo)
    assert "datos_desidentificados" not in cuerpo
    for clave in nuevas:
        assert cuerpo[clave]["etiqueta"]
        assert cuerpo[clave]["definicion"]


def test_glosario_tiene_las_entradas_del_panel_de_variable_en_deriva(client):
    """Cuatro conceptos del panel de variable en deriva, sobre las 44
    anteriores (45 menos "datos_desidentificados")."""
    cuerpo = client.get("/api/content/glosario").json()
    nuevas = {"psi", "ks", "perfil_variable", "cadena_correlacion"}
    assert nuevas <= set(cuerpo)
    for clave in nuevas:
        assert cuerpo[clave]["etiqueta"]
        assert cuerpo[clave]["definicion"]


def test_glosario_tiene_las_entradas_de_presentacion_demo_y_guia(client):
    """Cuatro conceptos de la
    presentación, la demo guiada y la guía de uso, sobre las 53 anteriores,
    para un total de 57; 58 con `etapa_alerta` (el estado de la alerta como
    último hito hecho) y los carriles con nombre."""
    cuerpo = client.get("/api/content/glosario").json()
    nuevas = {"etiqueta_favorable", "severidad", "motivo", "rol"}
    assert nuevas <= set(cuerpo)
    assert cuerpo["etapa_alerta"]["etiqueta"] == "Estado de la alerta"
    assert cuerpo["carril_modelo"]["etiqueta"] == "Carril Vigía"
    for clave in nuevas:
        assert cuerpo[clave]["etiqueta"]
        assert cuerpo[clave]["definicion"]


def test_glosario_tiene_distribuciones_deriva(client):
    """El bloque
    «Distribuciones» del monitor de deriva tiene su entrada de glosario."""
    cuerpo = client.get("/api/content/glosario").json()
    assert "distribuciones_deriva" in cuerpo
    assert cuerpo["distribuciones_deriva"]["etiqueta"] == "Distribuciones (deriva)"
    assert cuerpo["distribuciones_deriva"]["definicion"]


def test_glosario_tiene_deriva_lote_a_lote(client):
    """La pestaña «Lote a
    lote» del panel de variables del monitor de deriva tiene su entrada de
    glosario."""
    cuerpo = client.get("/api/content/glosario").json()
    assert "deriva_lote_a_lote" in cuerpo
    assert cuerpo["deriva_lote_a_lote"]["etiqueta"] == "Deriva lote a lote"
    assert "violín" in cuerpo["deriva_lote_a_lote"]["definicion"]
    assert "Solo para variables numéricas" in cuerpo["deriva_lote_a_lote"]["definicion"]


def test_glosario_tiene_las_entradas_de_capa_humana_y_auditoria(client):
    """Deskilling,
    overrides, vista propia, las tres cruzadas nuevas (CX-2 a CX-4),
    calibración, dossier de auditoría, su revisión, el crosswalk, outcome,
    el token del servidor MCP y el backend de lenguaje, sobre las 58
    entradas anteriores."""
    cuerpo = client.get("/api/content/glosario").json()
    nuevas = {
        "deskilling",
        "override",
        "vista_propia",
        "cx2",
        "cx3",
        "cx4",
        "calibracion_cruzadas",
        "dossier",
        "revision_dossier",
        "crosswalk",
        "outcome",
        "token_mcp",
        "backend_llm",
    }
    assert nuevas <= set(cuerpo)
    # test_guia_datos.py añade seis y test_content_regresion.py, cuatro
    assert len(cuerpo) == 71 + 6 + 4
    for clave in nuevas:
        assert cuerpo[clave]["etiqueta"]
        assert cuerpo[clave]["definicion"]
    for clave in ("cx1", "cx5", "cx6"):
        texto = cuerpo[clave]["definicion"]
        assert "clínic" not in texto and "pacient" not in texto


def test_get_protocolo_hitos_devuelve_los_cinco_pasos_en_orden(client):
    """La plantilla de contenido del protocolo por
    hitos, servida como objeto con `pasos` en el orden de los cinco
    pasos, con las claves exactas."""
    resp = client.get("/api/content/protocolo-hitos")
    assert resp.status_code == 200
    cuerpo = resp.json()
    assert set(cuerpo) == {"pasos"}
    pasos = cuerpo["pasos"]
    assert [paso["key"] for paso in pasos] == list(PASOS_PROTOCOLO)
    assert [paso["orden"] for paso in pasos] == [1, 2, 3, 4, 5]
    for paso in pasos:
        assert set(paso) == {"key", "orden", "titulo", "descripcion", "entregables"}
        assert paso["titulo"]
        assert paso["descripcion"]
        assert paso["entregables"]
        assert all(isinstance(item, str) and item for item in paso["entregables"])


@requiere_generador
def test_protocolo_hitos_json_versionado_tiene_los_cinco_pasos(client):
    """Puerta de regresión (`--check`, igual que el resto de `content/`): el
    fichero versionado (una lista) coincide con lo que genera
    `PROTOCOLO_HITOS` y con los `pasos` que sirve la API."""
    from build.gen_content import PROTOCOLO_HITOS

    assert [paso["key"] for paso in PROTOCOLO_HITOS] == list(PASOS_PROTOCOLO)
    versionado = json.loads(PROTOCOLO_HITOS_JSON.read_text(encoding="utf-8"))
    assert versionado == PROTOCOLO_HITOS
    cuerpo = client.get("/api/content/protocolo-hitos").json()
    assert cuerpo["pasos"] == PROTOCOLO_HITOS


# Ficheros de `content/` que narran el caso Digestivo con
# fines de demostración, exentos del vocabulario neutro (el diccionario de dominio de la demo
# sigue poniendo los nombres clínicos donde toca). `demo-digestivo.json` es el guion de
# `/demo`; `presentacion.json` son sus diapositivas previas
# (`pages/demo/presentacion/index.tsx`), la misma narrativa y con enlace
# explícito al guion en su última diapositiva ("«Ejecutar la demo» abre el
# paso 0 del guion de la demo"). El resto de `content/` (glosario, ayuda de
# métricas, textos de pantalla, protocolo, guía de uso) es vocabulario del
# producto y no puede depender del dominio del proyecto (`Project.domain`
# es libre por defecto; la sanidad es solo el dominio de la demo).
FICHEROS_DEMO_EXENTOS = {"demo-digestivo.json", "presentacion.json"}


def test_content_fuera_de_la_demo_usa_vocabulario_neutro():
    """Ningún fichero de `content/` fuera de la demo dice
    «paciente» ni «el clínico» («profesional» y «persona afectada»). La regla es
    de todo `content/` menos la demo."""
    ficheros = sorted(CONTENT_DIR.glob("*.json"))
    revisados = [f for f in ficheros if f.name not in FICHEROS_DEMO_EXENTOS]
    assert revisados, "no se ha encontrado ningún fichero de content/ para revisar"
    infracciones = []
    for fichero in revisados:
        texto = fichero.read_text(encoding="utf-8").lower()
        if "paciente" in texto:
            infracciones.append(f"{fichero.name}: contiene «paciente»")
        for palabra in ("el clínico", "clínic", "derivar", "cribado"):
            if palabra in texto:
                infracciones.append(f"{fichero.name}: contiene «{palabra}»")
    assert not infracciones, infracciones


def test_guia_uso_dominio_y_favorable_son_neutros(client):
    """La guía de crear un modelo (guía 2) no condiciona el
    dominio a «clínico» ni la etiqueta favorable a «el paciente»; sigue el
    patrón del vocabulario neutro (glosario, ver test_glosario_tiene_las_13_entradas_...)."""
    cuerpo = client.get("/api/content/guia-uso").json()
    crear_modelo = next(e for e in cuerpo["entradas"] if e["titulo"] == "Crear un modelo")
    texto = " ".join(crear_modelo["pasos"]).lower()
    assert "clínic" not in texto and "pacient" not in texto
    assert "persona afectada" in texto


def test_glosario_tipo_dataset_documenta_la_semantica_de_refer(client):
    """La ayuda de la subida de registros de uso (el concepto
    `tipo_dataset` del glosario, ya el único que menciona el registro de uso
    y se enseña como ⓘ en la columna «Tipo» de la tabla de datasets) dice
    que `refer` (o 1) es la decisión favorable para la persona afectada, en
    el mismo sentido que la etiqueta favorable del modelo."""
    cuerpo = client.get("/api/content/glosario").json()
    texto = cuerpo["tipo_dataset"]["definicion"]
    assert "`refer`" in texto and "(o 1)" in texto
    assert "decisión favorable para la persona afectada" in texto
    assert "en el mismo sentido que la etiqueta favorable del modelo" in texto
    assert "`no-refer`" in texto and "(o 0)" in texto


# --- Ayuda de la subida del registro de uso -----------------------


def test_registro_uso_ayuda_columnas_coinciden_con_el_servicio(client):
    """Las columnas de la ayuda son las del servicio (no se desvían si
    cambia `REQUIRED_COLUMNS`/`OPTIONAL_COLUMNS`), con formatos de fecha y la
    frase acordada."""
    from vigia.app.services.human_layer import OPTIONAL_COLUMNS, REQUIRED_COLUMNS

    cuerpo = client.get("/api/content/registro-uso").json()
    assert tuple(c["nombre"] for c in cuerpo["columnas_obligatorias"]) == tuple(REQUIRED_COLUMNS)
    assert tuple(c["nombre"] for c in cuerpo["columnas_opcionales"]) == tuple(OPTIONAL_COLUMNS)
    assert [f["formato"] for f in cuerpo["formatos_fecha"]] == ["aaaa-mm-dd", "dd/mm/aaaa", "dd-mm-aaaa"]
    cod = cuerpo["codificacion"]
    assert "decisión favorable para la persona afectada" in cod["frase"]
    assert "en el mismo sentido que la etiqueta favorable del modelo" in cod["frase"]
    assert cod["por_defecto"] == "refer"
    assert [o["valor"] for o in cod["opciones"]] == ["refer", "no-refer", "1", "0"]
    assert cod["aplica_a"] == ["human_decision", "model_output", "ground_truth"]


def test_registro_uso_ejemplo_tiene_cinco_filas_y_se_descarga(client):
    cuerpo = client.get("/api/content/registro-uso").json()
    ejemplo = cuerpo["ejemplo"]
    assert ejemplo["n_filas"] == 5 == len(ejemplo["filas"])
    assert ejemplo["csv"].count("\n") == 6  # cabecera y cinco filas
    resp = client.get("/api/content/registro-uso/ejemplo.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert ejemplo["nombre_fichero"] in resp.headers["content-disposition"]
    assert resp.text == ejemplo["csv"]


def test_registro_uso_ejemplo_entra_por_la_subida_real(client):
    """El ejemplo descargable se sube tal cual y da cinco filas."""
    from tests.api.conftest import actor_headers

    ejemplo = client.get("/api/content/registro-uso/ejemplo.csv")
    proyecto = client.post(
        "/api/projects", json={"name": "registro-ejemplo", "domain": "reuma"}, headers=actor_headers("miguel")
    ).json()
    resp = client.post(
        f"/api/projects/{proyecto['id']}/usage-logs/upload",
        files={"file": ("registro-uso-ejemplo.csv", ejemplo.content, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["n_rows"] == 5


@requiere_generador
def test_registro_uso_ayuda_esta_regenerada_y_sin_vocabulario_de_paciente():
    """`gen_content --check` cubre el fichero nuevo y el vocabulario neutro
    (el barrido de `content/` ya lo incluye)."""
    from build.gen_content import REGISTRO_USO_JSON, _volcar
    from build.gen_content_registro_uso import generar_registro_uso

    assert REGISTRO_USO_JSON.read_text(encoding="utf-8") == _volcar(generar_registro_uso())
    assert "paciente" not in REGISTRO_USO_JSON.read_text(encoding="utf-8").lower()


def test_glosario_cx6_recoge_la_regla_de_una_alerta_por_pareja_y_la_cascada():
    """La definición de CX-6 cierra con la regla de la
    pareja de dos grupos y con las dos exclusiones (alerta viva de equidad
    sobre el grupo y alerta CX-1 viva)."""
    definicion = json.loads(GLOSARIO_JSON.read_text(encoding="utf-8"))["cx6"]["definicion"]
    assert definicion.endswith(
        " Con dos grupos sale una sola alerta por pareja, anclada en el grupo "
        "que menos se aparta del modelo. Tampoco se emite mientras el monitor "
        "de equidad tenga una alerta viva (abierta, reconocida o en "
        "observación) sobre ese grupo, ni en un grupo con una alerta CX-1 "
        "viva: esa señal ya está cubierta, y CX-6 sigue callada en el grupo "
        "hasta que alguien cierre esa alerta."
    )
    assert "—" not in definicion
