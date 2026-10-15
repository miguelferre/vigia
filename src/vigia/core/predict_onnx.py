"""Predicción sobre un modelo ejecutable en ONNX.

Contrato: el marco de predicción se construye siempre desde
`mapping.feature_cols`, nunca desde las 41 columnas de reuma de
`vigia.sim`. Cada columna tiene un `kind` ("numerica" o "categorica")
declarado por la entrada real del modelo ONNX (no por el dtype de pandas):
una columna que el modelo espera como texto se convierte a texto aunque en
el fichero de origen llegue como entero (`admission_type_id` en Diabetes
130).

`onnxruntime` es dependencia obligatoria desde (no opcional como
`shap`/`lime`): se importa a nivel de módulo.
"""
from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import pandas as pd

from vigia.core.schema import TaskSpec, clave_clase

__all__ = [
    "ModeloEjecutableInvalido",
    "PredictFn",
    "build_artifact_inputs",
    "cast_frame_to_kinds",
    "coincidencia_argmax",
    "coincidencia_valor",
    "es_entrada_entera",
    "load_session",
    "orden_clases_onnx",
    "predecir_en_hilo",
    "sanitize_onnx_name",
    "session_predict_proba",
    "session_predict_value",
    "validar_coincidencia_valor",
    "validate_and_load",
]

# Nodos de ONNX-ML que llevan las etiquetas de clase en su orden de columnas.
_NODOS_CLASIFICADOR = frozenset(
    {"TreeEnsembleClassifier", "LinearClassifier", "SVMClassifier", "ZipMap"}
)
# Atributo de la sesión con el orden de clases leído del grafo.
_ATRIBUTO_ORDEN = "vigia_orden_clases"
# Atributo de la sesión que dice si el grafo trae un nodo de clasificador.
_ATRIBUTO_CLASIFICADOR = "vigia_es_clasificador"

MENSAJE_ES_CLASIFICADOR = (
    "el modelo ONNX es un clasificador (devuelve clases o probabilidades) y este proyecto es de "
    "regresión: sube un modelo que devuelva un único número por fila"
)
MENSAJE_ES_REGRESOR = (
    "el modelo ONNX parece un regresor (devuelve un único número por fila, no probabilidades) y este "
    "proyecto es de clasificación: sube un modelo clasificador o crea un proyecto de regresión"
)

PredictFn = Callable[[pd.DataFrame], np.ndarray]


class ModeloEjecutableInvalido(ValueError):
    """El artefacto subido no sirve para predecir: mensaje en español,
    sin traza ni texto de librería, listo para volver como 422."""


def sanitize_onnx_name(name: str) -> str:
    """Mismo saneado que `skl2onnx` aplica al nombre de columna al convertir
    (`education-num` -> `education_num`): sustituye cualquier carácter que no
    sea alfanumérico o `_` por `_`, y antepone `_` si empieza por un dígito."""
    saneado = re.sub(r"[^\w+]", "_", name)
    if re.match(r"^[0-9]", saneado):
        saneado = "_" + saneado
    return saneado


_ONNX_DTYPE_NUMPY: dict[str, Any] = {
    "tensor(float)": np.float32,
    "tensor(double)": np.float64,
    "tensor(int64)": np.int64,
    "tensor(int32)": np.int32,
    "tensor(string)": np.object_,
}


def _onnx_kind(onnx_type: str) -> str:
    return "categorica" if "string" in onnx_type else "numerica"


MENSAJE_DATOS_EXTERNOS = (
    "el modelo ONNX guarda parte de sus pesos en ficheros aparte (datos externos): "
    "Vigía solo carga modelos de un único fichero .onnx. Vuelve a exportarlo con "
    "todos los pesos dentro del fichero, sin la opción de datos externos"
)


