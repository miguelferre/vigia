"""explain: Explicabilidad v1: importancia por permutación, LIME local y
SHAP global sobre la función de predicción del modelo.

Contrato común: todas las funciones reciben `predict_fn` (una función que
toma un `pd.DataFrame` de features con nombres planos y devuelve una matriz
`(n, 2)` con `[P(no favorable), P(favorable)]`) y devuelven un
`ExplanationResult` (`vigia.core.schema`). Ninguna función lanza por
ausencia de una librería opcional: cuando `shap` o `lime` no están
disponibles, el resultado vuelve con `available=False` y un `motivo`.

Ningún import de `shap`, `lime` ni `matplotlib` ocurre a nivel de módulo
(la UI ofrece permutation y LIME por defecto; SHAP es opcional y
puede no estar instalado en el equipo del cliente). `lime` importa
`matplotlib` dentro de `lime.lime_tabular` al renderizar explicaciones,
pero aquí solo se usa `explain_instance` / `as_list()`: no se renderiza
nada, así que no arrastra el import de `matplotlib` a nivel de módulo de
`vigia.core`.
"""
from __future__ import annotations

import functools
import math
import threading
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd

from vigia.core import CORE_VERSION
from vigia.core.schema import (
    EvaluationResult,
    ExplanationResult,
    FeatureImportance,
    Measurement,
    MonitorThresholds,
    MonitorType,
    State,
    TaskSpec,
    WindowInfo,
    clave_clase,
)
from vigia.core.states import classify_with_motivo
from vigia.sim.model import DIAGNOSIS_MAPPING, FEATURE_COLS_PLAIN

PredictFn = Callable[[pd.DataFrame], np.ndarray]

# `KernelExplainer.shap_values` muestrea las coaliciones con el
# generador GLOBAL de NumPy, sin `random_state` propio. Para que dos peticiones
# den lo mismo, `global_shap` fija ese generador con su `seed` durante la
# llamada y restaura el estado anterior; el cerrojo evita que dos hilos (jobs
# en paralelo) se pisen el estado global.
_SHAP_RNG_LOCK = threading.Lock()

# /: truncado fijo, no configurable desde fuera de este
# módulo. Si el ranking es más corto, se rellena con ganancia cero.
P_TRUNCADO = 10


def harness_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve las 41 features del modelo con nombres planos, como float.

    Acepta un frame canónico o crudo del harness: columnas `PC_Diagnosis_*`
    (nombres crudos) o los nombres planos de `DIAGNOSIS_MAPPING`. Cualquier
    columna ausente se rellena a 0.0 (diagnóstico no presente).
    """
    out = df.rename(columns=DIAGNOSIS_MAPPING) if any(
        c in DIAGNOSIS_MAPPING for c in df.columns
    ) else df.copy()
    # out ahora puede tener columnas planas (Age, Previous_PC_episodes,
    # <nombre_diagnostico>) directamente, sea cual sea el origen (crudo con
    # nombres PC_Diagnosis_* o ya plano).
    cols: dict[str, np.ndarray] = {}
    for plano in FEATURE_COLS_PLAIN:
        if plano in out.columns:
            cols[plano] = out[plano].astype(float).to_numpy()
        else:
            cols[plano] = np.zeros(len(out), dtype=float)
    return pd.DataFrame(cols, index=out.index)


def _auroc(y_true: np.ndarray, y_score: np.ndarray) -> float | None:
    """AUROC calculado por rangos (Mann-Whitney), sin dependencia de
    scikit-learn. Devuelve None si `y_true` tiene una sola clase.
    """
    positivos = y_true == 1
    negativos = y_true == 0
    n_pos = int(positivos.sum())
    n_neg = int(negativos.sum())
    if n_pos == 0 or n_neg == 0:
        return None
    orden = np.argsort(y_score, kind="mergesort")
    rangos = np.empty(len(y_score), dtype=float)
    rangos[orden] = np.arange(1, len(y_score) + 1, dtype=float)
    # Empates: rango medio por grupo de valores iguales.
    valores_ordenados = y_score[orden]
    i = 0
    while i < len(valores_ordenados):
        j = i
        while j + 1 < len(valores_ordenados) and valores_ordenados[j + 1] == valores_ordenados[i]:
            j += 1
        if j > i:
            rango_medio = rangos[orden[i : j + 1]].mean()
            rangos[orden[i : j + 1]] = rango_medio
        i = j + 1
    suma_rangos_pos = rangos[positivos].sum()
    auc = (suma_rangos_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


def _tipo(task: TaskSpec | None) -> str:
    """Tipo de tarea; sin `task` es binario (como siempre)."""
    return task.task_type if task is not None else "binary"


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Raíz del error cuadrático medio (puntaje de la permutación en
    regresión)."""
    return float(np.sqrt(np.mean((np.asarray(y_true, dtype=float) - y_pred) ** 2)))


