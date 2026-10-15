"""Contenido estático de ayuda: glosario, ayuda de métricas,
presentación, demo guiada y guía de uso.

Sirve tal cual `src/vigia/content/{metricas-ayuda,glosario,presentacion,
demo-digestivo,guia-uso}.json`, generados por `build/gen_content.py` a
partir del glosario de métricas y los tres guiones de la guía de uso
(el paquete no depende de `docs/`: los JSON viajan
versionados dentro de `src/vigia/content/`). Sin sesión de base de datos ni
actor: es contenido estático dentro de una ejecución, igual que lo trata el
frontend con `staleTime: Infinity` en `api/queries-contenido.ts`.

Por qué en el backend y no como import directo del frontend: el MCP y el
informe necesitan el mismo texto.

`/onboarding` se retiró: `/presentacion`, `/demo` y
`/guia-uso` lo sustituyen.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response

from vigia.app.errores import no_encontrado
from vigia.app.schemas import dossiers as dsch
from vigia.app.schemas import respuestas as resp
from vigia.app.schemas.contenido_guia_datos import GuiaDatos
from vigia.app.schemas.contenido_registro_uso import RegistroUsoAyuda
from vigia.app.services import plantillas_datos

router = APIRouter(prefix="/content", tags=["contenido"])


@lru_cache(maxsize=12)
def _leer_json(nombre: str) -> Any:
    """Lee un JSON de `vigia.content` como recurso del paquete (funciona
    igual en el repositorio y en el paquete de Windows instalado). Objeto o
    lista según el fichero: `protocolo-hitos.json` es una lista, el resto son
    objetos. `maxsize=10`: los nueve JSON de `src/vigia/content/` caben todos
    en caché a la vez (tres se añadieron a los cuatro primeros:
    `dossier-plantillas.json`, `registro-uso-ayuda.json` y `guia-datos.json`)."""
    ref = resources.files("vigia.content").joinpath(nombre)
    return json.loads(ref.read_text(encoding="utf-8"))


@router.get(
    "/metricas",
    response_model=dict[str, resp.ContenidoMetrica],
    response_model_exclude_unset=True,
)
def metricas() -> dict[str, Any]:
    """Ayuda de métricas: qué mide y fórmula de cada `metric_key`."""
    return _leer_json("metricas-ayuda.json")


@router.get("/glosario", response_model=dict[str, resp.ContenidoGlosarioTermino])
def glosario() -> dict[str, Any]:
    """Glosario de conceptos no métricos (grupo supervisado, ventana...)."""
    return _leer_json("glosario.json")


@router.get("/presentacion", response_model=resp.ContenidoPresentacion)
def presentacion() -> dict[str, Any]:
    """Las 10 diapositivas de la presentación."""
    return _leer_json("presentacion.json")


@router.get("/demo", response_model=resp.ContenidoDemo)
def demo() -> dict[str, Any]:
    """El guion de la demo guiada: los 26 pasos del caso Digestivo."""
    return _leer_json("demo-digestivo.json")


@router.get("/guia-uso", response_model=resp.ContenidoGuiaUso)
def guia_uso() -> dict[str, Any]:
    """Las 12 entradas de la sección «Guía de uso» de `/ayuda`."""
    return _leer_json("guia-uso.json")


@router.get("/textos-pantalla", response_model=dict[str, dict[str, str]])
def textos_pantalla() -> dict[str, Any]:
    """Textos de pantalla por sección (subida de datos, explicabilidad, diario...)."""
    return _leer_json("textos-pantalla.json")


@router.get("/protocolo-hitos", response_model=resp.ContenidoProtocoloHitos)
def protocolo_hitos() -> dict[str, Any]:
    """Plantilla de contenido del protocolo de alertas: los
    cinco hitos en orden, con título, descripción y entregables genéricos.

    Objeto con `pasos`, no una lista bare ni un mapa por clave: el fichero
    en disco es una lista (`protocolo-hitos.json`, orden 1 a 5 por posición,
    intacto frente al `sort_keys=True` de `build/gen_content.py`, que sí
    reordenaría alfabéticamente un mapa de nivel superior por `key`); el
    envoltorio es solo de la respuesta, para que el esquema OpenAPI lleve un
    `$ref` en la raíz (ver `ContenidoProtocoloHitos`). El estado de cada
    hito para una alerta concreta (hecho, en curso, pendiente) y su fecha
    objetivo no están aquí: se añaden en `GET /alerts/{id}`
    (`protocol_steps`).
    """
    return {"pasos": _leer_json("protocolo-hitos.json")}


@router.get("/dossier-plantillas", response_model=dsch.DossierPlantillas)
def dossier_plantillas() -> Any:
    """Las tres plantillas reales de `interaction_review`,
    traducidas al vocabulario de Vigía por `build/gen_content_dossier.py`."""
    return _leer_json("dossier-plantillas.json")


@router.get("/guia-datos", response_model=GuiaDatos)
def guia_datos() -> Any:
    """Guía de datos: qué ficheros pide Vigía, sus columnas, los
    formatos, cómo decidir la clase favorable y qué hacer con una
    comprobación de codificación «inconclusa». Cada sección con CSV remite a
    su plantilla de `/content/plantillas/{tipo}.csv`."""
    return _leer_json("guia-datos.json")


@router.get("/registro-uso", response_model=RegistroUsoAyuda)
def registro_uso() -> Any:
    """Ayuda de la subida del registro de uso: columnas obligatorias
    y opcionales, formatos de fecha, codificación de la decisión favorable
    y un ejemplo de cinco filas."""
    return _leer_json("registro-uso-ayuda.json")


@router.get("/registro-uso/ejemplo.csv")
def registro_uso_ejemplo(
    tipo: Annotated[
        Literal["binary", "multiclass", "regression"],
        Query(
            description=(
                "Tipo de tarea del modelo: `multiclass` da el ejemplo con nombres de clase y "
                "`regression` el ejemplo con cifras."
            )
        ),
    ] = "binary",
) -> Response:
    """El ejemplo de cinco filas de `/content/registro-uso` como CSV
    descargable (datos sintéticos). Con `tipo=multiclass`, el de un
    modelo multiclase: las columnas de decisión llevan nombres de clase. Con
    `tipo=regression`, el de un modelo de regresión: llevan cifras."""
    match tipo:
        case "multiclass":
            clave = "ejemplo_multiclase"
        case "regression":
            clave = "ejemplo_regresion"
        case "binary":
            clave = "ejemplo"
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {tipo!r}")
    ejemplo = _leer_json("registro-uso-ayuda.json")[clave]
    return Response(
        content=ejemplo["csv"],
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={ejemplo['nombre_fichero']}"},
    )


@router.get("/plantillas/{tipo}.csv")
def plantilla_datos(tipo: str) -> Response:
    """Plantilla CSV sintética de la guía de datos: `linea-base`,
    `lote`, `etiquetas`, `registro-uso`, `outcomes`, `multiclase` o `regresion`."""
    if tipo not in plantillas_datos.TIPOS_PLANTILLA:
        raise no_encontrado("plantilla", tipo, "plantillas de la guía de datos")
    nombre, contenido = plantillas_datos.plantilla_csv(tipo)
    return Response(
        content=contenido,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={nombre}"},
    )
