"""Router del artefacto del modelo ejecutable.

`POST /model-versions/{id}/artifact` sube, guarda y valida el fichero.
Multipart, mismo patrón que `routers/datasets.py:upload_dataset`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlmodel import Session

from vigia.app.db import get_session
from vigia.app.errores import no_encontrado
from vigia.app.events import Actor, get_actor, get_correlation_id
from vigia.app.models import ModelVersion
from vigia.app.schemas.model_artifacts import ModelArtifactUploadResponse
from vigia.app.services import model_registry
from vigia.app.services.subidas import leer_subida

router = APIRouter(tags=["modelo"])


def _get_version(session: Session, version_id: int) -> ModelVersion:
    version = session.get(ModelVersion, version_id)
    if version is None:
        raise no_encontrado("versión", version_id, "versiones")
    return version


@router.post(
    "/model-versions/{version_id}/artifact",
    response_model=ModelArtifactUploadResponse,
)
def upload_artifact(
    version_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    actor: Annotated[Actor, Depends(get_actor)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    file: Annotated[UploadFile, File()],
    artifact_kind: Annotated[str, Form()] = "onnx",
    confirmacion_pickle: Annotated[bool, Form()] = False,
) -> dict:
    """Sube el modelo, lo valida y deja la versión `executable`."""
    version = _get_version(session, version_id)
    contenido = leer_subida(file.file)
    version, avisos = model_registry.upload_artifact(
        session,
        version,
        file_bytes=contenido,
        filename=file.filename or "modelo",
        artifact_kind=artifact_kind,
        confirmacion_pickle=confirmacion_pickle,
        data_dir=request.app.state.settings.data_dir,
        actor=actor,
        correlation_id=correlation_id,
        bus=request.app.state.bus,
    )
    return {
        "model_version_id": version.id,
        "model_kind": version.model_kind,
        "artifact_kind": version.artifact_kind,
        "artifact_sha256": version.artifact_sha256,
        "artifact_inputs": version.artifact_inputs_json or [],
        "artifact_uploaded_at": version.artifact_uploaded_at,
        "avisos": avisos,
    }
