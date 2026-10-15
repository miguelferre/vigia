"""Cuerpos y respuestas del dossier de auditoría:
`POST/GET /projects/{id}/dossiers`, `GET /dossiers/{id}`,
`POST /dossiers/{id}/reviews`, `GET /reviews/{id}`, `GET /reviews/{id}/report`,
y `GET /content/dossier-plantillas`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from vigia.app.schemas.common import MAX_DESCRIPCION, MAX_NOMBRE, ActorBody
from vigia.app.schemas.respuestas_base import Respuesta

__all__ = [
    "Dossier",
    "DossierConReviews",
    "DossierCreateBody",
    "DossierFinding",
    "DossierFuente",
    "DossierImportBody",
    "DossierPlantillaFormulario",
    "DossierPlantillaPregunta",
    "DossierPlantillas",
    "DossierReviewCreateBody",
    "DossierReviewDetalle",
    "DossierReviewResumen",
]

type DossierApproach = Literal["b0", "p3", "auto"]


class DossierCreateBody(ActorBody):
    """Cuerpo de `POST /projects/{id}/dossiers`."""

    system_name: str | None = Field(default=None, max_length=MAX_NOMBRE)
    domain: str | None = Field(default=None, max_length=MAX_DESCRIPCION)
    profile: dict[str, str] = Field(default_factory=dict)
    experience: dict[str, str] = Field(default_factory=dict)
    inventory: dict[str, str] = Field(default_factory=dict)
    include_telemetry: bool = False


# ruta de importación del `dossier.json` de `interaction_review`
# (nombre fijado antes de repartir).
RUTA_DOSSIER_IMPORT = "/projects/{project_id}/dossiers/import"


class DossierFuente(BaseModel):
    """Una entrada de `sources[]` del `dossier.json` del paquete."""

    id: str
    kind: str
    label: str
    content: str


class DossierImportBody(ActorBody):
    """Cuerpo de `POST /projects/{id}/dossiers/import`: los campos del
    `dossier.json` de `interaction_review` más actor y motivo. La respuesta
    es un `Dossier`; `summary` y las fuentes que no encajan en `profile`,
    `experience` o `inventory` van a una clave propia, nunca se pierden."""

    system_name: str = Field(max_length=MAX_NOMBRE)
    domain: str = Field(max_length=MAX_DESCRIPCION)
    summary: str = ""
    sources: list[DossierFuente] = Field(default_factory=list)
    include_telemetry: bool = False


class Dossier(Respuesta):
    """Serialización del dossier (`POST`/`GET`); nunca las respuestas
    completas fuera de aquí (privacidad de `interaction_review`, §8.2)."""

    id: int | None
    project_id: int
    system_name: str
    domain: str
    profile: dict[str, str]
    experience: dict[str, str]
    inventory: dict[str, str]
    telemetry_included: bool
    summary: str
    sha256: str
    created_at: str


class DossierReviewResumen(Respuesta):
    """Una revisión embebida en `GET /dossiers/{id}` (`reviews`), sin
    `report_html` ni `findings_json` completos."""

    id: int | None
    dossier_id: int
    approach: DossierApproach
    status: Literal["pendiente", "en_curso", "terminada", "error", "cancelada"]
    n_findings: int | None
    package_version: str
    job_id: int | None
    error: str | None
    created_at: str
    finished_at: str | None


class DossierConReviews(Dossier):
    """`GET /dossiers/{id}`: un dossier con sus revisiones embebidas."""

    reviews: list[DossierReviewResumen]


class DossierReviewCreateBody(ActorBody):
    """Cuerpo de `POST /dossiers/{id}/reviews`."""

    approach: DossierApproach = "b0"
    corpus: str = "todas"
    dedup: bool = True
    crosswalk: bool = True


class DossierFinding(Respuesta):
    """Un hallazgo de la revisión (`interaction_review.schemas.Finding`)."""

    id: str
    title: str
    guideline_ids: list[str]
    locus: str
    evidence: str
    anti_pattern: str | None
    severity: Literal["low", "medium", "high"]
    rationale: str
    recommendation: str
    merged_count: int


class DossierCrosswalkRef(Respuesta):
    """Una referencia regulatoria dentro de un marco (`regulatory.crosswalk`)."""

    ref: str
    guidelines: list[str]


class DossierReviewDetalle(Respuesta):
    """`GET /reviews/{id}`: hallazgos, crosswalk y bloque de reproducibilidad."""

    id: int | None
    dossier_id: int
    approach: DossierApproach
    status: Literal["pendiente", "en_curso", "terminada", "error", "cancelada"]
    findings: list[DossierFinding]
    crosswalk: dict[str, list[DossierCrosswalkRef]]
    package_version: str
    corpus_hash: str
    dossier_sha256: str
    prompt_sha256: str | None
    llm_backend: str | None
    model: str | None
    error: str | None
    created_at: str
    finished_at: str | None


class DossierPlantillaPregunta(Respuesta):
    id: str
    seccion: str
    texto: str
    original: str


class DossierPlantillaFormulario(Respuesta):
    titulo: str
    quien: str
    preguntas: list[DossierPlantillaPregunta]


class DossierPlantillas(Respuesta):
    """`GET /content/dossier-plantillas`: las tres plantillas reales de
    `interaction_review`, traducidas al vocabulario de Vigía."""

    system_card: DossierPlantillaFormulario
    usage_experience: DossierPlantillaFormulario
    document_inventory: DossierPlantillaFormulario

