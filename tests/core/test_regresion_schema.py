"""Nombres compartidos de `core/schema.py` para la regresión."""
from __future__ import annotations

import pytest

from vigia.core.schema import (
    CLAVES_REGRESION,
    CLAVES_SOLO_CLASIFICACION,
    COL_LABEL_VALUE,
    COL_PREDICTION_VALUE,
    MOTIVO_SIN_RANGO,
    ColumnMapping,
    DatosNoValidos,
    MappingTemplate,
    TaskSpec,
    en_rango,
    es_columna_canonica,
    pertenencia,
    texto_rangos,
    validar_mapeo_por_tipo,
    validar_rangos,
    validar_unidad,
)


def test_columnas_de_valor_son_canonicas():
    assert COL_PREDICTION_VALUE == "prediction_value"
    assert COL_LABEL_VALUE == "label_value"
    assert es_columna_canonica(COL_PREDICTION_VALUE)
    assert es_columna_canonica(COL_LABEL_VALUE)


def test_en_rango_incluye_extremos_y_abre_con_nulo():
    rangos = ((40.0, 81.0),)
    assert en_rango(40, rangos) is True
    assert en_rango(81.0, rangos) is True
    assert en_rango(39.99, rangos) is False
    assert en_rango(None, rangos) is None
    assert en_rango(float("nan"), rangos) is None
    assert en_rango("12 h", rangos) is None
    assert en_rango(1000, ((40.0, None),)) is True
    assert en_rango(-5, ((None, 0.0),)) is True
    dos = ((5.0, 20.0), (80.0, 120.0))
    assert en_rango(50, dos) is False and en_rango(100, dos) is True


def test_sin_rango_no_se_calcula():
    with pytest.raises(ValueError, match="sin rango favorable"):
        en_rango(10, ())
    assert MOTIVO_SIN_RANGO == "sin rango favorable: solo el error por grupo"


def test_pertenencia_da_la_forma_de_las_columnas():
    assert pertenencia([10, 50, None, 90], ((40.0, 81.0),)) == [0.0, 1.0, None, 0.0]


@pytest.mark.parametrize(
    ("rangos", "texto"),
    [
        ([[1, 2], [3, 4], [5, 6], [7, 8]], "de 1 a 3"),
        ([[10, 5]], "mayor que el máximo"),
        ([[None, None]], "no tiene extremos"),
        ([[0, 10], [5, 20]], "solaparse"),
        ([[0, 10], [10, 20]], "solaparse"),
        ([[None, 10], [None, 20]], "solaparse"),
        ([["x", 10]], "no es un número"),
        ([[float("inf"), None]], "infinito"),
        ([[1, 2, 3]], "pareja"),
    ],
)
def test_rangos_no_validos(rangos, texto):
    with pytest.raises(DatosNoValidos, match=texto):
        validar_rangos(rangos)


def test_rangos_validos_se_ordenan():
    assert validar_rangos([]) == ()
    assert validar_rangos([[80, 120], [5, 20]]) == ((5.0, 20.0), (80.0, 120.0))
    assert validar_rangos([[40, None]]) == ((40.0, None),)


def test_unidad():
    assert validar_unidad(None) is None
    assert validar_unidad(" horas por semana ") == "horas por semana"
    for mala in ("", "   ", "x" * 31):
        with pytest.raises(DatosNoValidos, match="target_unit"):
            validar_unidad(mala)


def test_mapeo_y_plantilla_ganan_las_dos_claves():
    m = ColumnMapping(prediction_col="p", target_unit="días", favorable_ranges=[[1, 3]])
    assert m.favorable_ranges == [(1.0, 3.0)] and m.target_unit == "días"
    t = MappingTemplate(target_unit="días", favorable_ranges=[[None, 3]])
    assert t.favorable_ranges == [(None, 3.0)]
    # Un mapeo guardado de antes de la regresión se relee igual.
    viejo = ColumnMapping.model_validate({"prediction_col": "p", "favorable_label": 1})
    assert viejo.target_unit is None and viejo.favorable_ranges == []


