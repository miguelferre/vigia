"""Tests de construcción, validadores y serialización de vigia.core.schema."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from vigia.core import CORE_VERSION
from vigia.core.schema import (
    HARNESS_DIAG_COLS,
    HARNESS_FEEDBACK_MAPPING,
    HARNESS_PAYLOAD_MAPPING,
    ColumnMapping,
    DatosNoValidos,
    EvaluationResult,
    MappingTemplate,
    Measurement,
    MonitorThresholds,
    MonitorType,
    ProtectedKind,
    State,
    TaskSpec,
    Threshold,
    ThresholdKind,
    WindowInfo,
    clave_clase,
    col_prob,
    es_columna_canonica,
    es_grupo_clase,
    grupo_clase,
    validar_mapeo_por_tipo,
    worst,
)


def test_column_mapping_construccion_basica():
    m = ColumnMapping(prediction_col="pred")
    assert m.probability_format == "scalar"
    # Sin valor, la ingesta lo hereda; el motor usa 1, como siempre.
    assert m.favorable_label is None
    assert m.favorable_resuelto == 1


def test_column_mapping_contrato():
    """Predicción opcional, favorable de texto o lista de
    uno y campos desconocidos rechazados. La lista de dos
    ya no la rechaza el modelo sino `validar_mapeo_por_tipo` en binario, y el
    motor binario no la lee como una clase."""
    assert ColumnMapping(id_col="id", label_col="y").prediction_col is None
    assert ColumnMapping(prediction_col="p", favorable_label="Sí").favorable_resuelto == "Sí"
    assert ColumnMapping(prediction_col="p", favorable_label=[0]).favorable_resuelto == 0
    dos = ColumnMapping(prediction_col="p", favorable_label=[0, 1])
    with pytest.raises(ValueError):
        _ = dos.favorable_resuelto
    with pytest.raises(DatosNoValidos):
        validar_mapeo_por_tipo(dos, "binary")
    with pytest.raises(ValidationError):
        ColumnMapping(prediction_col="p", columna_inventada="x")


# --------------------------------------------------------------------------
# Nombres compartidos del esquema común
# --------------------------------------------------------------------------

_CLASES = ["permitido", "spam", "odio", "desnudez", "violencia"]


def test_columnas_canonicas_y_grupo_clase():
    assert col_prob(0) == "prob__0" and col_prob(4) == "prob__4"
    for nombre in ("prediction_class", "label_class", "prob__0", "prob__19", "prediction"):
        assert es_columna_canonica(nombre), nombre
    for nombre in ("prob__x", "prob_spam", "edad", "probabilidad"):
        assert not es_columna_canonica(nombre), nombre
    assert grupo_clase("spam") == "clase:spam"
    assert grupo_clase(2.0) == "clase:2"
    assert es_grupo_clase("clase:spam") and not es_grupo_clase("unpriv")
    assert not es_grupo_clase(None)
    assert clave_clase(" spam ") == "spam" and clave_clase(1.0) == "1"


def test_mapeo_acepta_clases_y_probability_cols():
    m = ColumnMapping(
        prediction_col="pred",
        label_col="y",
        classes=[" permitido", *_CLASES[1:]],
        favorable_label=["permitido"],
        probability_cols=[f"prob_{c}" for c in _CLASES],
    )
    assert m.classes == _CLASES  # espacios recortados
    assert m.favorables == ["permitido"]
    # Un mapeo binario de antes de la multiclase se relee igual.
    viejo = ColumnMapping.model_validate({"prediction_col": "p", "favorable_label": 1})
    assert viejo.classes == [] and viejo.probability_cols == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"classes": ["a", "a ", "b"]},  # repetidas tras recortar
        {"classes": ["a", "b", "c"], "favorable_label": ["z"]},  # favorable fuera
        {"classes": ["a", "b", "c"], "probability_cols": ["pa", "pb"]},  # k distinto
        {"probability_cols": ["pa", "pb"], "probability_col": "p"},  # las dos formas
        {"classes": [f"c{i}" for i in range(21)]},  # más de 20
    ],
)
def test_mapeo_rechaza_clases_incoherentes(kwargs):
    with pytest.raises(ValidationError):
        ColumnMapping(prediction_col="p", **kwargs)


def test_validar_por_tipo():
    multi = ColumnMapping(prediction_col="p", classes=_CLASES, favorable_label=["permitido"])
    validar_mapeo_por_tipo(multi, "multiclass")
    # Sin conjunto favorable: válido.
    validar_mapeo_por_tipo(ColumnMapping(prediction_col="p", classes=_CLASES), "multiclass")
    # La regresión ya no se rechaza por tipo; un mapeo con clases sí.
    with pytest.raises(DatosNoValidos, match="classes, favorable_label"):
        validar_mapeo_por_tipo(multi, "regression")
    validar_mapeo_por_tipo(ColumnMapping(prediction_col="p", label_col="y"), "regression")
    with pytest.raises(DatosNoValidos, match="binario"):
        validar_mapeo_por_tipo(ColumnMapping(prediction_col="p", classes=["a", "b"]), "multiclass")
    with pytest.raises(DatosNoValidos, match="todas las clases"):
        validar_mapeo_por_tipo(
            ColumnMapping(prediction_col="p", classes=["a", "b", "c"], favorable_label=["a", "b", "c"]),
            "multiclass",
        )
    with pytest.raises(DatosNoValidos, match="probability_cols"):
        validar_mapeo_por_tipo(
            ColumnMapping(prediction_col="p", classes=["a", "b", "c"], probability_col="prob"),
            "multiclass",
        )
    validar_mapeo_por_tipo(
        ColumnMapping(prediction_col="p", probability_col="prob", probability_format="list"),
        "multiclass",
        ["a", "b", "c"],
    )
    with pytest.raises(DatosNoValidos, match="multiclase"):
        validar_mapeo_por_tipo(ColumnMapping(prediction_col="p", classes=["a", "b", "c"]), "binary")
    validar_mapeo_por_tipo(ColumnMapping(prediction_col="p", favorable_label="Sí"), "binary")


def test_task_spec():
    binario = TaskSpec.binario()
    assert binario.task_type == "binary" and binario.classes == () and binario.k == 2
    assert not binario.es_multiclase and not binario.sin_conjunto_favorable
    spec = TaskSpec.desde_mapeo(
        "multiclass", MappingTemplate(classes=_CLASES, favorable_label=["permitido", "spam"])
    )
    assert spec.k == 5 and spec.es_multiclase
    assert spec.indice("odio") == 2 and spec.indice(" odio") == 2
    assert spec.es_favorable("spam") and not spec.es_favorable("odio")
    with pytest.raises(ValueError):
        spec.indice("otra")
    sin = TaskSpec.desde_mapeo("multiclass", MappingTemplate(), classes=_CLASES)
    assert sin.sin_conjunto_favorable
    # `regression` se acepta; `k` no está definido.
    regresion = TaskSpec(task_type="regression")
    assert regresion.es_regresion and regresion.sin_rango_favorable
    with pytest.raises(ValueError):
        _ = regresion.k
    with pytest.raises(ValidationError):
        TaskSpec(task_type="regression", classes=("a", "b"))
    with pytest.raises(ValidationError):  # inmutable
        spec.task_type = "binary"  # type: ignore[misc]


def test_plantilla_sin_positive_label():
    """El campo sale del esquema; una plantilla guardada con él se
    relee sin error (con valor o sin él) y no lo conserva."""
    assert "positive_label" not in MappingTemplate.model_fields
    for valor in (None, "Sí"):
        t = MappingTemplate.model_validate({"favorable_label": 1, "positive_label": valor})
        assert "positive_label" not in t.model_dump()
    assert "positive_label" not in MappingTemplate.model_json_schema()["properties"]


def test_threshold_sin_origen_se_serializa_como_antes():
    """`origen` y `nota` solo salen cuando tienen valor."""
    from vigia.core.schema import Threshold

    antes = Threshold(metric_key="m", kind="lower_limit", value=0.8)
    assert antes.model_dump(mode="json") == {"metric_key": "m", "kind": "lower_limit", "value": 0.8}
    con = Threshold(metric_key="m", kind="lower_limit", value=0.8, origen="fabricante", nota="ficha")
    assert con.model_dump(mode="json")["origen"] == "fabricante"


def test_column_mapping_exige_grupos_si_hay_protegido():
    with pytest.raises(ValidationError):
        ColumnMapping(prediction_col="pred", protected_attr_col="Age")


def test_column_mapping_ok_con_grupos():
    m = ColumnMapping(
        prediction_col="pred",
        protected_attr_col="Age",
        unpriv_groups=[[18, 35]],
        priv_groups=[[36, 75]],
    )
    assert m.unpriv_groups == [[18, 35]]


def test_harness_diag_cols_39_en_orden():
    assert len(HARNESS_DIAG_COLS) == 39
    assert HARNESS_DIAG_COLS[0] == "Neck_signs_symptoms"
    assert HARNESS_DIAG_COLS[-1] == "Gout"


def test_harness_feedback_mapping():
    m = HARNESS_FEEDBACK_MAPPING
    assert m.prediction_col == "_original_prediction"
    assert m.probability_format == "list"
    assert m.label_col == "Has_Referral_in_Window"
    assert m.protected_attr_col == "Age"
    assert len(m.feature_cols) == 2 + 39


def test_harness_payload_mapping_sin_label():
    m = HARNESS_PAYLOAD_MAPPING
    assert m.prediction_col == "PREDICTION"
    assert m.label_col is None


def test_threshold_kind_valores():
    assert ThresholdKind.lower_limit == "lower_limit"
    assert ThresholdKind.upper_limit == "upper_limit"


def test_monitor_thresholds_limits_un_solo_umbral():
    mt = MonitorThresholds(
        thresholds=[Threshold(metric_key="fairness_value", kind=ThresholdKind.lower_limit, value=20.0)]
    )
    assert mt.limits("fairness_value") == (20.0, None)
    assert mt.limits("inexistente") == (None, None)


def test_monitor_thresholds_limits_doble_umbral_label_skew():
    mt = MonitorThresholds(
        thresholds=[
            Threshold(metric_key="label_skew", kind=ThresholdKind.lower_limit, value=-0.5),
            Threshold(metric_key="label_skew", kind=ThresholdKind.upper_limit, value=0.5),
        ]
    )
    assert mt.limits("label_skew") == (-0.5, 0.5)


def test_state_worst_orden():
    # orden del enunciado: alerta > inestable > aviso > sin_datos > ok
    assert worst([State.ok, State.aviso]) == State.aviso
    assert worst([State.aviso, State.alerta, State.inestable]) == State.alerta
    assert worst([State.aviso, State.inestable]) == State.inestable
    assert worst([State.sin_datos, State.ok]) == State.sin_datos
    assert worst([]) == State.sin_datos


def test_evaluation_result_to_dict_y_worst_state():
    m1 = Measurement(metric_key="a", value=1.0, state=State.ok)
    m2 = Measurement(metric_key="b", value=None, state=State.alerta)
    res = EvaluationResult(
        monitor=MonitorType.fairness,
        window=WindowInfo(kind="ultimos_n", n=10),
        measurements=[m1, m2],
        config_snapshot={"min_records": 200},
        core_version=CORE_VERSION,
    )
    d = res.to_dict()
    json.dumps(d)  # no debe lanzar
    assert res.worst_state == State.alerta
    assert res.states() == {"a": State.ok, "b": State.alerta}


def test_protected_kind_valores():
    assert ProtectedKind.numeric_ranges == "numeric_ranges"
    assert ProtectedKind.categorical == "categorical"


def test_column_mapping_saca_la_fecha_de_las_variables():
    """`timestamp_col` no es una variable; un mapeo ya guardado que la
    trae en las dos listas se sigue leyendo, con la fecha fuera de `feature_cols`."""
    m = ColumnMapping(
        prediction_col="pred", timestamp_col="fecha", feature_cols=["fecha", "importe", "canal"]
    )
    assert m.timestamp_col == "fecha"
    assert m.feature_cols == ["importe", "canal"]
    sin_fecha = ColumnMapping(prediction_col="pred", feature_cols=["fecha", "importe"])
    assert sin_fecha.feature_cols == ["fecha", "importe"]


def test_mapping_template_guarda_timestamp_col():
    t = MappingTemplate(timestamp_col="fecha", feature_cols=["importe"])
    assert t.model_dump(mode="json")["timestamp_col"] == "fecha"
    assert MappingTemplate().timestamp_col is None


def test_mapping_template_rechaza_la_fecha_entre_las_variables():
    with pytest.raises(ValidationError, match="columna de fecha"):
        MappingTemplate(timestamp_col="fecha", feature_cols=["fecha", "importe"])
