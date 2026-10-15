"""Adaptador de deskilling: junto a `human_layer._read_usage_csv`
(que solo valida cabecera), el único módulo que importa
`interaction_review.telemetry`.

Reconstruye `telemetry.Record` en memoria a partir de filas `UsageLog` ya
cargadas por SQLModel: nunca CSV temporal, nunca variable de entorno. La
partición "por versión de modelo" vive aquí: `deskilling_view` nunca
junta filas de dos `model_version_id`, igual que `human_layer.usage_frame`
hace para las cruzadas.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date as date_cls

from sqlmodel import Session, select

from vigia.app.models import ModelVersion, UsageLog
from vigia.human._vendor.interaction_review import __version__ as PACKAGE_VERSION
from vigia.human._vendor.interaction_review.telemetry import (
    DeskillingSignal,
    Record,
    Trends,
    WindowMetrics,
    compute_trends,
    compute_windows,
    deskilling_signal,
)
from vigia.human.deskilling_texto import MOTIVO_POCAS_VENTANAS, resumen_md_es

__all__ = [
    "EPS",
    "MIN_N",
    "PACKAGE_VERSION",
    "DeskillingResult",
    "deskilling_reason_es",
    "deskilling_view",
    "records_from_db",
    "ventanas_para_pendiente",
]

# Mismo mapeo entero/etiqueta que `human_layer._INT_TO_LABEL` (human_layer.py:59);
# duplicado aquí para no importar un nombre privado de otro módulo (frontera).
_INT_TO_LABEL = {1: "refer", 0: "no-refer"}

MIN_N = 30
EPS = 0.02

# Corrección, hallazgo 2: catálogo cerrado de las cadenas que produce
# `telemetry.deskilling_signal` (texto de librería, en inglés,
# `telemetry.py:189-211`). `GET /deskilling` lo enseña tal cual, a propósito
# (`DeskillingSignalOut`: "se traduce en el frontend"), pero cualquier
# consumidor que lo meta en un mensaje al usuario compuesto en el backend
# (CX-4, `cross_alerts._cx4`, vía `DeskillingInput.reason`) no puede: viola
# la regla de mensajes en español sin texto de librería. Van las 6
# cadenas posibles (la de "converging" tiene 3 variantes por el `" and
# ".join(why)` del paquete; no son 4 literales, son 4 plantillas con 6
# salidas literales distintas).
_DESKILLING_REASON_ES: dict[str, str] = {
    MOTIVO_POCAS_VENTANAS: (
        "quedan menos de 2 ventanas con eventos suficientes para estimar una "
        "tendencia (las ventanas pequeñas no aportan punto a la pendiente)"
    ),
    "Insufficient windows with ground truth to assess a trend.": (
        "ventanas insuficientes con verdad de terreno para estimar una tendencia"
    ),
    (
        "Human and model are converging while the human's own accuracy is not "
        "improving -- a pattern consistent with criterion erosion. Investigate; "
        "not a diagnosis."
    ): (
        "el profesional y el modelo convergen mientras la precisión propia del "
        "profesional no mejora: patrón compatible con erosión del criterio, a "
        "investigar, no es una conclusión"
    ),
    (
        "Human and model are converging while the rescue rate is falling -- a "
        "pattern consistent with criterion erosion. Investigate; not a diagnosis."
    ): (
        "el profesional y el modelo convergen mientras la tasa de rescate cae: "
        "patrón compatible con erosión del criterio, a investigar, no es una "
        "conclusión"
    ),
    (
        "Human and model are converging while the human's own accuracy is not "
        "improving and the rescue rate is falling -- a pattern consistent with "
        "criterion erosion. Investigate; not a diagnosis."
    ): (
        "el profesional y el modelo convergen mientras la precisión propia del "
        "profesional no mejora y la tasa de rescate cae: patrón compatible con "
        "erosión del criterio, a investigar, no es una conclusión"
    ),
    "Human and model are not converging over the period.": (
        "el profesional y el modelo no convergen en el periodo"
    ),
    "Convergence present, but the human's accuracy/rescue rate holds.": (
        "hay convergencia, pero la precisión o la tasa de rescate del profesional "
        "se mantiene"
    ),
}


def deskilling_reason_es(reason: str) -> str:
    """Traduce `reason` de `telemetry.deskilling_signal` para un consumidor
    que lo use en un mensaje al usuario (corrección, hallazgo 2). Si el
    paquete cambia el texto y no está en `_DESKILLING_REASON_ES`, no deja
    pasar inglés: motivo genérico que dice que hay que revisar la versión
    del paquete, no la cadena original."""
    return _DESKILLING_REASON_ES.get(
        reason,
        "señal de deskilling sin motivo reconocido en el catálogo de traducción "
        "(revisar la versión de interaction_review)",
    )


def _filtered_rows(
    rows: Sequence[UsageLog],
    *,
    clinician: str | None,
    subgroup: str | None,
) -> list[UsageLog]:
    """Filtro común de `records_from_db`/`deskilling_view`: nunca mezcla
    `model_version_id` (quien llama ya ha limitado `rows` a una sola
    versión) y descarta filas con `human_decision` o `model_output`
    nulos (el paquete exige ambos no vacíos, `telemetry.py:104-105`)."""
    return [
        f
        for f in rows
        if (clinician is None or f.clinician_pseudonym == clinician)
        and (subgroup is None or f.subgroup == subgroup)
        and f.human_decision is not None
        and f.model_output is not None
    ]


def _registro(f: UsageLog, fecha: date_cls) -> Record:
    """`Record` de una fila del diario. Multiclase: los nombres de clase
    (`human_class`, `model_class`, `truth_class`); el paquete compara por
    igualdad y no cambia. Binario, o una fila sin clases: `refer`/`no-refer`
    desde los enteros de siempre."""
    if f.human_class is not None and f.model_class is not None:
        return Record(date=fecha, human=f.human_class, model=f.model_class, truth=f.truth_class)
    return Record(
        date=fecha,
        human=_INT_TO_LABEL[f.human_decision],
        model=_INT_TO_LABEL[f.model_output],
        truth=_INT_TO_LABEL.get(f.ground_truth) if f.ground_truth is not None else None,
    )


def _records_and_excluded(
    rows: Sequence[UsageLog],
    *,
    clinician: str | None,
    subgroup: str | None,
) -> tuple[list[Record], int]:
    """Construye los `Record` y cuenta cuántas filas se excluyen por fecha
    no ISO (antes `date_cls.fromisoformat(f.date)` sin `try`,
    `ValueError` crudo que tumbaba `GET /deskilling` en 500).

    Defensa en profundidad: `POST /usage-logs/upload` ya normaliza la fecha
    a ISO antes de guardarla (`services/human_layer._normalize_date`), así
    que en el camino normal ninguna fila se excluye aquí; esto cubre datos
    que llegasen a `usage_log` por otra vía con una fecha que no lo sea.
    """
    filtradas = _filtered_rows(rows, clinician=clinician, subgroup=subgroup)
    registros: list[Record] = []
    excluidas = 0
    for f in filtradas:
        try:
            fecha = date_cls.fromisoformat(f.date)
        except (ValueError, TypeError):
            excluidas += 1
            continue
        registros.append(_registro(f, fecha))
    return registros, excluidas


def records_from_db(
    rows: Sequence[UsageLog],
    *,
    clinician: str | None = None,
    subgroup: str | None = None,
) -> list[Record]:
    """Filtra antes de construir. Nunca mezcla `model_version_id`: quien llama
    ya ha limitado `rows` a una sola versión.

    Descarta filas con `human_decision` o `model_output` nulos (el paquete
    exige ambos no vacíos, `telemetry.py:104-105`) y filas con fecha no ISO
    (`deskilling_view` usa `_records_and_excluded` para saber
    cuántas se excluyen así, este envoltorio se queda con la lista sola por
    compatibilidad con quien ya lo llama)."""
    registros, _excluidas = _records_and_excluded(rows, clinician=clinician, subgroup=subgroup)
    return registros


@dataclass(frozen=True)
class DeskillingResult:
    """Resultado agregado de una versión de modelo, listo para
    `GET /projects/{id}/deskilling` y para CX-4 (`services/human_layer.py`,
    `_deskilling_input_for_cx4`, que lee `signal.fired` y las pendientes de
    `trends`)."""

    sin_datos: bool
    motivo: str | None
    windows: list[WindowMetrics]
    trends: Trends | None
    signal: DeskillingSignal | None
    summary_md: str | None
    # Filas de `usage_log` excluidas por fecha no ISO (defensa
    # en profundidad, ver `_records_and_excluded`); 0 en el camino normal,
    # porque la subida ya normaliza. Con valor por defecto: las dos ramas
    # `sin_datos` de más abajo no cuentan ninguna.
    filas_excluidas_fecha: int = 0
    # El `MIN_N` aplicado y cuántas
    # ventanas de `windows` quedan fuera de la pendiente por tener menos de
    # `min_n` decisiones. Siguen en `windows` con su `n`; solo salen de la pendiente.
    min_n: int = MIN_N
    ventanas_excluidas: int = 0


def _sin_punto(w: WindowMetrics) -> WindowMetrics:
    """La ventana sin tasas: no aporta punto a la pendiente y conserva su
    posición (el índice de ventana de la regresión no se mueve)."""
    return replace(
        w, agreement_rate=None, human_accuracy=None, model_accuracy=None, rescue_rate=None
    )


def ventanas_para_pendiente(
    windows: Sequence[WindowMetrics], *, min_n: int = MIN_N
) -> list[WindowMetrics]:
    """Las ventanas con menos de `min_n` decisiones no aportan
    punto a la pendiente. Camino único de todas las lecturas del deskilling (la
    vista de la API, el filtro por subgrupo o por profesional, CX-4 y el
    dossier pasan por `deskilling_view`)."""
    return [_sin_punto(w) if w.n < min_n else w for w in windows]


def deskilling_view(
    session: Session,
    project_id: int,
    version: ModelVersion,
    *,
    clinician: str | None = None,
    subgroup: str | None = None,
    n_windows: int = 4,
    min_n: int = MIN_N,
) -> DeskillingResult:
    """Vista de deskilling para una única versión de modelo.

    `sin_datos=True` con `motivo="cambio de versión en el periodo"` si la
    versión no tiene filas pero el proyecto tiene diario de otra versión;
    con `motivo="sin diario de uso"` si no hay ninguna fila en absoluto (o
    ninguna sobrevive al filtro de `clinician`/`subgroup`).
    """
    filas_version = session.exec(
        select(UsageLog).where(
            UsageLog.project_id == project_id,
            UsageLog.model_version_id == version.id,
        )
    ).all()
    if not filas_version:
        hay_otra_version = session.exec(
            select(UsageLog.id).where(UsageLog.project_id == project_id).limit(1)
        ).first()
        motivo = "cambio de versión en el periodo" if hay_otra_version else "sin diario de uso"
        return DeskillingResult(True, motivo, [], None, None, None)

    records, filas_excluidas_fecha = _records_and_excluded(
        filas_version, clinician=clinician, subgroup=subgroup
    )
    if not records:
        return DeskillingResult(True, "sin diario de uso", [], None, None, None, filas_excluidas_fecha)

    windows = compute_windows(records, n_windows=n_windows)
    # Las ventanas con n < MIN_N se enseñan, pero no aportan punto a
    # la pendiente. Con menos de 2 puntos válidos, `compute_trends` da pendientes
    # nulas y `deskilling_signal` no dispara (el bloqueo de CX-4 y la
    # partición por versión siguen como estaban).
    trends = compute_trends(ventanas_para_pendiente(windows, min_n=min_n))
    signal = deskilling_signal(trends, eps=EPS)
    excluidas = [i for i, w in enumerate(windows, 1) if w.n < min_n]
    if excluidas and len(windows) - len(excluidas) < 2 and not signal.fired:
        # La causa es la celda mínima, no la verdad de referencia (revisión D).
        signal = DeskillingSignal(False, MOTIVO_POCAS_VENTANAS)
    # Resumen en español; `signal.reason` queda en inglés porque
    # CX-4 lo lee: se traduce en la respuesta de la API.
    summary_md = resumen_md_es(
        windows, trends, signal, min_n=min_n, excluidas=excluidas, validas=len(windows) - len(excluidas)
    )
    return DeskillingResult(
        False, None, windows, trends, signal, summary_md, filas_excluidas_fecha,
        min_n=min_n, ventanas_excluidas=len(excluidas),
    )
