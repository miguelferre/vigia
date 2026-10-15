"""Alta y carga del artefacto del modelo ejecutable.

`upload_artifact` guarda el fichero en la carpeta de datos del proyecto
(fuera del repo, mismo patrón que `ingest.register_upload`), lo valida (ONNX
con `core.predict_onnx`; pickle o joblib solo con `confirmacion_pickle`) y
deja la versión en `model_kind="executable"`. `get_predict_fn` reconstruye el
`PredictFn` para explicabilidad (`services/explain.py`), recomprobando el
sha256 en cada carga si el artefacto es un pickle: un fichero pickle
solo se abre con `joblib.load` cuando `artifact_kind == "pickle"`, nunca en
la ruta por defecto (ONNX).
"""

from __future__ import annotations

import hashlib
import io
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as TiempoAgotado
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import HTTPException
from sklearn.base import is_classifier, is_regressor
from sqlmodel import Session, select

from vigia.app.events import Actor, record_event
from vigia.app.models import Batch, Dataset, ModelVersion, Project, Record, now_iso
from vigia.app.services import tarea as tarea_service
from vigia.app.services.onnx_entradas_double import mensaje_si_entradas_double
from vigia.core.predict_onnx import (
    ModeloEjecutableInvalido,
    PredictFn,
    cast_frame_to_kinds,
    load_session,
    orden_clases_onnx,
    session_predict_proba,
    session_predict_value,
    validar_coincidencia_valor,
    validate_and_load,
)
from vigia.core.schema import ColumnMapping, DatosNoValidos, TaskSpec, clave_clase

__all__ = [
    "AVISO_PICKLE",
    "AVISO_SIN_COMPROBAR_VALORES",
    "AVISO_TIPOS_ANTIGUOS",
    "FECHA_CORRECCION_TIPOS",
    "MAX_ARTIFACT_BYTES",
    "aviso_tipos_antiguos",
    "get_predict_fn",
    "upload_artifact",
]

MAX_ARTIFACT_BYTES = 200 * 1024 * 1024


class _ErrorSinReintento(ModeloEjecutableInvalido):
    """Error de validación que no se arregla reintentando con otra lectura de
    tipos: tiempo agotado o clases distintas a las del proyecto."""

# filas de la línea base con las que se comprueba que el argmax de las
# probabilidades del modelo coincide con la predicción guardada, y la fracción
# mínima de coincidencias.
FILAS_COMPROBACION_ARGMAX = 200
FRACCION_MINIMA_ARGMAX = 0.99
# en regresión el modelo debe reproducir la predicción de la línea base
# (`|ŷ_modelo - ŷ_fichero| <= 1e-4 x max(1, |ŷ_fichero|)` en el 99 % de 200 filas).
FILAS_COMPROBACION_VALOR = 200
MENSAJE_PICKLE_ES_CLASIFICADOR = (
    "el modelo es un clasificador (tiene predict_proba) y este proyecto es de regresión: sube "
    "un modelo que devuelva un único número por fila"
)
MENSAJE_PICKLE_ES_REGRESOR = (
    "el modelo es un regresor (devuelve un único número por fila, sin predict_proba) y este "
    "proyecto es de clasificación: sube un modelo clasificador o crea un proyecto de regresión"
)
# tiempo máximo de la inferencia de validación; pasado, 422 y el
# hilo de la petición queda libre (el trabajo del modelo no se puede matar).
SEGUNDOS_MAXIMOS_INFERENCIA = 60.0
MENSAJE_NO_PREDICE = (
    "el modelo no ha podido predecir con las columnas del mapeo: comprueba que "
    "cada columna llega con el tipo (texto o número) con el que se entrenó"
)
AVISO_PICKLE = "un fichero pickle ejecuta código al abrirse: súbelo solo si lo has generado tú"
# sin variables guardadas en la línea base (`store_features=False`) no hay con qué
# comprobar que el modelo de una regresión reproduce sus predicciones, y se acepta sin esa
# comprobación; la persona lo sabe por este aviso.
AVISO_SIN_COMPROBAR_VALORES = (
    "la línea base no guarda variables: no se ha comprobado que el modelo reproduzca sus "
    "predicciones"
)

