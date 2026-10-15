"""Importación del `dossier.json` de `interaction_review`.

Módulo puro, sin importar el paquete: agrupa `sources[]` por `kind` en las tres
plantillas de Vigía y traduce los errores de validación a español. La
validación contra `schemas.Dossier` del paquete vive en
`human/dossier_adapter.py` (el único que lo importa).

Tabla `kind` a plantilla (fijada tras leer los 16 `dossier.json` de
`data/external`; ver `docs/api/formatos.md`):

| kind         | plantilla (campo)   | clave de la respuesta           |
|--------------|---------------------|---------------------------------|
| `technician` | `profile`           | `{label} [{id}]`                |
| `end_user`   | `experience`        | `{label} [{id}]`                |
| `document`   | `inventory`         | `{label} [{id}]`                |
| `other`, o contenido vacío, o `document` con contenido «no» | `profile`, clave propia `CLAVE_SIN_ENCAJE` | |
| `summary`    | `profile`, clave propia `CLAVE_RESUMEN` | |
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "CLAVE_RESUMEN",
    "CLAVE_SIN_ENCAJE",
    "KIND_A_PLANTILLA",
    "DossierAgrupado",
    "agrupar_fuentes",
    "clave_fuente",
    "traducir_errores",
]

CLAVE_RESUMEN = "Resumen del sistema (importado de dossier.json)"
CLAVE_SIN_ENCAJE = "Fuentes que no encajan en las plantillas (importado de dossier.json)"

KIND_A_PLANTILLA = {"technician": "profile", "end_user": "experience", "document": "inventory"}

_ESPACIOS = re.compile(r"\s+")


@dataclass(frozen=True)
class DossierAgrupado:
    profile: dict[str, str]
    experience: dict[str, str]
    inventory: dict[str, str]
    # Claves (`id`) de las fuentes que fueron a `CLAVE_SIN_ENCAJE`.
    sin_encaje: list[str] = field(default_factory=list)


def clave_fuente(label: str, fuente_id: str) -> str:
    """Pregunta con la que una fuente entra en su plantilla: `{label} [{id}]`,
    en una sola línea (el parser del paquete lee la pregunta de una línea)."""
    etiqueta = _ESPACIOS.sub(" ", label or "").strip() or "Fuente"
    return f"{etiqueta} [{_ESPACIOS.sub(' ', fuente_id or '').strip()}]"


def _clave_unica(clave: str, usadas: set[str]) -> str:
    final, n = clave, 2
    while final in usadas:
        final = f"{clave} #{n}"
        n += 1
    usadas.add(final)
    return final


def agrupar_fuentes(*, summary: str, sources: Sequence[Mapping[str, Any]]) -> DossierAgrupado:
    """Agrupa las fuentes por `kind`; `summary` y lo que no encaje van a una
    clave propia de `profile`, nunca se pierden."""
    destinos: dict[str, dict[str, str]] = {"profile": {}, "experience": {}, "inventory": {}}
    usadas: dict[str, set[str]] = {k: set() for k in destinos}
    sin_encaje: list[str] = []
    bloques_sin_encaje: list[str] = []

    for fuente in sources:
        kind = str(fuente.get("kind", ""))
        contenido = str(fuente.get("content", ""))
        destino = KIND_A_PLANTILLA.get(kind)
        vacio = not contenido.strip()
        # En el inventario, una respuesta vacía o «no» deja el documento sin marcar.
        if destino == "inventory" and contenido.strip().lower() == "no":
            destino = None
        if destino is None or vacio:
            clave = clave_fuente(str(fuente.get("label", "")), str(fuente.get("id", "")))
            bloques_sin_encaje.append(f"[{kind}] {clave}: {contenido.strip() or '(sin contenido)'}")
            sin_encaje.append(str(fuente.get("id", "")))
            continue
        clave = _clave_unica(clave_fuente(str(fuente.get("label", "")), str(fuente.get("id", ""))), usadas[destino])
        destinos[destino][clave] = contenido

    perfil: dict[str, str] = {}
    if summary and summary.strip():
        perfil[CLAVE_RESUMEN] = summary
    perfil.update(destinos["profile"])
    if bloques_sin_encaje:
        perfil[CLAVE_SIN_ENCAJE] = "\n\n".join(bloques_sin_encaje)
    return DossierAgrupado(perfil, destinos["experience"], destinos["inventory"], sin_encaje)


_TIPOS_ES = {
    "missing": "falta este campo",
    "string_type": "debe ser texto",
    "list_type": "debe ser una lista",
    "dict_type": "debe ser un objeto",
    "model_type": "debe ser un objeto",
    "model_attributes_type": "debe ser un objeto",
    "bool_type": "debe ser verdadero o falso",
    "string_too_short": "no puede estar vacío",
    "json_invalid": "el cuerpo no es un JSON válido",
}


def _ruta(loc: Sequence[Any]) -> str:
    partes = [p for p in loc if p not in ("body", "query", "path")]
    texto = ""
    for p in partes:
        texto += f"[{p}]" if isinstance(p, int) else (f".{p}" if texto else str(p))
    return texto or "(documento)"


def _mensaje(error: Mapping[str, Any]) -> str:
    tipo = str(error.get("type", ""))
    msg = str(error.get("msg", ""))
    if tipo == "enum":
        esperado = (error.get("ctx") or {}).get("expected", "document, technician, end_user, other")
        return f"valor no admitido (admitidos: {esperado})"
    if "at least one source" in msg:
        return "el dossier necesita al menos una fuente"
    if tipo in _TIPOS_ES:
        return _TIPOS_ES[tipo]
    return f"no es válido ({msg})"


def traducir_errores(errores: Sequence[Mapping[str, Any]], *, maximo: int = 5) -> str:
    """Mensaje de 422 en español con el campo que falla:
    `sources[2].kind: valor no admitido (…)`, hasta `maximo` campos."""
    lineas = [f"{_ruta(e.get('loc', ()))}: {_mensaje(e)}" for e in errores]
    resto = len(lineas) - maximo
    cuerpo = "; ".join(lineas[:maximo]) + (f"; y {resto} más" if resto > 0 else "")
    return f"El dossier.json no es válido. Campos que fallan: {cuerpo}"
