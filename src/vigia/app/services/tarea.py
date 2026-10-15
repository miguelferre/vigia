"""Tipo de tarea del proyecto en el backend.

Construye el `TaskSpec` que la ingesta y la evaluación pasan al motor desde el
proyecto y el mapeo, valida el mapeo por tipo en los cuatro puntos de entrada
(alta, plantilla, `PUT /datasets/{id}/mapping` e ingesta) y traduce
`DatosNoValidos` a 422 en español. Sin lógica de motor: eso vive en `core/`.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlmodel import Session

from vigia.app.bus import EventBus
from vigia.app.events import ACTOR_SISTEMA, record_event
from vigia.app.models import Project
from vigia.core.schema import (
    MOTIVO_CAPA_HUMANA_SIN_RANGO,
    ColumnMapping,
    DatosNoValidos,
    MappingTemplate,
    RangoFavorable,
    TaskSpec,
    clave_clase,
    validar_mapeo_por_tipo,
    validar_rangos,
)

__all__ = [
    "MENSAJE_CAMBIO_TIPO",
    "MENSAJE_CAMBIO_UNIDAD_O_RANGO",
    "clases_del_proyecto",
    "guardia_capa_humana",
    "limpiar_positive_label",
    "mismas_clases",
    "motivo_capa_humana",
    "rangos_capa_humana",
    "rangos_del_proyecto",
    "registrar_positive_label_entrante",
    "tarea_del_proyecto",
    "texto_guardia_capa_humana",
    "texto_validacion",
    "validar_mapeo_http",
    "validar_plantilla_http",
    "validar_tipo_http",
]

MENSAJE_CAMBIO_TIPO = (
    "El tipo de tarea no cambia después del alta: crea un proyecto nuevo con el tipo "
    "que necesitas"
)

# La pertenencia al rango se guarda al ingerir y en el diario de uso, así que
# el rango y la unidad no cambian una vez fijada la línea base.
MENSAJE_CAMBIO_UNIDAD_O_RANGO = (
    "La unidad de la salida y el rango favorable no cambian después de congelar la línea "
    "base: la pertenencia al rango ya está guardada en los lotes. Crea un proyecto nuevo "
    "con la unidad y el rango que necesitas"
)

# Qué hacer ante la guardia de la capa humana de regresión sin rango. La guardia añade
# esta frase al motivo (`MOTIVO_CAPA_HUMANA_SIN_RANGO`). El MCP repite el texto (no importa
# `app.services`) y un test lo compara con `texto_guardia_capa_humana`. Con rango la capa humana
# de regresión está abierta: ya no hay guardia.
QUE_HACER_SIN_RANGO = (
    "Crea un proyecto de regresión con rango favorable: el rango no cambia después de "
    "congelar la línea base"
)

Mapeo = ColumnMapping | MappingTemplate


def texto_validacion(exc: ValueError) -> str:
    """Texto en español de un error de validación de un modelo del motor
    (`MappingTemplate`, `ColumnMapping`): los mensajes de sus validadores, sin la
    cabecera de pydantic («1 validation error for ...», «Value error, »)."""
    if isinstance(exc, ValidationError):
        partes = [str(e.get("msg", "")).removeprefix("Value error, ") for e in exc.errors()]
        return "; ".join(p for p in partes if p) or "el mapeo no es válido"
    return " ".join(str(a) for a in exc.args) or "el mapeo no es válido"


def validar_tipo_http(task_type: str) -> None:
    """Los tres tipos de tarea del alta."""
    match task_type:
        case "binary" | "multiclass" | "regression":
            return
        case _:
            raise HTTPException(
                422,
                f"task_type debe ser binary, multiclass o regression; se recibió {task_type!r}",
            )


def clases_del_proyecto(project: Project) -> list[int | str] | None:
    """Clases declaradas del proyecto (`classes_json`), o `None` si no hay."""
    clases = project.classes_json
    return list(clases) if clases else None


def mismas_clases(a: list[Any], b: list[Any]) -> bool:
    """Misma lista de clases en el mismo orden (por `clave_clase`)."""
    return [clave_clase(x) for x in a] == [clave_clase(x) for x in b]


def _clases_coinciden(project: Project, mapping: Mapeo) -> None:
    """Las clases del mapeo no pueden contradecir a las del proyecto."""
    del_proyecto = clases_del_proyecto(project)
    if del_proyecto and mapping.classes and not mismas_clases(mapping.classes, del_proyecto):
        raise DatosNoValidos(
            "Las clases del mapeo ("
            + ", ".join(str(c) for c in mapping.classes)
            + ") no coinciden con las del proyecto ("
            + ", ".join(str(c) for c in del_proyecto)
            + "), que se fijan al crear el proyecto o al congelar la línea base. "
            "Si el modelo ha cambiado de clases, crea un proyecto nuevo."
        )


def validar_mapeo_http(project: Project | str, mapping: Mapeo, classes: list[Any] | None = None) -> None:
    """Reglas por tipo; `DatosNoValidos` sale como 422 en español.

    `project` puede ser el proyecto o directamente su `task_type` (el alta aún
    no tiene proyecto). `classes` explícito es la lista resuelta; sin él se usa
    la del proyecto y, a falta de ella, la del mapeo.
    """
    task_type = project if isinstance(project, str) else project.task_type
    if classes is None and not isinstance(project, str):
        classes = clases_del_proyecto(project)
    try:
        if not isinstance(project, str):
            _clases_coinciden(project, mapping)
        validar_mapeo_por_tipo(mapping, task_type, classes)  # type: ignore[arg-type]
    except DatosNoValidos as exc:
        raise HTTPException(422, str(exc)) from exc


def validar_plantilla_http(
    project: Project | str,
    plantilla: MappingTemplate,
    classes: list[Any] | None = None,
) -> None:
    """Valida una plantilla de mapeo por tipo (alta y PATCH, interfaz §2.5).

    Como `validar_mapeo_http`, pero una plantilla multiclase sin clases (ni en
    ella ni en el proyecto) pasa: las clases pueden salir de la línea base y el recuento de 3 a 20 se exige cuando se conocen."""
    task_type = project if isinstance(project, str) else project.task_type
    match task_type:
        case "multiclass":
            conocidas = list(classes or plantilla.classes or [])
            if not isinstance(project, str):
                conocidas = conocidas or (clases_del_proyecto(project) or [])
            if not conocidas:
                return
            classes = conocidas
        case "binary" | "regression":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {task_type!r}")
    validar_mapeo_http(project, plantilla, classes)


def rangos_del_proyecto(project: Project) -> tuple[RangoFavorable, ...] | None:
    """Rango favorable fijado en el proyecto (`favorable_ranges_json`). `None`
    si aún no está fijado (antes de congelar la línea base: manda el del mapeo o la
    plantilla); `()` si se fijó «sin rango»."""
    crudo = project.favorable_ranges_json
    return None if crudo is None else validar_rangos(crudo)


def _rango_efectivo(project: Project) -> tuple[RangoFavorable, ...]:
    """Rango favorable que rige hoy: el fijado en el proyecto o, a falta de él, el de la
    plantilla de mapeo. Un valor guardado que no valida cuenta como «sin rango»."""
    try:
        fijado = rangos_del_proyecto(project)
        if fijado is not None:
            return fijado
        plantilla = project.mapping_template_json
        return validar_rangos(plantilla.get("favorable_ranges") if isinstance(plantilla, dict) else None)
    except DatosNoValidos:
        return ()


def rangos_capa_humana(project: Project) -> tuple[RangoFavorable, ...]:
    """Rango favorable con el que el diario de uso de una regresión deriva la decisión
    (el fijado en el proyecto o, antes de congelar la línea base, el de la plantilla). Vacío:
    sin rango, y la capa humana no tiene datos."""
    return _rango_efectivo(project)


def motivo_capa_humana(project: Project) -> str | None:
    """Por qué la capa humana no tiene datos en este proyecto, o `None` si los tiene
    (clasificación, o regresión con rango favorable: ahí el diario guarda la decisión derivada). Sin rango favorable, `MOTIVO_CAPA_HUMANA_SIN_RANGO`: nunca cae al camino binario."""
    match project.task_type:
        case "binary" | "multiclass":
            return None
        case "regression":
            return None if _rango_efectivo(project) else MOTIVO_CAPA_HUMANA_SIN_RANGO
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")


def texto_guardia_capa_humana(*, sin_rango: bool = True) -> str:
    """El 422 de la guardia de la capa humana de regresión sin rango: el motivo más
    qué hacer. Con rango no hay guardia: `sin_rango=False` es un error de quien llama."""
    if not sin_rango:
        raise ValueError("con rango favorable la capa humana de regresión no tiene guardia")
    return (
        f"No se puede subir el registro de uso: {MOTIVO_CAPA_HUMANA_SIN_RANGO}. "
        f"{QUE_HACER_SIN_RANGO}"
    )


def guardia_capa_humana(project: Project) -> None:
    """422 con el motivo si el proyecto es de regresión sin rango favorable (la subida del
    registro de uso nunca cae al camino binario). No hace nada en clasificación ni en
    regresión con rango."""
    if motivo_capa_humana(project) is not None:
        raise HTTPException(422, texto_guardia_capa_humana(sin_rango=True))


def tarea_del_proyecto(project: Project, mapping: Mapeo) -> TaskSpec:
    """`TaskSpec` del proyecto con el mapeo resuelto (interfaz §2.2).

    Binario sin clases: `TaskSpec.binario()`, el comportamiento de antes de los tipos multiclase y regresión.
    Regresión: la unidad y el rango del proyecto mandan sobre los del mapeo una vez
    fijados. Lanza `DatosNoValidos` (el llamador la traduce o la deja salir al trabajo).
    """
    _clases_coinciden(project, mapping)
    mapeo = mapping
    match project.task_type:
        case "binary":
            validar_mapeo_por_tipo(mapeo, "binary", clases_del_proyecto(project))
            return TaskSpec.binario()
        case "multiclass":
            return TaskSpec.desde_mapeo("multiclass", mapeo, classes=clases_del_proyecto(project))
        case "regression":
            return TaskSpec.desde_mapeo(
                "regression",
                mapeo,
                unidad=project.target_unit,
                rangos=rangos_del_proyecto(project),
            )
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")


def limpiar_positive_label(
    session: Session, project: Project, *, bus: EventBus | None = None
) -> bool:
    """`MappingTemplate` ya no tiene `positive_label` y su validador
    `before` lo borra sin rastro. Para que quede constancia, esta función lee el
    JSON crudo de la plantilla guardada: si trae `positive_label` con valor deja
    un aviso en el diario (una vez, porque lo quita del JSON guardado) y lo
    elimina. Con `positive_label: null` lo quita sin aviso. No hace commit.
    Devuelve `True` si cambió la plantilla guardada."""
    plantilla = project.mapping_template_json
    if not isinstance(plantilla, dict) or "positive_label" not in plantilla:
        return False
    valor = plantilla["positive_label"]
    project.mapping_template_json = {k: v for k, v in plantilla.items() if k != "positive_label"}
    session.add(project)
    session.flush()
    if valor is not None:
        record_event(
            session,
            actor_kind=ACTOR_SISTEMA[0],
            actor_id=ACTOR_SISTEMA[1],
            action="proyecto.positive_label_ignorado",
            object_type="project",
            object_id=project.id,
            project_id=project.id,
            before={"positive_label": valor},
            bus=bus,
        )
    return True


def registrar_positive_label_entrante(
    session: Session, project: Project, valor: Any, *, bus: EventBus | None = None
) -> None:
    """Aviso de un `positive_label` que llegó en una plantilla nueva (PATCH)
    y que `MappingTemplate` ya quitó. No hace commit."""
    record_event(
        session,
        actor_kind=ACTOR_SISTEMA[0],
        actor_id=ACTOR_SISTEMA[1],
        action="proyecto.positive_label_ignorado",
        object_type="project",
        object_id=project.id,
        project_id=project.id,
        before={"positive_label": valor},
        bus=bus,
    )
