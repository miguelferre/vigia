"""Servicio de explicabilidad sobre modelos ejecutables.

Dos `model_kind` explicables: `sim_logistic` (el simulador; reconstruye el
frame de 41 columnas con `vigia.core.explain.harness_feature_frame` y llama a
`vigia.sim.model.predict_proba`) y `executable` (un modelo subido en ONNX o
pickle; el frame se construye SOLO con las columnas de
`ModelVersion.artifact_inputs_json`, nunca con las 41 de reuma, y el
`PredictFn` sale de `vigia.app.services.model_registry.get_predict_fn`). En
cualquier otro caso, o si el proyecto ingirió sin `store_features`, no hay
features que explicar: 409.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from fastapi import HTTPException
from sqlalchemy.orm import object_session
from sqlmodel import Session, select

from vigia.app.bus import EventBus
from vigia.app.errores import no_encontrado
from vigia.app.events import ACTOR_MODELO, record_event
from vigia.app.jobs import JobContext
from vigia.app.models import (
    Batch,
    Evaluation,
    Explanation,
    Measurement,
    ModelVersion,
    Project,
    Record,
)
from vigia.app.services import model_registry
from vigia.app.services import tarea as tarea_service
from vigia.core import explain as core_explain
from vigia.core.predict_onnx import PredictFn
from vigia.core.schema import TaskSpec, clave_clase
from vigia.sim.model import predict_proba

__all__ = [
    "check_explainable",
    "check_features_available",
    "explain_global",
    "explain_local",
    "explanation_to_dict",
    "explanations_summary",
    "find_row",
    "get_baseline_batch",
    "maybe_auto_explain",
    "resolve_batch",
    "validar_clase",
]

_KINDS_GLOBALES = ("global_permutation", "global_shap")

# SHAP global explica a lo sumo estas filas del lote: una muestra con semilla
# fija, para que el coste de la petición no crezca con el tamaño del lote.
MAX_FILAS_SHAP = 1000

# Mismo truncado que `core.explain.explain_stability_ndcg`, para
# que la comparación de rankings de la tarjeta no diga algo distinto de la
# estabilidad ya calculada con ese `p`.
_TOP_N_COMPARADO = core_explain.P_TRUNCADO


def check_explainable(version: ModelVersion) -> None:
    """409 si la versión no tiene con qué explicar.

    `sim_logistic` siempre puede (el simulador). `executable` solo si ya
    tiene un artefacto válido (`artifact_sha256` fijado tras
    `model_registry.upload_artifact`); si no, el motivo pide subir el
    modelo. Cualquier otro `model_kind` (`external_files` sin artefacto
    subido, o un `libre` sin ejecutable) cae en el mismo 409.

    Se llama tanto desde el router (para devolver el 409 antes de encolar el
    trabajo, no dentro de él) como desde `explain_global`/`explain_local`.
    """
    if version.model_kind == "sim_logistic":
        return
    if version.model_kind == "executable" and version.artifact_sha256:
        return
    raise HTTPException(
        409,
        "explicabilidad no disponible: sube el modelo en ONNX (o pickle, con "
        "confirmación) antes de pedir una explicación",
    )



def _batch_records(session: Session, batch: Batch) -> list[Record]:
    return list(
        session.exec(
            select(Record).where(Record.batch_id == batch.id).order_by(Record.seq)  # type: ignore[arg-type]
        ).all()
    )


def _feature_frame(records: list[Record], version: ModelVersion) -> pd.DataFrame:
    """Reconstruye el frame de features desde `Record.features_json`.

    `sim_logistic`: `harness_feature_frame` castea a float y admite nombres
    crudos o planos, así que basta con volcar los dicts guardados (ya en
    nombres planos), y da las 41 columnas de reuma.

    `executable`: el frame se construye SOLO con las columnas
    de `version.artifact_inputs_json` (las de `mapping.feature_cols` en el
    alta del artefacto), nunca con las 41 de reuma; sin casteo aquí, con las
    columnas crudas (SHAP Kernel las acepta tal cual) y el casteo a
    los tipos declarados lo hace el `PredictFn` de `model_registry`.
    """
    if not records or any(r.features_json is None for r in records):
        raise HTTPException(
            409,
            "no hay variables guardadas para este lote: activa «Guardar las variables de entrada de cada registro» "
            "en la pestaña Configuración del modelo y vuelve a ingerir el lote",
        )
    crudo = pd.DataFrame([r.features_json for r in records])
    if version.model_kind == "executable":
        columnas = [i["name"] for i in (version.artifact_inputs_json or [])]
        faltan = [c for c in columnas if c not in crudo.columns]
        if faltan:
            raise HTTPException(
                409,
                "el lote no tiene guardadas las columnas que el modelo necesita: "
                + ", ".join(faltan),
            )
        return crudo[columnas]
    return core_explain.harness_feature_frame(crudo)


def _predict_fn_for(version: ModelVersion, task: TaskSpec | None = None) -> PredictFn:
    """El `PredictFn` de la versión: el simulador para `sim_logistic`, el
    artefacto subido (ONNX o pickle) para `executable`. En multiclase devuelve `(n, k)` en el orden de `task.classes`."""
    if version.model_kind == "executable":
        return model_registry.get_predict_fn(version, task)
    return predict_proba


def _categorical_cols_for(version: ModelVersion) -> list[str] | None:
    """Columnas categóricas del artefacto, para `local_lime`.
    `None` para `sim_logistic` (las 41 columnas de reuma son numéricas)."""
    if version.model_kind != "executable":
        return None
    return [
        i["name"] for i in (version.artifact_inputs_json or []) if i.get("kind") == "categorica"
    ]


def _label_array(records: list[Record]) -> np.ndarray | None:
    if not records or all(r.label is None for r in records):
        return None
    return np.array([np.nan if r.label is None else r.label for r in records], dtype=float)


def _valor_array(records: list[Record]) -> np.ndarray | None:
    """`y` de una regresión: el valor real continuo, NaN sin etiqueta; la
    permutación puntúa por aumento del RMSE sobre él. `label` sería el 0/1 de pertenencia."""
    if not records or all(r.label_value is None for r in records):
        return None
    return np.array([np.nan if r.label_value is None else r.label_value for r in records], dtype=float)


def validar_clase(session: Session, version: ModelVersion, clase: int | str | None) -> None:
    """422 si se pide una clase que no está en `classes_json` del proyecto
    (o el proyecto es binario y no tiene selector de clase). una regresión
    tampoco tiene clases que elegir."""
    if clase is None:
        return
    project = session.get(Project, version.project_id)
    clases = tarea_service.clases_del_proyecto(project) if project is not None else None
    tipo = project.task_type if project is not None else "binary"
    match tipo:
        case "multiclass":
            if not clases:
                raise HTTPException(
                    422,
                    "el proyecto aún no tiene clases fijadas: se fijan al congelar la línea base. "
                    "Congélala y pide la clase de nuevo",
                )
        case "binary":
            raise HTTPException(
                422,
                "este modelo no tiene clases que elegir: la explicación por clase es de los "
                "proyectos multiclase",
            )
        case "regression":
            raise HTTPException(
                422,
                "este modelo es de regresión y no tiene clases que elegir: la explicación se "
                "da en la unidad de la salida del modelo",
            )
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    if clave_clase(clase) not in {clave_clase(c) for c in clases}:
        raise HTTPException(
            422,
            f"la clase {clase!r} no está entre las clases del proyecto ("
            f"{', '.join(str(c) for c in clases)}): elige una de ellas",
        )


def _tarea_de_explicacion(session: Session, version: ModelVersion, batch: Batch) -> TaskSpec | None:
    """`TaskSpec` multiclase o de regresión del proyecto con el mapeo del lote, o `None`
    en binario (el motor se llama entonces como siempre)."""
    from vigia.app.services.evaluate import _mapping_for_batch

    project = session.get(Project, version.project_id)
    tipo = project.task_type if project is not None else "binary"
    match tipo:
        case "binary":
            return None
        case "multiclass" | "regression":
            return tarea_service.tarea_del_proyecto(project, _mapping_for_batch(session, batch))
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")


def _clase_a_explicar(
    task: TaskSpec, clase: int | str | None, records: list[Record]
) -> int | str | None:
    """La clase de `task.classes` que corresponde a `clase`, tal como está
    declarada. Sin clase y sin conjunto favorable: la mayoritaria de los
    `records` que se pasan (los de la línea base); con conjunto favorable,
    `None` (el motor explica el conjunto)."""
    if clase is not None:
        return task.classes[task.indice(clase)]
    if task.sin_conjunto_favorable:
        cuentas: dict[str, int] = {}
        for r in records:
            clave = r.label_class if r.label_class is not None else r.prediction_class
            if clave is not None:
                cuentas[clave] = cuentas.get(clave, 0) + 1
        if cuentas:
            mayoritaria = max(task.claves, key=lambda c: cuentas.get(c, 0))
            return task.classes[task.claves.index(mayoritaria)]
    return None


def _etiquetas_de_clase(records: list[Record], task: TaskSpec, clase: int | str | None) -> np.ndarray | None:
    """`y` para explicar una clase concreta: 1 si la clase real es esa, 0 si es
    otra, NaN sin etiqueta. Sin clase, el 0/1 del conjunto favorable."""
    if clase is None:
        return _label_array(records)
    clave = clave_clase(clase)
    if all(r.label_class is None for r in records):
        return None
    conocidas = set(task.claves)
    # Una etiqueta de una clase desconocida queda fuera, como una fila sin etiqueta.
    return np.array(
        [
            np.nan
            if r.label_class is None or r.label_class not in conocidas
            else float(r.label_class == clave)
            for r in records
        ],
        dtype=float,
    )


def get_baseline_batch(session: Session, version: ModelVersion) -> Batch:
    """El lote baseline congelado de la versión, o 409 si no hay ninguno."""
    if version.baseline_batch_id is None:
        raise HTTPException(409, "la versión no tiene baseline congelado")
    batch = session.get(Batch, version.baseline_batch_id)
    if batch is None:
        raise HTTPException(404, "el lote de la línea base ya no existe: vuelve a ingerir la línea base")
    return batch


def resolve_batch(session: Session, version: ModelVersion, batch_id: int | None) -> Batch:
    """Lote indicado (validando que pertenece al proyecto de la versión) o el baseline.

    Si `batch_id` no existe, o existe pero es de otro proyecto, se devuelve 404
    genérico ("lote no encontrado") para no confirmar la existencia de lotes
    ajenos al proyecto.
    """
    if batch_id is not None:
        batch = session.get(Batch, batch_id)
        if batch is None or batch.project_id != version.project_id:
            raise no_encontrado("lote", batch_id, "lotes")
        # El lote es de la versión que se explica; el de otra versión
        # del mismo proyecto no se mezcla con sus explicaciones.
        if batch.model_version_id != version.id:
            raise HTTPException(
                422,
                f"el lote {batch_id} es de otra versión del modelo: elige un lote de la versión "
                f"«{version.label}»",
            )
        return batch
    return get_baseline_batch(session, version)


def check_features_available(session: Session, batch: Batch) -> list[Record]:
    """Registros del lote, o 409 si el lote no guardó features (`store_features=false`).

    Se llama desde el router, antes de encolar el trabajo, para que el 409
    llegue como error HTTP real y no como un job en estado `error`.
    """
    records = _batch_records(session, batch)
    if not records or any(r.features_json is None for r in records):
        raise HTTPException(
            409,
            "no hay variables guardadas para este lote: activa «Guardar las variables de entrada de cada registro» "
            "en la pestaña Configuración del modelo y vuelve a ingerir el lote",
        )
    return records


def find_row(session: Session, batch: Batch, row_seq: int) -> Record:
    """Fila `row_seq` del lote, o 404 si no existe.

    Se llama desde el router, antes de encolar el trabajo, para que el 404
    llegue como error HTTP real y no como un job en estado `error`.
    """
    registros = _batch_records(session, batch)
    fila = next((r for r in registros if r.seq == row_seq), None)
    if fila is None:
        raise HTTPException(
            404, f"la fila {row_seq} no existe en el lote {batch.id}: elige una fila de la tabla del lote"
        )
    return fila


def _aviso_tipos(e: Explanation) -> str | None:
    """Aviso de artefacto pickle anterior a la corrección de tipos. La
    versión se lee con la sesión a la que pertenece la explicación, para no
    cambiar la firma de `explanation_to_dict`."""
    sesion = object_session(e)
    if sesion is None:
        return None
    version = sesion.get(ModelVersion, e.model_version_id)
    if version is None:
        return None
    return model_registry.aviso_tipos_antiguos(version.artifact_kind, version.artifact_uploaded_at)


def _sin_no_finitos(valor: Any) -> Any:
    """Un NaN o infinito guardado antes de la guardia de finitud se
    sirve como `null`, para que ni el listado ni el resumen fallen al
    serializarlo."""
    if isinstance(valor, float):
        return valor if math.isfinite(valor) else None
    if isinstance(valor, dict):
        return {k: _sin_no_finitos(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sin_no_finitos(v) for v in valor]
    return valor


def _features_finitas(result_json: Any) -> list[dict[str, Any]]:
    """Variables de un resultado guardado con importancia numérica y finita
    (las de una explicación anterior a la guardia de valores no finitos pueden no tenerla)."""
    features = (result_json or {}).get("features") or []
    return [f for f in features if _sin_no_finitos(f.get("importance")) is not None]


def explanation_to_dict(e: Explanation) -> dict[str, Any]:
    return {
        "id": e.id,
        "project_id": e.project_id,
        "model_version_id": e.model_version_id,
        "batch_id": e.batch_id,
        "kind": e.kind,
        "row_seq": e.row_seq,
        "params": _sin_no_finitos(e.params_json),
        "result": _sin_no_finitos(e.result_json),
        "available": e.available,
        "motivo": e.motivo,
        "job_id": e.job_id,
        "created_at": e.created_at,
        "aviso_tipos": _aviso_tipos(e),
    }


def _guardar_y_notificar(
    session: Session,
    explanation: Explanation,
    *,
    after_extra: dict[str, Any],
    correlation_id: str | None,
    bus: EventBus | None,
) -> Explanation:
    session.add(explanation)
    session.flush()
    record_event(
        session,
        actor_kind=ACTOR_MODELO[0],
        actor_id=ACTOR_MODELO[1],
        action="explicacion.calculada",
        object_type="explanation",
        object_id=explanation.id,
        project_id=explanation.project_id,
        after={"available": explanation.available, **after_extra},
        motivo=explanation.motivo,
        correlation_id=correlation_id,
        job_id=explanation.job_id,
        bus=bus,
    )
    return explanation


def explain_global(
    session: Session,
    version: ModelVersion,
    *,
    kind: str = "permutation",
    batch: Batch | None = None,
    job: JobContext | None = None,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
    origen: str = "manual",
    n_repeats: int | None = None,
    clase: int | str | None = None,
) -> Explanation:
    """Importancia global por permutación (por defecto) o SHAP.

    `X` son las filas del lote indicado o, si no se pasa, del baseline congelado
    de la versión; `y` son las etiquetas si las hay (permutación con `auroc_drop`).
    Si `kind="shap"` y `shap_available()` es falso, el resultado vuelve con
    `available=False` y motivo: no se lanza, el job termina `terminado`.

    `n_repeats` solo afecta a `kind="permutation"`: sin pasarlo,
    el motor usa su valor por defecto (5, sin cambios respecto a antes;
    es el que usan las fases con `explain_global=True` del guion, cuyas
    cifras son el contrato del checklist de demo). `maybe_auto_explain` pasa
    un valor menor para no añadir casi un segundo a cada lote.
    """
    check_explainable(version)
    batch = batch if batch is not None else get_baseline_batch(session, version)
    records = _batch_records(session, batch)
    X = _feature_frame(records, version)
    # En multiclase, `task=` y la clase a explicar; en binario
    # el motor se llama como siempre.
    task = _tarea_de_explicacion(session, version, batch)
    predict_fn = _predict_fn_for(version, task)
    extra: dict[str, Any] = {}
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "binary":
            y = _label_array(records)
        case "multiclass":
            # Sin conjunto favorable y sin clase pedida, la mayoritaria de la LÍNEA BASE.
            registros_base = records
            if (
                clase is None
                and task.sin_conjunto_favorable  # type: ignore[union-attr]
                and version.baseline_batch_id not in (None, batch.id)
            ):
                base = session.get(Batch, version.baseline_batch_id)
                registros_base = _batch_records(session, base) if base is not None else records
            clase = _clase_a_explicar(task, clase, registros_base)  # type: ignore[arg-type]
            extra = {"task": task, "clase": clase}
            y = _etiquetas_de_clase(records, task, clase)  # type: ignore[arg-type]
        case "regression":
            # `PredictFn` de forma `(n,)`, `y` continua, sin clase.
            extra = {"task": task}
            y = _valor_array(records)
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")

    if kind == "shap":
        X_explicar = X if len(X) <= MAX_FILAS_SHAP else X.sample(MAX_FILAS_SHAP, random_state=0)
        resultado = core_explain.global_shap(predict_fn, X, X_explicar, **extra)
        explanation_kind = "global_shap"
    else:
        kwargs: dict[str, Any] = {} if n_repeats is None else {"n_repeats": n_repeats}
        resultado = core_explain.global_permutation(predict_fn, X, y=y, **kwargs, **extra)
        explanation_kind = "global_permutation"

    explanation = Explanation(
        project_id=version.project_id,
        model_version_id=version.id,
        batch_id=batch.id,
        kind=explanation_kind,
        params_json=resultado.params,
        result_json=resultado.to_dict(),
        available=resultado.available,
        motivo=resultado.motivo,
        job_id=job.job_id if job is not None else None,
    )
    return _guardar_y_notificar(
        session,
        explanation,
        after_extra={"kind": explanation_kind, "batch_id": batch.id, "origen": origen},
        correlation_id=correlation_id,
        bus=bus,
    )


def explain_local(
    session: Session,
    version: ModelVersion,
    *,
    batch: Batch,
    row_seq: int,
    job: JobContext | None = None,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
    clase: int | str | None = None,
) -> Explanation:
    """LIME local de la fila `row_seq` del lote, con fondo el baseline congelado.

    Si la versión no tiene baseline congelado (o coincide con el propio lote),
    el fondo es el propio lote.
    """
    check_explainable(version)

    fondo_batch = batch
    if version.baseline_batch_id is not None and version.baseline_batch_id != batch.id:
        candidato = session.get(Batch, version.baseline_batch_id)
        if candidato is not None:
            fondo_batch = candidato

    registros_batch = _batch_records(session, batch)
    fila = next((r for r in registros_batch if r.seq == row_seq), None)
    if fila is None:
        raise HTTPException(
            404, f"la fila {row_seq} no existe en el lote {batch.id}: elige una fila de la tabla del lote"
        )

    registros_fondo = (
        registros_batch if fondo_batch.id == batch.id else _batch_records(session, fondo_batch)
    )
    X_fondo = _feature_frame(registros_fondo, version)
    X_fila = _feature_frame([fila], version)
    # Sin clase, el motor explica la clase predicha de la fila.
    task = _tarea_de_explicacion(session, version, batch)
    predict_fn = _predict_fn_for(version, task)
    extra: dict[str, Any] = {}
    tipo = task.task_type if task is not None else "binary"
    match tipo:
        case "binary":
            pass
        case "multiclass":
            extra = {"task": task, "clase": task.classes[task.indice(clase)] if clase is not None else None}  # type: ignore[union-attr]
        case "regression":
            # LIME con `mode="regression"`, sin clase.
            extra = {"task": task}
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    resultado = core_explain.local_lime(
        predict_fn,
        X_fondo,
        X_fila.iloc[0],
        feature_names=list(X_fondo.columns),
        categorical_cols=_categorical_cols_for(version),
        row_seq=row_seq,
        **extra,
    )

    explanation = Explanation(
        project_id=version.project_id,
        model_version_id=version.id,
        batch_id=batch.id,
        kind="local_lime",
        row_seq=row_seq,
        params_json=resultado.params,
        result_json=resultado.to_dict(),
        available=resultado.available,
        motivo=resultado.motivo,
        job_id=job.job_id if job is not None else None,
    )
    return _guardar_y_notificar(
        session,
        explanation,
        after_extra={"kind": "local_lime", "row_seq": row_seq},
        correlation_id=correlation_id,
        bus=bus,
    )


# `maybe_auto_explain` se llama en línea antes de evaluar el lote
# (la explicación debe existir ANTES de `evaluate_batch_service`,
# que la usa para `explain_stability_ndcg`; no se puede mover a después ni a
# un job aparte sin perder esa comparación). Lo que sí se puede reducir es su
# coste: con `n_repeats` por defecto (5, el que siguen usando las fases con
# `explain_global=True` del guion) medido sobre el lote de línea base real
# de escenario 1 (450 filas, 41 columnas), `global_permutation` tarda ~0,67 s;
# con `n_repeats=2` (dos barajados por columna en vez de cinco, la importancia
# es más ruidosa pero el ranking que usa la comparación de estabilidad
# aguanta) baja a ~0,26 s, un 61 % menos.
_N_REPEATS_AUTO = 2


def maybe_auto_explain(
    session: Session,
    batch: Batch,
    version: ModelVersion,
    project: Project,
    *,
    job: JobContext | None = None,
    correlation_id: str | None = None,
    bus: EventBus | None = None,
) -> Explanation | None:
    """Explicación global automática tras evaluar un lote.

    Solo si `project.explain_auto` y `project.store_features`. Si la versión
    no tiene con qué explicar (`check_explainable`: ni `sim_logistic` ni un
    `executable` con artefacto ya subido), no hay nada que explicar
    por esta vía todavía: no es un fallo, así que se devuelve `None` en
    silencio, sin evento `explicacion.fallida` (queda para fallos reales,
    p.ej. un artefacto que deja de predecir). Cualquier otro fallo se
    registra como evento `explicacion.fallida` y no se relanza: la evaluación
    ya ha terminado, esto no debe tumbarla.

    con `kind="permutation"` pasa `_N_REPEATS_AUTO` en vez del
    valor por defecto del motor, para no bloquear la evaluación casi un
    segundo por lote (ver nota arriba). Con `kind="shap"` no aplica (SHAP no
    tiene `n_repeats`) y el coste no cambia.
    """
    if not project.explain_auto or not project.store_features:
        return None
    try:
        check_explainable(version)
    except HTTPException:
        return None
    n_repeats = _N_REPEATS_AUTO if project.explain_method != "shap" else None
    try:
        return explain_global(
            session,
            version,
            kind=project.explain_method,
            batch=batch,
            job=job,
            correlation_id=correlation_id,
            bus=bus,
            origen="auto",
            n_repeats=n_repeats,
        )
    except Exception as exc:  # noqa: BLE001 - se registra y no interrumpe la evaluación
        record_event(
            session,
            actor_kind=ACTOR_MODELO[0],
            actor_id=ACTOR_MODELO[1],
            action="explicacion.fallida",
            object_type="batch",
            object_id=batch.id,
            project_id=project.id,
            motivo=str(exc),
            correlation_id=correlation_id,
            job_id=job.job_id if job is not None else None,
            bus=bus,
        )
        return None


def _top3_features(explanation: Explanation) -> list[dict[str, Any]]:
    features = _features_finitas(explanation.result_json)
    return list(features[:3])


def _feature_dict(f: Any) -> dict[str, Any]:
    """Une el dict crudo de `Explanation.result_json` y el `FeatureImportance`
    del core: mismo par `feature`/`importance` en los dos casos."""
    if isinstance(f, dict):
        return {"feature": f["feature"], "importance": f["importance"]}
    return {"feature": f.feature, "importance": f.importance}


def _topn_features(features: list[Any], n: int) -> list[dict[str, Any]]:
    return [_feature_dict(f) for f in features[:n]]


def _ranking_delta(
    actual_top: list[dict[str, Any]], reference_top: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Variables cuyo puesto (1 = la más importante) difiere entre dos top N.

    `from`/`to` a `None` cuando la variable no está en `reference_top`/`actual_top`
    respectivamente. Ordenado por puesto actual, con las que salieron del top
    (sin `to`) al final por su puesto de referencia.
    """
    puesto_actual = {f["feature"]: i + 1 for i, f in enumerate(actual_top)}
    puesto_referencia = {f["feature"]: i + 1 for i, f in enumerate(reference_top)}
    variables = set(puesto_actual) | set(puesto_referencia)
    cambios = [
        {"feature": variable, "from": puesto_referencia.get(variable), "to": puesto_actual.get(variable)}
        for variable in variables
        if puesto_referencia.get(variable) != puesto_actual.get(variable)
    ]
    cambios.sort(key=lambda c: (c["to"] is None, c["to"] or c["from"]))
    return cambios