@pytest.mark.parametrize(
    ("kwargs", "campo"),
    [
        ({"classes": ["a", "b", "c"]}, "classes"),
        ({"favorable_label": 1}, "favorable_label"),
        ({"probability_col": "prob"}, "probability_col"),
        ({"probability_cols": ["pa", "pb"]}, "probability_cols"),
        ({"probability_col": "prob", "probability_format": "list"}, "probability_format"),
    ],
)
def test_regresion_rechaza_campos_de_clasificacion(kwargs, campo):
    with pytest.raises(DatosNoValidos, match=campo):
        validar_mapeo_por_tipo(ColumnMapping(prediction_col="p", **kwargs), "regression")


def test_regresion_valida_unidad_y_rangos():
    validar_mapeo_por_tipo(
        ColumnMapping(prediction_col="p", target_unit="h", favorable_ranges=[[40, 81]]),
        "regression",
    )
    with pytest.raises(DatosNoValidos, match="mayor que el máximo"):
        validar_mapeo_por_tipo(
            ColumnMapping(prediction_col="p", favorable_ranges=[[81, 40]]), "regression"
        )
    with pytest.raises(DatosNoValidos, match="classes"):
        validar_mapeo_por_tipo(ColumnMapping(prediction_col="p"), "regression", ["a", "b"])


@pytest.mark.parametrize("tipo", ["binary", "multiclass"])
def test_clasificacion_rechaza_unidad_y_rango(tipo):
    clases = ["a", "b", "c"] if tipo == "multiclass" else None
    with pytest.raises(DatosNoValidos, match="favorable_ranges es solo de regresión"):
        validar_mapeo_por_tipo(
            ColumnMapping(prediction_col="p", favorable_ranges=[[0, 1]]), tipo, clases
        )
    with pytest.raises(DatosNoValidos, match="target_unit es solo de regresión"):
        validar_mapeo_por_tipo(ColumnMapping(prediction_col="p", target_unit="h"), tipo, clases)


def test_task_spec_de_regresion():
    spec = TaskSpec.desde_mapeo(
        "regression",
        MappingTemplate(target_unit="horas por semana", favorable_ranges=[[40, 81]]),
    )
    assert spec.es_regresion and not spec.es_multiclase
    assert spec.classes == () and spec.favorables == ()
    assert spec.unidad == "horas por semana"
    assert spec.rangos_favorables == ((40.0, 81.0),)
    assert not spec.sin_rango_favorable and not spec.sin_conjunto_favorable
    assert spec.en_rango(50) is True and spec.en_rango(10) is False
    with pytest.raises(ValueError):
        _ = spec.k
    # Lo explícito (el proyecto) manda sobre el mapeo.
    otra = TaskSpec.desde_mapeo(
        "regression", MappingTemplate(target_unit="h"), unidad="días", rangos=[[1, 3]]
    )
    assert otra.unidad == "días" and otra.rangos_favorables == ((1.0, 3.0),)
    sin = TaskSpec.desde_mapeo("regression", MappingTemplate())
    assert sin.sin_rango_favorable


def test_task_spec_de_clasificacion_no_lleva_unidad_ni_rango():
    with pytest.raises(ValueError):
        TaskSpec(task_type="binary", unidad="h")
    with pytest.raises(ValueError):
        TaskSpec(task_type="multiclass", classes=("a", "b", "c"), rangos_favorables=((0.0, 1.0),))


def test_texto_rangos():
    assert texto_rangos(((40.0, 81.0),), "horas por semana") == "de 40 a 81 horas por semana"
    assert texto_rangos(((5.0, 20.0), (80.0, None))) == "de 5 a 20 y desde 80"
    assert texto_rangos((), "h") == ""


def test_claves_de_regresion_no_chocan_con_las_de_clasificacion():
    assert not set(CLAVES_REGRESION) & set(CLAVES_SOLO_CLASIFICACION)
    assert len(set(CLAVES_REGRESION)) == len(CLAVES_REGRESION) == 9
