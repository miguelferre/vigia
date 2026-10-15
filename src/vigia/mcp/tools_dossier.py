"""Tool de alta de dossier: por importación de un `dossier.json` del
paquete `interaction_review` o a mano con perfil, experiencia e inventario."""

from __future__ import annotations

import json
from typing import Any

import anyio

from vigia.mcp.client import get_client
from vigia.mcp.rutas import comprobar_ruta_de_subida


def registrar(mcp) -> None:
    @mcp.tool()
    async def create_dossier(
        project_id: int,
        motivo: str,
        actor: str | None = None,
        dossier_path: str | None = None,
        profile: dict[str, str] | None = None,
        experience: dict[str, str] | None = None,
        inventory: dict[str, str] | None = None,
        system_name: str | None = None,
        domain: str | None = None,
        include_telemetry: bool = False,
        role: str | None = None,
    ) -> dict[str, Any]:
        """Crea el dossier de auditoría de un proyecto y devuelve el dossier (con su
        `id`, que pide `run_dossier_review`). Dos vías, exactamente una: con
        `dossier_path` (ruta a un `dossier.json` del paquete `interaction_review`;
        solo se lee ese fichero) lo importa por `POST /projects/{id}/dossiers/import`;
        con `profile`, `experience` e `inventory` (diccionarios clave a texto) lo crea
        a mano por `POST /projects/{id}/dossiers`. `include_telemetry` añade la
        telemetría del propio proyecto. Úsala antes de lanzar una revisión.

        `actor` es opcional: el nombre del diario es el de la entrada del MCP
        (`--actor`); uno distinto se guarda como `actor_detalle`."""
        manual = any(x is not None for x in (profile, experience, inventory))
        if dossier_path is not None and manual:
            raise ValueError("pasa dossier_path o bien profile, experience e inventory, no las dos vías")
        if dossier_path is None and not manual:
            raise ValueError("falta la fuente del dossier: dossier_path, o profile, experience e inventory")
        client = get_client()
        cuerpo: dict[str, Any] = {
            **client.cuerpo_actor(actor),
            "role": role,
            "motivo": motivo,
            "include_telemetry": include_telemetry,
        }
        if dossier_path is not None:
            comprobar_ruta_de_subida(dossier_path)
            try:
                crudo = await anyio.Path(dossier_path).read_text(encoding="utf-8")
                datos = json.loads(crudo)
            except OSError as exc:
                raise ValueError(f"no se puede leer {dossier_path}: {exc.strerror or exc}") from exc
            except ValueError as exc:
                raise ValueError(f"{dossier_path} no es un JSON válido: {exc}") from exc
            if not isinstance(datos, dict):
                raise ValueError(f"{dossier_path} debe contener un objeto JSON con system_name, domain y sources")
            for clave in ("system_name", "domain", "summary", "sources"):
                if clave in datos:
                    cuerpo[clave] = datos[clave]
            return await client.post(f"/projects/{project_id}/dossiers/import", json=cuerpo)
        cuerpo.update(
            {
                "system_name": system_name,
                "domain": domain,
                "profile": profile or {},
                "experience": experience or {},
                "inventory": inventory or {},
            }
        )
        return await client.post(f"/projects/{project_id}/dossiers", json=cuerpo)
