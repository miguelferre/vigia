"""Plantillas de error de la API en español.

- `no_encontrado`: el 404 único de los routers.
- `traducir_validacion`: el texto en español de los 422 de pydantic que pinta
  el manejador global de `app/main.py`. Mantiene la forma de la
  respuesta (`loc`, `msg`, `type`); solo cambia `msg`.

Nombres fijados antes de implementarlos; se rellenan
`traducir_validacion` y los manejadores.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

__all__ = [
    "TEXTO_404_RUTA",
    "TEXTO_ERROR_INTERNO",
    "no_encontrado",
    "registrar_manejadores",
    "texto_error_trabajo",
    "texto_no_encontrado",
    "traducir_validacion",
]

_log = logging.getLogger("vigia.app.errores")

TEXTO_ERROR_INTERNO = (
    "error interno de Vigía: vuelve a intentarlo; si se repite, "
    "el registro del servidor tiene el detalle"
)
_TEXTO_405 = "esa dirección no admite esa operación: vuelve a la pantalla anterior e inténtalo desde allí"
TEXTO_404_RUTA = "esa dirección no existe: vuelve al inicio de Vigía"

# Tipo de trabajo (`Job.kind`) -> «error interno al <esto>».
_ACCION_DE_TRABAJO = {
    "ingesta": "ingerir el fichero",
    "evaluacion": "evaluar el lote",
    "explicacion": "calcular la explicación",
    "cruzadas": "evaluar las reglas cruzadas",
    "revision_dossier": "revisar el dossier",
    "demo": "reproducir la demo",
    "demo_lab": "generar el laboratorio",
}


def texto_no_encontrado(objeto: str, ident: int | str, objetos: str) -> str:
    """«<objeto> <id> no existe: vuelve a la lista de <objetos>»."""
    return f"{objeto} {ident} no existe: vuelve a la lista de {objetos}"


def no_encontrado(objeto: str, ident: int | str, objetos: str) -> HTTPException:
    """404 con la plantilla única. Uso: `raise no_encontrado("lote", batch_id, "lotes")`.

    `objeto` y `objetos` en el vocabulario de la interfaz: un proyecto es un
    «modelo» y su lista, «modelos».
    """
    return HTTPException(404, texto_no_encontrado(objeto, ident, objetos))


_RAIZ_PETICION = ("body", "query", "path", "header", "cookie")
_PREFIJO_VALUE_ERROR = "Value error, "


def _nombre_campo(loc: Sequence[Any]) -> str:
    """Nombre corto del campo que falla: el último texto de `loc`, con el índice
    si cuelga de una lista («feature_cols[2]»). Vacío si el error es del cuerpo entero."""
    partes = list(loc)
    if partes and isinstance(partes[0], str) and partes[0] in _RAIZ_PETICION:
        partes = partes[1:]
    if not partes:
        return ""
    ultimo = partes[-1]
    if isinstance(ultimo, int) and len(partes) > 1:
        return f"{partes[-2]}[{ultimo}]"
    return str(ultimo)


def _lista_valores(esperado: Any) -> str:
    """«'a', 'b' or 'c'» de pydantic a «a, b o c»."""
    texto = str(esperado).replace("'", "")
    return texto.replace(" or ", " o ")


def _texto_validacion(error: dict[str, Any]) -> str:
    tipo = str(error.get("type", ""))
    ctx = error.get("ctx") or {}
    campo = _nombre_campo(error.get("loc") or ())
    marca = f"«{campo}»" if campo else "el valor"
    if tipo == "json_invalid":
        return "el cuerpo de la petición no es un JSON válido: revisa las comas y las comillas"
    if tipo == "value_error":
        texto = str(error.get("msg", "")).removeprefix(_PREFIJO_VALUE_ERROR).strip()
        return texto or f"valor no válido en {campo or 'la petición'}"
    if tipo == "missing":
        return f"falta el campo {marca}: es obligatorio"
    if tipo == "extra_forbidden":
        return f"el campo {marca} no existe: quítalo o revisa cómo se escribe"
    if tipo in ("literal_error", "enum"):
        return f"{marca} no admite ese valor: los valores admitidos son {_lista_valores(ctx.get('expected', ''))}"
    if tipo == "string_too_short":
        return f"{marca} es demasiado corto: necesita al menos {ctx.get('min_length', 1)} caracteres"
    if tipo == "string_too_long":
        return f"{marca} es demasiado largo: admite como máximo {ctx.get('max_length', '')} caracteres"
    if tipo == "greater_than_equal":
        return f"{marca} no puede ser menor que {ctx.get('ge', '')}"
    if tipo == "less_than_equal":
        return f"{marca} no puede ser mayor que {ctx.get('le', '')}"
    fijos = {
        "int_parsing": "debe ser un número entero",
        "float_parsing": "debe ser un número",
        "bool_parsing": "debe ser verdadero o falso",
        "string_type": "debe ser un texto",
        "int_type": "debe ser un número entero",
        "float_type": "debe ser un número",
        "bool_type": "debe ser verdadero o falso",
        "list_type": "debe ser una lista",
        "dict_type": "debe ser un objeto",
    }
    if tipo in fijos:
        return f"{marca} {fijos[tipo]}" if campo else f"el valor {fijos[tipo]}"
    return f"valor no válido en {campo or 'la petición'}"


def traducir_validacion(errores: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copia de los errores de `RequestValidationError.errors()` con `msg` en español.

    Cada error conserva `loc` y `type`; `msg` pasa al español con el campo. Un `type` sin traducción da «valor no válido en <campo>». No se
    devuelve `input` ni `ctx`: el 422 no repite el dato enviado, y un valor
    no finito no rompe la respuesta.
    """
    return [
        {"loc": e.get("loc"), "type": e.get("type"), "msg": _texto_validacion(e)}
        for e in errores
    ]