def _columnas_objetivo(
    task: TaskSpec | None, clase: Any
) -> tuple[list[int] | None, str | None]:
    """Qué columnas de `(n, k)` se explican. `(None, None)` es
    el caso binario de siempre (`[:, 1]`). Con `clase` explícita, esa columna y
    su nombre; sin ella, la suma de las columnas del conjunto favorable
    (`[]` si no hay: el llamador cae en la clase mayoritaria). Una clase que no
    está en `task.classes` lanza `ValueError`, que el backend traduce a 422."""
    tipo = _tipo(task)
    match tipo:
        case "regression":
            # Una regresión no tiene clases ni selector de clase.
            if clase is not None:
                raise ValueError(
                    "una explicación de regresión no tiene clase: quita la clase de la petición"
                )
            return None, None
        case "binary" | "multiclass":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    if clase is not None:
        if task is None or not task.classes:
            raise ValueError(
                "clase solo vale en un proyecto con clases declaradas: quita la clase "
                "de la petición o declara las clases del proyecto"
            )
        try:
            i = task.indice(clase)
        except ValueError:
            raise ValueError(
                f"La clase {clave_clase(clase)} no está entre las clases del proyecto "
                f"({', '.join(task.claves)})."
            ) from None
        return [i], task.claves[i]
    match tipo:
        case "multiclass":
            return [task.indice(f) for f in task.favorables], None  # type: ignore[union-attr]
        case _:
            return None, None


def _clase_mayoritaria(P: np.ndarray, task: TaskSpec) -> tuple[list[int], str]:
    """Sin conjunto favorable: la clase que más veces predice el modelo
    sobre las filas explicadas. Es un respaldo: el contrato pide la mayoritaria de
    la línea base, que el llamador pasa como `clase=` (`clase_mayoritaria_de`)."""
    i = int(np.bincount(P.argmax(axis=1), minlength=task.k).argmax())
    return [i], task.claves[i]


def clase_mayoritaria_de(valores: Any, task: TaskSpec) -> str:
    """Clave de la clase más frecuente de `valores` (la columna de clase
    real o predicha de la línea base). El backend la pasa como `clase=` a
    `global_permutation` y `global_shap` cuando el proyecto no tiene conjunto
    favorable, para que la clase explicada no cambie de un lote a otro."""
    claves = pd.Series([clave_clase(v) for v in valores if not pd.isna(v)])
    claves = claves[claves.isin(task.claves)]
    if claves.empty:
        raise ValueError(
            "no hay valores de clase conocidos en la línea base: vuelve a subir "
            "el fichero de referencia con la columna de clase"
        )
    return str(claves.value_counts().idxmax())


def _vector_objetivo(
    P: np.ndarray, columnas: list[int] | None, *, regresion: bool = False
) -> np.ndarray:
    """Lo que se explica de la salida del modelo. Binario: `P[:, 1]`. Multiclase:
    la suma de las columnas elegidas.: en regresión la salida ya es el
    vector `(n,)` del valor predicho (o `(n, 1)`), sin indexar."""
    if regresion:
        valores = np.asarray(P, dtype=float)
        if valores.ndim == 2 and valores.shape[1] == 1:
            return valores[:, 0]
        if valores.ndim != 1:
            raise ValueError(
                "el modelo de regresión debe devolver un único valor por fila "
                f"(devuelve {valores.shape})"
            )
        return valores
    if columnas is None:
        return P[:, 1]
    return P[:, columnas].sum(axis=1)


def _y_del_objetivo(
    y: np.ndarray | None, clase: Any, nombre: str | None
) -> np.ndarray | None:
    """`y` numérico se toma tal cual (0/1 de lo que se explica). Con `clase` y
    `y` de texto (la clase real), pasa a 1 donde coincide con esa clase."""
    if y is None or clase is None or nombre is None:
        return y
    arr = np.asarray(y)
    if arr.dtype.kind in "OUS":
        return np.array(
            [np.nan if pd.isna(v) else float(clave_clase(v) == nombre) for v in arr], dtype=float
        )
    return y