def _cargar_proto(modelo: Any) -> Any | None:
    """`ModelProto` de un `Path`, texto de ruta, `bytes` o un proto ya cargado, sin
    leer datos externos. `None` si la librería `onnx` no está en el equipo o el
    fichero no se puede leer."""
    try:
        import onnx
    except ImportError:
        return None
    try:
        if isinstance(modelo, onnx.ModelProto):
            return modelo
        if isinstance(modelo, (bytes, bytearray)):
            return onnx.load_from_string(bytes(modelo))
        return onnx.load(str(modelo), load_external_data=False)
    except Exception:  # noqa: BLE001 (un fichero que onnx no lee lo dice `load_session`)
        return None


def _tensores_con_datos_externos(grafo: Any) -> bool:
    """Recorre inicializadores, constantes de los nodos y subgrafos."""
    from onnx import AttributeProto, TensorProto

    externo = TensorProto.EXTERNAL
    if any(t.data_location == externo for t in grafo.initializer):
        return True
    for esparso in grafo.sparse_initializer:
        if (
            esparso.values.data_location == externo
            or esparso.indices.data_location == externo
        ):
            return True
    for nodo in grafo.node:
        for atributo in nodo.attribute:
            if atributo.type == AttributeProto.TENSOR and atributo.t.data_location == externo:
                return True
            if atributo.type == AttributeProto.GRAPH and _tensores_con_datos_externos(atributo.g):
                return True
            if atributo.type == AttributeProto.GRAPHS and any(
                _tensores_con_datos_externos(g) for g in atributo.graphs
            ):
                return True
    return False


def _tensores_con_datos_externos_funcion(funcion: Any) -> bool:
    """Constantes dentro de las funciones locales del modelo."""
    from onnx import AttributeProto, TensorProto

    for nodo in funcion.node:
        for atributo in nodo.attribute:
            if atributo.type == AttributeProto.TENSOR and (
                atributo.t.data_location == TensorProto.EXTERNAL
            ):
                return True
            if atributo.type == AttributeProto.GRAPH and _tensores_con_datos_externos(atributo.g):
                return True
    return False


def tiene_datos_externos(modelo: Any) -> bool:
    """`True` si algún tensor del modelo apunta a un fichero externo."""
    proto = _cargar_proto(modelo)
    if proto is None:
        return False
    return _tensores_con_datos_externos(proto.graph) or any(
        _tensores_con_datos_externos_funcion(f) for f in proto.functions
    )


def orden_clases_onnx(modelo: Any) -> list[str] | None:
    """Orden de las columnas de probabilidad según el grafo, leído de
    `classlabels_strings`, `classlabels_int64s` o `classlabels_ints` del nodo clasificador
    (`TreeEnsembleClassifier`, `LinearClassifier`, `SVMClassifier`) o del `ZipMap`,
    en la forma `clave_clase`. `modelo` es una ruta, `bytes` o un `ModelProto`.
    `None` si no se puede leer (sin `onnx` o sin esas etiquetas): el llamador
    exige entonces `classes` en el orden del modelo y lo comprueba con la línea
    base. Con `skl2onnx` el orden es `sklearn.classes_`, ordenado, no el de
    aparición."""
    proto = _cargar_proto(modelo)
    if proto is None:
        return None
    from onnx import helper

    hallado: list[str] | None = None
    for nodo in proto.graph.node:
        if nodo.op_type not in _NODOS_CLASIFICADOR:
            continue
        etiquetas: list[str] | None = None
        for atributo in nodo.attribute:
            if atributo.name == "classlabels_strings":
                valores = helper.get_attribute_value(atributo)
                etiquetas = [
                    clave_clase(v.decode("utf-8") if isinstance(v, bytes) else v)
                    for v in valores
                ]
            elif atributo.name in ("classlabels_int64s", "classlabels_ints"):
                etiquetas = [clave_clase(int(v)) for v in helper.get_attribute_value(atributo)]
        if etiquetas:
            if nodo.op_type == "ZipMap":
                return etiquetas  # el ZipMap es la salida visible: manda
            hallado = etiquetas
    return hallado


