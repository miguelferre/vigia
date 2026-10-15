"""Tool de auditoría: lanza una revisión de dossier."""

from __future__ import annotations

from typing import Any

from vigia.mcp.client import get_client

# Estados de una revisión que cuentan como «ya hecha o en marcha».
ESTADOS_REVISION_VIVA = ("pendiente", "en_curso", "terminada")


def registrar(mcp) -> None:
    @mcp.tool()
    async def run_dossier_review(
        dossier_id: int,
        motivo: str,
        actor: str | None = None,
        approach: str = "b0",
        corpus: str = "todas",
        dedup: bool = True,
        crosswalk: bool = False,
        role: str | None = None,
        wait: bool = True,
        timeout_s: int = 60,
        forzar: bool = False,
    ) -> dict[str, Any]:
        """Lanza una revisión (`b0`, `p3` o `auto`) sobre un dossier ya creado.

        `p3`/`auto` con backend LLM no local exigen la confirmación
        en `/ajustes`; esta tool no la sustituye.

        Si el dossier ya tiene una revisión del mismo `approach` pendiente, en curso
        o terminada, NO lanza otra: devuelve `{"status": "ya_existe", "aviso": ...,
        "revision": {...}}` con la existente (`GET /reviews/{id}` da los hallazgos).
        Para lanzar otra de todos modos, `forzar=true`.

        `actor` es opcional: el nombre del diario es el de la entrada del MCP
        (`--actor`); uno distinto se guarda como `actor_detalle`."""
        client = get_client()
        if not forzar:
            dossier = await client.get(f"/dossiers/{dossier_id}")
            previa = next(
                (
                    r
                    for r in dossier.get("reviews") or []
                    if r.get("approach") == approach and r.get("status") in ESTADOS_REVISION_VIVA
                ),
                None,
            )
            if previa is not None:
                return {
                    "status": "ya_existe",
                    "aviso": (
                        f"el dossier {dossier_id} ya tiene la revisión {previa.get('id')} con el "
                        f"enfoque {approach} ({previa.get('status')}); no se lanza otra. "
                        "Pasa forzar=true para crear una nueva"
                    ),
                    "revision": previa,
                }
        cuerpo = {
            "approach": approach,
            "corpus": corpus,
            "dedup": dedup,
            "crosswalk": crosswalk,
            **client.cuerpo_actor(actor),
            "role": role,
            "motivo": motivo,
        }
        job = await client.post(f"/dossiers/{dossier_id}/reviews", json=cuerpo)
        return await client.seguir_job(job, wait, timeout_s)