def global_permutation(
    predict_fn: PredictFn,
    X: pd.DataFrame,
    *,
    y: np.ndarray | None = None,
    n_repeats: int = 5,
    seed: int = 0,
    max_rows: int = 500,
    task: TaskSpec | None = None,
    clase: Any = None,
) -> ExplanationResult:
    """Importancia global por permutación, determinista.

    Si `y` se pasa (y tiene ambas clases): importancia de una columna es el
    descenso medio del AUROC al permutarla frente al AUROC base. Si `y` no
    se pasa, o tiene una sola clase, la importancia es la media de
    `|P(favorable) permutada - P(favorable) base|`: una medida de
    sensibilidad de la salida del modelo a esa columna, no de fidelidad
    predictiva (no hay etiqueta contra la que fallar).

    `X` debe tener las columnas de features con nombres planos. Si
    `len(X) > max_rows`, se toma una muestra determinista de `max_rows`
    filas con `np.random.default_rng(seed)`.

    `predict_fn` devuelve `(n, k)` en el orden de `task.classes`. En
    multiclase se explica la suma de las columnas del conjunto favorable (sin
    conjunto favorable, la clase mayoritaria de lo predicho) o la `clase`
    pedida. `y` es el 0/1 de lo que se explica; con `clase`, `y` puede ser la
    clase real en texto. Sin `task` (o binario), todo como antes.
    """
    cols_obj, nombre_clase = _columnas_objetivo(task, clase)
    es_regresion = False
    match _tipo(task):
        case "regression":
            es_regresion = True
        case _:
            pass
    y = _y_del_objetivo(y, clase, nombre_clase)
    rng = np.random.default_rng(seed)
    n_rows_total = len(X)
    if n_rows_total > max_rows:
        idx = rng.choice(n_rows_total, size=max_rows, replace=False)
        idx.sort()
        Xs = X.iloc[idx].reset_index(drop=True)
        y_sample = y[idx] if y is not None else None
    else:
        Xs = X.reset_index(drop=True)
        y_sample = y

    columnas = list(Xs.columns)
    n_rows = len(Xs)

    etiqueta_valida = ~pd.isna(y_sample) if y_sample is not None else None
    usa_y = y_sample is not None and len(np.unique(y_sample[etiqueta_valida])) > 1
    if usa_y:
        scoring = "rmse_increase" if es_regresion else "auroc_drop"
    else:
        scoring = "sensibilidad_media"

    P_base = predict_fn(Xs)
    if cols_obj == [] and task is not None:
        cols_obj, nombre_clase = _clase_mayoritaria(P_base, task)
    base_probs = _vector_objetivo(P_base, cols_obj, regresion=es_regresion)
    # El AUROC se calcula solo sobre las filas con etiqueta conocida: si se
    # deja pasar y_sample con NaN, numpy castea el NaN a un centinela int64
    # que _auroc excluye de positivos/negativos pero no de la población de
    # scores usada para el ranking, sesgando el AUROC.
    if es_regresion:
        # `y` continua; el puntaje es el aumento del RMSE al permutar.
        y_validas = y_sample[etiqueta_valida].astype(float) if usa_y else None
        base_auc = (
            _rmse(y_validas, base_probs[etiqueta_valida]) if usa_y and y_validas is not None else None
        )
    else:
        y_validas = y_sample[etiqueta_valida].astype(int) if usa_y else None
        base_auc = _auroc(y_validas, base_probs[etiqueta_valida]) if usa_y else None

    importancias: dict[str, float] = {}
    for col in columnas:
        deltas = []
        original = Xs[col].to_numpy(copy=True)
        for _ in range(n_repeats):
            permutado = original.copy()
            rng.shuffle(permutado)
            Xp = Xs.copy()
            Xp[col] = permutado
            probs = _vector_objetivo(predict_fn(Xp), cols_obj, regresion=es_regresion)
            if usa_y and base_auc is not None and es_regresion:
                delta = _rmse(y_validas, probs[etiqueta_valida]) - base_auc  # type: ignore[arg-type]
            elif usa_y and base_auc is not None:
                auc_perm = _auroc(y_validas, probs[etiqueta_valida])
                delta = 0.0 if auc_perm is None else base_auc - auc_perm
            else:
                delta = float(np.abs(probs - base_probs).mean())
            deltas.append(delta)
        importancias[col] = float(np.mean(deltas))

    params: dict[str, Any] = {
        "n_repeats": n_repeats,
        "seed": seed,
        "n_rows": n_rows,
        "scoring": scoring,
    }
    if cols_obj is not None:
        params.update(_params_objetivo(task, cols_obj, nombre_clase))
    return _resultado_global(
        "global_permutation", list(importancias.items()), params, nombre_clase
    )


MOTIVO_IMPORTANCIA_NO_FINITA = (
    "el modelo devolvió valores que no son números al explicar (por ejemplo, por "
    "celdas vacías que no sabe leer): no se puede calcular la importancia de las variables"
)