def load_session(path: Path | bytes) -> ort.InferenceSession:
    """Carga el fichero con el proveedor de CPU. 422 si no es un ONNX válido o si
    guarda pesos en ficheros externos (se comprueba antes de abrirlo, porque
    `onnxruntime` los leería de la ruta que diga el propio modelo). Deja en la
    sesión el orden de clases leído del grafo (`orden_clases_onnx`). Con `bytes`
    comprueba y abre los mismos bytes (sin ventana entre el hash y la carga)."""
    proto = _cargar_proto(path)
    if proto is None:
        # Cerrar por defecto: si no se puede leer el modelo para comprobar
        # sus datos externos, no se abre con onnxruntime, que sí los leería.
        raise ModeloEjecutableInvalido(
            "el fichero no es un modelo ONNX válido: no se ha podido leer para "
            "comprobarlo. Vuelve a exportarlo y a subirlo"
        )
    if tiene_datos_externos(proto):
        raise ModeloEjecutableInvalido(MENSAJE_DATOS_EXTERNOS)
    try:
        origen = bytes(path) if isinstance(path, (bytes, bytearray)) else str(path)
        sesion = ort.InferenceSession(origen, providers=["CPUExecutionProvider"])
    except Exception as exc:
        raise ModeloEjecutableInvalido(
            "el fichero no es un modelo ONNX válido: no se ha podido abrir"
        ) from exc
    try:
        setattr(sesion, _ATRIBUTO_ORDEN, orden_clases_onnx(proto))
        setattr(
            sesion,
            _ATRIBUTO_CLASIFICADOR,
            any(nodo.op_type in _NODOS_CLASIFICADOR for nodo in proto.graph.node),
        )
    except AttributeError:  # pragma: no cover (una sesión sin atributos nuevos)
        pass
    return sesion


def build_artifact_inputs(
    session: ort.InferenceSession, feature_cols: list[str]
) -> list[dict[str, Any]]:
    """`artifact_inputs_json`: una entrada por `feature_cols`, en ese
    orden, con el nombre saneado de `skl2onnx` buscado en las entradas reales
    del modelo. 422 si a alguna columna del mapeo le falta su entrada."""
    entradas = {inp.name: inp for inp in session.get_inputs()}
    resultado: list[dict[str, Any]] = []
    faltan: list[str] = []
    for nombre in feature_cols:
        info = entradas.get(sanitize_onnx_name(nombre))
        if info is None:
            faltan.append(nombre)
            continue
        resultado.append({"name": nombre, "type": info.type, "kind": _onnx_kind(info.type)})
    if faltan:
        raise ModeloEjecutableInvalido(
            "el modelo ONNX no tiene una entrada para estas columnas del mapeo: "
            + ", ".join(faltan)
            + ". Rehaz el mapeo sin esas columnas: en Configuración, «Reiniciar despliegue», "
            "quita las columnas de la plantilla de mapeo y vuelve a subir los ficheros."
        )
    return resultado


