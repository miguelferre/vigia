"""Tools de versiones de modelo y su comparación."""

from __future__ import annotations

from typing import Any

from vigia.mcp.client import get_client


def registrar(mcp) -> None:
    @mcp.tool()
    async def list_versions(project_id: int) -> dict[str, Any]:
        """Lista las versiones de modelo de un proyecto, con su línea base y su artefacto.

        Qué hace: lee el proyecto y devuelve solo sus versiones. Qué devuelve:
        `{"project_id", "active_version_id", "versions": [...]}`; cada versión trae
        `id`, `label`, `is_active`, `model_kind`, `baseline_batch_id` (el lote de su
        línea base, o `null` si aún no la tiene), `frozen_at`, `artifact_kind` y
        `artifact_uploaded_at` (el modelo ejecutable subido, o `null`). Cuándo usarla:
        antes de `create_version`, `activate_version`, `freeze_baseline` o
        `compare_versions`, para saber qué ids hay y cuál está activa."""
        proyecto = await get_client().get(f"/projects/{project_id}")
        return {
            "project_id": proyecto["id"],
            "active_version_id": proyecto.get("active_version_id"),
            "versions": proyecto.get("versions", []),
        }

    @mcp.tool()
    async def create_version(
        project_id: int,
        label: str,
        motivo: str,
        actor: str | None = None,
        role: str | None = None,
        model_kind: str = "external_files",
        fairness_window_n: int | None = None,
        fairness_interval_method: str | None = None,
    ) -> dict[str, Any]:
        """Crea una versión nueva de modelo dentro de un proyecto, sin activarla.

        Qué hace: da de alta la versión (`POST /projects/{id}/versions`) y deja el
        evento en el diario. Qué devuelve: la versión creada, con su `id`; no tiene
        línea base ni artefacto todavía. Cuándo usarla: al empezar la v2 de un modelo.
        Orden habitual: `create_version`, `upload_model_artifact` si el modelo es
        ejecutable, `upload_dataset` con `role="baseline"` y `model_version_id` de la
        versión nueva (esa ingesta ya congela su línea base), `activate_version` y
        `compare_versions`.

        `model_kind`: `external_files` (los lotes traen ya las predicciones),
        `executable` o `sim_logistic` (solo dominios del simulador).
        `fairness_interval_method`: `ventanas` o `lote`; sin él, hereda el de la activa.
        `actor` es opcional: el nombre del diario es el de la entrada del MCP; uno
        distinto se guarda como `actor_detalle`."""
        client = get_client()
        cuerpo: dict[str, Any] = {
            **client.cuerpo_actor(actor),
            "role": role,
            "motivo": motivo,
            "label": label,
            "model_kind": model_kind,
        }
        if fairness_window_n is not None:
            cuerpo["fairness_window_n"] = fairness_window_n
        if fairness_interval_method is not None:
            cuerpo["fairness_interval_method"] = fairness_interval_method
        return await client.post(f"/projects/{project_id}/versions", json=cuerpo)

    @mcp.tool()
    async def activate_version(
        version_id: int,
        motivo: str,
        actor: str | None = None,
        role: str | None = None,
        congelar_linea_base: int | None = None,
    ) -> dict[str, Any]:
        """Activa una versión de modelo: los lotes nuevos del proyecto pasan a ella.

        Qué hace: marca la versión como activa y desactiva la anterior
        (`POST /model-versions/{id}/activate`). Con `congelar_linea_base` (el id de un
        lote o de un dataset ya ingerido de la versión) congela su línea base en el
        mismo paso. Qué devuelve: la versión activada. Cuándo usarla: cuando la v2 ya
        tiene su línea base y quieres que reciba la producción. `congelar_linea_base`
        solo vale si la versión aún no la tiene congelada (si no, 409). Para comparar antes de
        activar no hace falta: `compare_versions` acepta cualquier par de versiones.
        `actor` es opcional: el nombre del diario es el de la entrada del MCP."""
        client = get_client()
        cuerpo: dict[str, Any] = {**client.cuerpo_actor(actor), "role": role, "motivo": motivo}
        if congelar_linea_base is not None:
            cuerpo["congelar_linea_base"] = congelar_linea_base
        return await client.post(f"/model-versions/{version_id}/activate", json=cuerpo)

    @mcp.tool()
    async def freeze_baseline(
        version_id: int,
        batch_id: int,
        motivo: str,
        actor: str | None = None,
        role: str | None = None,
        laboratorio: bool = False,
    ) -> dict[str, Any]:
        """Congela la línea base de una versión sobre un lote ya ingerido.

        Qué hace: fija ese lote como referencia de la versión
        (`POST /model-versions/{id}/baseline`); los umbrales propuestos, la deriva y
        la comparación de versiones miden contra ella. Qué devuelve: la versión con
        `baseline_batch_id` y `frozen_at`. Cuándo usarla: solo si la versión aún
        no tiene línea base congelada (la ingesta de un dataset `baseline` ya la
        congela, y entonces esta tool da 409), por ejemplo con un lote de producción
        ya ingerido en la versión; el `batch_id` sale de `ingest_job.result.batch_id`.
        `laboratorio=true` permite recongelar y marca una línea base de laboratorio
        (datos sintéticos a la carta).
        `actor` es opcional: el nombre del diario es el de la entrada del MCP."""
        client = get_client()
        cuerpo = {
            **client.cuerpo_actor(actor),
            "role": role,
            "motivo": motivo,
            "batch_id": batch_id,
            "laboratorio": laboratorio,
        }
        return await client.post(f"/model-versions/{version_id}/baseline", json=cuerpo)