def _resultado_global(
    kind: Any, pares: list[tuple[str, float]], params: dict[str, Any], nombre_clase: str | None
) -> ExplanationResult:
    """Ordena las importancias y deja fuera las que no son finitas.

    Una importancia NaN o infinita nunca llega al JSON guardado. Si se descarta
    alguna variable, `params["variables_sin_importancia"]` la nombra; si no queda
    ninguna, la explicación sale `available=False` con motivo, no como un
    resultado vacío presentado como válido."""
    finitas = [(f, v) for f, v in pares if math.isfinite(v)]
    descartadas = [f for f, v in pares if not math.isfinite(v)]
    if descartadas:
        params = {**params, "variables_sin_importancia": descartadas}
    if not finitas:
        return ExplanationResult(
            kind=kind,
            available=False,
            motivo=MOTIVO_IMPORTANCIA_NO_FINITA,
            params=params,
            clase_explicada=nombre_clase,
        )
    ordenadas = sorted(finitas, key=lambda t: t[1], reverse=True)
    return ExplanationResult(
        kind=kind,
        available=True,
        features=[FeatureImportance(feature=f, importance=v) for f, v in ordenadas],
        params=params,
        clase_explicada=nombre_clase,
    )


def _params_objetivo(task: TaskSpec | None, columnas: list[int], nombre: str | None) -> dict[str, Any]:
    if task is None:
        return {}
    if nombre is not None:
        return {"objetivo": "clase", "clase": nombre}
    return {"objetivo": "favorables", "clases": [task.claves[i] for i in columnas]}


def _nombre_feature_en_regla(regla: str, feature_names: list[str]) -> str:
    """Extrae de la cadena de una regla LIME (p.ej. "Age > 45.00" o
    "0.00 < Previous_PC_episodes <= 1.00") el nombre de la feature: el más
    largo de `feature_names` que aparece como subcadena de `regla`.
    """
    candidatas = [f for f in feature_names if f in regla]
    if not candidatas:
        return regla
    return max(candidatas, key=len)


def _codigos_categoria(valores: pd.Series) -> tuple[list[str], dict[str, int]]:
    """Categorías ordenadas de una columna categórica y su código:
    mismo orden para el fondo, la fila a explicar y la decodificación."""
    categorias = sorted(valores.astype(str).unique().tolist())
    return categorias, {valor: codigo for codigo, valor in enumerate(categorias)}


