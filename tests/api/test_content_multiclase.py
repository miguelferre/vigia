"""El bloque `multiclase` de `metricas-ayuda.json`, el
glosario y la guía de uso (alcance del modelo y cómo se lee cada medida).

Leen el contenido servido por la API y el JSON versionado, sin el generador:
corren también en el árbol público.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from vigia.core.schema import CLAVES_REGRESION
from vigia.human.ir_adapter import MIN_N

CAMPOS = ("que_mide", "como_se_lee", "formula", "formula_vars", "umbral_por_defecto")
# Las que cambian de fórmula en multiclase.
CAMBIAN_DE_FORMULA = (
    "accuracy",
    "precision",
    "recall",
    "true_positive_rate",
    "false_positive_rate",
    "matthews_correlation_coefficient",
)
# Sin bloque: CX-2 a CX-6 (comparan tasas de override y acuerdo, no dependen de
# las clases; CX-1 sí, por sus falsos negativos), la deriva de variables (no
# depende de las clases) y las tres entradas sin equivalente local.
SIN_BLOQUE = {
    # Las nueve claves propias de regresión no existen en multiclase.
    "mean_absolute_error",
    "root_mean_squared_error",
    "r2",
    "mean_error",
    "mean_squared_error",
    "median_absolute_error",
    "mean_absolute_error_difference",
    "mean_absolute_error_ratio",
    "mean_error_difference",
    "CX-2",
    "CX-3",
    "CX-4",
    "CX-5",
    "CX-6",
    "human_review_zero",  # La tasa de override no depende de las clases
    "feature_drift_score",
    "input_metadata_drift_score",
    "output_metadata_drift_score",
    "model_quality_score",
}
PROHIBIDO_EN_MULTICLASE = re.compile(
    r"dos resultados|los dos valores|dos valores|binari", re.IGNORECASE
)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _efectivo(entrada: dict[str, Any]) -> dict[str, Any]:
    """El bloque que ve un proyecto multiclase: un campo nulo hereda el de la
    entrada. `formula_vars: []` sustituye a las variables (no se instancia) y
    `umbral_por_defecto: {}` quita el umbral de fábrica."""
    efectivo = {campo: entrada.get(campo) for campo in CAMPOS}
    for campo, valor in (entrada.get("multiclase") or {}).items():
        if valor is not None:
            efectivo[campo] = valor
    return efectivo


def test_cada_entrada_con_cambio_de_sentido_lleva_su_bloque(client):
    metricas = client.get("/api/content/metricas").json()
    con_bloque = {clave for clave, entrada in metricas.items() if "multiclase" in entrada}
    assert con_bloque == set(metricas) - SIN_BLOQUE
    for clave in con_bloque:
        assert set(metricas[clave]["multiclase"]) == set(CAMPOS), clave


def test_las_entradas_sin_bloque_no_traen_la_clave(client):
    metricas = client.get("/api/content/metricas").json()
    for clave in SIN_BLOQUE:
        assert "multiclase" not in metricas[clave], clave


def test_las_seis_claves_que_cambian_su_formula_en_multiclase(client):
    metricas = client.get("/api/content/metricas").json()
    for clave in CAMBIAN_DE_FORMULA:
        entrada = metricas[clave]
        bloque = entrada["multiclase"]
        assert bloque["formula"] and bloque["formula"] != entrada["formula"], clave
        assert bloque["formula_vars"] == [], clave
        assert "macro" in (bloque["formula"] + (bloque["que_mide"] or "")).lower() or (
            clave in ("accuracy", "matthews_correlation_coefficient")
        ), clave


def test_ninguna_entrada_dice_dos_resultados_en_su_bloque_efectivo(client):
    metricas = client.get("/api/content/metricas").json()
    for clave, entrada in metricas.items():
        if clave in SIN_BLOQUE:
            continue
        efectivo = _efectivo(entrada)
        for campo in ("que_mide", "como_se_lee", "formula"):
            texto = efectivo[campo] or ""
            assert not PROHIBIDO_EN_MULTICLASE.search(texto), (clave, campo, texto)


# Los que en multiclase tienen umbral, pero sale de la línea base.
UMBRAL_DE_LINEA_BASE = ("accuracy", "f1_measure", "area_under_roc", "prediction_drift_score")


def test_en_multiclase_la_calidad_no_trae_umbral_de_fabrica(client):
    """El 0,8 o el 0,75 de binario no se sirve a un proyecto multiclase."""
    metricas = client.get("/api/content/metricas").json()
    sin_umbral = [
        c
        for c, e in metricas.items()
        # `label_skew` es una tasa de etiqueta con su umbral de siempre.
        if e["monitor"] == "quality"
        and e["umbral_por_defecto"] is not None
        and c != "label_skew"
        and c not in CLAVES_REGRESION  # sin valor de fábrica y sin bloque multiclase
    ]
    sin_umbral.append("prediction_drift_score")
    for clave in sin_umbral:
        assert _efectivo(metricas[clave])["umbral_por_defecto"] == {}, clave
    # El binario conserva el suyo.
    assert metricas["accuracy"]["umbral_por_defecto"] == {"limite_inferior": 0.8}
    # Equidad, explicabilidad y confianza no cambian de umbral.
    for clave in ("statistical_parity_difference", "confidence_drift_score"):
        assert _efectivo(metricas[clave])["umbral_por_defecto"] == metricas[clave]["umbral_por_defecto"]
    # El texto no habla de un umbral que no existe.
    for clave in sin_umbral:
        if clave in UMBRAL_DE_LINEA_BASE:
            assert "línea base" in _efectivo(metricas[clave])["como_se_lee"], clave
            continue
        texto = _efectivo(metricas[clave])["como_se_lee"]
        assert "Por debajo del umbral" not in texto and "Por encima del umbral" not in texto, clave


def test_el_bloque_efectivo_no_cuela_claves_tecnicas_en_texto_llano(client):
    metricas = client.get("/api/content/metricas").json()
    for clave, entrada in metricas.items():
        efectivo = _efectivo(entrada)
        for variable in efectivo["formula_vars"] or []:
            for campo in ("que_mide", "como_se_lee"):
                assert variable.lower() not in (efectivo[campo] or "").lower(), (clave, campo)


def test_las_de_equidad_dicen_conjunto_favorable_y_el_caso_sin_conjunto(client):
    metricas = client.get("/api/content/metricas").json()
    for clave in ("rate_priv", "rate_unpriv", "disparate_impact", "statistical_parity_difference"):
        efectivo = _efectivo(metricas[clave])
        assert "conjunto de clases favorables" in efectivo["que_mide"], clave
    # Toda medida de equidad con umbral dice qué pasa sin conjunto favorable.
    con_umbral = [
        c
        for c, e in metricas.items()
        if e["monitor"] == "fairness" and _efectivo(e)["umbral_por_defecto"] and "multiclase" in e
    ]
    assert len(con_umbral) >= 10
    for clave in con_umbral:
        assert "no tiene conjunto de clases favorables" in _efectivo(metricas[clave])["como_se_lee"], clave


def test_cx1_en_multiclase_cuenta_la_pertenencia_al_conjunto_favorable(client):
    efectivo = _efectivo(client.get("/api/content/metricas").json()["CX-1"])
    assert "conjunto de clases favorables" in efectivo["como_se_lee"]
    assert "sale sin datos" in efectivo["como_se_lee"]
    assert "conjunto de clases favorables" in efectivo["formula"]


def test_los_titulares_multiclase_no_tienen_umbral_de_fabrica_y_lo_dicen(client):
    metricas = client.get("/api/content/metricas").json()
    for clave in ("accuracy", "f1_measure", "area_under_roc"):
        assert "línea base" in _efectivo(metricas[clave])["como_se_lee"], clave


def test_area_under_pr_binario_dice_que_su_umbral_es_relativo_a_la_prevalencia(client):
    entrada = client.get("/api/content/metricas").json()["area_under_pr"]
    assert "relativo" in entrada["como_se_lee"]
    assert "línea base" in entrada["como_se_lee"]


def test_la_clase_favorable_del_glosario_admite_un_conjunto(client):
    glosario = client.get("/api/content/glosario").json()
    assert "conjunto de clases favorables" in glosario["etiqueta_favorable"]["definicion"]
    assert "conjunto de clases favorables" in glosario["plantilla_mapeo"]["definicion"]


def test_la_guia_de_uso_ya_no_limita_el_alcance_a_binario(client):
    entradas = client.get("/api/content/guia-uso").json()["entradas"]
    primera = next(e for e in entradas if e["id"] == 1)
    texto = " ".join(primera["pasos"])
    assert "clasificación binaria" not in texto
    assert "multiclase" in texto
    assert "regresión" in texto


def test_la_guia_de_uso_explica_la_lectura_del_deskilling(client):
    """La guía dice cómo leer la pendiente del deskilling."""
    entradas = client.get("/api/content/guia-uso").json()["entradas"]
    capa_humana = next(e for e in entradas if e["titulo"] == "Capa humana")
    limite = next(p for p in capa_humana["pasos"] if p.startswith("Cómo se lee el deskilling"))
    assert "pendiente" in limite
    assert f"{MIN_N} decisiones" in limite
    assert "serie de coincidencia por ventana" in limite


def test_el_manual_lleva_el_limite_y_la_plantilla_multiclase():
    manual = REPO_ROOT / "docs" / "manual"
    if not manual.is_dir():
        return
    uso = (manual / "uso.md").read_text(encoding="utf-8")
    datos = (manual / "datos.md").read_text(encoding="utf-8")
    assert "Cómo se lee el deskilling" in uso
    assert "plantilla-multiclase-sintetico.csv" in datos
