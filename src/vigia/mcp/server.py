"""Servidor MCP de Vigía: `FastMCP("vigia")` con las 39 tools,
los 7 resources y los 3 prompts. `main()` es el entry point
`vigia-mcp` (`pyproject.toml`) y el que `vigia mcp` invoca.

Nada de `print` a stdout en todo el paquete: stdout es el canal del protocolo
(`mcp.run()` habla `stdio`); los mensajes de arranque van a stderr.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from vigia.mcp import (
    prompts,
    resources,
    tools_alertas,
    tools_auditoria,
    tools_datasets,
    tools_demo,
    tools_diario,
    tools_dossier,
    tools_evaluacion,
    tools_humano,
    tools_monitores,
    tools_proyectos,
    tools_riesgos,
    tools_versiones,
    tools_versiones_modelo,
)
from vigia.mcp.client import VigiaClient, VigiaError, set_client, validar_url_local


class _VigiaFastMCP(FastMCP):
    """`FastMCP` que deja el error de la API tal cual lo escribió `VigiaError`:
    el texto que ve el agente empieza por el código HTTP, no por el
    prefijo «Error executing tool» con que FastMCP envuelve las excepciones."""

    async def call_tool(self, name, arguments):
        try:
            return await super().call_tool(name, arguments)
        except ToolError as exc:
            if isinstance(exc.__cause__, VigiaError):
                raise ToolError(str(exc.__cause__)) from exc.__cause__
            raise


mcp = _VigiaFastMCP("vigia")

tools_proyectos.registrar(mcp)
tools_datasets.registrar(mcp)
tools_monitores.registrar(mcp)
tools_evaluacion.registrar(mcp)
tools_alertas.registrar(mcp)
tools_demo.registrar(mcp)
tools_auditoria.registrar(mcp)
tools_diario.registrar(mcp)
tools_humano.registrar(mcp)
tools_dossier.registrar(mcp)
tools_riesgos.registrar(mcp)
tools_versiones.registrar(mcp)
tools_versiones_modelo.registrar(mcp)
resources.registrar(mcp)
prompts.registrar(mcp)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vigia-mcp", description="Servidor MCP de Vigía (stdio)")
    parser.add_argument("--data-dir", type=str, default=None, help="Carpeta de datos de `vigia serve`")
    parser.add_argument("--url", type=str, default=None, help="URL explícita de la API (gana al lock)")
    parser.add_argument("--actor", type=str, default="claude-code", help="Nombre del actor en el diario")
    return parser


def _preparar(argv: list[str] | None = None) -> VigiaClient:
    """Construye el cliente y localiza la API (§6.6), sin abrir conexión todavía.

    Nada de `async` aquí: el `httpx.AsyncClient` y el `mcp_token` se piden en la
    primera petición, ya dentro del bucle de eventos de `mcp.run()`.
    """
    args = _parser().parse_args(argv)
    data_dir = Path(args.data_dir) if args.data_dir else None
    if data_dir is None and args.url is None:
        from vigia.app.settings import Settings

        data_dir = Settings().data_dir
    if args.url is not None:
        validar_url_local(args.url)
    client = VigiaClient(url=args.url, data_dir=data_dir, actor=args.actor)
    client.discover()
    return client


def main(argv: list[str] | None = None) -> int:
    """Entry point `vigia-mcp` y el que `vigia mcp` invoca directamente."""
    try:
        client = _preparar(argv)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    set_client(client)
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