def local_lime(
    predict_fn: PredictFn,
    X_background: pd.DataFrame,
    row: pd.Series | np.ndarray,
    *,
    feature_names: list[str] | None = None,
    categorical_cols: list[str] | None = None,
    num_features: int = 8,
    seed: int = 0,
    class_names: tuple[str, str] = ("no_derivacion", "derivacion"),
    row_seq: int | None = None,
    task: TaskSpec | None = None,
    clase: Any = None,
) -> ExplanationResult:
    """Explicación local LIME de una fila, sobre un fondo de entrenamiento.

    `predict_fn` debe aceptar un `np.ndarray` (2D) además de un
    `pd.DataFrame`: LIME llama al predictor con arrays desnudos. Se envuelve
    aquí reconstruyendo el `DataFrame` con `feature_names` antes de llamar
    a `predict_fn`.

    `categorical_cols`: columnas de `feature_names` que son
    categóricas en texto (modelo ejecutable con `mapping.feature_cols`
    categóricas). Sin ella (la ruta de `sim_logistic`, todo numérico), el
    comportamiento es exactamente el de antes. Con ella, LIME opera sobre un
    marco codificado (cada categoría, un entero) con `categorical_features`
    y `categorical_names`, y `_predict_np` decodifica esas columnas a texto
    antes de llamar a `predict_fn`: sin esto, `LimeTabularExplainer`
    revienta con `TypeError` en cuanto hay una columna de texto.

    Con `task` multiclase explica la clase predicha de la fila (o la
    `clase` pedida), con los `k` nombres de clase, y devuelve las `k`
    probabilidades en `probabilities`, la clase en `clase_explicada` y
    `prob_favorable` como la suma del conjunto favorable (nula sin él). Sin
    `task` (o binario), todo como antes.
    """
    columnas_pedidas, nombre_pedido = _columnas_objetivo(task, clase)
    multiclase = regresion = False
    match _tipo(task):
        case "multiclass":
            multiclase = True
        case "regression":
            regresion = True
        case _:
            pass
    nombres_clase = list(task.claves) if multiclase and task is not None else list(class_names)
    # En regresión LIME va en `mode="regression"`, sin nombres de clase.
    modo_lime: dict[str, Any] = (
        {"mode": "regression"} if regresion else {"class_names": nombres_clase}
    )
    try:
        import lime.lime_tabular
    except ImportError:
        return ExplanationResult(
            kind="local_lime",
            available=False,
            motivo=MOTIVO_LIME_NO_DISPONIBLE,
            row_seq=row_seq,
        )

    nombres = feature_names if feature_names is not None else list(X_background.columns)
    # X_background y row pueden traer sus columnas en un orden distinto de
    # `nombres` (p.ej. si el llamador pasa feature_names explícito, o si
    # row es una Series con las mismas columnas reordenadas). Reindexar por
    # nombre antes de convertir a ndarray: LIME y predict_fn trabajan sobre
    # posiciones, no nombres, así que un desorden aquí corrompe la
    # explicación en silencio (sin excepción).
    X_background = X_background.reindex(columns=nombres)
    categorical_cols = [c for c in (categorical_cols or []) if c in nombres]
    cat_idx = [nombres.index(c) for c in categorical_cols]

    if isinstance(row, pd.Series):
        row_raw = row.reindex(nombres)
    else:
        row_raw = pd.Series(np.asarray(row), index=nombres)

    if cat_idx:
        categorias_por_col: dict[str, list[str]] = {}
        codigos_por_col: dict[str, dict[str, int]] = {}
        entrenamiento = pd.DataFrame(index=X_background.index)
        for col in nombres:
            if col in categorical_cols:
                categorias, codigos = _codigos_categoria(X_background[col])
                categorias_por_col[col] = categorias
                codigos_por_col[col] = codigos
                entrenamiento[col] = X_background[col].astype(str).map(codigos).astype(float)
            else:
                entrenamiento[col] = pd.to_numeric(X_background[col], errors="coerce")

        row_encoded = row_raw.copy()
        for col in categorical_cols:
            valor = str(row_raw[col])
            codigos = codigos_por_col[col]
            if valor not in codigos:
                codigos[valor] = len(categorias_por_col[col])
                categorias_por_col[col].append(valor)
            row_encoded[col] = float(codigos[valor])
        for col in nombres:
            if col not in categorical_cols:
                row_encoded[col] = float(row_raw[col])

        def _predict_np(X: np.ndarray) -> np.ndarray:
            df = pd.DataFrame(X, columns=nombres)
            for col in categorical_cols:
                categorias = categorias_por_col[col]
                codigos_fila = np.clip(
                    np.rint(df[col].to_numpy()).astype(int), 0, len(categorias) - 1
                )
                df[col] = [categorias[c] for c in codigos_fila]
            for col in nombres:
                if col not in categorical_cols:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return predict_fn(df)

        explainer = lime.lime_tabular.LimeTabularExplainer(
            training_data=entrenamiento[nombres].to_numpy(),
            feature_names=nombres,
            categorical_features=cat_idx,
            categorical_names={i: categorias_por_col[nombres[i]] for i in cat_idx},
            discretize_continuous=True,
            random_state=seed,
            **modo_lime,
        )
        row_np = row_encoded.to_numpy(dtype=float)
        if regresion:
            return _lime_regresion(
                explainer, row_np, _predict_np, nombres, num_features, seed, row_seq
            )
        if multiclase and task is not None:
            return _lime_multiclase(
                explainer, row_np, _predict_np, task, columnas_pedidas, nombre_pedido,
                nombres, num_features, seed, row_seq,
            )
        exp = explainer.explain_instance(row_np, _predict_np, num_features=num_features)
        prob_favorable = float(_predict_np(row_np.reshape(1, -1))[0, 1])
        features = [
            FeatureImportance(
                feature=_nombre_feature_en_regla(regla, nombres),
                importance=float(peso),
                rule=regla,
            )
            for regla, peso in exp.as_list()
        ]
        return ExplanationResult(
            kind="local_lime",
            available=True,
            features=features,
            row_seq=row_seq,
            prob_favorable=prob_favorable,
            params={"num_features": num_features, "seed": seed},
        )

    def _predict_np(X: np.ndarray) -> np.ndarray:
        df = pd.DataFrame(X, columns=nombres)
        return predict_fn(df)

    explainer = lime.lime_tabular.LimeTabularExplainer(
        training_data=X_background.to_numpy(),
        feature_names=nombres,
        discretize_continuous=True,
        random_state=seed,
        **modo_lime,
    )
    row_np = row_raw.to_numpy()
    if regresion:
        return _lime_regresion(explainer, row_np, _predict_np, nombres, num_features, seed, row_seq)
    if multiclase and task is not None:
        return _lime_multiclase(
            explainer, row_np, _predict_np, task, columnas_pedidas, nombre_pedido,
            nombres, num_features, seed, row_seq,
        )
    exp = explainer.explain_instance(row_np, _predict_np, num_features=num_features)

    features = [
        FeatureImportance(
            feature=_nombre_feature_en_regla(regla, nombres),
            importance=float(peso),
            rule=regla,
        )
        for regla, peso in exp.as_list()
    ]

    prob_favorable = float(_predict_np(row_np.reshape(1, -1))[0, 1])

    return ExplanationResult(
        kind="local_lime",
        available=True,
        features=features,
        row_seq=row_seq,
        prob_favorable=prob_favorable,
        params={"num_features": num_features, "seed": seed},
    )


