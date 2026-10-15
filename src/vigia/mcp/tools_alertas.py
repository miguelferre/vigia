"""Tools de alertas: aquí vive `close` de `act_on_alert`, una de las dos
acciones destructivas del MCP (la otra, `reset_project`, está en `tools_proyectos.py`)."""

from __future__ import annotations

from typing import Any

from vigia.mcp.client import get_client


def registrar(mcp) -> None:
    @mcp.tool()
    async def get_alerts(
        project_id: int,
        status: str | None = None,
        severity: str | None = None,
        monitor_type: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Alertas de un proyecto, filtradas por estado, severidad o monitor. Sin `status`
        no salen las retiradas (las que nacieron en un lote borrado): pídelas con
        `status=retirada`."""
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if status:
            params["status"] = status
        if severity:
            params["severity"] = severity
        if monitor_type:
            params["monitor_type"] = monitor_type
        return await get_client().get(f"/projects/{project_id}/alerts", params=params)

    @mcp.tool()
    async def get_alert(alert_id: int) -> dict[str, Any]:
        """Detalle de una alerta: métrica, severidad, etapa, evidencia, historial de
        acciones, pasos del protocolo por hito y riesgos enlazados. Úsala antes de
        `act_on_alert` para decidir el siguiente hito; `get_alerts` solo lista."""
        return await get_client().get(f"/alerts/{alert_id}")

    @mcp.tool()
    async def act_on_alert(
        alert_id: int,
        accion: str,
        motivo: str,
        actor: str | None = None,
        role: str | None = None,
        hallazgos: str | None = None,
        acciones: list[dict[str, Any]] | None = None,
        action: str | None = None,
        attachment_path: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Actúa sobre una alerta por uno de sus hitos: `acknowledge`, `investigate`,
        `decide`, `close` o `acciones` (una acción suelta del catálogo).

        `decide` exige que la investigación ya esté registrada (`investigate`, con sus
        `hallazgos`) y `acciones`: una lista de `{"key": <clave>, "notes": <texto
        opcional>}` con al menos un elemento; cualquier otro campo del elemento da
        422. `key` es una clave del catálogo: `contener_subgrupo`,
        `cambiar_umbral`, `pedir_reentrenamiento`, `escalar`, `retirar_modelo`,
        `cribado_retrospectivo`, `registrar_riesgo`, `nota` o `seguir_vigilando`;
        otra clave da 422. `notes` es el motivo propio de esa acción y, si falta,
        se usa `motivo`. La decisión se registra una sola vez por alerta (409 si ya
        está) y no la cierra. Ojo: `registrar_riesgo` en `decide` solo anota la
        decisión; NO crea el riesgo. Para darlo de alta, llama a `create_risk`.

        `actor` es opcional: el nombre que sale en el diario es siempre el de la
        entrada del MCP (`--actor`). Si pasas un `actor` distinto, se guarda como
        `actor_detalle`, solo de contexto («por encargo de …»), en el payload del
        evento; no cambia quién figura como autor.

        `attachment_path` (solo con `accion="acciones"`) es una referencia en texto a
        un documento de apoyo (una ruta o un identificador): Vigía la guarda tal cual en
        la acción y no sube ni lee el fichero.

        `close` es irreversible desde la interfaz (solo se reabre a mano) y exige
        `confirm=true`; sin él, esta tool falla antes de llamar a la API. El modelo
        rellena `confirm`: la aprobación por llamada es del host del MCP, no de Vigía."""
        if accion not in ("acknowledge", "investigate", "decide", "close", "acciones"):
            raise ValueError(
                f"accion no reconocida: {accion!r}; válidas: acknowledge, investigate, decide, close, acciones"
            )
        if accion == "close" and not confirm:
            raise ValueError("cerrar una alerta es irreversible: pasa confirm=true para hacerlo")
        client = get_client()
        cuerpo: dict[str, Any] = {**client.cuerpo_actor(actor), "role": role, "motivo": motivo}
        if accion == "investigate":
            if not hallazgos:
                raise ValueError("investigate exige 'hallazgos'")
            cuerpo["hallazgos"] = hallazgos
            return await client.post(f"/alerts/{alert_id}/investigate", json=cuerpo)
        if accion == "decide":
            if not acciones:
                raise ValueError("decide exige al menos una acción del catálogo en 'acciones'")
            cuerpo["acciones"] = acciones
            return await client.post(f"/alerts/{alert_id}/decide", json=cuerpo)
        if accion == "acciones":
            if not action:
                raise ValueError("accion='acciones' exige 'action' (clave del catálogo)")
            cuerpo["action"] = action
            cuerpo["attachment_path"] = attachment_path
            return await client.post(f"/alerts/{alert_id}/actions", json=cuerpo)
        if accion == "close":
            return await client.post(f"/alerts/{alert_id}/close", json=cuerpo)
        return await client.post(f"/alerts/{alert_id}/acknowledge", json=cuerpo)
