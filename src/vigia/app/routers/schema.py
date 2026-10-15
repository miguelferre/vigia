"""Esquema de la base de datos, introspeccionado en vivo.

Sirve al resource `schema://tables` del servidor MCP. Lee `SQLModel.metadata`
(nombre de tabla, columnas, tipo, claves ajenas) en vez de mantener un JSON a
mano: así nunca queda desincronizado tras una migración. Sin actor ni evento:
es introspección, no dato de negocio; sin sesión de escritura.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlmodel import SQLModel

from vigia.app.schemas import respuestas as resp

router = APIRouter(tags=["esquema"])


def _tabla(tabla) -> dict:
    columnas = [
        {
            "name": col.name,
            "type": str(col.type),
            "nullable": bool(col.nullable),
            "primary_key": bool(col.primary_key),
        }
        for col in tabla.columns
    ]
    claves_ajenas = [
        {
            "column": fk.parent.name,
            "references": f"{fk.column.table.name}.{fk.column.name}",
        }
        for fk in sorted(tabla.foreign_keys, key=lambda fk: fk.parent.name)
    ]
    return {"name": tabla.name, "columns": columnas, "foreign_keys": claves_ajenas}


@router.get("/schema/tables", response_model=resp.SchemaTables)
def read_schema_tables(request: Request) -> dict:
    """Tablas del esquema, en el orden de la metadata, con columnas y claves ajenas."""
    version = getattr(request.app.state, "schema_version", None)
    tablas = [_tabla(t) for t in SQLModel.metadata.sorted_tables]
    return {"schema_version": int(version or 0), "tables": tablas}
