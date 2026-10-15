"""Tools de lectura del diario, exportación de informes y ajustes."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from vigia.mcp.client import get_client

# El diario entero llegó a 108 384 caracteres; por defecto, los 200 más recientes.
LIMITE_DIARIO_POR_DEFECTO = 200


def registrar(mcp) -> None:
    @mcp.tool()
    async def get_events(
        actor_kind: str | None = None,
        object_type: str | None = None,
        object_id: int | None = None,
        project_id: int | None = None,
        since: str | None = None,
        until: str | None = None,
        correlation_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Eventos del diario, filtrados; del más reciente al más antiguo."""
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        for clave, valor in (
            ("actor_kind", actor_kind),
            ("object_type", object_type),
            ("object_id", object_id),
            ("project_id", project_id),
            ("since", since),
            ("until", until),
            ("correlation_id", correlation_id),
        ):
            if valor is not None:
                params[clave] = valor
        return await get_client().get("/events", params=params)

    @mcp.tool()
    async def export_report(
        kind: str,
        since: str | None = None,
        until: str | None = None,
        review_id: int | None = None,
        format: str = "json",
        limit: int = LIMITE_DIARIO_POR_DEFECTO,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Exporta el diario (`kind="diario"`) o el informe de una revisión de
        dossier (`kind="revision"`, solo `format="html"`). Siempre devuelve un objeto
        (no texto JSON): el informe de una revisión sale como `{"review_id", "html"}`.

        `project_id` acota el diario a ese proyecto (más los eventos globales, los que
        no son de ningún proyecto); sin él sale el diario de todos los proyectos.

        El diario sale acotado: `limit` (por defecto 200) es el máximo de eventos y
        se quedan los MÁS RECIENTES, en orden cronológico; `since` y `until` siguen
        acotando por fecha antes de aplicar `limit`. La respuesta es
        `{"total", "devueltos", "limit", "truncado", "eventos"}` con `format="json"`:
        `total` son los eventos que hay en el periodo y `truncado` es `true` si `limit`
        dejó fuera los más antiguos (para verlos, acota con `since`/`until`). Con
        `format="html"` la respuesta lleva los mismos campos salvo `eventos` y el
        documento en `html`, recortado desde el evento más antiguo que cabe
        (`since_aplicado`; si hay varios eventos en ese mismo instante entran
        todos y `devueltos` los cuenta). `limit` no afecta a `kind="revision"`."""
        client = get_client()
        if kind == "diario":
            if limit < 1:
                raise ValueError("limit debe ser 1 o más")
            params: dict[str, Any] = {"format": "json"}
            if project_id is not None:
                params["project_id"] = project_id
            if since:
                params["since"] = since
            if until:
                params["until"] = until
            if format not in ("json", "html"):
                # La API responde con su 422 («formato no soportado»).
                return await client.get("/events/export", params={**params, "format": format})
            eventos = await client.get("/events/export", params=params)
            total = len(eventos)
            truncado = total > limit
            resumen: dict[str, Any] = {"total": total, "limit": limit, "truncado": truncado}
            if format == "json":
                recientes = eventos[-limit:] if truncado else eventos
                return {**resumen, "devueltos": len(recientes), "eventos": recientes}
            devueltos = total
            if truncado:
                params["since"] = eventos[-limit]["ts"]
                devueltos = sum(1 for e in eventos if e["ts"] >= params["since"])
            resumen["devueltos"] = devueltos
            resumen["since_aplicado"] = params.get("since")
            resumen["html"] = await client.get("/events/export", params={**params, "format": "html"})
            return resumen
        if kind == "revision":
            if review_id is None:
                raise ValueError("kind='revision' exige review_id")
            return {"review_id": review_id, "html": await client.get(f"/reviews/{review_id}/report")}
        raise ValueError(f"kind no reconocido: {kind!r}; válidos: diario, revision")

    @mcp.tool()
    async def get_settings(reveal: bool = False) -> dict[str, Any]:
        """Ajustes actuales de la aplicación (el token MCP va oculto salvo `reveal=true`;
        la clave LLM va siempre oculta, también con `reveal=true`)
        e `instancia`, la instancia de Vigía a la que habla esta entrada del MCP:
        `url_base`, `puerto_en_uso`, `data_dir` y `version`.

        Ojo con el puerto: `puerto` (en los ajustes) es el PREFERIDO del próximo
        arranque; `instancia.puerto_en_uso` es donde escucha ahora este servidor.
        Si hay dos entradas del MCP (dos instancias), llama a esta tool para saber a
        cuál estás hablando antes de escribir nada."""
        client = get_client()
        ajustes = await client.get("/settings", params={"reveal": reveal})
        salud = await client.get("/health")
        url_base = client.base_url
        puerto = salud.get("port")
        if puerto is None:  # servidor sin `app.state.port`: el de la URL
            puerto = urlsplit(url_base).port
        return {
            **ajustes,
            "instancia": {
                "url_base": url_base,
                "puerto_en_uso": puerto,
                "data_dir": salud.get("data_dir"),
                "version": salud.get("version"),
            },
        }
