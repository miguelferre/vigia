"""Tool `set_monitor` (fusión de umbrales)."""

from __future__ import annotations

from typing import Any

from vigia.mcp.client import get_client


def _fusionar_umbrales(actual: Any, nuevos: Any) -> Any:
    """Los umbrales de `nuevos` sustituyen a los de `actual` con la misma
    `metric_key` y `kind` (en su sitio) o se añaden al final; el resto se conserva.
    La clave es la de `alta-umbrales-guardar.ts`. Algo que no tenga la forma
    `{"thresholds": [...]}` pasa tal cual y lo valida la API."""
    if not isinstance(nuevos, dict) or not isinstance(nuevos.get("thresholds"), list):
        return nuevos
    lista = actual.get("thresholds") if isinstance(actual, dict) else None
    fusion: dict[tuple[Any, Any], Any] = {
        (t.get("metric_key"), t.get("kind")): t for t in (lista or []) if isinstance(t, dict)
    }
    for t in nuevos["thresholds"]:
        if not isinstance(t, dict):
            return nuevos
        fusion[(t.get("metric_key"), t.get("kind"))] = t
    return {**nuevos, "thresholds": list(fusion.values())}


def registrar(mcp) -> None:
    @mcp.tool()
    async def set_monitor(
        monitor_id: int,
        motivo: str,
        actor: str | None = None,
        role: str | None = None,
        enabled: bool | None = None,
        config: dict[str, Any] | None = None,
        thresholds: dict[str, Any] | None = None,
        protocolo_md: str | None = None,
        protocol: list[dict[str, Any]] | None = None,
        laboratorio: dict[str, Any] | None = None,
        reemplazar_umbrales: bool = False,
    ) -> dict[str, Any]:
        """Cambia configuración, umbrales, activación o protocolo de un monitor.

        `thresholds` (`{"thresholds": [{metric_key, kind, value, origen?, nota?}]}`) se
        FUSIONA con los umbrales que ya tiene el monitor: cada entrada nombrada sustituye
        a la de su misma `metric_key` y `kind` (o se añade), y las no nombradas se
        conservan. Con `reemplazar_umbrales=true` la lista pasa a ser
        exactamente la que se manda, que es la forma de quitar un umbral.

        `origen` de un umbral: `linea_base` (propuesto desde la línea base del modelo),
        `fabricante`, `criterio_clinico`, `politica_organizacion` (lo impone una
        política de la organización; úsalo en vez de `criterio_clinico` o `fabrica`
        cuando el valor viene de una norma interna) o `fabrica` (el valor por defecto
        sin calibrar). Sin `origen`, Vigía lo sirve como `fabrica`.

        En un proyecto MULTICLASE los umbrales se fijan sobre las medidas del monitor
        (`accuracy`, `f1_measure`, `area_under_roc`, `prediction_drift_score`...), no sobre
        una clase: las medidas por clase (`group_code` `clase:<valor>`) no tienen umbral y
        un umbral que apunte a una da 422 con un mensaje que lo explica. Los umbrales
        que Vigía propuso desde la línea base al congelarla tienen origen `linea_base`;
        `get_threshold_proposal` los recalcula.

        `actor` es opcional: el nombre del diario es el de la entrada del MCP
        (`--actor`); uno distinto se guarda como `actor_detalle`, solo de contexto
        («por encargo de …»)."""
        client = get_client()
        cuerpo: dict[str, Any] = {**client.cuerpo_actor(actor), "role": role, "motivo": motivo}
        if enabled is not None:
            cuerpo["enabled"] = enabled
        if config is not None:
            cuerpo["config"] = config
        if thresholds is not None:
            if not reemplazar_umbrales:
                actual = (await client.get(f"/monitors/{monitor_id}")).get("thresholds") or {}
                thresholds = _fusionar_umbrales(actual, thresholds)
            cuerpo["thresholds"] = thresholds
        if protocolo_md is not None:
            cuerpo["protocolo_md"] = protocolo_md
        if protocol is not None:
            cuerpo["protocol"] = protocol
        if laboratorio is not None:
            cuerpo["laboratorio"] = laboratorio
        return await client.patch(f"/monitors/{monitor_id}", json=cuerpo)