def texto_error_trabajo(exc: BaseException, tipo_trabajo: str = "") -> str:
    """Texto de `job.error`, sin código de estado ni texto de librería.

    `HTTPException`: su `detail` tal cual. `DatosNoValidos`: su texto tal cual
    (ya está pensado para el usuario). Cualquier otra excepción da «error
    interno al <tipo de trabajo>: el registro del servidor tiene el detalle».
    """
    from vigia.core.schema import DatosNoValidos

    if isinstance(exc, StarletteHTTPException):
        detalle = exc.detail
        return detalle if isinstance(detalle, str) else str(jsonable_encoder(detalle))
    if isinstance(exc, DatosNoValidos):
        return str(exc) or "los datos no son válidos"
    accion = _ACCION_DE_TRABAJO.get(tipo_trabajo, "ejecutar el trabajo")
    return f"error interno al {accion}: el registro del servidor tiene el detalle"


def registrar_manejadores(app: FastAPI) -> None:
    """Manejadores globales en español. Misma forma de respuesta
    que antes: `{"detail": ...}`, y en el 422 la lista con `loc`, `msg` y `type`."""

    async def _validacion(request: Request, exc: RequestValidationError) -> Response:
        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(traducir_validacion(exc.errors()))},
        )

    async def _http(request: Request, exc: StarletteHTTPException) -> Response:
        if exc.status_code == 405 and exc.detail == "Method Not Allowed":
            return JSONResponse(
                status_code=405, content={"detail": _TEXTO_405}, headers=exc.headers
            )
        if exc.status_code == 404 and exc.detail == "Not Found":
            return JSONResponse(status_code=404, content={"detail": TEXTO_404_RUTA})
        return await http_exception_handler(request, exc)

    async def _interno(request: Request, exc: Exception) -> Response:
        _log.error(
            "error no controlado en %s %s",
            request.method,
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(status_code=500, content={"detail": TEXTO_ERROR_INTERNO})

    app.add_exception_handler(RequestValidationError, _validacion)
    app.add_exception_handler(StarletteHTTPException, _http)
    app.add_exception_handler(Exception, _interno)