def _lime_regresion(
    explainer: Any,
    row_np: np.ndarray,
    predict_np: Callable[[np.ndarray], np.ndarray],
    nombres: list[str],
    num_features: int,
    seed: int,
    row_seq: int | None,
) -> ExplanationResult:
    """LIME en regresión: explica el valor predicho de la fila, en la
    unidad de la salida. `prediction_value` lleva ese valor; no hay clase ni
    probabilidades."""
    exp = explainer.explain_instance(row_np, predict_np, num_features=num_features)
    features = [
        FeatureImportance(
            feature=_nombre_feature_en_regla(regla, nombres),
            importance=float(peso),
            rule=regla,
        )
        for regla, peso in exp.as_list()
    ]
    valor = float(np.asarray(predict_np(row_np.reshape(1, -1)), dtype=float).reshape(-1)[0])
    return ExplanationResult(
        kind="local_lime",
        available=True,
        features=features,
        row_seq=row_seq,
        params={"num_features": num_features, "seed": seed},
        prediction_value=valor,
    )


def _lime_multiclase(
    explainer: Any,
    row_np: np.ndarray,
    predict_np: Callable[[np.ndarray], np.ndarray],
    task: TaskSpec,
    columnas_pedidas: list[int] | None,
    nombre_pedido: str | None,
    nombres: list[str],
    num_features: int,
    seed: int,
    row_seq: int | None,
) -> ExplanationResult:
    """LIME en multiclase: por defecto la clase predicha de la fila;
    LIME explica `label=1` si no se le dice otra cosa, que solo vale en binario."""
    probs = np.asarray(predict_np(row_np.reshape(1, -1)), dtype=float)[0]
    if nombre_pedido is not None and columnas_pedidas:
        idx = columnas_pedidas[0]
    else:
        idx = int(np.argmax(probs))
    exp = explainer.explain_instance(
        row_np, predict_np, num_features=num_features, labels=(idx,)
    )
    features = [
        FeatureImportance(
            feature=_nombre_feature_en_regla(regla, nombres),
            importance=float(peso),
            rule=regla,
        )
        for regla, peso in exp.as_list(label=idx)
    ]
    favorables = [task.indice(f) for f in task.favorables]
    return ExplanationResult(
        kind="local_lime",
        available=True,
        features=features,
        row_seq=row_seq,
        prob_favorable=float(probs[favorables].sum()) if favorables else None,
        params={"num_features": num_features, "seed": seed},
        probabilities=[float(p) for p in probs],
        clase_explicada=task.claves[idx],
    )


MOTIVO_LIME_NO_DISPONIBLE = (
    "LIME no disponible en este equipo: falta una librería o es incompatible"
)
MOTIVO_SHAP_NO_DISPONIBLE = (
    "SHAP no disponible en este equipo: falta una librería o es incompatible"
)


@functools.lru_cache(maxsize=1)
def shap_available() -> tuple[bool, str | None]:
    """Comprueba si `shap` está disponible en este equipo, sin lanzar.

    Cachea el resultado: `shap_available.cache_clear()` para forzar una
    nueva comprobación (los tests que simulan su ausencia lo necesitan).
    """
    try:
        import shap  # noqa: F401
    except ImportError:
        return False, MOTIVO_SHAP_NO_DISPONIBLE
    except OSError:
        return False, MOTIVO_SHAP_NO_DISPONIBLE
    except Exception:  # noqa: BLE001 (llvmlite/numba y otros fallos de carga nativa)
        return False, MOTIVO_SHAP_NO_DISPONIBLE
    return True, None


