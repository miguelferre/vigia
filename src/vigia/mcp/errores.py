"""Errores del cliente MCP: `VigiaError`, el texto de
los fallos de la API y la línea «qué hacer» por código y ruta."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx

MENSAJE_SIN_ARRANQUE = (
    "Vigía no está en marcha en esa carpeta de datos; arranca `vigia serve` o pasa `--url`"
)


def mensaje_sin_respuesta(url: str) -> str:
    """Con `--url` el MCP no busca ninguna carpeta de datos; el texto
    nombra la dirección a la que llamó y lo que falta, un `vigia serve` en ella."""
    return f"Vigía no contesta en {url}; arranca `vigia serve` en esa dirección o comprueba la URL de `--url`"


class VigiaError(RuntimeError):
    """Error de la API visto por el agente. El texto empieza por el
    código HTTP, sigue con el `detail` en español y, si lo hay, una línea
    «qué hacer». Hereda de `RuntimeError` para no romper a quien ya lo captura."""

    def __init__(self, status_code: int, detail: str, que_hacer: str | None = None) -> None:
        self.status_code = status_code
        self.detail = detail
        self.que_hacer = que_hacer
        texto = f"{status_code}: {detail}"
        if que_hacer:
            texto += f"\nQué hacer: {que_hacer}"
        super().__init__(texto)


# Claves válidas de `MappingTemplate` y de `ColumnMapping` (core/schema.py): las dos
# rechazan las demás con `extra="forbid"`. Copias para no importar el motor en el
# proceso MCP; `tests/mcp/test_tools_actor_exportacion.py` comprueba que coinciden con los modelos.
CLAVES_MAPPING_TEMPLATE = (
    "favorable_label",
    "classes",
    "probability_cols",
    "prediction_col",
    "probability_col",
    "label_col",
    "id_col",
    "timestamp_col",
    "feature_cols",
    "protected_attr_col",
    "protected_kind",
    "unpriv_groups",
    "priv_groups",
    "target_unit",
    "favorable_ranges",
)
CLAVES_COLUMN_MAPPING = (
    "prediction_col",
    "probability_col",
    "probability_format",
    "probability_index",
    "label_col",
    "id_col",
    "timestamp_col",
    "protected_attr_col",
    "protected_kind",
    "unpriv_groups",
    "priv_groups",
    "feature_cols",
    "clinician_col",
    "subgroup_col",
    "favorable_label",
    "classes",
    "probability_cols",
    "target_unit",
    "favorable_ranges",
)


def _claves_validas(loc: Any) -> str | None:
    """«claves válidas: …» si un 422 `extra_forbidden` cuelga de `mapping_template`
    o de `mapping`; `None` en cualquier otro caso."""
    partes = [str(x) for x in loc]
    if "mapping_template" in partes:
        return "claves válidas de mapping_template: " + ", ".join(CLAVES_MAPPING_TEMPLATE)
    if "mapping" in partes:
        return "claves válidas de mapping: " + ", ".join(CLAVES_COLUMN_MAPPING)
    return None


def _texto_detalle(detalle: Any) -> str:
    """El `detail` de la API como texto: una lista de errores de validación de
    FastAPI se reduce a «campo: mensaje» por entrada. Un `extra_forbidden` bajo
    `mapping_template` o `mapping` añade al final las claves válidas."""
    if isinstance(detalle, list):
        partes = []
        ayudas: list[str] = []
        for e in detalle:
            if isinstance(e, dict) and "msg" in e:
                campo = ".".join(str(x) for x in e.get("loc", ()) if x not in ("body", "query"))
                partes.append(f"{campo}: {e['msg']}" if campo else str(e["msg"]))
                if e.get("type") == "extra_forbidden":
                    ayuda = _claves_validas(e.get("loc", ()))
                    if ayuda and ayuda not in ayudas:
                        ayudas.append(ayuda)
            else:
                partes.append(str(e))
        return "; ".join(partes + ayudas)
    return str(detalle)


# La tool de listado que nombra un 404 según la ruta, de la más específica a
# la menos (`/projects/5/alerts` es una alerta, no un proyecto).
# El tercer campo es el parámetro de la tool que lleva el id, para que el texto no hable
# de «modelo» cuando el parámetro es `project_id`.
_LISTADO_POR_RUTA = (
    ("/jobs", "get_job", "job_id"),
    ("/versions/compare", "list_projects o list_versions", "project_id"),
    ("/model-versions", "list_versions", "version_id"),
    ("/alerts", "get_alerts", "alert_id"),
    ("/risks", "list_risks", "risk_id"),
    ("/projects", "list_projects", "project_id"),
)


def _listado_de(ruta: str) -> tuple[str, str] | None:
    for fragmento, tool, parametro in _LISTADO_POR_RUTA:
        if fragmento in ruta:
            return tool, parametro
    return None


# Lo que falta y la tool que lo da, según el detalle del 409. De la más
# específica a la menos; el texto del detalle es el de los routers y servicios.
_ACCION_409 = (
    (
        "tiene una sola versión",
        "crea la versión nueva con create_version y vuelve a comparar con compare_versions",
    ),
    ("no tiene versión activa", "activa una versión con activate_version (list_versions dice cuáles hay)"),
    (
        "línea base congelada de una versión",
        "ese lote es la línea base de una versión y no se borra: crea otra versión con create_version y fija su línea base",
    ),
    (
        "ya tiene un baseline congelado",
        "esa versión ya tiene su línea base fijada: no hace falta fijarla otra vez; si quieres otra, crea una versión con create_version",
    ),
    (
        ("línea base congelada", "baseline congelado"),
        "falta la línea base: sube un dataset con role=\"baseline\" con upload_dataset, o fíjala con freeze_baseline",
    ),
    ("explicabilidad no disponible", "sube el modelo ejecutable de la versión con upload_model_artifact"),
    ("fichero del modelo ha cambiado", "vuelve a subir el modelo con upload_model_artifact"),
    (
        "variables guardadas",
        "ese lote no guardó las variables de entrada: crea el modelo con store_features=true (create_project) y vuelve a subir el lote con upload_dataset",
    ),
    (
        "columnas que el modelo necesita",
        "ese lote no guardó las columnas que pide el modelo: vuelve a subirlo con upload_dataset incluyéndolas en feature_cols",
    ),
    (
        "aún no tiene informe",
        "espera a que termine la revisión (get_job) o lánzala otra vez con run_dossier_review",
    ),
    (
        "configura un backend",
        "lanza la revisión sin LLM con run_dossier_review (approach=\"b0\") o configura el backend en Ajustes",
    ),
    (
        "primero hay que",
        "registra antes el paso anterior del protocolo con act_on_alert (get_alert dice en cuál está)",
    ),
    (
        ("ya está cerrada", "ya está hecho", "ya está registrad"),
        "no queda nada que registrar en ese paso: consulta en qué estado está la alerta con get_alert",
    ),
    ("retirada", "la alerta ya no admite acciones: consulta su estado con get_alert"),
)

# Sin pista en el detalle: la tool de lectura que dice el estado, según la ruta.
_LECTURA_409_POR_RUTA = (
    ("/alerts", "get_alert"),
    ("/model-versions", "list_versions"),
    ("/versions", "list_versions"),
    ("/dossiers", "run_dossier_review"),
    ("/projects", "list_projects"),
)


def _que_hacer_409(detalle: str, ruta: str) -> str:
    bajo = detalle.lower()
    for pista, accion in _ACCION_409:
        pistas = (pista,) if isinstance(pista, str) else pista
        if any(p in bajo for p in pistas):
            return accion
    for fragmento, tool in _LECTURA_409_POR_RUTA:
        if fragmento in ruta:
            return f"el estado actual no lo permite: consúltalo con {tool} y haz primero el paso que dice el mensaje"
    return "el estado actual no lo permite: haz primero el paso que dice el mensaje o consulta el estado con la tool de lectura"


def _que_hacer(codigo: int, detalle: str, ruta: str = "") -> str | None:
    """La línea «qué hacer» según el código HTTP y la ruta. Un 409 y
    un 422 no repiten el `detail`, que ya va en la línea de arriba."""
    if codigo == 404:
        listado = _listado_de(ruta)
        if listado:
            tool, parametro = listado
            return f"el {parametro} no existe: consulta los ids vigentes con {tool}"
        return "comprueba el id con la tool de listado"
    if codigo == 409:
        return _que_hacer_409(detalle, ruta)
    if codigo == 422:
        return "corrige el campo que nombra el mensaje y vuelve a llamar; la ficha de la tool lista los valores válidos"
    if codigo >= 500:
        return "error de Vigía; el diario tiene el detalle"
    return None


@contextmanager
def fallos_de_conexion(url: str | None = None) -> Iterator[None]:
    """Un backend parado, un `discover` sin lock vivo o un fallo de conexión
    de `httpx` salen como `VigiaError` con el texto de `MENSAJE_SIN_ARRANQUE`, no
    como una excepción de librería. Con `url` (el MCP se arrancó con `--url`) el
    texto es `mensaje_sin_respuesta`, que nombra esa dirección."""
    sin_arranque = mensaje_sin_respuesta(url) if url else MENSAJE_SIN_ARRANQUE
    try:
        yield
    except VigiaError:
        raise
    except RuntimeError as exc:
        if str(exc) != MENSAJE_SIN_ARRANQUE:
            raise
        raise VigiaError(503, sin_arranque) from exc
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise VigiaError(503, sin_arranque) from exc
    except httpx.TimeoutException as exc:
        raise VigiaError(
            504,
            "Vigía no contestó a tiempo",
            "espera y consulta el estado con la tool de lectura; si era un trabajo, con get_job",
        ) from exc