def _a_texto_categorico(valor: Any) -> str:
    """Un entero declarado como texto se convierte a texto, sin dejar
    el `.0` de un `float` de pandas (`admission_type_id` 3.0 -> "3")."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


def es_entrada_entera(meta: dict[str, Any]) -> bool:
    """Una entrada numérica cuyo tipo declarado es entero (`tensor(int64)` en
    ONNX, `int` en la línea base de un pickle).: el modelo la recibe
    entera en las dos rutas, así que LIME (que muestrea valores continuos)
    ve el mismo marco con ONNX y con joblib."""
    return meta.get("kind") != "categorica" and "int" in str(meta.get("type", "")).lower()


def cast_frame_to_kinds(df: pd.DataFrame, artifact_inputs: list[dict[str, Any]]) -> pd.DataFrame:
    """Selecciona y castea las columnas de `artifact_inputs` (en su orden):
    texto para "categorica", número para "numerica" (redondeado al entero
    más cercano si la entrada es entera). Nunca las 41 columnas
    de reuma: solo lo que declara `artifact_inputs`."""
    nombres = [i["name"] for i in artifact_inputs]
    faltan = [n for n in nombres if n not in df.columns]
    if faltan:
        raise ModeloEjecutableInvalido(
            "faltan columnas del mapeo en los datos a predecir: " + ", ".join(faltan)
        )
    columnas: dict[str, Any] = {}
    for meta in artifact_inputs:
        nombre = meta["name"]
        serie = df[nombre]
        if meta.get("kind") == "categorica":
            columnas[nombre] = serie.map(_a_texto_categorico)
        else:
            numero = pd.to_numeric(serie, errors="coerce")
            columnas[nombre] = np.rint(numero) if es_entrada_entera(meta) else numero
    return pd.DataFrame(columnas, index=df.index)


def _probs_y_orden(
    outputs: list[Any], task: TaskSpec | None = None
) -> tuple[np.ndarray, bool]:
    """Extrae las probabilidades `(n, k)` de la salida de `session.run`: un
    array 2D si el modelo se convirtió con `zipmap=False`, o una lista de
    `dict` (el `ZipMap` por defecto de `skl2onnx`) si no.

    Con `task` multiclase y un `ZipMap`, las columnas salen ya en el orden de
    `task.classes` buscando cada clase por su nombre (segundo valor `True`);
    si el modelo no devuelve exactamente esas clases, `ModeloEjecutableInvalido`.
    Sin `task`, como siempre: claves ordenadas."""
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "binary" | "multiclass":
            pass
        case "regression":
            raise ValueError(
                "un proyecto de regresión no tiene probabilidades por clase: Vigía lee su valor "
                "numérico (error interno, avisa a quien mantiene Vigía)"
            )
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    for salida in outputs:
        if isinstance(salida, np.ndarray) and salida.ndim == 2 and salida.shape[1] >= 2:
            return salida.astype(float), False
    for salida in outputs:
        if isinstance(salida, list) and salida and isinstance(salida[0], dict):
            match tipo:
                case "multiclass":
                    por_clave = {clave_clase(k): k for k in salida[0]}
                    _comprobar_mismas_clases(list(por_clave), task)  # type: ignore[arg-type]
                    matriz = np.array(
                        [[fila[por_clave[c]] for c in task.claves] for fila in salida],  # type: ignore[union-attr]
                        dtype=float,
                    )
                    return matriz, True
                case _:
                    claves = sorted(salida[0].keys())
                    return (
                        np.array([[fila[c] for c in claves] for fila in salida], dtype=float),
                        False,
                    )
    # Un regresor devuelve un único número por fila, `(n)` o `(n, 1)`.
    for salida in outputs:
        if (
            isinstance(salida, np.ndarray)
            and np.issubdtype(salida.dtype, np.floating)
            and (salida.ndim == 1 or (salida.ndim == 2 and salida.shape[1] == 1))
        ):
            raise ModeloEjecutableInvalido(MENSAJE_ES_REGRESOR)
    raise ModeloEjecutableInvalido(
        "el modelo ONNX no expone una salida de probabilidades (una columna por clase)"
    )


def _comprobar_mismas_clases(leidas: list[str], task: TaskSpec) -> None:
    if set(leidas) != set(task.claves):
        raise ModeloEjecutableInvalido(
            f"el modelo ONNX devuelve las clases ({', '.join(leidas)}) y el proyecto "
            f"declara ({', '.join(task.claves)}): deben ser las mismas. Corrige las "
            "clases del proyecto o sube el modelo que corresponde"
        )


def _reordenar_a_clases(
    probs: np.ndarray, orden: list[str] | None, task: TaskSpec
) -> np.ndarray:
    """Lleva las columnas de `probs` (en el orden `orden` del grafo) al orden
    de `task.classes`. Sin orden legible, se confía en que `classes` va en el
    orden del modelo y se comprueba contra la línea base (`coincidencia_argmax`)."""
    if probs.shape[1] != task.k:
        raise ModeloEjecutableInvalido(
            f"el modelo ONNX da {probs.shape[1]} probabilidades por fila y el proyecto "
            f"tiene {task.k} clases ({', '.join(task.claves)}): comprueba que sea el "
            "modelo de este proyecto"
        )
    if orden is None or list(orden) == list(task.claves):
        return probs
    _comprobar_mismas_clases(list(orden), task)
    posicion = {c: i for i, c in enumerate(orden)}
    return probs[:, [posicion[c] for c in task.claves]]


def _correr_sesion(
    session: ort.InferenceSession,
    entradas: dict[str, Any],
    artifact_inputs: list[dict[str, Any]],
    X: pd.DataFrame,
) -> list[Any]:
    """Castea `X` a los tipos declarados, arma el `feed` con los nombres saneados
    de `skl2onnx` y corre la sesión. Común a clasificadores y regresores."""
    frame = cast_frame_to_kinds(X, artifact_inputs)
    feed: dict[str, np.ndarray] = {}
    for meta in artifact_inputs:
        nombre_onnx = sanitize_onnx_name(meta["name"])
        info = entradas.get(nombre_onnx)
        if info is None:
            raise ModeloEjecutableInvalido(
                f"la entrada '{meta['name']}' no está en el modelo ONNX"
            )
        dtype_np = _ONNX_DTYPE_NUMPY.get(info.type, np.float32)
        valores = frame[meta["name"]].to_numpy()
        if dtype_np is np.object_:
            feed[nombre_onnx] = np.array([[str(v)] for v in valores], dtype=object)
        else:
            feed[nombre_onnx] = valores.astype(dtype_np).reshape(-1, 1)
    try:
        return session.run(None, feed)
    except Exception as exc:
        raise ModeloEjecutableInvalido(
            "el modelo ONNX no ha podido predecir con las columnas del mapeo: "
            "comprueba que cada columna llega con el tipo (texto o número) con "
            "el que se entrenó"
        ) from exc


def session_predict_proba(
    session: ort.InferenceSession,
    artifact_inputs: list[dict[str, Any]],
    task: TaskSpec | None = None,
) -> PredictFn:
    """`PredictFn` (contrato de `core.explain`) que corre la sesión ONNX en
    lote sobre las columnas de `artifact_inputs`, con nombres crudos de
    entrada (para SHAP/LIME) y nombres saneados de `skl2onnx` en el feed.

    Con `task` multiclase devuelve `(n, k)` en el orden de
    `task.classes`; si el orden leído del grafo difiere, reordena las columnas.
    Sin `task` (o binario), `(n, 2)` como siempre.: un proyecto de regresión no
    usa esta función (`session_predict_value`). La función devuelta es
    síncrona y segura para llamarla desde un hilo (`predecir_en_hilo`)."""
    entradas = {inp.name: inp for inp in session.get_inputs()}
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "binary" | "multiclass":
            pass
        case "regression":
            raise ValueError(
                "un proyecto de regresión no tiene probabilidades por clase: Vigía lee su valor "
                "numérico (error interno, avisa a quien mantiene Vigía)"
            )
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    orden = getattr(session, _ATRIBUTO_ORDEN, None)

    def predict_fn(X: pd.DataFrame) -> np.ndarray:
        salidas = _correr_sesion(session, entradas, artifact_inputs, X)
        match tipo:
            case "multiclass":
                matriz, ya_en_orden = _probs_y_orden(salidas, task)
                return _reordenar_a_clases(matriz, None if ya_en_orden else orden, task)  # type: ignore[arg-type]
            case _:
                probs = _probs_y_orden(salidas)[0]
                if probs.shape[1] != 2:
                    raise ModeloEjecutableInvalido(
                        f"el modelo ONNX da {probs.shape[1]} probabilidades por fila; Vigía "
                        "vigila hoy modelos binarios (2)"
                    )
                return probs

    return predict_fn


def _valores_de_salida(salidas: list[Any]) -> np.ndarray:
    """El vector `(n)` de un regresor desde la salida de la sesión.
    Acepta `(n,)` y `(n, 1)` (la forma de `skl2onnx`). Una sola salida con más de
    una columna, una lista de `dict` (`ZipMap`) o más de una salida es un
    clasificador: 422 con «es un clasificador»."""
    if len(salidas) != 1:
        raise ModeloEjecutableInvalido(MENSAJE_ES_CLASIFICADOR)
    salida = salidas[0]
    if not isinstance(salida, np.ndarray) or not np.issubdtype(salida.dtype, np.number):
        raise ModeloEjecutableInvalido(MENSAJE_ES_CLASIFICADOR)
    if salida.ndim == 1:
        return salida.astype(float)
    if salida.ndim == 2 and salida.shape[1] == 1:
        return salida[:, 0].astype(float)
    raise ModeloEjecutableInvalido(MENSAJE_ES_CLASIFICADOR)


def session_predict_value(
    session: ort.InferenceSession, artifact_inputs: list[dict[str, Any]]
) -> PredictFn:
    """`PredictFn` de un regresor ONNX. Devuelve el vector
    `(n,)` en `float64` (aplana el `(n, 1)` de `skl2onnx`). 422 si el grafo es
    de un clasificador (`classlabels_*`, `ZipMap`) o si da más de una columna de
    salida. Misma entrada que `session_predict_proba`: nombres crudos de columna,
    nombres saneados en el feed; síncrona y segura desde un hilo."""
    if getattr(session, _ATRIBUTO_CLASIFICADOR, False):
        raise ModeloEjecutableInvalido(MENSAJE_ES_CLASIFICADOR)
    entradas = {inp.name: inp for inp in session.get_inputs()}

    def predict_fn(X: pd.DataFrame) -> np.ndarray:
        return _valores_de_salida(_correr_sesion(session, entradas, artifact_inputs, X))

    return predict_fn


async def predecir_en_hilo(predict_fn: PredictFn, X: pd.DataFrame) -> np.ndarray:
    """La inferencia ONNX es síncrona y puede tardar; el backend la llama
    desde su bucle de eventos con `await predecir_en_hilo(predict_fn, X)` para no
    bloquearlo. `onnxruntime` admite `run` concurrente sobre una misma sesión."""
    return await asyncio.to_thread(predict_fn, X)


def coincidencia_argmax(
    predict_fn: PredictFn, X: pd.DataFrame, clases_predichas: Any, task: TaskSpec
) -> float:
    """Fracción de filas de `X` en que la clase con mayor probabilidad
    coincide con la columna de predicción de la línea base (`clases_predichas`,
    en texto). El backend la pide sobre una muestra de 200 filas y exige al menos
    0,99; si no, 422 con el orden leído y el declarado. Detecta un `classes` en
    otro orden que el del modelo cuando el grafo no dice el suyo."""
    probs = np.asarray(predict_fn(X), dtype=float)
    obtenidas = np.array(task.claves, dtype=object)[probs.argmax(axis=1)]
    esperadas = np.array([clave_clase(c) for c in clases_predichas], dtype=object)
    if len(esperadas) != len(obtenidas):
        raise ValueError(
            f"hay {len(esperadas)} clases predichas y {len(obtenidas)} filas: "
            "deben ser las mismas. Comprueba que la muestra y la columna de "
            "predicción de la línea base son del mismo lote"
        )
    if len(esperadas) == 0:
        return 1.0
    return float((obtenidas == esperadas).mean())


_TOLERANCIA_VALOR = 1e-4
_MINIMO_COINCIDENCIA_VALOR = 0.99


def coincidencia_valor(
    predict_fn: PredictFn,
    X: pd.DataFrame,
    valores_esperados: Any,
    *,
    tolerancia: float = _TOLERANCIA_VALOR,
) -> float:
    """Fracción de filas de `X` en que la predicción del modelo
    ejecutable coincide con la columna de predicción de la línea base
    (`valores_esperados`): `|y_modelo - y_fichero| <= tolerancia x max(1, |y_fichero|)`.
    El ONNX trabaja en `float32` y el fichero en `float64`, de ahí la tolerancia
    relativa. Es el análogo de `coincidencia_argmax` y la defensa contra subir el
    modelo equivocado."""
    obtenidos = np.asarray(predict_fn(X), dtype=float).reshape(-1)
    esperados = np.asarray(valores_esperados, dtype=float).reshape(-1)
    if len(esperados) != len(obtenidos):
        raise ValueError(
            f"hay {len(esperados)} predicciones de la línea base y {len(obtenidos)} filas: "
            "deben ser las mismas. Comprueba que la muestra y la columna de "
            "predicción de la línea base son del mismo lote"
        )
    if len(esperados) == 0:
        return 1.0
    dentro = np.abs(obtenidos - esperados) <= tolerancia * np.maximum(1.0, np.abs(esperados))
    return float(dentro.mean())


def validar_coincidencia_valor(
    predict_fn: PredictFn,
    X: pd.DataFrame,
    valores_esperados: Any,
    *,
    minimo: float = _MINIMO_COINCIDENCIA_VALOR,
    tolerancia: float = _TOLERANCIA_VALOR,
) -> float:
    """Como `coincidencia_valor`, pero lanza `ModeloEjecutableInvalido`
    (422) con la mediana de la diferencia si coincide menos de `minimo` (0,99)."""
    obtenidos = np.asarray(predict_fn(X), dtype=float).reshape(-1)
    esperados = np.asarray(valores_esperados, dtype=float).reshape(-1)
    fraccion = coincidencia_valor(lambda _x: obtenidos, X, esperados, tolerancia=tolerancia)
    if fraccion < minimo:
        mediana = float(np.median(np.abs(obtenidos - esperados)))
        raise ModeloEjecutableInvalido(
            f"el modelo ONNX no reproduce la predicción de la línea base: solo coincide en el "
            f"{fraccion * 100:.0f} % de {len(esperados)} filas (se pide al menos el "
            f"{minimo * 100:.0f} %) y la diferencia mediana es {mediana:.6g}. Comprueba que es "
            "el modelo de este proyecto y que se exportó con las mismas columnas"
        )
    return fraccion


def validate_and_load(
    path: Path,
    feature_cols: list[str],
    baseline_row: pd.Series,
    task: TaskSpec | None = None,
    *,
    muestra: pd.DataFrame | None = None,
    valores_esperados: Any = None,
) -> tuple[ort.InferenceSession, list[dict[str, Any]]]:
    """ entero: carga, entradas por `feature_cols` y una fila de la línea
    base convertida a los tipos declarados da `(1, 2)` probabilidades, o
    `(1, k)` con `task` multiclase.

    Con `task` de regresión, la fila da un único valor `(1)`, y un
    modelo de clasificación (`classlabels_*`, `ZipMap`, más de una columna) da
    422. Si se pasan `muestra` (200 filas de la línea base) y `valores_esperados`
    (su columna de predicción), comprueba además que el modelo reproduce esos
    valores (`validar_coincidencia_valor`)."""
    if not feature_cols:
        raise ModeloEjecutableInvalido(
            "el mapeo no tiene columnas de características (feature_cols) para "
            "validar el modelo: mapea el dataset de línea base antes de subirlo"
        )
    session = load_session(path)
    artifact_inputs = build_artifact_inputs(session, feature_cols)
    frame_uno = pd.DataFrame([baseline_row])[feature_cols]
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "regression":
            predict_value = session_predict_value(session, artifact_inputs)
            valores = predict_value(frame_uno)
            if valores.shape != (1,):
                raise ModeloEjecutableInvalido(
                    "el modelo ONNX no da un único valor sobre la fila de línea base "
                    f"(da {valores.shape})"
                )
            if muestra is not None and valores_esperados is not None:
                validar_coincidencia_valor(predict_value, muestra[feature_cols], valores_esperados)
        case "binary" | "multiclass":
            predict_fn = session_predict_proba(session, artifact_inputs, task)
            probs = predict_fn(frame_uno)
            k = task.k if task is not None else 2  # binario: 2 con o sin clases declaradas
            if probs.shape != (1, k):
                raise ModeloEjecutableInvalido(
                    f"el modelo ONNX no da (1, {k}) probabilidades sobre la fila de línea base "
                    f"(da {probs.shape})"
                )
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    return session, artifact_inputs
