"""Esquemas de proyectos, versiones de modelo y estado del proyecto.

Las respuestas (proyecto, versión, monitor, detalle, estado) se construyen como
`dict` en `services/projects.py` (`project_to_dict`, `version_to_dict`,
`monitor_to_dict`, `project_detail`, `project_state`) para controlar qué campos
se exponen (`hmac_salt` dejó de existir con una migración). Aquí solo
van los cuerpos de petición.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from vigia.app.schemas.common import (
    MAX_DESCRIPCION,
    MAX_NOMBRE,
    MAX_NOMBRE_CLASE,
    ActorBody,
    Nombre,
    NombreClase,
    no_blanco,
)
from vigia.app.schemas.respuestas_base import DeploymentStage
from vigia.core.schema import MappingTemplate, RangoFavorable, TaskType

__all__ = [
    "DOMINIOS_SIMULADOR",
    "MENSAJE_SIM_LOGISTIC",
    "ActivateVersionBody",
    "BaselineBody",
    "FairnessIntervalMethod",
    "ModelKind",
    "ProjectCreate",
    "ProjectPatch",
    "ProjectResetBody",
    "VersionCreate",
]


# Tipo de modelo. `sim_logistic` es el modelo del
# simulador: solo tiene sentido en los dominios del simulador (la demo, el
# laboratorio y los tests lo crean con `reuma` o `digestivo`); en `libre`, 422.
ModelKind = Literal["external_files", "executable", "sim_logistic"]
DOMINIOS_SIMULADOR = frozenset({"reuma", "digestivo"})
MENSAJE_SIM_LOGISTIC = (
    "model_kind 'sim_logistic' es el modelo del simulador de Vigía y solo vale en los "
    "dominios de la demo (reuma, digestivo): para tu modelo usa 'external_files' "
    "(ficheros de predicciones) o 'executable' (sube el modelo en ONNX)"
)

# Método del intervalo de equidad. `None` en el alta: el
# servicio pone `lote` en los proyectos nuevos; `ventanas` es el original.
FairnessIntervalMethod = Literal["ventanas", "lote"]

# el nombre de una clase entra en el código de grupo de cada medida de cada
# evaluación; sin tope se multiplicaría. `core.schema.Clase` no lo trae.
ClaseAlta = int | NombreClase


def _plantilla_con_clases_acotadas(plantilla: MappingTemplate | None) -> None:
    """422 si la plantilla trae un nombre de clase de más de `MAX_NOMBRE_CLASE` caracteres."""
    if plantilla is None:
        return
    for clase in plantilla.classes:
        if isinstance(clase, str) and len(clase) > MAX_NOMBRE_CLASE:
            raise ValueError(
                f"un nombre de clase de la plantilla pasa de {MAX_NOMBRE_CLASE} caracteres"
            )


class ProjectCreate(BaseModel):
    """Cuerpo de creación de un proyecto. Sin actor/motivo: crear no los exige.

    `extra="forbid"`, un campo desconocido da 422 en vez de
    descartarse en silencio. `task_type` `regression` lo rechaza el servicio con
    el mensaje de formato. `classes` (multiclase) también puede venir en la
    plantilla de mapeo; si vienen las dos, mandan las de `classes`.
    """

    model_config = ConfigDict(extra="forbid")

    name: Nombre
    domain: str = "libre"
    # opcional. En clasificación sin valor es 1 (el defecto de siempre); en
    # regresión no hay clase favorable y el servicio lo ignora.
    favorable_label: int | None = None
    task_type: TaskType = "binary"
    classes: list[ClaseAlta] = Field(default_factory=list)
    # unidad de la salida y rango favorable de una regresión (de 1 a 3
    # intervalos `[min, max]`, extremo nulo abierto). Mandan sobre los de la plantilla.
    target_unit: str | None = Field(default=None, max_length=MAX_NOMBRE_CLASE)
    favorable_ranges: list[RangoFavorable] = Field(default_factory=list)
    store_features: bool = True
    model_kind: ModelKind = "external_files"
    deployment_stage: DeploymentStage = "desarrollo"
    # plantilla de mapeo, si el proyecto recibirá
    # feedback y método del intervalo.
    mapping_template: MappingTemplate | None = None
    acepta_feedback: bool = True
    fairness_interval_method: FairnessIntervalMethod | None = None

    _name_no_blanco = field_validator("name")(no_blanco)

    @model_validator(mode="after")
    def _sim_logistic_solo_en_la_demo(self) -> ProjectCreate:
        if self.model_kind == "sim_logistic" and self.domain not in DOMINIOS_SIMULADOR:
            raise ValueError(MENSAJE_SIM_LOGISTIC)
        return self

    @model_validator(mode="after")
    def _clases_de_la_plantilla_acotadas(self) -> ProjectCreate:
        _plantilla_con_clases_acotadas(self.mapping_template)
        return self


class ProjectPatch(ActorBody):
    """Cuerpo del PATCH de proyecto: nombre, descripción, calibración o si guarda features.

    `description=None` es "no tocar" (igual que `calibration_until`); para
    vaciarla se manda `clear_description=True`.
    """

    name: str | None = Field(default=None, max_length=MAX_NOMBRE)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPCION)
    clear_description: bool = False
    calibration_until: str | None = None
    clear_calibration: bool = False
    store_features: bool | None = None
    explain_auto: bool | None = None
    explain_method: str | None = None
    # `None` es "no tocar" (mismo convenio que el resto de campos opcionales).
    deployment_stage: DeploymentStage | None = None
    # `None` es "no tocar"; la plantilla se sustituye entera.
    mapping_template: MappingTemplate | None = None
    acepta_feedback: bool | None = None
    # el tipo de tarea no cambia después del alta. Se acepta para dar
    # un 409 claro (y no un 422 de campo desconocido) si alguien intenta cambiarlo.
    task_type: TaskType | None = None
    # `MappingTemplate` quita `positive_label` antes de validar; este campo
    # interno (fuera del OpenAPI) guarda el valor entrante para dejar el aviso.
    # Lo rellena `_recoger_positive_label`; lo que mande el cliente se descarta.
    positive_label_descartado: Annotated[Any, SkipJsonSchema()] = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _recoger_positive_label(cls, datos: Any) -> Any:
        if not isinstance(datos, dict):
            return datos
        datos = {k: v for k, v in datos.items() if k != "positive_label_descartado"}
        plantilla = datos.get("mapping_template")
        if isinstance(plantilla, dict) and plantilla.get("positive_label") is not None:
            datos["positive_label_descartado"] = plantilla["positive_label"]
        return datos

    @model_validator(mode="after")
    def _clases_de_la_plantilla_acotadas(self) -> ProjectPatch:
        _plantilla_con_clases_acotadas(self.mapping_template)
        return self


class ProjectResetBody(ActorBody):
    """Cuerpo del reinicio de proyecto: exige confirmación explícita."""

    confirm: bool = False


class VersionCreate(ActorBody):
    """Cuerpo de creación de una versión de modelo."""

    label: Nombre
    # `sim_logistic` fuera de los dominios del simulador lo rechaza el servicio,
    # que conoce el dominio del proyecto.
    model_kind: ModelKind = "external_files"
    fairness_window_n: int | None = None
    # `None`: la versión nueva hereda el método de la activa.
    fairness_interval_method: FairnessIntervalMethod | None = None

    _label_no_blanco = field_validator("label")(no_blanco)


class BaselineBody(ActorBody):
    """Cuerpo de congelación de baseline de una versión."""

    batch_id: int
    laboratorio: bool = False


class ActivateVersionBody(ActorBody):
    """Cuerpo de activación de una versión.

    `congelar_linea_base`, si se manda, es el id de un lote o de un dataset
    con lotes de esta versión: la activación congela la línea base en el
    mismo paso. La API sigue permitiendo activar sin congelar (por defecto).
    """

    congelar_linea_base: int | None = None
