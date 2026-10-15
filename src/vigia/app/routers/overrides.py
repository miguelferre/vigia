"""Router de overrides: vista de gestor agregada y vista propia."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from vigia.app.db import get_session
from vigia.app.schemas.overrides import (
    OverridesByClinicianResponse,
    OverridesByGroupResponse,
    OverridesCambiosResponse,
    OverridesClinicianList,
    OverridesMeResponse,
)
from vigia.app.services import overrides as overrides_service
from vigia.app.services import overrides_cambios as overrides_cambios_service
from vigia.app.services import projects as projects_service
from vigia.app.services import tarea as tarea_service
from vigia.app.services.overrides_me import overrides_me
from vigia.human.ir_adapter import MIN_N

router = APIRouter(tags=["capa-humana"])


def _resolver_version_id(session: Session, project_id: int, model_version_id: int | None) -> int:
    """Versión a consultar: la pedida, o la activa del proyecto (mismo criterio que `human.py`)."""
    project = projects_service.get_project(session, project_id)
    if model_version_id is not None:
        version = projects_service.get_version(session, model_version_id)
        if version.project_id != project.id:
            raise HTTPException(422, "esa versión no es de este modelo: elige una de las versiones del modelo")
        return version.id
    if project.active_version_id is None:
        raise HTTPException(409, "el modelo no tiene versión activa: activa una versión en la pantalla Versiones")
    return project.active_version_id


@router.get(
    "/projects/{project_id}/overrides",
    response_model=OverridesByGroupResponse | OverridesByClinicianResponse,
)
def get_overrides(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    by: Literal["subgroup", "phase", "clinician"] = "subgroup",
    model_version_id: Annotated[int | None, Query()] = None,
    min_n: Annotated[int, Query(ge=1)] = MIN_N,
) -> dict:
    """Vista de gestor: agregada por subgrupo, fase o distribución entre profesionales.

    `by=clinician` nunca lleva fila por pseudónimo: solo cuartiles y
    recuento por tramos de 0,1 entre los profesionales cualificados. Lectura sin
    evento (agregada, sin identidad, no cambia estado). `min_n` es la celda mínima
    (por defecto 30): una celda con menos decisiones da la tasa `null` con su `n`.
    """
    version_id = _resolver_version_id(session, project_id, model_version_id)
    motivo = tarea_service.motivo_capa_humana(projects_service.get_project(session, project_id))
    if motivo is not None:
        # una regresión sin rango no pasa por el camino binario de los overrides.
        if by == "clinician":
            return {
                "by": by,
                "model_version_id": version_id,
                "n_total": 0,
                "n_clinicians": 0,
                "n_qualified": 0,
                "distribution": None,
                "motivo": motivo,
            }
        return {
            "by": by,
            "model_version_id": version_id,
            "n_total": 0,
            "min_n": min_n,
            "groups": [],
            "motivo": motivo,
        }
    project = projects_service.get_project(session, project_id)
    match project.task_type:
        case "regression":
            # diferencia media entre la cifra del profesional y la del modelo.
            return overrides_service.overrides_by_group(
                session, project_id, version_id, by, min_n=min_n,
                unidad=project.target_unit, con_diferencia=True,
            )
        case "binary" | "multiclass":
            return overrides_service.overrides_by_group(session, project_id, version_id, by, min_n=min_n)
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")


@router.get("/projects/{project_id}/overrides/cambios", response_model=OverridesCambiosResponse)
def get_overrides_cambios(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    model_version_id: Annotated[int | None, Query()] = None,
    min_n: Annotated[int, Query(ge=1)] = MIN_N,
) -> dict:
    """Tabla de cambios: salida del modelo frente a decisión del profesional,
    con recuentos, en los tres tipos. Binario: `refer`/`no-refer`; multiclase: las clases;
    regresión con rango: «dentro del rango» y «fuera del rango»; regresión sin rango: tabla
    vacía con el motivo. Una fila con menos de `min_n` decisiones da sus tasas `null` con su
    `n`. Lectura sin evento."""
    version_id = _resolver_version_id(session, project_id, model_version_id)
    project = projects_service.get_project(session, project_id)
    return overrides_cambios_service.overrides_cambios(session, project, version_id, min_n=min_n)


@router.get("/projects/{project_id}/overrides/clinicians", response_model=OverridesClinicianList)
def get_overrides_clinicians(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    model_version_id: Annotated[int | None, Query()] = None,
) -> OverridesClinicianList:
    """Pseudónimos distintos del diario de esa versión: fuente del selector de profesional."""
    version_id = _resolver_version_id(session, project_id, model_version_id)
    motivo = tarea_service.motivo_capa_humana(projects_service.get_project(session, project_id))
    if motivo is not None:
        return OverridesClinicianList(clinicians=[], motivo=motivo)
    clinicians = overrides_service.overrides_clinicians(session, project_id, version_id)
    return OverridesClinicianList(clinicians=clinicians)


@router.get("/projects/{project_id}/overrides/me", response_model=OverridesMeResponse)
def get_overrides_me(
    project_id: int,
    session: Annotated[Session, Depends(get_session)],
    clinician: Annotated[str, Query(min_length=1)],
    model_version_id: Annotated[int | None, Query()] = None,
) -> dict:
    """Vista propia del profesional: sus curvas frente a la media y el p25-p75 del
    servicio. No genera evento: es de lectura y el pseudónimo se elige como
    el rol, en `vigia-session`.
    """
    version_id = _resolver_version_id(session, project_id, model_version_id)
    motivo = tarea_service.motivo_capa_humana(projects_service.get_project(session, project_id))
    if motivo is not None:
        return {
            "clinician": clinician,
            "model_version_id": version_id,
            "n_windows": 0,
            "windows": [],
            "motivo": motivo,
        }
    return overrides_me(session, project_id, version_id, clinician)
