"""Comparación de dos versiones del mismo proyecto.

La comparación es por evaluaciones: cada versión contra su propia línea
base, métrica a métrica, con los umbrales del proyecto. Se calcula al leer;
ninguna tabla cambia. La respuesta es `schemas/versiones.ComparacionVersiones`.
La lectura de medidas vive en `comparacion_lectura` y la regla de dirección en
`comparacion_direccion`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from fastapi import HTTPException
from sqlmodel import Session, select

from vigia.app.errores import no_encontrado
from vigia.app.models import Evaluation, Event, Measurement, ModelVersion, Project, Record
from vigia.app.services import alerting
from vigia.app.services.comparacion_alertas import alertas_vivas
from vigia.app.services.comparacion_direccion import (
    UMBRAL_IGUAL,
    decidir_direccion,
    decidir_direccion_neutra,
    regla_del_umbral,
)
from vigia.app.services.comparacion_lectura import Clave, MedidasVersion, cargar_medidas, leer_lado
from vigia.core.schema import es_grupo_clase

NOTA_ALERTAS = "las alertas son del modelo, no de la versión"

_ORDEN_MONITOR = {"fairness": 0, "quality": 1, "drift": 2}

# medidas por clase que son proporciones (no hay «mejor»).
_PROPORCIONES_DE_CLASE = frozenset({"label_rate", "prediction_rate"})
# Medidas por clase en las que más bajo es mejor.
_TASAS_DE_ERROR = frozenset({"false_positive_rate", "false_negative_rate"})

# La explicabilidad y las reglas cruzadas no entran en la tabla.
_MONITORES_COMPARABLES = frozenset(_ORDEN_MONITOR)

# las claves de una regresión que van en la unidad de la salida
# (`alerting.CLAVES_EN_UNIDAD`). «Igual» es una diferencia menor que el 1 % de la
# desviación del valor real en la línea base de la versión A. `r2`,
# `mean_absolute_error_ratio` y `prediction_drift_score` no llevan unidad: siguen con 0,01.
_FRACCION_IGUAL_EN_UNIDAD = 0.01

MOTIVO_SIN_ESCALA = (
    "; sin escala: la versión A no tiene línea base con valor real que varíe, así que "
    "la igualdad por diferencia no se evalúa"
)

# la respuesta sin filas dice por qué, en los tres tipos. Sin un lote de producción
# evaluado en cada versión no hay nada que comparar; con lotes pero sin umbrales, hay que
# fijarlos (en binario ya nacen de fábrica, así que allí solo faltan los lotes).
MOTIVO_SIN_LOTES = (
    "Falta evaluar un lote de producción en cada versión: evalúa uno en la versión A y otro "
    "en la B y vuelve a comparar"
)
MOTIVO_SIN_UMBRALES = (
    "Ninguna medida de las dos versiones tiene umbral que comparar: congela la línea base "
    "de cada versión (Vigía propone entonces los umbrales) o fija los umbrales a mano en "
    "los monitores, evalúa un lote y vuelve a comparar"
)
MOTIVO_SIN_UMBRALES_BINARIO = (
    "Ninguna medida de las dos versiones tiene umbral que comparar: fija los umbrales a "
    "mano en los monitores, evalúa un lote y vuelve a comparar"
)


def _motivo_sin_filas(project: Project, da: MedidasVersion, db: MedidasVersion) -> str:
    if not da.lotes_evaluados or not db.lotes_evaluados:
        return MOTIVO_SIN_LOTES
    match project.task_type:
        case "binary":
            return MOTIVO_SIN_UMBRALES_BINARIO
        case "multiclass" | "regression":
            return MOTIVO_SIN_UMBRALES
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")


def _desviacion_del_valor_real(session: Session, version: ModelVersion) -> float | None:
    """Desviación típica del valor real (`label_value`) de la línea base de `version`;
    `None` si no hay línea base, hay menos de dos valores o no varía."""
    if version.baseline_batch_id is None:
        return None
    valores = session.exec(
        select(Record.label_value).where(
            Record.batch_id == version.baseline_batch_id,
            Record.label_value.is_not(None),  # type: ignore[union-attr]
        )
    ).all()
    if len(valores) < 2:
        return None
    desviacion = float(np.std(np.asarray(valores, dtype=float), ddof=1))
    return desviacion if np.isfinite(desviacion) and desviacion > 0 else None


def _version_previa_activada(session: Session, project: Project, b: int) -> int | None:
    """Versión activa justo antes de `b`, según el último evento `version.activada` de `b`."""
    eventos = session.exec(
        select(Event)
        .where(
            Event.project_id == project.id,
            Event.action == "version.activada",
            Event.object_id == b,
        )
        .order_by(Event.id.desc())  # type: ignore[union-attr]
    ).all()
    for ev in eventos:
        antes = (ev.before_json or {}).get("active_version_id")
        if isinstance(antes, int) and antes != b:
            return antes
    return None


def _resolver_versiones(
    session: Session, project: Project, a: int | None, b: int | None
) -> tuple[ModelVersion, ModelVersion]:
    versiones = {
        v.id: v
        for v in session.exec(
            select(ModelVersion).where(ModelVersion.project_id == project.id)
        ).all()
    }
    for ident in (a, b):
        if ident is not None and ident not in versiones:
            raise no_encontrado("versión", ident, "versiones")
    if len(versiones) < 2:
        raise HTTPException(
            409,
            "El modelo tiene una sola versión: crea la versión nueva en la ficha del "
            "modelo y vuelve a comparar.",
        )
    if b is None:
        b = project.active_version_id
    if b is None or b not in versiones:
        raise HTTPException(
            409, "El modelo no tiene versión activa: activa una versión o elige cuál comparar."
        )
    if a is None:
        a = _version_previa_activada(session, project, b)
        if a not in versiones:
            con_evaluaciones = session.exec(
                select(Evaluation.model_version_id)
                .where(Evaluation.project_id == project.id, Evaluation.model_version_id != b)
                .order_by(Evaluation.id.desc())  # type: ignore[union-attr]
            ).first()
            a = con_evaluaciones or max((i for i in versiones if i != b), default=None)
    if a == b:
        raise HTTPException(
            409, "Elige dos versiones distintas para comparar: las dos son la misma."
        )
    return versiones[a], versiones[b]  # type: ignore[index]


def _umbrales(*candidatos: Any) -> tuple[float | None, float | None]:
    for m in candidatos:
        if m is not None and (m.threshold_low is not None or m.threshold_high is not None):
            return m.threshold_low, m.threshold_high
    return None, None


def _es_medida_por_clase(clave: Clave) -> bool:
    """una medida de calidad de una clase (`group_code` `clase:<valor>`)
    no tiene umbral, pero se compara entre versiones: más alto es mejor. El
    recuento `n` de la clase no es mejor ni peor y no entra."""
    return clave[0] == "quality" and es_grupo_clase(clave[2]) and clave[1] != "n"


def _es_proporcion_de_clase(clave: Clave) -> bool:
    """`label_rate` y `prediction_rate` de una clase son proporciones, sin
    sentido de mejora: la dirección es `igual` o `cambia`."""
    return _es_medida_por_clase(clave) and clave[1] in _PROPORCIONES_DE_CLASE


def _claves_con_umbral(da: MedidasVersion, db: MedidasVersion) -> list[Clave]:
    claves: set[Clave] = set()
    for datos in (da, db):
        for clave, m in datos.linea_base.items():
            if clave[0] in _MONITORES_COMPARABLES and (
                _umbrales(m) != (None, None) or _es_medida_por_clase(clave)
            ):
                claves.add(clave)
        for clave, lista in datos.produccion.items():
            if clave[0] in _MONITORES_COMPARABLES and (
                any(_umbrales(t[2]) != (None, None) for t in lista) or _es_medida_por_clase(clave)
            ):
                claves.add(clave)
    return sorted(
        claves, key=lambda c: (_ORDEN_MONITOR[c[0]], c[1], c[2] or "")
    )


def _fila(
    da: MedidasVersion,
    db: MedidasVersion,
    clave: Clave,
    ventana: str,
    desviacion_real: float | None = None,
    regresion: bool = False,
) -> dict[str, Any]:
    """`regresion` y `desviacion_real` solo los pasa `comparar_versiones` en una regresión.
    Una regresión sin desviación (la versión A no tiene línea base con valor real
    que varíe) no tiene escala para decidir «igual» por diferencia en las claves en la
    unidad: solo cuentan los intervalos solapados."""

    def ultima(d: MedidasVersion) -> Measurement | None:
        lista = d.produccion.get(clave, [])
        return lista[-1][2] if lista else None

    low, high = _umbrales(
        ultima(db), ultima(da), db.linea_base.get(clave), da.linea_base.get(clave)
    )
    lado_a, lado_b = leer_lado(da, clave, ventana), leer_lado(db, clave, ventana)
    va, vb = lado_a["valor"], lado_b["valor"]
    fila: dict[str, Any] = {
        "monitor_type": clave[0],
        "metric_key": clave[1],
        "group_code": clave[2],
        "threshold_low": low,
        "threshold_high": high,
        "a": lado_a,
        "b": lado_b,
        "diferencia": None,
    }
    if va is None or vb is None:
        partes = [f"{d.version.label}: {lado['motivo']}" for d, lado in ((da, lado_a), (db, lado_b))
                  if lado["valor"] is None]
        fila.update(direccion="sin_datos", motivo="; ".join(partes))
        return fila
    intervalos = {
        "intervalo_a": (lado_a["interval_low"], lado_a["interval_high"]),
        "intervalo_b": (lado_b["interval_low"], lado_b["interval_high"]),
    }
    if _es_proporcion_de_clase(clave):
        # la proporción de una clase no mejora ni empeora al subir.
        direccion, motivo = decidir_direccion_neutra(va, vb, **intervalos)
    else:
        # Una medida por clase no tiene umbral: la regla es «más alto es mejor»,
        # salvo las tasas de error, donde más bajo es mejor.
        regla_low, regla_high = low, high
        if _es_medida_por_clase(clave) and low is None and high is None:
            if clave[1] in _TASAS_DE_ERROR:
                regla_high = 1.0
            else:
                regla_low = 0.0
        umbral_igual = UMBRAL_IGUAL
        sin_escala = False
        if regresion and clave[1] in alerting.CLAVES_EN_UNIDAD:
            if desviacion_real is not None:
                umbral_igual = _FRACCION_IGUAL_EN_UNIDAD * desviacion_real
            else:
                umbral_igual = 0.0
                sin_escala = True
        direccion, motivo = decidir_direccion(
            va, vb, low=regla_low, high=regla_high, umbral_igual=umbral_igual, **intervalos
        )
        if sin_escala and motivo != "intervalos solapados":
            motivo += MOTIVO_SIN_ESCALA
    if clave[0] == "drift":
        motivo = (
            f"distancia a su propia línea base ({da.version.label} contra el lote "
            f"{da.version.baseline_batch_id}, {db.version.label} contra el lote "
            f"{db.version.baseline_batch_id}); {regla_del_umbral(low, high)}"
            if direccion != "igual"
            else f"{motivo}; distancia a su propia línea base de cada versión"
        )
    fila.update(diferencia=vb - va, direccion=direccion, motivo=motivo)
    return fila


def _resumen(datos: MedidasVersion) -> dict[str, Any]:
    v = datos.version
    return {
        "id": v.id,
        "label": v.label,
        "is_active": v.is_active,
        "baseline_batch_id": v.baseline_batch_id,
        "n_lotes_evaluados": len(datos.lotes_evaluados),
    }


def comparar_versiones(
    session: Session,
    project: Project,
    *,
    a: int | None = None,
    b: int | None = None,
    ventana: str = "ultimo",
) -> dict[str, Any]:
    """Compara la versión `a` con la `b` del proyecto.

    Sin `b`, la versión activa. Sin `a`, la versión activa anterior: la que
    el último evento `version.activada` de `b` dejó atrás o, si no hay evento,
    la versión distinta de `b` con la evaluación más reciente (y, sin
    evaluaciones, la de id más alto). Lanza `HTTPException` 404 si una versión
    no existe o es de otro proyecto, y 409 si el proyecto tiene una sola
    versión o `a` y `b` son la misma.
    """
    va, vb = _resolver_versiones(session, project, a, b)
    da, db = cargar_medidas(session, va), cargar_medidas(session, vb)
    match project.task_type:
        case "binary" | "multiclass":
            regresion, desviacion_real = False, None
        case "regression":
            regresion, desviacion_real = True, _desviacion_del_valor_real(session, va)
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")
    filas = [
        _fila(da, db, c, ventana, desviacion_real, regresion) for c in _claves_con_umbral(da, db)
    ]
    return {
        "project_id": project.id,
        "ventana": ventana,
        "version_a": _resumen(da),
        "version_b": _resumen(db),
        "filas": filas,
        # sin umbrales que comparar la respuesta lo dice, en los tres tipos.
        "motivo": None if filas else _motivo_sin_filas(project, da, db),
        "alertas_vivas": alertas_vivas(session, project),
        "nota_alertas": NOTA_ALERTAS,
    }
