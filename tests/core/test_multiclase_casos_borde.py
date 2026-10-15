"""Casos borde sin test: el normalizador de clases, los umbrales
desde la línea base con una línea base pequeña o con una clase sin filas, y `k = 2`
declarado como multiclase.

Cada test fija el comportamiento que piden los contratos. Los que describen un defecto llevan `xfail(strict=True)` con
la razón; si alguien lo arregla, el test pasa a verde y strict avisa de que hay
que quitar la marca.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from vigia.core.calibration import monitor_de_umbral, umbrales_linea_base_multiclase
from vigia.core.quality import evaluate_quality
from vigia.core.schema import (
    ColumnMapping,
    DatosNoValidos,
    MonitorThresholds,
    MonitorType,
    QualityConfig,
    State,
    TaskSpec,
    clave_clase,
)

from ._datos_multiclase import CLASES, canonico, crudo, historia, mapeo, tarea

TITULARES = {"accuracy", "f1_measure", "area_under_roc"}


# ---------------------------------------------------------------------------
# 3. clave_clase con "01", "1", 1, "nan", float("nan") y espacios
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("1", "1"),
        ("01", "01"),  # no se interpreta como número: "01" y "1" son claves distintas
        (1, "1"),
        (1.0, "1"),  # lo que lee pandas cuando la columna lleva un hueco
        (np.int64(1), "1"),
        (np.float64(1.0), "1"),
        (True, "1"),
        (False, "0"),
        (" 1 ", "1"),
        ("\t01\n", "01"),
        ("  spam ", "spam"),
        ("Spam", "Spam"),  # el normalizador no cambia mayúsculas (lo decide la ingesta)
        ("1.0", "1.0"),  # un texto no se convierte: solo el decimal entero numérico
        (1.5, "1.5"),
        ("", ""),
        ("   ", ""),
        ("nan", "nan"),
        (float("nan"), "nan"),
    ],
)
def test_clave_clase_normaliza_numeros_espacios_y_nan(valor, esperado):
    assert clave_clase(valor) == esperado


def test_clave_clase_01_y_1_no_se_confunden_como_claves():
    assert clave_clase("01") != clave_clase("1")
    assert clave_clase(1) == clave_clase("1") == clave_clase(1.0) == clave_clase(" 1 ")


def test_clave_clase_de_un_nulo_no_es_la_cadena_vacia():
    """Un NaN no se vuelve «vacío»: sale como la clave «nan». Quien lee celdas
    (la ingesta con `es_valor_nulo`) tiene que mirar el nulo antes. Este test
    deja escrito ese reparto de trabajo."""
    resultado = clave_clase(float("nan"))
    assert resultado == "nan" and resultado != ""


def test_taskspec_busca_la_clase_por_clave_y_distingue_01_de_1():
    t = TaskSpec(task_type="multiclass", classes=(0, 1, 2), favorables=(1,))
    assert t.indice("1") == t.indice(1) == t.indice(1.0) == t.indice(" 1 ") == 1
    assert t.es_favorable("1") and t.es_favorable(1.0)
    with pytest.raises(ValueError):
        t.indice("01")
    assert not t.es_favorable("01")


def test_taskspec_con_01_y_1_como_clases_distintas_las_indexa_aparte():
    t = TaskSpec(task_type="multiclass", classes=("01", "1", "2"), favorables=("01",))
    assert (t.indice("01"), t.indice("1"), t.indice(1)) == (0, 1, 1)
    assert t.es_favorable("01") and not t.es_favorable("1")


def test_las_clases_01_y_1_son_distintas_para_el_mapeo():
    m = mapeo(["01", "1", "2"], ("01",))
    assert m.classes == ["01", "1", "2"] and m.favorables == ["01"]
    # 1 (entero) y "1" son la misma clase: repetida.
    with pytest.raises(ValueError, match="distintas"):
        ColumnMapping(classes=["1", 1, "2"], probability_cols=["a", "b", "c"], favorable_label=["2"])


def test_una_clase_con_nombre_nan_se_rechaza_en_el_mapeo():
    """La ingesta y el diario leen «nan» como celda vacía, así que el
    esquema la rechaza como nombre de clase."""
    with pytest.raises(ValueError, match="«nan» no sirve como nombre de clase"):
        mapeo(["nan", "b", "c"], ("b",))


# ---------------------------------------------------------------------------
# 5. umbrales_linea_base_multiclase con una línea base pequeña
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [0, 1, 5, 30, 99])
def test_linea_base_por_debajo_del_minimo_de_etiquetas_no_propone_calidad(n):
    """Con menos de `QualityConfig().min_feedback` filas etiquetadas no hay
    remuestreo de calidad: ni excepción ni umbrales inventados."""
    base = canonico(n, seed=3) if n else canonico(10, seed=3).iloc[0:0]
    umbrales = umbrales_linea_base_multiclase(base, tarea(), n_remuestreos=20)
    assert not ({t.metric_key for t in umbrales} & TITULARES)
    assert all(math.isfinite(t.value) and t.value > 0 for t in umbrales)


def test_linea_base_vacia_no_propone_nada():
    vacia = canonico(10, seed=3).iloc[0:0]
    assert umbrales_linea_base_multiclase(vacia, tarea(), n_remuestreos=20) == []


def test_linea_base_de_justo_el_minimo_propone_los_cuatro_umbrales():
    minimo = QualityConfig().min_feedback
    umbrales = umbrales_linea_base_multiclase(canonico(minimo, seed=3), tarea(), n_remuestreos=20)
    assert {t.metric_key for t in umbrales} == TITULARES | {"prediction_drift_score"}
    assert all(t.origen == "linea_base" for t in umbrales)
    exactitud = next(t for t in umbrales if t.metric_key == "accuracy")
    assert exactitud.value >= 1 / len(CLASES)


def test_linea_base_sin_etiquetas_solo_propone_la_deriva_de_la_prediccion():
    base = canonico(500, seed=7).assign(label=np.nan, label_class=None)
    umbrales = umbrales_linea_base_multiclase(base, tarea(), n_remuestreos=20)
    assert [t.metric_key for t in umbrales] == ["prediction_drift_score"]


def test_linea_base_sin_la_clase_predicha_no_propone_deriva_ni_lanza():
    base = canonico(600, seed=7).drop(columns=["prediction_class"])
    claves = {t.metric_key for t in umbrales_linea_base_multiclase(base, tarea(), n_remuestreos=20)}
    assert "prediction_drift_score" not in claves and claves <= TITULARES


def test_el_umbral_con_una_linea_base_pequena_sigue_el_mismo_orden_que_con_una_grande():
    """Más ruido, umbral no más apretado. Con 100 filas el
    suelo de exactitud (`1/k`) y el límite inferior se respetan igual."""
    pequena = umbrales_linea_base_multiclase(canonico(100, seed=9), tarea(), n_remuestreos=60)
    grande = umbrales_linea_base_multiclase(canonico(3000, seed=9), tarea(), n_remuestreos=60)
    for conjunto in (pequena, grande):
        by = {t.metric_key: t for t in conjunto}
        assert by["accuracy"].value >= 1 / len(CLASES)
        assert 0 < by["area_under_roc"].value < 1
    assert monitor_de_umbral("prediction_drift_score") == MonitorType.drift


# ---------------------------------------------------------------------------
# 5. umbrales_linea_base_multiclase con una clase sin filas
# ---------------------------------------------------------------------------


def _sin_filas_de_baja(n: int, seed: int) -> pd.DataFrame:
    """Línea base de tres clases declaradas en la que `baja` no tiene ninguna
    fila etiquetada (el modelo sí la predice alguna vez)."""
    base = canonico(n, seed=seed, pesos=[0.5, 0.5, 0.0])
    assert "baja" not in set(base["label_class"].dropna())
    return base


def test_clase_sin_filas_en_la_linea_base_propone_los_cuatro_umbrales_finitos():
    base = _sin_filas_de_baja(800, seed=5)
    umbrales = umbrales_linea_base_multiclase(base, tarea(), n_remuestreos=30)
    assert {t.metric_key for t in umbrales} == TITULARES | {"prediction_drift_score"}
    for t in umbrales:
        assert math.isfinite(t.value) and t.value > 0, t
    exactitud = next(t for t in umbrales if t.metric_key == "accuracy")
    assert exactitud.value >= 1 / len(CLASES)  # el suelo usa k = 3 declarado, no las 2 con filas


def test_clase_sin_filas_la_linea_base_no_alerta_con_sus_propios_umbrales():
    """El umbral y la medida salen de la misma función: un lote sano de la
    misma población no puede caer por debajo del umbral propuesto."""
    base = _sin_filas_de_baja(1000, seed=5)
    umbrales = umbrales_linea_base_multiclase(base, tarea(), n_remuestreos=40)
    calidad = MonitorThresholds(
        thresholds=[t for t in umbrales if monitor_de_umbral(t.metric_key) == MonitorType.quality]
    )
    lote = canonico(800, seed=6, batch=1, seq_start=1000, pesos=[0.5, 0.5, 0.0])
    res = evaluate_quality(
        historia(base, lote), batch_seq=1, config=QualityConfig(), thresholds=calidad, task=tarea()
    )
    for clave in sorted(TITULARES):
        m = next(x for x in res.measurements if x.metric_key == clave and x.group_code is None)
        assert m.state in (State.ok, State.aviso), (clave, m.value, m.threshold_low, m.state)


def test_clase_con_tres_filas_en_la_linea_base_no_rompe_el_remuestreo():
    base = canonico(800, seed=6, pesos=[0.5, 0.495, 0.005])
    assert 0 < (base["label_class"] == "baja").sum() < 20  # por debajo de min_group
    umbrales = umbrales_linea_base_multiclase(base, tarea(), n_remuestreos=30, min_group=20)
    assert TITULARES <= {t.metric_key for t in umbrales}
    assert all(math.isfinite(t.value) for t in umbrales)


# ---------------------------------------------------------------------------
# 2. k = 2 declarado como multiclase
# ---------------------------------------------------------------------------


def test_task_spec_desde_mapeo_rechaza_dos_clases_en_multiclase_con_el_mensaje_de_la_spec():
    with pytest.raises(DatosNoValidos) as exc:
        TaskSpec.desde_mapeo("multiclass", mapeo(["a", "b"], ("a",)))
    texto = str(exc.value)
    assert "3 a 20 clases" in texto and "hay 2" in texto and "proyecto binario" in texto


def test_task_spec_desde_mapeo_rechaza_una_clase_y_mas_de_veinte():
    with pytest.raises(DatosNoValidos, match="hay 1"):
        TaskSpec.desde_mapeo("multiclass", mapeo(["a"], ("a",), probability_cols=["p_a"]))
    veintiuna = [f"c{i}" for i in range(21)]
    with pytest.raises(ValueError):  # el esquema ya lo corta antes del tipo
        mapeo(veintiuna, (veintiuna[0],))


def test_task_spec_desde_mapeo_acepta_tres_y_veinte_clases():
    assert TaskSpec.desde_mapeo("multiclass", mapeo(CLASES)).k == 3
    veinte = [f"c{i}" for i in range(20)]
    assert TaskSpec.desde_mapeo("multiclass", mapeo(veinte, (veinte[0],))).k == 20


def test_task_spec_binario_con_dos_clases_declaradas_vale():
    """Lo que el multiclase de dos clases pide ser: un proyecto binario."""
    t = TaskSpec.desde_mapeo("binary", mapeo(["a", "b"], ("a",)))
    assert t.task_type == "binary" and t.k == 2


def test_el_motor_de_umbrales_no_exige_el_minimo_de_clases_si_le_llega_un_task_k2():
    """La barrera de «de 3 a 20 clases» es de `validar_mapeo_por_tipo` (alta, mapeo,
    ingesta). Si un `TaskSpec` de dos clases llega a `core/` sin pasar por ahí,
    el cálculo funciona con `k = 2` y el suelo de exactitud es 1/2: no hay
    excepción ni resultado sin sentido. Fija ese reparto."""
    clases = ["a", "b"]
    t2 = TaskSpec(task_type="multiclass", classes=tuple(clases), favorables=("a",))
    from vigia.core.loaders import to_canonical

    base = to_canonical(crudo(500, seed=2, clases=clases), mapeo(clases, ("a",)), batch_seq=0, seq_start=0, task=t2)
    umbrales = umbrales_linea_base_multiclase(base, t2, n_remuestreos=30)
    by = {t.metric_key: t for t in umbrales}
    assert TITULARES | {"prediction_drift_score"} == set(by)
    assert by["accuracy"].value >= 0.5