def global_shap(
    predict_fn: PredictFn,
    X_background: pd.DataFrame,
    X_explain: pd.DataFrame,
    *,
    n_background: int = 30,
    nsamples: int = 100,
    seed: int = 0,
    task: TaskSpec | None = None,
    clase: Any = None,
) -> ExplanationResult:
    """Importancia global SHAP (KernelExplainer) sobre un subconjunto de
    filas a explicar, con un fondo muestreado del baseline.

    Si SHAP no está disponible en el equipo, devuelve `available=False`
    con el motivo de `shap_available` (la UI ofrece permutation
    y LIME como alternativa siempre disponible).

    En multiclase, SHAP de la suma de las columnas del conjunto
    favorable (lineal en la salida, así que es la suma de sus valores SHAP), de
    la clase mayoritaria si no hay conjunto, o de la `clase` pedida.
    """
    cols_obj, nombre_clase = _columnas_objetivo(task, clase)
    indice_salida = 1  # binario: la columna de P(favorable)
    match _tipo(task):
        case "regression":
            indice_salida = 0  # La salida de un regresor es una sola columna
        case _:
            pass
    disponible, motivo = shap_available()
    if not disponible:
        return ExplanationResult(kind="global_shap", available=False, motivo=motivo)

    import shap

    columnas = list(X_background.columns)
    background = shap.sample(X_background, n_background, random_state=seed)
    # X_explain puede traer las mismas columnas en otro orden que
    # X_background: KernelExplainer opera por posición, así que reindexar
    # por nombre antes de pasarlo evita que la atribución se asigne a la
    # feature equivocada sin ningún aviso.
    X_explain = X_explain.reindex(columns=columnas)

    def _predict_np(X: np.ndarray) -> np.ndarray:
        df = pd.DataFrame(X, columns=columnas)
        return predict_fn(df)

    with _SHAP_RNG_LOCK:
        estado_previo = np.random.get_state()
        try:
            np.random.seed(seed)
            explainer = shap.KernelExplainer(_predict_np, background)
            shap_values = explainer.shap_values(X_explain, nsamples=nsamples, silent=True)
        finally:
            np.random.set_state(estado_previo)

    if cols_obj == [] and task is not None:
        cols_obj, nombre_clase = _clase_mayoritaria(_predict_np(X_explain), task)
    if cols_obj is not None:
        if isinstance(shap_values, list):
            sv1 = np.sum([np.asarray(shap_values[i]) for i in cols_obj], axis=0)
        else:
            sv1 = np.asarray(shap_values)[:, :, cols_obj].sum(axis=2)
    elif isinstance(shap_values, list):
        sv1 = np.array(shap_values[1])
    elif np.asarray(shap_values).ndim == 3:
        sv1 = np.asarray(shap_values)[:, :, indice_salida]
    else:
        sv1 = np.asarray(shap_values)

    mean_abs = np.abs(sv1).mean(axis=0)
    params: dict[str, Any] = {
        "n_background": len(background),
        "nsamples": nsamples,
        "n_rows": len(X_explain),
        "seed": seed,
    }
    if cols_obj is not None:
        params.update(_params_objetivo(task, cols_obj, nombre_clase))
    return _resultado_global("global_shap", list(zip(columnas, mean_abs.tolist())), params, nombre_clase)


