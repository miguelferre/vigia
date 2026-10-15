"""Lectura de las medidas de una versión para la comparación.

Por versión: las medidas de la evaluación de su línea base y las de sus lotes
de producción evaluados, agrupadas por clave (monitor, métrica, grupo). Si un
lote tiene varias evaluaciones del mismo monitor, cuenta la última.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session, select

from vigia.app.models import Batch, Evaluation, Measurement, ModelVersion

Clave = tuple[str, str, str | None]

# De peor a mejor para resumir varios lotes (`ventana=todos`).
_ORDEN_ESTADO = ("inestable", "alerta", "aviso", "ok")


@dataclass
class MedidasVersion:
    """Medidas de una versión: línea base y producción (ordenada por `Batch.seq`)."""

    version: ModelVersion
    linea_base: dict[Clave, Measurement] = field(default_factory=dict)
    # clave -> [(seq, batch_id, medida)] en orden de lote.
    produccion: dict[Clave, list[tuple[int, int, Measurement]]] = field(default_factory=dict)
    lotes_evaluados: list[int] = field(default_factory=list)


def cargar_medidas(session: Session, version: ModelVersion) -> MedidasVersion:
    """Medidas de `version` por clave, separando línea base y producción."""
    salida = MedidasVersion(version=version)
    evaluaciones = session.exec(
        select(Evaluation).where(
            Evaluation.model_version_id == version.id,
            Evaluation.batch_id.is_not(None),  # type: ignore[union-attr]
        )
    ).all()
    ultima: dict[tuple[int, int], Evaluation] = {}
    for ev in evaluaciones:
        previa = ultima.get((ev.monitor_id, ev.batch_id))  # type: ignore[arg-type]
        if previa is None or (ev.id or 0) > (previa.id or 0):
            ultima[(ev.monitor_id, ev.batch_id)] = ev  # type: ignore[index]
    if not ultima:
        return salida
    ids_lote = {b for _, b in ultima}
    seq_de = {
        b.id: b.seq
        for b in session.exec(select(Batch).where(Batch.id.in_(ids_lote))).all()  # type: ignore[union-attr]
    }
    lote_de = {e.id: e.batch_id for e in ultima.values()}
    medidas = session.exec(
        select(Measurement).where(Measurement.evaluation_id.in_(list(lote_de)))  # type: ignore[attr-defined]
    ).all()
    produccion_ids: set[int] = set()
    for m in medidas:
        lote = lote_de[m.evaluation_id]
        clave: Clave = (m.monitor_type, m.metric_key, m.group_code)
        if lote == version.baseline_batch_id:
            salida.linea_base[clave] = m
        else:
            produccion_ids.add(lote)
            salida.produccion.setdefault(clave, []).append((seq_de.get(lote, 0), lote, m))
    for lista in salida.produccion.values():
        lista.sort(key=lambda t: (t[0], t[1]))
    salida.lotes_evaluados = sorted(produccion_ids, key=lambda i: (seq_de.get(i, 0), i))
    return salida


def _n_de(m: Measurement) -> int | None:
    extra: Any = m.extra_json
    n = extra.get("n") if isinstance(extra, dict) else None
    return int(n) if isinstance(n, (int, float)) and not isinstance(n, bool) else None


def _peor_estado(estados: list[str]) -> str:
    for e in _ORDEN_ESTADO:
        if e in estados:
            return e
    return "sin_datos"


def leer_lado(
    datos: MedidasVersion, clave: Clave, ventana: str
) -> dict[str, Any]:
    """Campos de `ComparacionLado` de `datos.version` para `clave`.

    `ultimo`: el último lote evaluado de ese monitor; si la clave no tiene
    valor en él, `sin_datos` con el lote en el motivo (no se rellena con un lote
    viejo). `todos`: la media de los lotes con valor, el peor estado de ellos y
    sin intervalo (una media no lo tiene). El estado es el de la medida del motor
    (se guarda con los umbrales de ese momento; no se recalcula). La deriva dice
    en `motivo` que se mide contra su propia línea base.
    """
    v = datos.version
    base = datos.linea_base.get(clave)
    lado: dict[str, Any] = {
        "version_id": v.id,
        "valor_linea_base": base.value if base is not None else None,
        "valor": None,
        "n": None,
        "interval_low": None,
        "interval_high": None,
        "estado": "sin_datos",
        "batch_ids": [],
        "motivo": None,
    }
    entradas = datos.produccion.get(clave, [])
    if not datos.lotes_evaluados:
        lado["motivo"] = f"la versión {v.label} no tiene lotes de producción evaluados"
        return lado
    if ventana != "todos":
        return _lado_ultimo(datos, clave, lado, entradas)
    con_valor = [t for t in entradas if t[2].value is not None]
    if not con_valor:
        propio = entradas[-1][2].motivo if entradas else None
        lado["motivo"] = propio or (
            f"sin medida de esta métrica en los lotes evaluados de la versión {v.label}"
        )
        return lado
    valores = [t[2].value for t in con_valor]
    ns = [_n_de(t[2]) for t in con_valor]
    lado["valor"] = sum(valores) / len(valores)  # type: ignore[arg-type]
    lado["n"] = sum(ns) if all(n is not None for n in ns) else None  # type: ignore[arg-type]
    lado["estado"] = _peor_estado([t[2].state for t in con_valor])
    lado["batch_ids"] = [t[1] for t in con_valor]
    lado["motivo"] = f"media de {len(con_valor)} lotes"
    return _cola_deriva(datos, clave, lado)


def _ultimo_lote_del_monitor(datos: MedidasVersion, monitor: str) -> tuple[int, int] | None:
    """(seq, lote) del último lote de producción con alguna medida de ese monitor."""
    vistos = [
        (seq, lote)
        for c, lista in datos.produccion.items()
        if c[0] == monitor
        for seq, lote, _ in lista
    ]
    return max(vistos) if vistos else None


def _lado_ultimo(
    datos: MedidasVersion,
    clave: Clave,
    lado: dict[str, Any],
    entradas: list[tuple[int, int, Measurement]],
) -> dict[str, Any]:
    v = datos.version
    ultimo = _ultimo_lote_del_monitor(datos, clave[0])
    esta = next((t for t in entradas if ultimo is not None and t[1] == ultimo[1]), None)
    if esta is None or esta[2].value is None:
        lote = ultimo[1] if ultimo else None
        propio = esta[2].motivo if esta is not None else None
        lado["motivo"] = propio or (
            f"el último lote evaluado de la versión {v.label} (lote {lote}) no tiene "
            "medida de esta métrica"
        )
        return lado
    _, lote, m = esta
    lado.update(
        valor=m.value, n=_n_de(m), interval_low=m.interval_low,
        interval_high=m.interval_high, estado=m.state, batch_ids=[lote],
    )
    return _cola_deriva(datos, clave, lado)


def _cola_deriva(datos: MedidasVersion, clave: Clave, lado: dict[str, Any]) -> dict[str, Any]:
    v = datos.version
    if clave[0] == "drift":
        cola = f"deriva medida contra la línea base de esta versión (lote {v.baseline_batch_id})"
        lado["motivo"] = f"{lado['motivo']}; {cola}" if lado["motivo"] else cola
    return lado
