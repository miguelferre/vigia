"""`to_canonical`, `avisos_clases` y cardinalidad con tarea
multiclase y la regla de los 31 números."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from vigia.core.engine import _default_feature_cols
from vigia.core.loaders import avisos_clases, detectar_cardinalidad_binaria, to_canonical
from vigia.core.schema import (
    COL_LABEL,
    COL_LABEL_CLASS,
    COL_PREDICTION,
    COL_PREDICTION_CLASS,
    COL_PROB,
    DatosNoValidos,
    TaskSpec,
    col_prob,
)

from ._datos_multiclase import CLASES, canonico, crudo, mapeo, tarea


def test_frame_multiclase_lleva_clases_y_probabilidades():
    df = canonico(200, favorables=("alta", "media"))
    assert {COL_PREDICTION_CLASS, COL_LABEL_CLASS}.issubset(df.columns)
    assert [col_prob(i) for i in range(3)] == [c for c in df.columns if c.startswith("prob__")]
    # Prediction y label son la pertenencia al conjunto favorable
    fav = df[COL_PREDICTION_CLASS].isin(["alta", "media"]).astype(int)
    assert (df[COL_PREDICTION] == fav).all()
    assert (df[COL_LABEL] == df[COL_LABEL_CLASS].isin(["alta", "media"]).astype(float)).all()
    suma = df["prob__0"] + df["prob__1"]
    assert np.allclose(df[COL_PROB], suma)


def test_columnas_nuevas_no_son_variables_con_feature_cols_vacio():
    """Sin `feature_cols`, `prediction_class`, `label_class` y `prob__i` no
    se cuelan como variables."""
    df = canonico(80)
    visibles = _default_feature_cols(df)
    for nombre in (COL_PREDICTION_CLASS, COL_LABEL_CLASS, "prob__0", "prob__2"):
        assert nombre not in visibles
    # y desde el fichero crudo sin feature_cols: las probabilidades por clase no son variables
    m = mapeo(favorables=("alta",)).model_copy(update={"feature_cols": []})
    out = to_canonical(crudo(60), m, task=tarea())
    assert not any(c.startswith("p_") for c in _default_feature_cols(out))


def test_sin_conjunto_favorable_pone_ceros_y_prob_nula():
    """Prediction y label en 0 (no nulos donde hay etiqueta), prob nula."""
    df = canonico(100, favorables=None)
    assert (df[COL_PREDICTION] == 0).all()
    assert (df[COL_LABEL] == 0).all()
    assert df[COL_PROB].isna().all()
    assert df["prob__0"].notna().all()


def test_prediccion_con_clase_desconocida_da_el_mensaje_de_clase_desconocida():
    raw = crudo(40)
    raw.loc[3, "pred"] = "critica"
    with pytest.raises(DatosNoValidos) as exc:
        to_canonical(raw, mapeo(), task=tarea())
    assert str(exc.value) == (
        "El modelo predice la clase critica, que no está entre las clases del proyecto "
        "(alta, media, baja). Si es una versión nueva del modelo, créala."
    )


def test_etiqueta_sin_mayusculas_y_con_espacios_se_asigna_c62():
    raw = crudo(40)
    raw.loc[0, "real"] = " Alta "
    raw.loc[1, "real"] = "MEDIA"
    df = to_canonical(raw, mapeo(), task=tarea())
    assert df.loc[0, COL_LABEL_CLASS] == "alta"
    assert df.loc[1, COL_LABEL_CLASS] == "media"
    avisos = avisos_clases(raw, mapeo(), tarea(), es_linea_base=False)
    assert len(avisos) == 1
    assert "2 etiquetas" in avisos[0] and "sin distinguir mayúsculas" in avisos[0]


def test_etiqueta_desconocida_queda_fuera_de_la_calidad_y_se_cuenta():
    raw = crudo(50)
    raw.loc[[0, 1, 2], "real"] = "rara"
    df = to_canonical(raw, mapeo(), task=tarea())
    assert df[COL_LABEL].isna().sum() == 3
    assert (df.loc[[0, 1, 2], COL_LABEL_CLASS] == "rara").all()
    avisos = avisos_clases(raw, mapeo(), tarea(), es_linea_base=False)
    assert any("3 filas" in a and "rara" in a for a in avisos)


def test_clase_sin_filas_en_la_linea_base_avisa_con_soporte_cero():
    raw = crudo(60, clases=CLASES, pesos=[0.5, 0.5, 1e-9])
    # fuerza una sola clase real y predicha fuera de "baja"
    raw["real"] = raw["real"].replace("baja", "media")
    raw["pred"] = raw["pred"].replace("baja", "media")
    avisos = avisos_clases(raw, mapeo(), tarea(), es_linea_base=True)
    assert any("La clase baja no tiene filas en la línea base" in a for a in avisos)
    assert avisos_clases(raw, mapeo(), tarea(), es_linea_base=False) == []
    # sigue habiendo k columnas de probabilidad
    df = to_canonical(raw, mapeo(), task=tarea())
    assert "prob__2" in df.columns


def test_probabilidad_en_una_columna_con_lista_de_k():
    raw = crudo(30)
    raw["probs"] = [list(r) for r in raw[["p_alta", "p_media", "p_baja"]].to_numpy()]
    m = mapeo().model_copy(
        update={
            "probability_cols": [],
            "probability_col": "probs",
            "probability_format": "list",
        }
    )
    df = to_canonical(raw.drop(columns=["p_alta", "p_media", "p_baja"]), m, task=tarea())
    assert np.allclose(df["prob__1"], raw["p_media"])
    raw.at[4, "probs"] = [0.5, 0.5]
    with pytest.raises(DatosNoValidos, match="3 probabilidades por fila"):
        to_canonical(raw.drop(columns=["p_alta", "p_media", "p_baja"]), m, task=tarea())


def test_probabilidad_con_nan_da_datos_no_validos():
    raw = crudo(30)
    raw.loc[2, "p_media"] = np.nan
    with pytest.raises(DatosNoValidos, match="probabilidad vacía"):
        to_canonical(raw, mapeo(), task=tarea())


def test_cardinalidad_multiclase_no_avisa_y_binario_remite_a_multiclase():
    df = pd.DataFrame({"prediction": [0, 1, 2], "label": [0, 1, 0]})
    m = mapeo().model_copy(update={"prediction_col": "prediction", "label_col": "label"})
    assert detectar_cardinalidad_binaria(df, m, tarea()) == []
    avisos = detectar_cardinalidad_binaria(df, m)
    assert len(avisos) == 1
    assert "crea un proyecto multiclase" in avisos[0] and "3 valores" in avisos[0]
    assert detectar_cardinalidad_binaria(df, m, TaskSpec.binario()) == avisos


def test_binario_con_task_binario_da_lo_mismo_que_sin_task():
    raw = pd.DataFrame(
        {"pred": [1, 0, 1, 1], "real": [1, 0, 0, 1], "p": [0.9, 0.2, 0.7, 0.8]}
    )
    from vigia.core.schema import ColumnMapping

    m = ColumnMapping(prediction_col="pred", label_col="real", probability_col="p", favorable_label=1)
    a = to_canonical(raw, m)
    b = to_canonical(raw, m, task=TaskSpec.binario())
    pd.testing.assert_frame_equal(a, b)
    assert COL_PREDICTION_CLASS not in a.columns
