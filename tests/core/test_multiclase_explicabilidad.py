"""Explicabilidad con `predict_fn` de salida `(n, k)`."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from vigia.core.explain import global_permutation, global_shap, local_lime, shap_available
from vigia.core.schema import TaskSpec

CLASES = ["alta", "media", "baja"]
FEATS = ["x1", "x2", "x3"]


@pytest.fixture(scope="module")
def modelo():
    rng = np.random.default_rng(0)
    n = 600
    X = pd.DataFrame(rng.normal(size=(n, 3)), columns=FEATS)
    # x1 separa alta de baja; x2 separa media; x3 es ruido
    puntuacion = np.c_[2.5 * X.x1, 2.0 * X.x2, -2.5 * X.x1] + rng.normal(0, 0.7, (n, 3))
    y = np.array(CLASES)[puntuacion.argmax(axis=1)]
    clf = LogisticRegression(max_iter=500).fit(X, y)
    # el orden de sklearn es alfabético: lo reordenamos al de las clases del proyecto
    orden = [list(clf.classes_).index(c) for c in CLASES]

    def predict_fn(df: pd.DataFrame) -> np.ndarray:
        return clf.predict_proba(df[FEATS].to_numpy())[:, orden]

    return X, y, predict_fn


def _tarea(favorables=("alta",)):
    return TaskSpec(task_type="multiclass", classes=tuple(CLASES), favorables=tuple(favorables))


def test_permutacion_por_defecto_explica_la_suma_del_conjunto_favorable(modelo):
    X, _y, fn = modelo
    r = global_permutation(fn, X, task=_tarea(("alta", "media")), n_repeats=3)
    assert r.params["objetivo"] == "favorables" and r.params["clases"] == ["alta", "media"]
    assert r.clase_explicada is None
    esperado = global_permutation(
        lambda d: np.c_[1 - fn(d)[:, :2].sum(axis=1), fn(d)[:, :2].sum(axis=1)], X, n_repeats=3
    )
    assert [(f.feature, round(f.importance, 12)) for f in r.features] == [
        (f.feature, round(f.importance, 12)) for f in esperado.features
    ]


def test_permutacion_de_una_clase_lee_su_columna_y_x3_no_importa(modelo):
    X, y, fn = modelo
    r = global_permutation(fn, X, task=_tarea(), clase="media", n_repeats=3)
    assert r.clase_explicada == "media" and r.params["clase"] == "media"
    assert r.features[0].feature == "x2" and r.features[-1].feature == "x3"
    # y de texto con la clase real: AUROC por la clase pedida
    con_y = global_permutation(fn, X, y=y, task=_tarea(), clase="baja", n_repeats=3)
    assert con_y.params["scoring"] == "auroc_drop"
    assert con_y.features[0].feature == "x1"


def test_clase_fuera_de_las_clases_del_proyecto_lanza_value_error(modelo):
    X, _y, fn = modelo
    with pytest.raises(ValueError, match="no está entre las clases del proyecto"):
        global_permutation(fn, X, task=_tarea(), clase="critica")
    with pytest.raises(ValueError, match="no está entre las clases"):
        local_lime(fn, X, X.iloc[0], task=_tarea(), clase="critica")


def test_sin_conjunto_favorable_explica_la_clase_mayoritaria_predicha(modelo):
    X, _y, fn = modelo
    r = global_permutation(fn, X, task=_tarea(()), n_repeats=2)
    mayoritaria = CLASES[int(np.bincount(fn(X.reset_index(drop=True)).argmax(axis=1)).argmax())]
    assert r.clase_explicada == mayoritaria and r.params["objetivo"] == "clase"


def test_lime_explica_la_clase_predicha_y_devuelve_las_k_probabilidades(modelo):
    X, _y, fn = modelo
    fila = X.iloc[3]
    r = local_lime(fn, X, fila, task=_tarea(("alta", "media")), seed=0)
    probs = fn(pd.DataFrame([fila]))[0]
    assert r.available and r.clase_explicada == CLASES[int(probs.argmax())]
    assert len(r.probabilities) == 3 and abs(sum(r.probabilities) - 1) < 1e-9
    assert np.allclose(r.probabilities, probs)
    assert abs(r.prob_favorable - (probs[0] + probs[1])) < 1e-12
    d = r.to_dict()
    assert d["clase_explicada"] == r.clase_explicada and len(d["probabilities"]) == 3


def test_lime_con_clase_explicita_no_usa_la_columna_1_por_defecto(modelo):
    X, _y, fn = modelo
    fila = X.iloc[7]
    alta = local_lime(fn, X, fila, task=_tarea(), clase="alta", seed=0)
    baja = local_lime(fn, X, fila, task=_tarea(), clase="baja", seed=0)
    assert alta.clase_explicada == "alta" and baja.clase_explicada == "baja"
    # x1 empuja alta y baja en sentidos opuestos
    pesos_alta = {f.feature: f.importance for f in alta.features}
    pesos_baja = {f.feature: f.importance for f in baja.features}
    assert pesos_alta["x1"] * pesos_baja["x1"] < 0


def test_lime_sin_conjunto_favorable_deja_prob_favorable_nula(modelo):
    X, _y, fn = modelo
    r = local_lime(fn, X, X.iloc[0], task=_tarea(()), seed=0)
    assert r.prob_favorable is None and len(r.probabilities) == 3


def test_shap_multiclase_por_clase_y_por_conjunto(modelo):
    disponible, motivo = shap_available()
    if not disponible:
        pytest.skip(motivo)
    X, _y, fn = modelo
    explicar = X.iloc[:12]
    una = global_shap(fn, X, explicar, task=_tarea(), clase="baja", n_background=15, nsamples=60)
    assert una.available and una.clase_explicada == "baja"
    assert una.features[0].feature == "x1"
    conjunto = global_shap(
        fn, X, explicar, task=_tarea(("alta", "media")), n_background=15, nsamples=60
    )
    assert conjunto.params["objetivo"] == "favorables" and conjunto.clase_explicada is None


def test_binario_no_cambia_la_forma_del_resultado():
    rng = np.random.default_rng(1)
    X = pd.DataFrame(rng.normal(size=(120, 2)), columns=["a", "b"])
    clf = LogisticRegression().fit(X, (X.a > 0).astype(int))
    r = global_permutation(lambda d: clf.predict_proba(d[["a", "b"]]), X, n_repeats=2)
    assert "objetivo" not in r.params
    assert r.clase_explicada is None
    lime = local_lime(lambda d: clf.predict_proba(d[["a", "b"]]), X, X.iloc[0])
    d = lime.to_dict()
    assert "probabilities" not in d and "clase_explicada" not in d


def test_clase_mayoritaria_de_la_linea_base_se_pasa_como_clase(modelo):
    """Sin conjunto favorable el backend pasa la mayoritaria de la línea
    base con `clase=`; no cambia con el lote explicado."""
    from vigia.core.explain import clase_mayoritaria_de

    X, _y, fn = modelo
    t = _tarea(())
    linea_base = ["media"] * 5 + ["alta"] * 2 + ["baja"]
    assert clase_mayoritaria_de(linea_base, t) == "media"
    r = global_permutation(fn, X, task=t, clase=clase_mayoritaria_de(linea_base, t), n_repeats=2)
    assert r.clase_explicada == "media"
    with pytest.raises(ValueError, match="vuelve a subir"):
        clase_mayoritaria_de(["otra", None], t)
