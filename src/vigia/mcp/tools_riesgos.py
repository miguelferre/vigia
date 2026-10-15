"""Tools del registro de riesgos."""

from __future__ import annotations

import uuid
from typing import Any

from vigia.mcp.client import get_client

ACCIONES_RIESGO = ("mover", "seguimiento", "cerrar")


def registrar(mcp) -> None:
    @mcp.tool()
    async def list_risks(
        project_id: int, status: str | None = None, offset: int = 0, limit: int = 50
    ) -> dict[str, Any]:
        """Riesgos del proyecto (matriz 5x5), filtrables por `status` (`abierto`,
        `en_seguimiento`, `cerrado`). Devuelve `items` con código, niveles de impacto
        y probabilidad, nivel, estado y alerta de origen, y el `total`."""
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if status:
            params["status"] = status
        return await get_client().get(f"/projects/{project_id}/risks", params=params)

    @mcp.tool()
    async def create_risk(
        project_id: int,
        title: str,
        motivo: str,
        impact_level: int | None = None,
        probability_level: int | None = None,
        description: str | None = None,
        origin_alert_id: int | None = None,
        actor: str | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        """Da de alta un riesgo y lo devuelve. Dos vías: desde una alerta
        (`origin_alert_id`; los niveles son opcionales y, si vienen, sustituyen a la
        propuesta) o a mano (sin alerta, `impact_level` y `probability_level` de 1 a 5
        son obligatorios). Úsala cuando una alerta o un hallazgo merece quedar en el
        registro de riesgos (`registrar_riesgo` en `act_on_alert` no lo crea).

        `actor` es opcional: el nombre del diario es siempre el de la entrada del MCP
        (`--actor`); uno distinto se guarda como `actor_detalle`, solo de contexto
        («por encargo de …»)."""
        client = get_client()
        cuerpo: dict[str, Any] = {
            "title": title,
            "description": description,
            "origin_alert_id": origin_alert_id,
            "impact_level": impact_level,
            "probability_level": probability_level,
            **client.cuerpo_actor(actor),
            "role": role,
            "motivo": motivo,
        }
        return await client.post(f"/projects/{project_id}/risks", json=cuerpo)

    @mcp.tool()
    async def update_risk(
        risk_id: int,
        accion: str,
        motivo: str,
        impact_level: int | None = None,
        probability_level: int | None = None,
        actor: str | None = None,
        role: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Cambia un riesgo y lo devuelve. `accion`: `mover` (a otra celda de la
        matriz; exige `impact_level` y `probability_level`), `seguimiento` (pasa de
        `abierto` a `en_seguimiento`) o `cerrar`. `cerrar` es terminal
        y exige `confirm=true`; sin él, esta tool falla antes de llamar a la API. El
        modelo rellena `confirm`: la aprobación por llamada es del host del MCP, no de
        Vigía. `actor` es opcional: el nombre del diario es el de la entrada del MCP
        (`--actor`); uno distinto se guarda como `actor_detalle`."""
        if accion not in ACCIONES_RIESGO:
            raise ValueError(f"accion no reconocida: {accion!r}; válidas: {', '.join(ACCIONES_RIESGO)}")
        client = get_client()
        base: dict[str, Any] = {**client.cuerpo_actor(actor), "role": role, "motivo": motivo}
        cid = str(uuid.uuid4())
        if accion == "mover":
            if impact_level is None or probability_level is None:
                raise ValueError("mover exige impact_level y probability_level (de 1 a 5)")
            cuerpo = {**base, "impact_level": impact_level, "probability_level": probability_level}
            return await client.patch(f"/risks/{risk_id}/move", json=cuerpo, correlation_id=cid)
        if accion == "seguimiento":
            return await client.patch(
                f"/risks/{risk_id}/status", json={**base, "status": "en_seguimiento"}, correlation_id=cid
            )
        if not confirm:
            raise ValueError("cerrar un riesgo es terminal: pasa confirm=true para hacerlo")
        return await client.post(f"/risks/{risk_id}/close", json=base, correlation_id=cid)
