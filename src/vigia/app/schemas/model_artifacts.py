"""Esquema de respuesta de la subida del artefacto del modelo.

La subida es multipart (form `file`, `artifact_kind`, `confirmacion_pickle`),
sin cuerpo JSON: se declara con `Form`/`File` en `routers/model_artifacts.py`,
igual que `routers/datasets.py:upload_dataset`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ArtifactInputOut", "ModelArtifactUploadResponse"]


class ArtifactInputOut(BaseModel):
    """Una entrada del modelo (`ModelVersion.artifact_inputs_json`): nombre
    crudo de `mapping.feature_cols`, tipo declarado por el modelo y si Vigía
    la trata como numérica o categórica."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    kind: Literal["numerica", "categorica"]


class ModelArtifactUploadResponse(BaseModel):
    """Respuesta de `POST /model-versions/{id}/artifact`.

    `avisos` lleva el texto del pickle («un fichero pickle ejecuta código al
    abrirse...») cuando `artifact_kind == "pickle"`; vacío con ONNX.
    """

    model_config = ConfigDict(extra="forbid")

    model_version_id: int
    model_kind: str
    artifact_kind: Literal["onnx", "pickle"]
    artifact_sha256: str
    artifact_inputs: list[ArtifactInputOut]
    artifact_uploaded_at: str
    avisos: list[str] = Field(default_factory=list)
