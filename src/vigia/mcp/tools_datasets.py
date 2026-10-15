"""Tool de subida de datasets (`model_version_id`)."""

from __future__ import annotations

import uuid
from typing import Any

from vigia.mcp.campos_respuesta import con_campos_tardios
from vigia.mcp.client import VigiaError, get_client
from vigia.mcp.mapeo_plantilla import _mapeo_desde_plantilla, _plantilla_utilizable
from vigia.mcp.rutas import comprobar_ruta_de_subida


def registrar(mcp) -> None:
    @mcp.tool()
    async def upload_dataset(
        project_id: int,
        file_path: str,
        kind: str,
        role: str,
        name: str | None = None,
        mapping: dict[str, Any] | None = None,
        wait: bool = True,
        timeout_s: int = 60,
        model_version_id: int | None = None,
    ) -> dict[str, Any]:
        """Sube un dataset (fichero nombrado explícitamente), fija su mapeo y siempre
        lo ingiere. `upload_dataset` nunca escanea directorios.

        `role`: `baseline` (la línea base de la versión) o `production` (un lote de
        producción). `kind`: `combined` (un fichero con predicción y etiqueta),
        `payload` (solo entradas y salidas del modelo), `feedback` (etiquetas, que
        se emparejan con un `payload` por `id_col`), `usage_log` o `outcome`
        (para estos dos hay tools propias: `upload_usage_log`, `upload_outcomes`).
        Otro valor da 422.

        Etiquetas tardías (`kind="feedback"`): la respuesta trae `lotes_con_verdad` (los
        lotes que recibieron al menos una etiqueta), `lotes_reevaluados` y
        `lotes_a_reevaluar`. Si `lotes_a_reevaluar` no está vacío (o `evaluate_motivo` lo
        dice), la calidad aún no usa esa verdad: llama a `run_evaluation` con cada uno de
        esos lotes.

        Claves válidas de `mapping` (otra clave da 422): `prediction_col`,
        `probability_col`, `probability_format` (`scalar` o `list`),
        `probability_index`, `label_col`, `id_col`, `timestamp_col`,
        `protected_attr_col`, `protected_kind` (`numeric_ranges` o `categorical`),
        `unpriv_groups`, `priv_groups` (listas no vacías con `protected_attr_col`),
        `feature_cols`, `clinician_col`, `subgroup_col`, `favorable_label`, y
        `classes` y `probability_cols` (listas, para multiclase), `target_unit` y
        `favorable_ranges` (solo en regresión). Ejemplo: `{"prediction_col": "pred", "label_col": "y", "id_col": "id",
        "feature_cols": ["edad", "crp"]}`.

        Proyecto MULTICLASE (de 3 a 20 clases): `prediction_col` y `label_col` llevan
        el NOMBRE de la clase (texto, sin espacios sobrantes); `classes` es la lista de
        clases en el orden de las probabilidades; la probabilidad va en `probability_cols`
        (una columna por clase, en el orden de `classes`) o en una sola columna con
        `probability_format="list"` de longitud k. `probability_index` no se usa.
        `favorable_label` es una LISTA de 1 a k-1 clases (el conjunto favorable) o
        `null`. Una predicción con una clase fuera de las del proyecto da 422 al guardar
        el mapeo; una etiqueta real con una clase nueva se ingiere y avisa. Los avisos
        de la ingesta (orden de las probabilidades, suma distinta de 1, clases sin
        filas) salen en `ingest_job`. En la línea base, la ingesta fija las clases del
        proyecto y aplica sus umbrales. Ejemplo: `{"prediction_col": "pred",
        "label_col": "y", "id_col": "id", "favorable_label": ["legitimo"],
        "classes": ["spam", "phishing", "legitimo"],
        "probability_cols": ["p_spam", "p_phishing", "p_legitimo"]}`.

        Proyecto de REGRESIÓN: `prediction_col` y `label_col` llevan cifras (con punto
        decimal, sin unidad) y no hay `probability_col`. `target_unit` y `favorable_ranges`
        (de 1 a 3 intervalos `[min, max]`; `null` abre un extremo) van como claves del
        `mapping`, no como parámetros. El rango no cambia después de congelar la línea
        base. La ingesta de la línea base fija la unidad y el rango del proyecto y aplica
        los umbrales de error (origen `linea_base`). Ejemplo: `{"prediction_col": "pred",
        "label_col": "y", "id_col": "id", "target_unit": "horas",
        "favorable_ranges": [[40, 81]]}`.

        Mapeo: si pasas `mapping`, se usa tal cual (`mapping_origen="parametro"`). Si no
        lo pasas, hereda la plantilla de mapeo del proyecto, la que fija
        `set_mapping_template` o `create_project` (`mapping_origen="plantilla_proyecto"`,
        y `mapping_aplicado` trae el mapeo resultante). Si no pasas `mapping` y el proyecto
        no tiene plantilla, falla con 422 antes de subir nada: pasa `mapping` o fija la
        plantilla con `set_mapping_template`.

        `model_version_id` (opcional) ingiere el dataset en esa versión del modelo y no
        en la activa: así se sube la línea base de una versión nueva sin activarla
        (la ingesta de una línea base ya la congela). Sin él, va a la versión activa. Los ids de
        versión los da `list_versions`.

        Con `wait=true` (por defecto) espera al trabajo de ingesta hasta `timeout_s` y
        devuelve su resultado en `ingest_job` (filas, avisos y errores de ingesta); si
        se agota, `ingest_job` trae `status="en_curso"` y `job_id` para seguirlo con
        `get_job`. Con `wait=false` devuelve el trabajo encolado."""
        comprobar_ruta_de_subida(file_path)
        client = get_client()
        cid = str(uuid.uuid4())
        if mapping is None:
            # Sin `mapping`, la plantilla del proyecto o un error claro
            # ANTES de subir y encolar nada.
            proyecto = await client.get(f"/projects/{project_id}")
            plantilla = proyecto.get("mapping_template_json")
            if not _plantilla_utilizable(plantilla):
                motivo = (
                    "el proyecto no tiene plantilla de mapeo"
                    if not plantilla
                    else "la plantilla de mapeo del proyecto no fija ninguna columna"
                )
                raise VigiaError(
                    422,
                    f"falta el mapeo: no se pasó `mapping` y {motivo}",
                    "pasa `mapping` o fija la plantilla del proyecto con set_mapping_template",
                )
        subida = await client.upload(
            f"/projects/{project_id}/datasets/upload",
            file_path=file_path,
            fields={"kind": kind, "role": role, **({"name": name} if name else {})},
            correlation_id=cid,
        )
        dataset_id = subida["dataset"]["id"]
        mapping_aplicado: dict[str, Any] | None = None
        if mapping is None:
            mapping = mapping_aplicado = _mapeo_desde_plantilla(subida.get("suggested_mapping"))
        await client.put(
            f"/datasets/{dataset_id}/mapping",
            json={"mapping": mapping},
            correlation_id=cid,
        )
        cuerpo_ingesta: dict[str, Any] = {}
        if model_version_id is not None:
            cuerpo_ingesta["model_version_id"] = model_version_id
        ingesta = await client.post(f"/datasets/{dataset_id}/ingest", json=cuerpo_ingesta, correlation_id=cid)
        ingesta = await client.seguir_job(ingesta, wait, timeout_s)
        if ingesta.get("status") == "error":
            # Una ingesta fallida es un error de la tool, con el motivo del trabajo.
            motivo = str(ingesta.get("error") or ingesta.get("message") or "la ingesta falló")
            codigo, _, detalle = motivo.partition(": ")
            if codigo.isdigit() and detalle:
                raise VigiaError(int(codigo), detalle, "corrige el mapeo (set_mapping_template o `mapping`) y vuelve a subir")
            raise VigiaError(422, motivo, "corrige el mapeo (set_mapping_template o `mapping`) y vuelve a subir")
        respuesta: dict[str, Any] = {
            "dataset": subida["dataset"],
            "ingest_job": ingesta,
            "mapping_origen": "plantilla_proyecto" if mapping_aplicado is not None else "parametro",
        }
        if mapping_aplicado is not None:
            respuesta["mapping_aplicado"] = mapping_aplicado
        return con_campos_tardios(respuesta, ingesta.get("result"))
