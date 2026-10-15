"""Tools de la demo guiada y su laboratorio."""

from __future__ import annotations

from typing import Any

from vigia.mcp.client import get_client


def registrar(mcp) -> None:
    @mcp.tool()
    async def run_scenario(
        scenario_key: str,
        source: str = "canned",
        with_human: bool = False,
        project_id: int | None = None,
        project_name: str | None = None,
        play: bool = True,
    ) -> dict[str, Any]:
        """Crea una reproducción de demo y, si `play`, la reproduce entera."""
        client = get_client()
        cuerpo: dict[str, Any] = {
            "scenario_key": scenario_key,
            "source": source,
            "with_human": with_human,
        }
        if project_id is not None:
            cuerpo["project_id"] = project_id
        if project_name is not None:
            cuerpo["project_name"] = project_name
        run = await client.post("/demo/runs", json=cuerpo)
        if not play:
            return run
        job = await client.post(f"/demo/runs/{run['id']}/play", json={})
        resultado = await client.wait_for_job(job["id"])
        return {"run": run, "play_job": resultado}

    @mcp.tool()
    async def next_phase(run_id: int, wait: bool = True, timeout_s: int = 60) -> dict[str, Any]:
        """Reproduce la siguiente fase pendiente del guion de una demo. Con `wait=true`
        espera hasta `timeout_s`; si se agota devuelve `status="en_curso"` y `job_id`
        para seguirlo con `get_job`."""
        client = get_client()
        job = await client.post(f"/demo/runs/{run_id}/next", json={})
        return await client.seguir_job(job, wait, timeout_s)

    @mcp.tool()
    async def lab_generate(
        run_id: int,
        phase_key: str,
        motivo: str,
        actor: str | None = None,
        params: dict[str, Any] | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Genera una fase a la carta (laboratorio) sobre el proyecto de la demo, sin avanzar el guion.
        `actor` es opcional: el nombre del diario es el de la entrada del MCP (`--actor`);
        uno distinto se guarda como `actor_detalle`."""
        client = get_client()
        cuerpo: dict[str, Any] = {
            "phase_key": phase_key,
            "params": params or {},
            **client.cuerpo_actor(actor),
            "motivo": motivo,
        }
        if seed is not None:
            cuerpo["seed"] = seed
        job = await client.post(f"/demo/runs/{run_id}/lab", json=cuerpo)
        return await client.wait_for_job(job["id"])
