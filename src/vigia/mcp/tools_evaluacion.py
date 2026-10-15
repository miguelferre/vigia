"""Tools de evaluación, medidas y explicabilidad."""

from __future__ import annotations

import uuid
from typing import Any

from vigia.mcp.campos_respuesta import con_unidad
from vigia.mcp.client import get_client

# La propuesta multiclase remuestrea la deriva en el servidor y tarda unos 7 s;
# el tiempo de espera general (5 s de httpx) la cortaba con un 504. Solo esta tool.
TIEMPO_PROPUESTA_S = 60.0


def registrar(mcp) -> None:
    @mcp.tool()
    async def run_evaluation(batch_id: int, wait: bool = True, timeout_s: int = 60) -> dict[str, Any]:
        """Encola la evaluación de un lote ya ingerido en los tres monitores del motor.
        Con `wait=true` espera hasta `timeout_s` y, si se agota, devuelve
        `{"status": "en_curso", "timeout": true, "job_id": ...}`: sigue con `get_job`."""
        client = get_client()
        cid = str(uuid.uuid4())
        job = await client.post(f"/batches/{batch_id}/evaluate", json={}, correlation_id=cid)
        return await client.seguir_job(job, wait, timeout_s)

    @mcp.tool()
    async def get_measurements(
        project_id: int,
        monitor_type: str,
        metric_key: str,
        group_code: str | None = None,
        since: str | None = None,
        until: str | None = None,
        model_version_id: int | None = None,
    ) -> dict[str, Any]:
        """Serie temporal de una o varias medidas del proyecto.

        `group_code` filtra por grupo (varios, separados por coma; sin él salen todos). En un
        proyecto MULTICLASE las medidas por clase (precisión, exhaustividad, F1,
        soporte y tasa predicha de cada clase) salen con `group_code` `clase:<valor>`
        (por ejemplo `clase:spam`) y la misma `metric_key` de siempre; para una clase
        concreta, `group_code="clase:spam"` (la API filtra por él). Sin `group_code` salen
        también las medidas por clase, junto al promedio macro (`group_code` nulo). Las
        medidas por clase no tienen umbral (`threshold_low` y `threshold_high` nulos) y
        una clase ausente del lote da `sin_datos`, nunca 0.

        Proyecto de REGRESIÓN: `value` va en la unidad del proyecto (`target_unit`:
        horas, días...) en MAE, RMSE, sesgo medio y sus diferencias entre grupos; `r2`, las
        razones y las tasas de pertenencia al rango no llevan unidad. En las medidas de error
        por grupo, `group_code` es el grupo (`unpriv` o `priv`) y `threshold_low` y
        `threshold_high` van en la misma unidad. Antes de congelar la línea base el monitor
        de calidad no tiene umbrales y sus titulares dan `sin_datos` con «umbral pendiente de
        la línea base». La respuesta trae `unidad` (la `target_unit` del proyecto, o `null`).

        `model_version_id` (opcional) deja solo los puntos de esa versión del modelo;
        sin él salen los de todas. Los ids de versión los da `list_versions`."""
        params: dict[str, Any] = {"monitor_type": monitor_type, "metric_key": metric_key}
        if model_version_id is not None:
            params["model_version_id"] = model_version_id
        if group_code:
            params["group_code"] = group_code
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        serie = await get_client().get(f"/projects/{project_id}/timeline", params=params)
        return await con_unidad(project_id, serie)

    @mcp.tool()
    async def explain_global(
        version_id: int, wait: bool = True, timeout_s: int = 60, clase: int | str | None = None
    ) -> dict[str, Any]:
        """Encola la explicabilidad global (permutación) de la última versión del modelo.

        `clase` (opcional, solo proyectos MULTICLASE): la clase cuya probabilidad se
        explica. Sin ella se explica la probabilidad del conjunto favorable (la suma de
        sus clases) o, si el proyecto no tiene conjunto favorable, la clase más
        frecuente de la línea base. Una clase que no está entre las del proyecto da 422
        con la lista de las válidas. El resultado dice qué se explicó en
        `clase_explicada`. En un proyecto de REGRESIÓN no hay clases que elegir:
        `clase` da 422 («este modelo es de regresión y no tiene clases que elegir»); no la
        pases. La importancia mide el aumento del RMSE al permutar cada variable (con
        etiquetas en la línea base) o la sensibilidad media de la predicción (sin ellas)."""
        client = get_client()
        cid = str(uuid.uuid4())
        cuerpo: dict[str, Any] = {"kind": "permutation"}
        if clase is not None:
            cuerpo["clase"] = clase
        job = await client.post(f"/model-versions/{version_id}/explain/global", json=cuerpo, correlation_id=cid)
        return await client.seguir_job(job, wait, timeout_s)

    @mcp.tool()
    async def explain_row(
        version_id: int,
        batch_id: int,
        row_seq: int,
        wait: bool = True,
        timeout_s: int = 60,
        clase: int | str | None = None,
    ) -> dict[str, Any]:
        """Encola la explicación local (LIME) de una fila concreta de un lote.

        `clase` (opcional, solo proyectos MULTICLASE): la clase a explicar. Sin ella
        se explica la clase que el modelo predijo para esa fila. El resultado trae las
        `k` probabilidades de la fila (`probabilities`) y la clase explicada
        (`clase_explicada`). Una clase fuera de las del proyecto da 422 con las válidas.

        Proyecto de REGRESIÓN: el resultado trae `prediction_value`, la cifra que el
        modelo da para esa fila, en la unidad del proyecto, y los pesos de LIME son
        contribuciones a esa cifra. No hay clase que elegir: `clase` da 422 («este modelo es
        de regresión y no tiene clases que elegir»); no la pases."""
        client = get_client()
        cid = str(uuid.uuid4())
        cuerpo: dict[str, Any] = {"batch_id": batch_id, "row_seq": row_seq}
        if clase is not None:
            cuerpo["clase"] = clase
        job = await client.post(f"/model-versions/{version_id}/explain/local", json=cuerpo, correlation_id=cid)
        return await client.seguir_job(job, wait, timeout_s)

    @mcp.tool()
    async def get_job(job_id: int) -> dict[str, Any]:
        """Estado de un trabajo en segundo plano (evaluación, ingesta, explicación,
        revisión, alertas cruzadas). Devuelve `status`, `progress`, `message`,
        `result` y `error`. Úsala para seguir un trabajo cuando una tool con
        `wait=true` devolvió `{"status": "en_curso", "timeout": true, "job_id": ...}`."""
        return await get_client().get(f"/jobs/{job_id}")

    @mcp.tool()
    async def get_threshold_proposal(project_id: int, tamano_lote: int = 1000) -> dict[str, Any]:
        """Propuesta de umbrales de equidad y calidad calculada sobre la línea base
        congelada de la versión activa, para un tamaño de lote dado (`tamano_lote`,
        1000 por defecto). Devuelve los umbrales propuestos por métrica, cada uno con
        el umbral que tiene hoy el monitor y su origen (`origen_actual`). Solo
        `fabrica` es un valor por defecto sin calibrar y trae `aviso`; un umbral con
        otro origen (`linea_base`, `fabricante`, `criterio_clinico`,
        `politica_organizacion`) es una decisión fijada y no se llama «de fábrica».
        Solo lee: no cambia ningún monitor (para aplicarla, `set_monitor`). Da 409 si
        la versión no tiene línea base congelada.

        En un proyecto MULTICLASE la forma es la misma y la propuesta usa el mismo
        cálculo que Vigía aplicó sola al congelar la línea base (con el mismo
        `tamano_lote` la calidad coincide; la deriva depende del lote, porque remuestrea):
        `quality` con `accuracy` (suelo 1/k),
        `f1_measure` y `area_under_roc` (promedio macro) y `drift` con
        `prediction_drift_score`. La equidad tiene propuesta si el proyecto tiene conjunto
        favorable: el monitor `fairness` propone los umbrales de las medidas
        de pertenencia al conjunto, con el cálculo de la equidad binaria. Sin conjunto
        favorable no se listan medidas de pertenencia. Las medidas por clase (`group_code`
        `clase:<valor>`) no llevan umbral y la API rechaza fijarlo. En las filas de
        calidad y deriva multiclase `valor_linea_base` va nulo. Para ajustar un umbral,
        `set_monitor`. Tarda unos segundos (la deriva remuestrea): esta tool espera hasta
        60 s.

        Proyecto de REGRESIÓN: la forma es la de siempre. `quality` propone
        `mean_absolute_error`, `root_mean_squared_error`, `r2`, `mean_error` y las
        diferencias y razones entre grupos, con valores en la unidad del proyecto (`r2` y
        las razones no llevan unidad), y `drift` propone `prediction_drift_score`. Con rango
        favorable, `fairness` añade las medidas de pertenencia al rango; sin rango no
        hay. Los umbrales salen de remuestrear la línea base con el tamaño de un lote
        (percentiles 1 y 99 con un margen). Al congelar la línea base Vigía ya los aplicó con
        origen `linea_base`; la propuesta sirve para revisarlos o recalcularlos con otro
        `tamano_lote`. La respuesta trae `unidad` (la `target_unit`, o `null`)."""
        propuesta = await get_client().get(
            f"/projects/{project_id}/thresholds/proposal",
            params={"tamano_lote": tamano_lote},
            timeout=TIEMPO_PROPUESTA_S,
        )
        return await con_unidad(project_id, propuesta)
