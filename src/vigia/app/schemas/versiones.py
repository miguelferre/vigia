"""Respuesta de la comparación de versiones.

`GET /projects/{id}/versions/compare?a=&b=&ventana=` compara dos versiones del
mismo proyecto por evaluaciones: cada versión contra su propia
línea base, métrica a métrica, con los umbrales del proyecto. Las alertas no se
comparan porque son del proyecto; se listan aparte con la versión de su última
medida en `alerta` o `inestable`.

Los rellena `services/comparacion_versiones.py` y los lee el MCP.
"""

from __future__ import annotations

from typing import Literal

from vigia.app.schemas.respuestas_base import EstadoMotor, MonitorType, Respuesta

__all__ = [
    "AlertaVivaVersion",
    "ComparacionFila",
    "ComparacionLado",
    "ComparacionVersiones",
    "DireccionComparacion",
    "VentanaComparacion",
    "VersionComparada",
]

# `ultimo`: el último lote de producción evaluado de cada versión.
# `todos`: la media de todos sus lotes de producción evaluados.
type VentanaComparacion = Literal["ultimo", "todos"]
# `sin_datos`: algún lado no tiene valor (sin lotes evaluados o sin la medida).
# `cambia`: una medida sin sentido de mejora (la proporción de una clase)
# que se movió más allá de la regla de igualdad: ni mejora ni empeora.
type DireccionComparacion = Literal["mejora", "empeora", "igual", "cambia", "sin_datos"]


class VersionComparada(Respuesta):
    """Una de las dos versiones resueltas: el cliente ve qué se comparó aunque
    no pasara `a` ni `b` (por defecto, la activa anterior y la activa)."""

    id: int
    label: str
    is_active: bool
    baseline_batch_id: int | None
    # Lotes de producción de esta versión con evaluación (0 si ninguno).
    n_lotes_evaluados: int


class ComparacionLado(Respuesta):
    """Valor de una métrica en una versión, frente a su propia línea base."""

    version_id: int
    # Valor de la medida en la evaluación de la línea base de esta versión.
    valor_linea_base: float | None
    # Último lote evaluado (`ventana=ultimo`) o media de sus lotes (`todos`).
    valor: float | None
    # Tamaño de muestra de la medida (filas o filas del grupo), si el motor lo da.
    n: int | None
    interval_low: float | None
    interval_high: float | None
    # Estado contra los umbrales del proyecto; `sin_datos` si no hay valor.
    estado: EstadoMotor
    # Lotes que entran en `valor` (1 con `ultimo`, varios con `todos`).
    batch_ids: list[int]
    # Por qué no hay valor, o cómo se leyó (deriva: distancia a su línea base).
    motivo: str | None


class ComparacionFila(Respuesta):
    """Una métrica con umbral de un monitor, comparada entre las dos versiones."""

    monitor_type: MonitorType
    metric_key: str
    group_code: str | None
    threshold_low: float | None
    threshold_high: float | None
    a: ComparacionLado
    b: ComparacionLado
    # `b.valor - a.valor`; `None` si algún lado no tiene valor.
    diferencia: float | None
    direccion: DireccionComparacion
    # Regla aplicada: «más alto es mejor», «más bajo es mejor», «más
    # cerca del centro del intervalo», «intervalos solapados», «distancia a
    # su propia línea base» o por qué es `sin_datos`.
    motivo: str


class AlertaVivaVersion(Respuesta):
    """Alerta viva del proyecto con la versión de su última medida en
    `alerta` o `inestable` de su clave (no usa `Alert.last_evaluation_id`)."""

    alert_id: int
    monitor_type: str
    metric_key: str
    group_code: str | None
    status: str
    title: str
    # `None` con `motivo` si ninguna medida de la clave estuvo en alerta o inestable.
    model_version_id: int | None
    version_label: str | None
    motivo: str | None


class ComparacionVersiones(Respuesta):
    """Respuesta de `GET /projects/{id}/versions/compare`."""

    project_id: int
    ventana: VentanaComparacion
    version_a: VersionComparada
    version_b: VersionComparada
    filas: list[ComparacionFila]
    # Por qué `filas` está vacía (ninguna medida con umbral); nulo si hay filas.
    motivo: str | None = None
    alertas_vivas: list[AlertaVivaVersion]
    # Frase de cabecera fija: «las alertas son del modelo, no de la versión».
    nota_alertas: str