def explain_stability_ndcg(
    actual: Sequence[FeatureImportance],
    referencia: Sequence[FeatureImportance],
    p: int = P_TRUNCADO,
) -> float:
    """nDCG normalizado (`nDCG_p = DCG_p / IDCG_p`) entre el orden de
    `actual` y el de `referencia`.

    La ganancia de cada posición del ranking `actual` es la importancia de
    esa característica **en la referencia**, no su posición en `actual`: si
    una característica que era la primera en la referencia cae al puesto 8
    en `actual`, su ganancia sigue siendo alta pero se descuenta mucho por
    el logaritmo de la posición, así que el nDCG baja. Una característica
    de `actual` que no aparece en `referencia` aporta ganancia 0.0.

    Fórmula, con `rel(f)` la importancia de la característica `f` en
    `referencia` (recortada a `>= 0.0`; una explicación global nunca trae
    importancias negativas, pero se recorta por si acaso) y `rel_ref` esa
    misma lista de importancias ordenada de mayor a menor (la referencia ya
    llega así por construcción, pero se reordena aquí para no depender de
    que el llamador lo respete):

        DCG_p  = sum_{i=1}^{p} rel(actual_i)  / log2(i + 1)
        IDCG_p = sum_{i=1}^{p} rel_ref[i]      / log2(i + 1)
        nDCG_p = DCG_p / IDCG_p     (1.0 si IDCG_p es 0.0: no hay nada que
                                      reordenar, así que se cuenta como
                                      estable)

    TRUNCADO DECLARADO (`p = 10` fijo): si `actual` o
    `referencia` tienen menos de `p` elementos, las posiciones que faltan
    rellenan con ganancia 0.0 en vez de acortar la suma. Si `actual` y
    `referencia` son la misma lista en el mismo orden, `DCG_p == IDCG_p` y
    el resultado es exactamente 1.0.

    Ejemplo numérico (con `p = 3` para poder seguirlo a mano; la llamada
    real desde `evaluate_explain` usa `p = 10`):

        referencia (orden descendente): A=0.6, B=0.3, C=0.1
        actual (intercambia las dos primeras posiciones): B, A, C

        DCG  = rel(B)/log2(2) + rel(A)/log2(3) + rel(C)/log2(4)
             = 0.3/1 + 0.6/1.584963 + 0.1/2 ≈ 0.728558
        IDCG = rel(A)/log2(2) + rel(B)/log2(3) + rel(C)/log2(4)
             = 0.6/1 + 0.3/1.584963 + 0.1/2 ≈ 0.839279
        nDCG = 0.728558 / 0.839279 ≈ 0.8681
    """
    relevancia = {fi.feature: max(0.0, fi.importance) for fi in referencia}
    relevancia_ideal = sorted((max(0.0, fi.importance) for fi in referencia), reverse=True)

    def _dcg(ganancias: list[float]) -> float:
        return sum(g / math.log2(i + 2) for i, g in enumerate(ganancias))

    ganancias_actual = [
        relevancia.get(actual[i].feature, 0.0) if i < len(actual) else 0.0 for i in range(p)
    ]
    ganancias_ideales = [
        relevancia_ideal[i] if i < len(relevancia_ideal) else 0.0 for i in range(p)
    ]

    idcg = _dcg(ganancias_ideales)
    if idcg == 0.0:
        return 1.0
    return _dcg(ganancias_actual) / idcg


def evaluate_explain(
    actual: ExplanationResult,
    referencia: ExplanationResult | None,
    *,
    thresholds: MonitorThresholds,
    model_version: str | None = None,
    batch_seq: int | None = None,
    p: int = P_TRUNCADO,
) -> EvaluationResult:
    """Evalúa la estabilidad de una explicación global frente a su
    referencia: una medida, `explain_stability_ndcg`, clasificada
    con `classify_with_motivo` igual que `evaluate_fairness` /
    `evaluate_quality` / `evaluate_drift`.

    Si todavía no hay explicación de referencia para `model_version` (la
    primera vez que se explica una versión, antes de fijarla con
    `History.set_explain_reference`), el estado es `sin_datos` con su
    motivo: no es un error, es la situación normal de calibración.
    """
    batches = [batch_seq] if batch_seq is not None else []

    if referencia is None:
        motivo = (
            f"sin explicación de referencia para la versión {model_version}"
            if model_version
            else "sin explicación de referencia"
        )
        measurement = Measurement(
            metric_key="explain_stability_ndcg",
            value=None,
            threshold_low=None,
            threshold_high=None,
            state=State.sin_datos,
            motivo=motivo,
        )
        window = WindowInfo(
            kind="baseline_vs_batch",
            n=len(actual.features),
            batches=batches,
            model_version=model_version,
            complete=False,
            motivo=motivo,
        )
        details = {"p": p, "referencia_disponible": False, "actual_kind": actual.kind}
        return EvaluationResult(
            monitor=MonitorType.explain,
            window=window,
            measurements=[measurement],
            config_snapshot={"p": p},
            core_version=CORE_VERSION,
            details=details,
        )

    valor = explain_stability_ndcg(actual.features, referencia.features, p=p)
    low, high = thresholds.limits("explain_stability_ndcg")
    estado, motivo_medida = classify_with_motivo(valor, low, high)
    measurement = Measurement(
        metric_key="explain_stability_ndcg",
        value=valor,
        threshold_low=low,
        threshold_high=high,
        state=estado,
        motivo=motivo_medida,
    )
    window = WindowInfo(
        kind="baseline_vs_batch",
        n=len(actual.features),
        batches=batches,
        model_version=model_version,
        complete=True,
    )
    details = {
        "p": p,
        "referencia_disponible": True,
        "actual_kind": actual.kind,
        "referencia_kind": referencia.kind,
        "actual_top": [f.feature for f in actual.features[:p]],
        "referencia_top": [f.feature for f in referencia.features[:p]],
    }
    return EvaluationResult(
        monitor=MonitorType.explain,
        window=window,
        measurements=[measurement],
        config_snapshot={"p": p},
        core_version=CORE_VERSION,
        details=details,
    )