def explanations_summary(session: Session, project: Project) -> dict[str, Any]:
    """Resumen de explicabilidad para la tarjeta del cuadro de mando.

    Todo el resumen se calcula sobre `project.active_version_id`, nunca sobre
    el proyecto entero: distintas versiones del modelo no comparten ranking
    de características ni estabilidad. `top_features` sale de la última
    explicación global disponible de esa versión; `stability`/`stability_state`,
    de la última medida `explain_stability_ndcg` del monitor `explain`
    (`Measurement`, ya calculada por `core/explain.py:evaluate_explain`) cuya
    `Evaluation` pertenece a esa misma versión; `ranking_changed_at` recorre
    las explicaciones globales de la versión activa en orden y se queda con
    la fecha de la última cuyo ranking de las tres primeras características
    difiere del de la explicación anterior (`None` si hay como mucho una, o
    si nunca ha cambiado). Sin versión activa, el resumen sale vacío.

    `reference_top_features`/`ranking_delta` comparan el top 10 de la
    última explicación con el de su explicación de referencia
    (`_explain_reference_for_version` de `services/evaluate.py`: la
    primera explicación global disponible de la versión activa, la misma que
    ya usa `explain_stability_ndcg` para `stability`); `None`/`[]` sin
    referencia (una única explicación, o ninguna).
    """
    version_id = project.active_version_id
    explicaciones = (
        list(
            session.exec(
                select(Explanation)
                .where(
                    Explanation.project_id == project.id,
                    Explanation.model_version_id == version_id,
                    Explanation.kind.in_(_KINDS_GLOBALES),  # type: ignore[attr-defined]
                    Explanation.available == True,  # SQLAlchemy exige `==`, no `is`
                )
                .order_by(Explanation.created_at)  # type: ignore[attr-defined]
            ).all()
        )
        if version_id is not None
        else []
    )
    # El resumen compara rankings del mismo objetivo (en multiclase, la
    # misma clase o el mismo conjunto favorable) que el de la última explicación.
    if explicaciones:
        from vigia.app.services.evaluate import objetivo_de

        objetivo = objetivo_de(explicaciones[-1].params_json)
        explicaciones = [e for e in explicaciones if objetivo_de(e.params_json) == objetivo]

    top_features: list[dict[str, Any]] = []
    ranking_changed_at: str | None = None
    if explicaciones:
        top_features = [
            {"feature": f["feature"], "importance": f["importance"]}
            for f in _top3_features(explicaciones[-1])
        ]
        ranking_anterior = [f["feature"] for f in _top3_features(explicaciones[0])]
        for explicacion in explicaciones[1:]:
            ranking_actual = [f["feature"] for f in _top3_features(explicacion)]
            if ranking_actual != ranking_anterior:
                ranking_changed_at = explicacion.created_at
            ranking_anterior = ranking_actual

    n_explanations = len(explicaciones)

    # Con menos de dos explicaciones globales, `stability` no compara nada
    # (la única medida existente compararía la explicación consigo misma como
    # referencia) y se fuerza a "sin_datos" aunque `Measurement` traiga un
    # valor calculado.
    if n_explanations < 2 or version_id is None:
        stability, stability_state = None, "sin_datos"
    else:
        medida = session.exec(
            select(Measurement)
            .join(Evaluation, Evaluation.id == Measurement.evaluation_id)  # type: ignore[arg-type]
            .where(
                Measurement.project_id == project.id,
                Measurement.monitor_type == "explain",
                Measurement.metric_key == "explain_stability_ndcg",
                Evaluation.model_version_id == version_id,
            )
            .order_by(Measurement.created_at.desc())  # type: ignore[attr-defined]
            .limit(1)
        ).first()
        stability = medida.value if medida else None
        stability_state = medida.state if medida else None

    # Mismo cálculo de referencia que `stability` (`_explain_reference_for_version`,
    # La primera explicación global disponible de la versión, excluyendo
    # la que se está resumiendo) para no comparar contra una referencia
    # distinta de la que ya sostiene la estabilidad de esta misma tarjeta.
    # Import perezoso: `evaluate.py` no importa `explain.py`, pero se evita el
    # acoplamiento en el nivel de módulo por si cambia en el futuro (mismo
    # patrón que `routers/datasets.py`).
    reference_top_features: list[dict[str, Any]] | None = None
    ranking_delta: list[dict[str, Any]] = []
    if explicaciones and version_id is not None:
        from vigia.app.services.evaluate import _explain_reference_for_version

        version = session.get(ModelVersion, version_id)
        referencia = (
            _explain_reference_for_version(
                session,
                version,
                excluir_explanation_id=explicaciones[-1].id,
                objetivo=objetivo,
            )
            if version is not None
            else None
        )
        if referencia is not None:
            actual_features = _features_finitas(explicaciones[-1].result_json)
            actual_top = _topn_features(actual_features, _TOP_N_COMPARADO)
            reference_top_features = _topn_features(referencia.features, _TOP_N_COMPARADO)
            ranking_delta = _ranking_delta(actual_top, reference_top_features)

    return {
        "top_features": top_features,
        "stability": stability,
        "stability_state": stability_state,
        "ranking_changed_at": ranking_changed_at,
        "n_explanations": n_explanations,
        "reference_top_features": reference_top_features,
        "ranking_delta": ranking_delta,
    }
