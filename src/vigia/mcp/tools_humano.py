"""Tools de la capa humana: diario de uso, alertas cruzadas,
deskilling, overrides y outcomes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from vigia.core.schema import MOTIVO_CAPA_HUMANA_SIN_RANGO
from vigia.mcp.client import VigiaError, get_client
from vigia.mcp.rutas import comprobar_ruta_de_subida

VALORES_FAVORABLES = ("refer", "no-refer", "1", "0")
AGRUPACIONES_OVERRIDES = ("subgroup", "phase", "clinician", "profesionales", "cambios")
AVISO_CALIBRACION = (
    "Esta evaluación es de calibración: fija la referencia de la versión y no genera "
    "reglas ni alertas todavía. Sube el siguiente diario de uso (upload_usage_log) y "
    "repite evaluate_cross para obtener reglas."
)
# Con `calibration_until` vigente el proyecto sigue calibrando y la referencia aún no se fija.
AVISO_CALIBRACION_HASTA = (
    "Esta evaluación es de calibración y no fija todavía la referencia: el proyecto "
    "sigue en calibración hasta {fecha} (calibration_until) y no genera reglas ni "
    "alertas. Pasada esa fecha, la primera evaluación fija la referencia; sube el "
    "siguiente diario de uso (upload_usage_log) y repite evaluate_cross para obtener reglas."
)


MENSAJE_FAVORABLE_EN_MULTICLASE = (
    "En un modelo multiclase no se usa valor_favorable: el registro trae los nombres de "
    "clase en human_decision, model_output y ground_truth. Quita el parámetro y vuelve a llamar."
)


# Sin rango favorable la capa humana de regresión no tiene decisión que
# derivar. Mismo texto que el 422 de la API (`tarea.texto_guardia_capa_humana(sin_rango=True)`,
# que un test compara con este); el MCP lo da antes de subir nada. El motivo viene del motor; la
# frase con qué hacer se repite aquí porque el MCP no importa `app.services`. Con rango, la
# subida pasa: la API valida las cifras y da el 422 de «el registro trae las cifras».
MOTIVO_REGRESION_SIN_RANGO = MOTIVO_CAPA_HUMANA_SIN_RANGO
TEXTO_SIN_RANGO = (
    f"No se puede subir el registro de uso: {MOTIVO_REGRESION_SIN_RANGO}. Crea un proyecto "
    "de regresión con rango favorable: el rango no cambia después de congelar la línea base"
)


# En regresión no hay `valor_favorable`. Mismo texto que el 422 de la API
# (`human_layer.MENSAJE_VALOR_FAVORABLE_REGRESION`; un test los compara). La tool lo da antes de
# subir, porque la API valida el valor contra `refer`, `no-refer`, `1` y `0` antes de mirar el tipo
# y un valor raro daría otro mensaje.
TEXTO_VALOR_FAVORABLE_EN_REGRESION = (
    "En un modelo de regresión el registro de uso no se recodifica con valor_favorable: "
    "en regresión el registro trae las cifras de human_decision, model_output y ground_truth, "
    "como números con punto decimal y sin unidad. Quita valor_favorable y sube el registro "
    "con las cifras"
)


def _regresion_con_rango(proyecto: Any) -> bool:
    """El proyecto de regresión leído tiene rango favorable."""
    return bool(proyecto.get("favorable_ranges")) if isinstance(proyecto, dict) else False


def _tipo_de_tarea(proyecto: Any) -> str:
    """`task_type` del proyecto leído de la API; `binary` si no se pudo leer (la API da el
    422 que corresponda)."""
    if isinstance(proyecto, dict) and proyecto.get("task_type"):
        return str(proyecto["task_type"])
    return "binary"


MENSAJE_FALTA_FAVORABLE = (
    "valor_favorable es obligatorio en un modelo binario: pasa 'refer' o '1' si la decisión "
    "favorable se escribe así en el fichero, o 'no-refer' o '0' si es la contraria. Si no lo "
    "sabes, léelo de la ficha del modelo o pregúntaselo a la persona."
)


def _aun_vigente(calibration_until: Any) -> bool:
    """`calibration_until` (ISO 8601) todavía no ha vencido; un valor ilegible cuenta como no vigente."""
    if not isinstance(calibration_until, str):
        return False
    try:
        limite = datetime.fromisoformat(calibration_until)
    except ValueError:
        return False
    if limite.tzinfo is None:
        limite = limite.replace(tzinfo=UTC)
    return datetime.now(UTC) < limite


def registrar(mcp) -> None:
    @mcp.tool()
    async def upload_usage_log(
        project_id: int,
        file_path: str,
        valor_favorable: str | None = None,
        model_version_id: int | None = None,
    ) -> dict[str, Any]:
        """Sube el CSV del diario de uso (date, human_decision, model_output,
        ground_truth; opcionales clinician_pseudonym, subgroup, record_seq) e indica
        qué valor del fichero es la decisión FAVORABLE para la persona afectada.

        `valor_favorable` es obligatorio en un proyecto BINARIO (sin él, la tool da un error
        que lo pide): `refer` o `1` si la decisión favorable se
        escribe así en el fichero; `no-refer` o `0` si es la contraria, y entonces la
        subida recodifica. Si no lo sabes, pregúntaselo a la persona o léelo de la
        ficha del modelo: no lo supongas. Devuelve `n_rows`, el `valor_favorable`
        aplicado y `comprobacion_codificacion` (`coherente`, `posible_inversion` o
        `inconcluso`): es un aviso, la subida se guarda igual, pero ante
        `posible_inversion` revisa el valor declarado. Sin `model_version_id` usa la
        versión activa.

        Proyecto MULTICLASE: `valor_favorable` NO se usa: no lo pases (si se pasa, la
        tool da un error que pide quitarlo). `human_decision`, `model_output` y
        `ground_truth` llevan el NOMBRE DE CLASE en las mismas columnas del CSV (por
        ejemplo `spam`, `phishing`, `legitimo`) y la tool pasa el fichero tal cual; la API
        valida contra las clases del proyecto y devuelve 422 en español con la fila y las
        clases válidas si una celda trae otra clase o si trae `refer`/`no-refer` (eso
        solo vale en binario). Una discrepancia entre dos clases cuenta como override
        aunque ninguna sea favorable. En multiclase `comprobacion_codificacion` va
        `inconcluso` con `r` y `p` nulos y el motivo «no aplica en multiclase»: no hay
        codificación que invertir porque los nombres de clase se validan.

        Proyecto de REGRESIÓN: hace falta un rango favorable en el proyecto
        (`favorable_ranges`); sin él la tool falla antes de subir nada con el motivo «la
        capa humana de regresión necesita un rango favorable» y qué hacer. Con rango, el
        registro trae las CIFRAS, con punto decimal y sin unidad, en las mismas columnas:
        `human_decision` (la cifra del profesional), `model_output` (la del modelo) y
        `ground_truth` (el valor real; puede ir en blanco). Vigía deriva de cada cifra el 0/1
        de «dentro del rango favorable» y con él calcula alertas cruzadas, overrides y
        deskilling. `refer`, `no-refer` o texto en una celda dan 422 con la fila y «en
        regresión el registro trae las cifras». `valor_favorable` NO se usa en regresión: no
        lo pases (la tool no lo manda; si lo pasas, da un error que pide quitarlo). La comprobación de
        codificación no corre en regresión: con cifras no hay inversión posible."""
        if valor_favorable is not None and valor_favorable not in VALORES_FAVORABLES:
            # En multiclase, un valor no reconocido (por ejemplo, un nombre de
            # clase) da el mensaje de multiclase. Si el proyecto no se puede leer,
            # queda el de «no reconocido».
            try:
                leido = await get_client().get(f"/projects/{project_id}")
            except Exception:  # noqa: BLE001 - solo elige el texto del error
                leido = None
            match _tipo_de_tarea(leido):
                case "multiclass":
                    raise ValueError(MENSAJE_FAVORABLE_EN_MULTICLASE)
                case "regression":
                    # Sin rango, la guardia dice su motivo antes que un valor_favorable
                    # raro. Con rango, el texto.
                    if not _regresion_con_rango(leido):
                        raise ValueError(TEXTO_SIN_RANGO)
                    raise ValueError(TEXTO_VALOR_FAVORABLE_EN_REGRESION)
                case "binary":
                    raise ValueError(
                        f"valor_favorable no reconocido: {valor_favorable!r}; válidos: "
                        f"{', '.join(VALORES_FAVORABLES)}"
                    )
                case tipo_raro:
                    raise ValueError(f"tipo de tarea no reconocido: {tipo_raro!r}")
        comprobar_ruta_de_subida(file_path)
        proyecto = await get_client().get(f"/projects/{project_id}")
        match _tipo_de_tarea(proyecto):
            case "multiclass":
                if valor_favorable is not None:
                    raise ValueError(MENSAJE_FAVORABLE_EN_MULTICLASE)
                # En multiclase el valor por defecto de la API (`refer`) no recodifica nada.
                campos = {"valor_favorable": "refer"}
            case "binary":
                if valor_favorable is None:
                    raise ValueError(MENSAJE_FALTA_FAVORABLE)
                campos = {"valor_favorable": valor_favorable}
            case "regression":
                if not _regresion_con_rango(proyecto):
                    raise ValueError(TEXTO_SIN_RANGO)
                # El registro trae las cifras y no hay `valor_favorable`: la tool no lo
                # manda, y si la persona lo pasó (`refer`, `1`...), da el texto.
                if valor_favorable is not None:
                    raise ValueError(TEXTO_VALOR_FAVORABLE_EN_REGRESION)
                campos = {}
            case tipo_raro:
                raise ValueError(f"tipo de tarea no reconocido: {tipo_raro!r}")
        if model_version_id is not None:
            campos["model_version_id"] = str(model_version_id)
        return await get_client().upload(
            f"/projects/{project_id}/usage-logs/upload", file_path=file_path, fields=campos
        )

    @mcp.tool()
    async def evaluate_cross(project_id: int, wait: bool = True, timeout_s: int = 60) -> dict[str, Any]:
        """Encola la evaluación de las alertas cruzadas (modelo frente a decisión
        humana) sobre la versión activa. Con `wait=true` espera hasta `timeout_s` y
        devuelve el trabajo terminado; si se agota devuelve `status="en_curso"` y
        `job_id` para seguirlo con `get_job`. El resultado se lee con
        `get_cross_latest`.

        La primera evaluación de una versión es de calibración (`mode="calibracion"`):
        fija la referencia, no genera reglas ni alertas, y la respuesta trae un
        `aviso` que lo dice. Para obtener reglas hay que subir el siguiente diario
        (`upload_usage_log`) y repetir `evaluate_cross`. Si el proyecto tiene una
        `calibration_until` aún vigente, sigue calibrando sin fijar la referencia y
        el `aviso` lo dice. El `aviso` solo sale con `wait=true` y el trabajo
        terminado; con `wait=false` consulta `mode` en `get_cross_latest`."""
        client = get_client()
        job = await client.post(
            f"/projects/{project_id}/cross/evaluate", json={}, correlation_id=str(uuid.uuid4())
        )
        resultado = await client.seguir_job(job, wait, timeout_s)
        # El agente no sabía que esta pasada solo calibraba.
        contenido = resultado.get("result")
        if isinstance(contenido, dict) and contenido.get("mode") == "calibracion":
            aviso = AVISO_CALIBRACION
            try:
                ultima = await client.get(f"/projects/{project_id}/cross/latest")
                hasta = ultima.get("calibration_until") if isinstance(ultima, dict) else None
            except (VigiaError, httpx.HTTPError):  # el aviso nunca debe romper la evaluación ya hecha
                hasta = None
            if _aun_vigente(hasta):
                aviso = AVISO_CALIBRACION_HASTA.format(fecha=hasta)
            resultado = {**resultado, "aviso": aviso}
        return resultado

    @mcp.tool()
    async def get_cross_latest(project_id: int) -> dict[str, Any]:
        """Última evaluación de las alertas cruzadas del proyecto: estado del monitor
        `cross` y el resultado de cada regla (CX-1 a CX-6) con su evidencia. Solo
        lee; para actualizarla, `evaluate_cross`."""
        return await get_client().get(f"/projects/{project_id}/cross/latest")

    @mcp.tool()
    async def get_deskilling(
        project_id: int,
        subgroup: str | None = None,
        clinician: str | None = None,
        n_windows: int = 4,
        model_version_id: int | None = None,
    ) -> dict[str, Any]:
        """Deskilling de la revisión humana sobre el diario de uso de una versión del
        modelo: ventanas temporales (acuerdo, acierto humano, acierto del modelo,
        rescate), tendencias y señal. `subgroup` o `clinician` (un pseudónimo, véase
        `get_overrides` con `by="profesionales"`) filtran: el agregado puede diluir un
        efecto que sí aparece en un subgrupo o en un profesional. `n_windows` va de 1 a
        12. Devuelve `sin_datos` con su `motivo` si no hay filas suficientes.

        Una ventana con menos decisiones que `min_n` es demasiado pequeña para una
        pendiente fiable: sale en `windows` con `excluida_de_pendiente=true` y no cuenta
        para las tendencias (`trends`). La respuesta trae `min_n` (el mínimo aplicado) y
        `ventanas_excluidas`. Con menos de 2 ventanas válidas las pendientes van nulas, la
        señal no dispara y el resumen dice por qué. En un proyecto multiclase compara
        nombres de clase."""
        params: dict[str, Any] = {"n_windows": n_windows}
        if subgroup is not None:
            params["subgroup"] = subgroup
        if clinician is not None:
            params["clinician"] = clinician
        if model_version_id is not None:
            params["model_version_id"] = model_version_id
        return await get_client().get(f"/projects/{project_id}/deskilling", params=params)

    @mcp.tool()
    async def get_overrides(
        project_id: int, by: str = "subgroup", model_version_id: int | None = None
    ) -> dict[str, Any]:
        """Overrides (veces que la persona corrige al modelo), en vista de gestor,
        agrupados con `by`: `subgroup`, `phase`, `clinician` (distribución entre
        profesionales en cuartiles y tramos, nunca una fila por persona) o `cambios`
        (tabla de cambios entre decisiones, más abajo). Con
        `by="profesionales"` devuelve la lista de pseudónimos del diario, que es lo
        que acepta el filtro `clinician` de `get_deskilling`. Solo lee.

        Cada celda (por subgrupo o por fase) lleva `n` y `tasa`; la respuesta trae
        `min_n`, la celda mínima: una celda con `n < min_n` da `tasa = null` y no se
        interpreta (una tasa sobre pocas decisiones engaña). En un proyecto multiclase
        un override es cualquier discrepancia entre la clase de la persona y la del
        modelo.

        `by="cambios"` (sin parámetro `min_n`: la celda mínima es la de la API) devuelve la tabla de cambios entre decisiones: una fila
        por salida del modelo y, en ella, cuántas veces la persona decidió cada categoría
        (`n` y `tasa` por celda; `tasa_cambio` en la fila es 1 menos la tasa de la
        diagonal). Las categorías son `refer` y `no-refer` en binario, las clases del
        proyecto en multiclase y «dentro del rango» y «fuera del rango» en regresión con
        rango (sin rango, `filas` va vacío y `motivo` lo dice). Una fila con menos de
        `min_n` decisiones da las tasas nulas y conserva los `n`. `n_sin_decision` cuenta
        las filas del diario que no entran en la tabla.

        Proyecto de REGRESIÓN: con `by="subgroup"` o `by="phase"` cada fila trae
        además `diferencia_media` (media de |cifra de la persona - cifra del modelo|, en la
        unidad del proyecto; la respuesta trae `unidad`). Es informativa: no tiene umbral
        ni alerta, y es nula si el grupo tiene menos de `min_n` decisiones. Un override en
        regresión es un cambio que cruza el corte del rango favorable; un cambio que no lo
        cruza no cuenta como override, y `diferencia_media` sí lo recoge."""
        if by not in AGRUPACIONES_OVERRIDES:
            raise ValueError(f"by no reconocido: {by!r}; válidos: {', '.join(AGRUPACIONES_OVERRIDES)}")
        params: dict[str, Any] = {}
        if model_version_id is not None:
            params["model_version_id"] = model_version_id
        client = get_client()
        if by == "profesionales":
            return await client.get(f"/projects/{project_id}/overrides/clinicians", params=params)
        if by == "cambios":
            return await client.get(f"/projects/{project_id}/overrides/cambios", params=params)
        params["by"] = by
        return await client.get(f"/projects/{project_id}/overrides", params=params)

    @mcp.tool()
    async def upload_outcomes(project_id: int, file_path: str) -> dict[str, Any]:
        """Sube el CSV de resultados (outcomes) del proyecto: una fila por periodo,
        métrica y fuente; si ya existe, la actualiza. Devuelve cuántas filas leyó,
        creó y actualizó. Solo se lee el fichero nombrado."""
        comprobar_ruta_de_subida(file_path)
        return await get_client().upload(
            f"/projects/{project_id}/outcomes", file_path=file_path, fields={}
        )

    @mcp.tool()
    async def get_outcomes(project_id: int, metric_key: str | None = None) -> dict[str, Any]:
        """Tabla y series de outcomes del proyecto, opcionalmente de una sola métrica
        (`metric_key`). Devuelve `rows` y `series` por métrica. Solo lee."""
        params = {"metric_key": metric_key} if metric_key else None
        return await get_client().get(f"/projects/{project_id}/outcomes", params=params)