# los pickle subidos antes del 2026-09-29 guardaron
# `artifact_inputs_json` con enteros en columnas que eran continuas, y la
# explicación los redondea. Se compara con `artifact_uploaded_at` (ISO 8601, así
# que la comparación de cadenas es la de fechas).
FECHA_CORRECCION_TIPOS = "2026-09-29"
AVISO_TIPOS_ANTIGUOS = (
    "subido antes de la corrección de tipos: vuelve a subirlo para que la "
    "explicación no redondee"
)


def aviso_tipos_antiguos(artifact_kind: str | None, artifact_uploaded_at: str | None) -> str | None:
    """Aviso para un artefacto pickle o joblib subido antes del
    2026-09-29; `None` en cualquier otro caso (ONNX, sin artefacto, sin fecha
    o subido después)."""
    if artifact_kind != "pickle" or not artifact_uploaded_at:
        return None
    if artifact_uploaded_at < FECHA_CORRECCION_TIPOS:
        return AVISO_TIPOS_ANTIGUOS
    return None


def _safe_filename(filename: str) -> str:
    nombre = Path(filename).name or "modelo"
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in nombre)


def _mapping_batch_for_version(session: Session, version: ModelVersion) -> tuple[Batch, Dataset]:
    """El lote y el dataset cuyo mapeo se usa para validar: el de la
    línea base congelada si la hay, si no el lote más reciente de la
    versión que tenga mapeo."""
    if version.baseline_batch_id is not None:
        batch = session.get(Batch, version.baseline_batch_id)
        if batch is not None and batch.dataset_id is not None:
            dataset = session.get(Dataset, batch.dataset_id)
            if dataset is not None and dataset.mapping_json:
                return batch, dataset
    lotes = session.exec(
        select(Batch)
        .where(Batch.model_version_id == version.id)
        .order_by(Batch.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    for batch in lotes:
        if batch.dataset_id is None:
            continue
        dataset = session.get(Dataset, batch.dataset_id)
        if dataset is not None and dataset.mapping_json:
            return batch, dataset
    raise HTTPException(
        422,
        "no hay ningún lote con mapeo de columnas para esta versión: ingiere y "
        "mapea la línea base antes de subir el modelo",
    )


def _baseline_row(session: Session, batch: Batch) -> pd.Series:
    """Una fila real del lote para validar el modelo: el fichero en
    bruto del dataset se purga tras ingerir, así que la fila sale de
    `Record.features_json` (exige `project.store_features=true`, igual que
    la explicabilidad, `services/explain.py:_feature_frame`)."""
    fila = session.exec(
        select(Record)
        .where(Record.batch_id == batch.id)
        .order_by(Record.seq)  # type: ignore[arg-type]
        .limit(1)
    ).first()
    if fila is None or fila.features_json is None:
        raise HTTPException(
            422,
            "no hay features guardadas en el lote de línea base para validar el "
            "modelo: actívalas (store_features) y vuelve a ingerir",
        )
    return pd.Series(fila.features_json)


def _artifact_inputs_from_baseline(
    feature_cols: list[str], baseline_row: pd.Series
) -> list[dict[str, Any]]:
    """`artifact_inputs_json` para un pickle: sin entradas ONNX declaradas,
    el tipo se infiere del valor de la fila de línea base."""
    resultado = []
    for nombre in feature_cols:
        valor = baseline_row.get(nombre)
        es_numerico = isinstance(valor, (int, float, np.integer, np.floating)) and not isinstance(
            valor, bool
        )
        resultado.append(
            {
                "name": nombre,
                "type": type(valor).__name__,
                "kind": "numerica" if es_numerico else "categorica",
            }
        )
    return resultado


def _columnas_no_enteras(session: Session, batch: Batch, limite: int = 500) -> set[str]:
    """Columnas con algún valor numérico no entero en las primeras filas del
    lote. Una columna continua cuya fila 0 es entera (edad 70) no debe
    tratarse como entera: se redondearían las perturbaciones de SHAP y LIME."""
    filas = session.exec(
        select(Record)
        .where(Record.batch_id == batch.id)
        .order_by(Record.seq)  # type: ignore[arg-type]
        .limit(limite)
    ).all()
    resultado: set[str] = set()
    for fila in filas:
        for nombre, valor in (fila.features_json or {}).items():
            if (
                isinstance(valor, (int, float, np.integer, np.floating))
                and not isinstance(valor, bool)
                and not float(valor).is_integer()
            ):
                resultado.add(nombre)
    return resultado


def _columnas_categoricas_del_modelo(modelo: Any) -> set[str]:
    """Columnas que el modelo sklearn espera como texto: las que un
    `OneHotEncoder` u `OrdinalEncoder` ajustado con categorías de texto recibe
    dentro de un `ColumnTransformer`, buscado en `Pipeline` anidados. Vacío si
    no se puede saber: entonces manda el tipo de la línea base."""
    encontradas: set[str] = set()

    def _es_texto(cat: Any) -> bool:
        return any(isinstance(v, str) for v in np.asarray(cat, dtype=object).ravel()[:50])

    def _hoja(transformador: Any) -> Any:
        while hasattr(transformador, "steps") and transformador.steps:
            transformador = transformador.steps[-1][1]
        return transformador

    def _recorrer(nodo: Any) -> None:
        for _n, paso in getattr(nodo, "steps", None) or []:
            _recorrer(paso)
        for _n, trans, cols in getattr(nodo, "transformers_", None) or []:
            _recorrer(trans)
            categorias = getattr(_hoja(trans), "categories_", None)
            if categorias is None or not isinstance(cols, (list, tuple)):
                continue
            for col, cat in zip(cols, categorias, strict=False):
                if isinstance(col, str) and _es_texto(cat):
                    encontradas.add(col)

    try:
        _recorrer(modelo)
    except Exception:  # noqa: BLE001 (modelo ajeno: si no se puede leer, manda la línea base)
        return set()
    return encontradas


def _inputs_pickle(
    feature_cols: list[str],
    baseline_row: pd.Series,
    modelo: Any,
    *,
    enteros_a_texto: bool = False,
    no_enteras: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Entradas de un pickle con los tipos que el modelo espera: lo
    que el modelo declara como texto manda sobre el tipo Python del valor de
    la línea base (`admission_type_id` llega como entero y el modelo lo
    espera como texto). `enteros_a_texto` es el último recurso si el modelo
    no declara sus categorías."""
    declaradas = _columnas_categoricas_del_modelo(modelo)
    entradas = _artifact_inputs_from_baseline(feature_cols, baseline_row)
    for entrada in entradas:
        if entrada["name"] in (no_enteras or set()) and entrada["kind"] == "numerica":
            entrada["type"] = "float"
        entero = "int" in entrada["type"] and entrada["kind"] == "numerica"
        if entrada["name"] in declaradas or (enteros_a_texto and entero):
            entrada["kind"] = "categorica"
            entrada["type"] = "str"
    return entradas


def _con_limite(funcion: Any, *args: Any, segundos: float | None = None) -> Any:
    """corre la inferencia de validación en un hilo propio con un
    tiempo máximo. Pasado el tiempo, error en español y el hilo de ejecución de la petición
    queda libre; el trabajo del modelo ya no se espera (no se puede matar)."""
    segundos = SEGUNDOS_MAXIMOS_INFERENCIA if segundos is None else segundos
    ejecutor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vigia-inferencia")
    try:
        return ejecutor.submit(funcion, *args).result(timeout=segundos)
    except TiempoAgotado as exc:
        raise _ErrorSinReintento(
            f"El modelo tarda más de {int(segundos)} segundos en predecir una muestra de la "
            "línea base: Vigía no lo carga. Comprueba que es el modelo correcto y que no "
            "tiene operadores que no terminan"
        ) from exc
    finally:
        ejecutor.shutdown(wait=False, cancel_futures=True)


def _texto_orden(clases: Any) -> str:
    if not clases:
        return "no se pudo leer"
    return "(" + ", ".join(str(c) for c in clases) + ")"


def _reordenar_a_task(probs: np.ndarray, orden_modelo: list[str], task: TaskSpec) -> np.ndarray:
    """reordena las columnas de `probs` del orden del modelo al de
    `task.classes`. Si no son las mismas clases, error con los dos órdenes."""
    claves = [clave_clase(c) for c in orden_modelo]
    if sorted(claves) != sorted(task.claves):
        raise _ErrorSinReintento(
            "Las clases del modelo no son las del proyecto. Orden de clases que lee Vigía en el "
            f"modelo: {_texto_orden(claves)}. Orden declarado en el proyecto: "
            f"{_texto_orden(task.claves)}."
        )
    if claves == list(task.claves):
        return probs
    return probs[:, [claves.index(c) for c in task.claves]]


def _predict_fn_sklearn(
    modelo: Any, artifact_inputs: list[dict[str, Any]], task: TaskSpec | None = None
) -> PredictFn:
    columnas = [i["name"] for i in artifact_inputs]
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "regression":
            # `PredictFn` de forma `(n,)`, con `predict`.
            def predict_valor(X: pd.DataFrame) -> np.ndarray:
                frame = cast_frame_to_kinds(X, artifact_inputs)
                try:
                    return np.asarray(modelo.predict(frame[columnas]), dtype=float).reshape(-1)
                except Exception as exc:
                    raise ModeloEjecutableInvalido(MENSAJE_NO_PREDICE) from exc

            return predict_valor
        case "binary":
            multiclase = False
        case "multiclass":
            multiclase = True
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    orden_modelo = (
        [str(c) for c in getattr(modelo, "classes_", [])] if multiclase else []
    )

    def predict_fn(X: pd.DataFrame) -> np.ndarray:
        frame = cast_frame_to_kinds(X, artifact_inputs)
        try:
            probs = np.asarray(modelo.predict_proba(frame[columnas]))
        except Exception as exc:
            raise ModeloEjecutableInvalido(MENSAJE_NO_PREDICE) from exc
        if multiclase and orden_modelo and probs.ndim == 2 and probs.shape[1] == len(orden_modelo):
            return _reordenar_a_task(probs, orden_modelo, task)  # type: ignore[arg-type]
        return probs

    return predict_fn


def _tarea_del_modelo(session: Session, version: ModelVersion, dataset: Dataset) -> TaskSpec:
    """`TaskSpec` del proyecto con el mapeo del dataset de validación."""
    project = session.get(Project, version.project_id)
    if project is None:
        raise HTTPException(404, "el modelo del proyecto ya no existe")
    try:
        return tarea_service.tarea_del_proyecto(project, ColumnMapping(**(dataset.mapping_json or {})))
    except DatosNoValidos as exc:
        raise HTTPException(422, str(exc)) from exc


def _comprobar_argmax(
    session: Session,
    batch: Batch,
    feature_cols: list[str],
    predict_fn: PredictFn,
    task: TaskSpec,
    orden_leido: list[str] | None,
) -> None:
    """la clase de mayor probabilidad del modelo coincide con la predicción
    guardada en al menos el 99 % de las primeras 200 filas de la línea base. Si
    no, `ModeloEjecutableInvalido` con el orden leído y el declarado (el fallo
    silencioso más caro: columnas de probabilidad cambiadas de orden)."""
    filas = session.exec(
        select(Record.features_json, Record.prediction_class)
        .where(Record.batch_id == batch.id, Record.features_json.is_not(None))  # type: ignore[union-attr]
        .order_by(Record.seq)  # type: ignore[arg-type]
        .limit(FILAS_COMPROBACION_ARGMAX)
    ).all()
    if not filas:
        return
    faltan = [c for c in feature_cols if any(c not in f for f, _ in filas)]
    if faltan:
        raise ModeloEjecutableInvalido(
            "Las filas de la línea base no traen todas las variables del mapeo: faltan "
            + ", ".join(faltan[:10])
            + ". Vuelve a ingerir la línea base con el mismo mapeo de variables."
        )
    X = pd.DataFrame([f for f, _ in filas])[feature_cols]
    probs = np.asarray(_con_limite(predict_fn, X))
    if probs.ndim != 2 or probs.shape != (len(X), task.k):
        columnas = probs.shape[1] if probs.ndim == 2 else probs.shape
        raise ModeloEjecutableInvalido(
            f"El modelo da {columnas} probabilidades por fila y el proyecto declara {task.k} "
            f"clases. Orden de clases que lee Vigía en el modelo: {_texto_orden(orden_leido)}. "
            f"Orden declarado en el proyecto: {_texto_orden(task.claves)}."
        )
    predichas = [task.claves[i] for i in probs.argmax(axis=1)]
    pares = [(p, real) for p, (_f, real) in zip(predichas, filas, strict=True) if real is not None]
    if not pares:
        return
    tasa = sum(1 for p, real in pares if p == real) / len(pares)
    if tasa < FRACCION_MINIMA_ARGMAX:
        raise ModeloEjecutableInvalido(
            "Las probabilidades del modelo no coinciden con las predicciones de la línea base: "
            f"la clase de mayor probabilidad coincide en el {tasa:.0%} de {len(pares)} filas y "
            f"hace falta el {FRACCION_MINIMA_ARGMAX:.0%}. Orden de clases que lee Vigía en el "
            f"modelo: {_texto_orden(orden_leido)}. Orden declarado en el proyecto: "
            f"{_texto_orden(task.claves)}. Si el orden es otro, declara las clases en el orden "
            "del modelo."
        )


def _muestra_valores_linea_base(
    session: Session, batch: Batch, feature_cols: list[str]
) -> tuple[pd.DataFrame | None, np.ndarray | None]:
    """las primeras 200 filas de la línea base con sus variables y su
    `prediction_value`, para comprobar que el modelo reproduce la predicción guardada.
    `(None, None)` si la línea base no guarda variables (no hay nada con qué comprobar)."""
    filas = session.exec(
        select(Record.features_json, Record.prediction_value)
        .where(
            Record.batch_id == batch.id,
            Record.features_json.is_not(None),  # type: ignore[union-attr]
            Record.prediction_value.is_not(None),  # type: ignore[union-attr]
        )
        .order_by(Record.seq)  # type: ignore[arg-type]
        .limit(FILAS_COMPROBACION_VALOR)
    ).all()
    if not filas:
        return None, None
    faltan = [c for c in feature_cols if any(c not in f for f, _ in filas)]
    if faltan:
        raise ModeloEjecutableInvalido(
            "Las filas de la línea base no traen todas las variables del mapeo: faltan "
            + ", ".join(faltan[:10])
            + ". Vuelve a ingerir la línea base con el mismo mapeo de variables."
        )
    muestra = pd.DataFrame([f for f, _ in filas])[feature_cols]
    return muestra, np.array([v for _f, v in filas], dtype=float)


def _tipo_sklearn(modelo: Any, comprueba: Any) -> bool:
    """`is_classifier` / `is_regressor` de scikit-learn; un objeto que no es un estimador
    (cualquier clase con `predict_proba`) no lo es y no rompe la comprobación."""
    try:
        return bool(comprueba(modelo))
    except Exception:  # noqa: BLE001
        return False


def _comprobar_pickle_de_regresion(modelo: Any) -> None:
    """un clasificador en un proyecto de regresión da 422 (tiene `predict_proba`)."""
    if _tipo_sklearn(modelo, is_classifier) or hasattr(modelo, "predict_proba"):
        raise ModeloEjecutableInvalido(MENSAJE_PICKLE_ES_CLASIFICADOR)


def _comprobar_pickle_de_clasificacion(modelo: Any) -> None:
    """un regresor en un proyecto de clasificación da 422."""
    if _tipo_sklearn(modelo, is_regressor) and not hasattr(modelo, "predict_proba"):
        raise ModeloEjecutableInvalido(MENSAJE_PICKLE_ES_REGRESOR)


_CERROJOS_SUBIDA: dict[int, threading.Lock] = {}
_CERROJOS_SUBIDA_GUARDA = threading.Lock()


def _cerrojo_de_subida(version_id: int | None) -> threading.Lock:
    """Un cerrojo por versión: dos subidas de la misma versión se
    validan y se activan una detrás de otra."""
    with _CERROJOS_SUBIDA_GUARDA:
        return _CERROJOS_SUBIDA.setdefault(version_id or 0, threading.Lock())


def upload_artifact(
    session: Session,
    version: ModelVersion,
    *,
    file_bytes: bytes,
    filename: str,
    artifact_kind: str,
    confirmacion_pickle: bool,
    data_dir: Path,
    actor: Actor,
    correlation_id: str | None = None,
    job_id: int | None = None,
    bus: Any | None = None,
) -> tuple[ModelVersion, list[str]]:
    """Sube el artefacto de una versión; las subidas de la misma versión se serializan.
    El detalle está en `_subir_artefacto`."""
    with _cerrojo_de_subida(version.id):
        return _subir_artefacto(
            session,
            version,
            file_bytes=file_bytes,
            filename=filename,
            artifact_kind=artifact_kind,
            confirmacion_pickle=confirmacion_pickle,
            data_dir=data_dir,
            actor=actor,
            correlation_id=correlation_id,
            job_id=job_id,
            bus=bus,
        )


def _subir_artefacto(
    session: Session,
    version: ModelVersion,
    *,
    file_bytes: bytes,
    filename: str,
    artifact_kind: str,
    confirmacion_pickle: bool,
    data_dir: Path,
    actor: Actor,
    correlation_id: str | None = None,
    job_id: int | None = None,
    bus: Any | None = None,
) -> tuple[ModelVersion, list[str]]:
    """Guarda, valida y activa el artefacto. Devuelve la versión
    actualizada y los avisos a mostrar (el de pickle, si aplica).

    El fichero se guarda en un temporal junto al definitivo (para poder abrirlo
    con `onnxruntime`/`joblib` desde disco); si la validación falla se borra el
    temporal, el artefacto vigente sigue intacto y no queda ningún resto en
    `ModelVersion` (todo o nada).
    """
    if artifact_kind not in ("onnx", "pickle"):
        raise HTTPException(422, "artifact_kind debe ser 'onnx' o 'pickle'")
    if len(file_bytes) > MAX_ARTIFACT_BYTES:
        raise HTTPException(422, "el fichero supera el límite de 200 MB")
    if artifact_kind == "pickle" and not confirmacion_pickle:
        # sin confirmación, 422 SIN escribir ni cargar nada (nunca se
        # llega a `pickle.load`/`joblib.load`).
        raise HTTPException(
            422,
            "confirmacion_pickle debe ser true para subir un fichero pickle o joblib: "
            + AVISO_PICKLE,
        )

    batch, dataset = _mapping_batch_for_version(session, version)
    feature_cols = list((dataset.mapping_json or {}).get("feature_cols") or [])
    baseline_row = _baseline_row(session, batch)
    no_enteras = _columnas_no_enteras(session, batch)
    task = _tarea_del_modelo(session, version, dataset)

    nombre_seguro = _safe_filename(filename)
    carpeta = Path(data_dir) / "artifacts" / str(version.project_id)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{version.id}_{nombre_seguro}"
    # El fichero nuevo se valida en un temporal y solo sustituye al vigente si es válido.
    # Nombre único por subida: ninguna otra petición reescribe este fichero
    # entre la validación y el `os.replace`.
    temporal = carpeta / f"{version.id}_{nombre_seguro}.{uuid.uuid4().hex}.nuevo"
    temporal.write_bytes(file_bytes)
    sha256 = hashlib.sha256(file_bytes).hexdigest()

    sin_comprobar_valores = False
    try:
        if artifact_kind == "onnx":
            muestra_valores: pd.DataFrame | None = None
            esperados_valores: np.ndarray | None = None
            match task.task_type:
                case "regression":
                    muestra_valores, esperados_valores = _muestra_valores_linea_base(
                        session, batch, feature_cols
                    )
                    sin_comprobar_valores = muestra_valores is None
                case "binary" | "multiclass":
                    pass
                case _:
                    raise ValueError(f"tipo de tarea no reconocido: {task.task_type!r}")
            session_validacion, artifact_inputs = validate_and_load(
                temporal,
                feature_cols,
                baseline_row,
                task,
                muestra=muestra_valores,
                valores_esperados=esperados_valores,
            )
            match task.task_type:
                case "multiclass":
                    _comprobar_argmax(
                        session,
                        batch,
                        feature_cols,
                        session_predict_proba(session_validacion, artifact_inputs, task),
                        task,
                        orden_clases_onnx(temporal),
                    )
                case "binary" | "regression":
                    pass
                case _:
                    raise ValueError(f"tipo de tarea no reconocido: {task.task_type!r}")
        else:
            modelo = joblib.load(temporal)
            match task.task_type:
                case "regression":
                    _comprobar_pickle_de_regresion(modelo)
                case "binary" | "multiclass":
                    _comprobar_pickle_de_clasificacion(modelo)
                case _:
                    raise ValueError(f"tipo de tarea no reconocido: {task.task_type!r}")
            frame_uno = pd.DataFrame([baseline_row])[feature_cols]
            try:
                artifact_inputs = _inputs_pickle(
                    feature_cols, baseline_row, modelo, no_enteras=no_enteras
                )
                probs = np.asarray(
                    _con_limite(_predict_fn_sklearn(modelo, artifact_inputs, task), frame_uno)
                )
            except _ErrorSinReintento:
                raise
            except ModeloEjecutableInvalido:
                # Último recurso: el modelo no declara sus categorías y una
                # columna entera en la línea base es en realidad un código.
                artifact_inputs = _inputs_pickle(
                    feature_cols, baseline_row, modelo, enteros_a_texto=True, no_enteras=no_enteras
                )
                probs = np.asarray(
                    _con_limite(_predict_fn_sklearn(modelo, artifact_inputs, task), frame_uno)
                )
            match task.task_type:
                case "regression":
                    if probs.shape != (1,):
                        raise ModeloEjecutableInvalido(
                            f"el modelo no da un único valor sobre la fila de línea base (da {probs.shape})"
                        )
                    muestra_valores, esperados_valores = _muestra_valores_linea_base(
                        session, batch, feature_cols
                    )
                    if muestra_valores is not None:
                        validar_coincidencia_valor(
                            _predict_fn_sklearn(modelo, artifact_inputs, task),
                            muestra_valores,
                            esperados_valores,
                        )
                    else:
                        sin_comprobar_valores = True
                case "binary" | "multiclass":
                    if probs.shape != (1, task.k):
                        raise ModeloEjecutableInvalido(
                            f"el modelo no da (1, {task.k}) probabilidades sobre la fila de línea "
                            f"base (da {probs.shape})"
                        )
                    match task.task_type:
                        case "multiclass":
                            _comprobar_argmax(
                                session,
                                batch,
                                feature_cols,
                                _predict_fn_sklearn(modelo, artifact_inputs, task),
                                task,
                                [str(c) for c in getattr(modelo, "classes_", [])] or None,
                            )
                        case _:
                            pass
                case _:
                    raise ValueError(f"tipo de tarea no reconocido: {task.task_type!r}")
    except ModeloEjecutableInvalido as exc:
        propio = mensaje_si_entradas_double(temporal) if artifact_kind == "onnx" else None
        temporal.unlink(missing_ok=True)
        raise HTTPException(422, propio or str(exc)) from exc
    except HTTPException:
        temporal.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporal.unlink(missing_ok=True)
        raise HTTPException(
            422,
            "el fichero no se ha podido cargar como modelo: comprueba que es un "
            "ONNX o un pickle de scikit-learn con predict_proba"
        ) from exc

    anterior = version.artifact_path
    try:
        os.replace(temporal, ruta)
    except OSError as exc:
        temporal.unlink(missing_ok=True)
        raise HTTPException(
            409, "no se ha podido guardar el modelo nuevo: ciérralo en otros programas y súbelo otra vez"
        ) from exc
    if anterior and Path(anterior) != ruta:
        Path(anterior).unlink(missing_ok=True)

    version.artifact_path = str(ruta)
    version.artifact_kind = artifact_kind
    version.artifact_sha256 = sha256
    version.artifact_inputs_json = artifact_inputs
    version.artifact_uploaded_at = now_iso()
    version.model_kind = "executable"
    session.add(version)
    session.flush()

    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="version.artefacto_subido",
        object_type="model_version",
        object_id=version.id,
        project_id=version.project_id,
        after={"artifact_kind": artifact_kind},
        correlation_id=correlation_id,
        job_id=job_id,
        bus=bus,
    )
    session.commit()
    session.refresh(version)

    avisos = [AVISO_PICKLE] if artifact_kind == "pickle" else []
    if sin_comprobar_valores:
        avisos.append(AVISO_SIN_COMPROBAR_VALORES)
    return version, avisos


def get_predict_fn(version: ModelVersion, task: TaskSpec | None = None) -> PredictFn:
    """`PredictFn` de la versión activa para explicabilidad.

    `task`: en multiclase la función devuelve `(n, k)` en el orden de
    `task.classes`, reordenando las columnas si el modelo da otro orden.
    En regresión devuelve `(n,)`, el valor predicho en la unidad de la salida.

    Pickle: recomprueba el sha256 del fichero en disco contra
    `artifact_sha256` ANTES de `joblib.load`; si difiere, 409 sin
    ejecutar nada.
    """
    if not version.artifact_path or not version.artifact_kind:
        raise HTTPException(
            422,
            "esta versión no tiene un artefacto de modelo válido: sube el modelo "
            "en ONNX antes de pedir una explicación",
        )
    ruta = Path(version.artifact_path)
    if not ruta.exists():
        raise HTTPException(
            422, "el artefacto del modelo ha desaparecido del disco: vuelve a subirlo"
        )
    artifact_inputs = version.artifact_inputs_json or []

    if version.artifact_kind == "onnx":
        # como con el pickle, el hash del fichero se recomprueba antes de abrirlo.
        # Se leen los bytes una vez y se abren esos mismos bytes: sin ventana entre hash y carga.
        contenido_onnx = ruta.read_bytes()
        if hashlib.sha256(contenido_onnx).hexdigest() != version.artifact_sha256:
            raise HTTPException(
                409, "el fichero del modelo ha cambiado desde que se subió: vuelve a subirlo"
            )
        session_onnx = load_session(contenido_onnx)
        tipo = task.task_type if task is not None else "binary"
        match tipo:
            case "binary" | "multiclass":
                return session_predict_proba(session_onnx, artifact_inputs, task)
            case "regression":
                # `(n,)` en la unidad de la salida del modelo.
                return session_predict_value(session_onnx, artifact_inputs)
            case _:
                raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")

    contenido = ruta.read_bytes()
    if hashlib.sha256(contenido).hexdigest() != version.artifact_sha256:
        raise HTTPException(
            409, "el fichero del modelo ha cambiado desde que se subió: vuelve a subirlo"
        )
    modelo = joblib.load(io.BytesIO(contenido))
    return _predict_fn_sklearn(modelo, artifact_inputs, task)
