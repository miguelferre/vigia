"""Diario de uso multiclase.

En un proyecto multiclase, `human_decision`, `model_output` y `ground_truth`
del CSV llevan nombres de clase. Se validan contra `classes_json` del proyecto
(con `clave_clase`) y se guardan en `usage_log.human_class`, `model_class` y
`truth_class`; los enteros de siempre guardan el 0/1 de pertenencia al
conjunto favorable, para que la codificación y la composición sigan
iguales. Vive aparte de `human_layer.py` para no engordarlo.

`refer`/`no-refer` no es vocabulario de multiclase y la inversión por
`valor_favorable` tampoco: las dos dan 422 con qué hacer.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from vigia.app.models import Batch, Dataset, Project
from vigia.app.services import tarea as tarea_service
from vigia.core.schema import ColumnMapping, MappingTemplate, TaskSpec, clave_clase

__all__ = [
    "MENSAJE_SIN_CLASES",
    "MENSAJE_VALOR_FAVORABLE",
    "etiqueta_de_fila",
    "favorables_del_proyecto",
    "parse_clase",
    "tarea_de_uso",
]

MENSAJE_VALOR_FAVORABLE = (
    "En un modelo multiclase el registro de uso no se recodifica con valor_favorable: "
    "el fichero debe traer los nombres de clase en human_decision, model_output y "
    "ground_truth. Quita valor_favorable y sube el registro con los nombres de clase"
)

MENSAJE_SIN_CLASES = (
    "El modelo multiclase aún no tiene clases fijadas: se declaran al crear el proyecto "
    "o se fijan al congelar la línea base. Congela la línea base y sube el registro de nuevo"
)

_VOCABULARIO_BINARIO = ("refer", "no-refer")


def favorables_del_proyecto(session: Session, project: Project) -> list[Any]:
    """Conjunto favorable del proyecto: el del mapeo del último lote y, a
    falta de lotes, el de la plantilla. Vacío si no se ha fijado."""
    lote = session.exec(
        select(Batch).where(Batch.project_id == project.id).order_by(Batch.seq.desc())  # type: ignore[attr-defined]
    ).first()
    if lote is not None and lote.dataset_id is not None:
        dataset = session.get(Dataset, lote.dataset_id)
        if dataset is not None and dataset.mapping_json:
            try:
                return list(ColumnMapping(**dataset.mapping_json).favorables)
            except ValueError:
                pass
    if project.mapping_template_json:
        try:
            return list(MappingTemplate(**project.mapping_template_json).favorables)
        except (TypeError, ValueError):
            pass
    return []


def tarea_de_uso(session: Session, project: Project) -> TaskSpec | None:
    """`TaskSpec` del proyecto para el diario de uso, o `None` en binario (el diario sigue como
    siempre). Multiclase sin clases fijadas: 422.
    En regresión, el `TaskSpec` con la unidad y el rango favorable que derivan
    la decisión; sin rango, 422 con el motivo (nunca cae al camino binario)."""
    match project.task_type:
        case "binary":
            return None
        case "multiclass":
            pass
        case "regression":
            tarea_service.guardia_capa_humana(project)
            return TaskSpec(
                task_type="regression",
                unidad=project.target_unit,
                rangos_favorables=tarea_service.rangos_capa_humana(project),
            )
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")
    clases = tarea_service.clases_del_proyecto(project)
    if not clases:
        raise HTTPException(422, MENSAJE_SIN_CLASES)
    return TaskSpec(
        task_type="multiclass",
        classes=tuple(clases),
        favorables=tuple(favorables_del_proyecto(session, project)),
    )


def _lista(tarea: TaskSpec) -> str:
    return ", ".join(tarea.claves)


def parse_clase(
    valor: Any, tarea: TaskSpec, *, fila_n: int, columna: str
) -> tuple[str | None, int | None]:
    """Clase declarada que corresponde a `valor` y su pertenencia 0/1 al
    conjunto favorable. `(None, None)` si la celda está en blanco.

    Orden: igual por `clave_clase` (también «1.0» frente a 1), igual sin
    distinguir mayúsculas con una sola clase, `refer`/`no-refer`
 y clase desconocida (422 con la fila y las clases)."""
    if valor is None:
        return None, None
    texto = str(valor).strip()
    if not texto or texto.lower() == "nan":
        return None, None
    claves = list(tarea.claves)
    clave = clave_clase(texto)
    if clave not in claves:
        # Solo «1.0» frente a 1; «01», «+1» o «1e0» no son alias.
        numero = float(texto) if re.fullmatch(r"-?\d+\.0+", texto) else None
        if numero is not None and clave_clase(numero) in claves:
            clave = clave_clase(numero)
        else:
            iguales = [c for c in claves if c.casefold() == texto.casefold()]
            if len(iguales) == 1:
                clave = iguales[0]
    if clave in claves:
        clase = tarea.classes[claves.index(clave)]
        return clave, int(tarea.es_favorable(clase))
    if texto.casefold() in _VOCABULARIO_BINARIO:
        raise HTTPException(
            422,
            f"la fila {fila_n} trae {texto!r} en {columna}: refer y no-refer son de los modelos "
            f"binarios. En este modelo multiclase escribe el nombre de una clase ({_lista(tarea)})",
        )
    raise HTTPException(
        422,
        f"la fila {fila_n} trae la clase {texto!r} en {columna}, que no está entre las clases "
        f"del modelo ({_lista(tarea)}): escribe el nombre de una de ellas",
    )


def etiqueta_de_fila(entero: int | None, clase: str | None, etiquetas: dict[int, str]) -> str | None:
    """Lo que ve el motor de cruzadas y la exportación: el nombre de clase si
    la fila lo tiene; si no, `refer`/`no-refer` desde el entero."""
    if clase is not None:
        return clase
    return etiquetas.get(entero) if entero is not None else None
