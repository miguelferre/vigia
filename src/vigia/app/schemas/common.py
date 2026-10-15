"""Esquemas comunes a toda la API: actor y motivo de las mutaciones, y páginas."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "MAX_ACTOR",
    "MAX_ACTOR_DETALLE",
    "MAX_DESCRIPCION",
    "MAX_MOTIVO",
    "MAX_NOMBRE",
    "MAX_NOMBRE_CLASE",
    "MAX_TEXTO_LARGO",
    "ActorBody",
    "ErrorDetail",
    "ListResponse",
    "Nombre",
    "NombreActor",
    "NombreClase",
    "TextoDescripcion",
    "TextoLargo",
    "TextoMotivo",
    "no_blanco",
    "recordar_actor_detalle",
]

# Máximo de `actor_detalle`, el contexto que un agente añade a su nombre.
MAX_ACTOR_DETALLE = 200

# cotas de los textos libres que acaban en el diario, que es de solo
# añadir: lo que entra no se puede retirar. Ningún motivo fijo de los tests, de la
# interfaz ni del MCP pasa de 120 caracteres (medido con `rg`), así que las cotas
# dejan mucho margen a lo que escribe una persona.
MAX_ACTOR = 200
MAX_MOTIVO = 2_000
MAX_NOMBRE = 200
MAX_NOMBRE_CLASE = 100
MAX_DESCRIPCION = 2_000
MAX_TEXTO_LARGO = 20_000

NombreActor = Annotated[str, Field(min_length=1, max_length=MAX_ACTOR)]
TextoMotivo = Annotated[str, Field(min_length=1, max_length=MAX_MOTIVO)]
Nombre = Annotated[str, Field(min_length=1, max_length=MAX_NOMBRE)]
# Sin `min_length`: una clase vacía la rechaza `core.schema` con su propio mensaje.
NombreClase = Annotated[str, Field(max_length=MAX_NOMBRE_CLASE)]
TextoDescripcion = Annotated[str, Field(max_length=MAX_DESCRIPCION)]
TextoLargo = Annotated[str, Field(min_length=1, max_length=MAX_TEXTO_LARGO)]


def no_blanco(valor: str) -> str:
    """Rechaza cadenas vacías o formadas solo por espacios (422 vía pydantic)."""
    if not valor.strip():
        raise ValueError("no puede estar vacío ni ser solo espacios")
    return valor


class ActorBody(BaseModel):
    """Cuerpo mínimo de una mutación que exige actor nominal y motivo."""

    actor: NombreActor
    role: str | None = Field(default=None, max_length=MAX_ACTOR)
    motivo: TextoMotivo
    # Contexto libre del agente («por encargo de …»). El nombre del diario
    # es `actor`; esto solo se guarda en el payload (`after`) de los eventos.
    actor_detalle: str | None = Field(default=None, max_length=MAX_ACTOR_DETALLE)

    _actor_no_blanco = field_validator("actor")(no_blanco)
    _motivo_no_blanco = field_validator("motivo")(no_blanco)

    @model_validator(mode="after")
    def _recordar_actor_detalle(self) -> ActorBody:
        recordar_actor_detalle(self.actor, self.actor_detalle)
        return self


def recordar_actor_detalle(actor: str, detalle: str | None) -> None:
    """Deja `actor_detalle` a mano de `record_event` durante la petición.
    FastAPI valida el cuerpo en la misma tarea que luego llama a la ruta, y el
    hilo de la ruta hereda el contexto: así los servicios no cambian de firma.
    Un cuerpo sin detalle lo borra, para que no sobreviva a la petición en
    quien reutiliza el contexto (clientes ASGI en proceso)."""
    from vigia.app.events import fijar_actor_detalle

    fijar_actor_detalle(actor, detalle.strip() if detalle and detalle.strip() else None)


class ErrorDetail(BaseModel):
    """Forma de los errores de la API."""

    detail: str


class ListResponse[T](BaseModel):
    """Envoltura de todas las listas de la API: elementos y total sin paginar.

    El OpenAPI la publica como `ListResponse_<T>_`, un esquema por tipo de
    elemento; el frontend la reexporta como `ListResponse<T>`.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[T]
    total: int
