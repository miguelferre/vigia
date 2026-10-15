"""Utilidades de privacidad, sin llamadas desde `services/ingest.py`.

`empty_report` es lo único que usa la ingesta: la constante que dice que Vigía
no pseudonimiza. El resto (`privacy_report`, `hmac_id`, `apply_decisions`,
`mask_preview`) queda como utilidad para cuando se quiera detectar datos personales; sus tests
(`tests/api/test_privacy.py`) las ejercitan directamente. Dos vías de
detección: por nombre de columna (patrones normalizados, insensibles a
mayúsculas, acentos y separadores) y por valores (muestra de hasta 500 filas
no nulas contra expresiones regulares de DNI, NIE, correo, teléfono español y
fechas de nacimiento completas).
"""

from __future__ import annotations

import hashlib
import hmac as hmac_lib
import math
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

import pandas as pd

__all__ = [
    "IDENTIFIER_PATTERNS",
    "apply_decisions",
    "empty_report",
    "hmac_id",
    "mask_preview",
    "normalize_name",
    "privacy_report",
    "to_jsonable",
]

# Patrón normalizado -> tipo de dato personal. Los de tipo "identificador" se
# recomiendan `hashear`; el resto (nombres, contacto, nacimiento), `descartar`.
IDENTIFIER_PATTERNS: dict[str, str] = {
    "nhc": "identificador",
    "historia": "identificador",
    "dni": "identificador",
    "nie": "identificador",
    "nif": "identificador",
    "pasaporte": "identificador",
    "cip": "identificador",
    "sip": "identificador",
    "tis": "identificador",
    "ssn": "identificador",
    "patient_id": "identificador",
    "episode_id": "identificador",
    "nombre": "dato_personal",
    "apellido": "dato_personal",
    "name": "dato_personal",
    "surname": "dato_personal",
    "email": "dato_personal",
    "correo": "dato_personal",
    "telefono": "dato_personal",
    "phone": "dato_personal",
    "movil": "dato_personal",
    "direccion": "dato_personal",
    "address": "dato_personal",
    "fecha_nac": "cuasi_identificador",
    "nacimiento": "cuasi_identificador",
    "birth": "cuasi_identificador",
    "dob": "cuasi_identificador",
}

_MUESTRA_MAX = 500

_RE_DNI = re.compile(r"^\d{8}[A-Za-z]$")
_RE_NIE = re.compile(r"^[XYZxyz]\d{7}[A-Za-z]$")
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RE_TELEFONO_ES = re.compile(r"^(\+34)?[6789]\d{8}$")
_RE_FECHA_COMPLETA = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T].*)?$|^\d{2}/\d{2}/\d{4}$")

_CHECKS_VALORES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (_RE_DNI, "identificador", "hashear"),
    (_RE_NIE, "identificador", "hashear"),
    (_RE_EMAIL, "dato_personal", "descartar"),
    (_RE_TELEFONO_ES, "dato_personal", "descartar"),
)


def normalize_name(name: str) -> str:
    """Nombre de columna en minúsculas, sin acentos y con separadores a `_`."""
    descompuesto = unicodedata.normalize("NFKD", str(name))
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    minuscula = sin_acentos.lower()
    return re.sub(r"[^a-z0-9]+", "_", minuscula).strip("_")


def _recomendacion(kind: str) -> str:
    return "hashear" if kind == "identificador" else "descartar"


def _detectar_por_nombre(nombre_normalizado: str) -> str | None:
    # Comprobación por "palabra" (delimitada por `_` o los extremos), no por
    # subcadena suelta: patrones cortos como "tis" (tarjeta individual
    # sanitaria) no deben disparar con sufijos médicos como "-itis"
    # (osteoartri-tis, sinovi-tis) que aparecen en las columnas de diagnóstico
    # del harness.
    for patron, kind in IDENTIFIER_PATTERNS.items():
        if re.search(rf"(?:^|_){re.escape(patron)}(?:_|$)", nombre_normalizado):
            return kind
    return None


def _detectar_por_valores(serie: pd.Series, nombre_normalizado: str) -> dict[str, Any] | None:
    muestra = serie.dropna().astype(str).str.strip().head(_MUESTRA_MAX)
    n = len(muestra)
    if n == 0:
        return None
    for patron, kind, recomendacion in _CHECKS_VALORES:
        coincidencias = int(muestra.map(lambda v, patron=patron: bool(patron.match(v))).sum())
        if coincidencias / n > 0.5:
            return {"reason": "valores", "kind": kind, "recommendation": recomendacion, "matches": coincidencias}
    if any(p in nombre_normalizado for p in ("nacimiento", "fecha_nac", "birth", "dob")):
        coincidencias = int(muestra.map(lambda v: bool(_RE_FECHA_COMPLETA.match(v))).sum())
        if coincidencias / n > 0.9:
            return {
                "reason": "valores",
                "kind": "cuasi_identificador",
                "recommendation": "descartar",
                "matches": coincidencias,
            }
    return None


def privacy_report(df: pd.DataFrame) -> dict[str, Any]:
    """Informe de privacidad: columnas marcadas como identificadoras, con motivo y recomendación."""
    columnas: list[dict[str, Any]] = []
    for col in df.columns:
        nombre_normalizado = normalize_name(col)
        kind = _detectar_por_nombre(nombre_normalizado)
        if kind is not None:
            columnas.append(
                {
                    "name": col,
                    "reason": "nombre",
                    "kind": kind,
                    "recommendation": _recomendacion(kind),
                    "matches": 1,
                }
            )
            continue
        por_valores = _detectar_por_valores(df[col], nombre_normalizado)
        if por_valores is not None:
            columnas.append({"name": col, **por_valores})
    return {
        "columns": columnas,
        "n_flagged": len(columnas),
        "checked_at": datetime.now(UTC).isoformat(timespec="microseconds"),
    }


def empty_report() -> dict[str, Any]:
    """Informe de privacidad de la ingesta: Vigía no pseudonimiza.

    Sustituye a la detección de columnas identificadoras: la ingesta ya no la
    llama, así que este es el único informe que existe. `privacy_report`,
    `hmac_id`, `apply_decisions` y `mask_preview` se quedan como utilidades
    sin llamadas desde `services/ingest.py`.
    """
    return {"aplicado": False, "motivo": "sin_pseudonimizacion"}


def hmac_id(salt_hex: str, value: Any) -> str | None:
    """HMAC-SHA256 hexadecimal de `value` con la sal del proyecto. `None`/NaN -> `None`."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    clave = bytes.fromhex(salt_hex)
    return hmac_lib.new(clave, str(value).encode("utf-8"), hashlib.sha256).hexdigest()


def apply_decisions(
    df: pd.DataFrame,
    report: dict[str, Any],
    decisions: dict[str, str],
    salt_hex: str,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Aplica `hashear`/`descartar` a las columnas marcadas por `privacy_report`.

    Las columnas marcadas sin decisión levantan `ValueError` con la lista de
    nombres pendientes: el llamador la traduce a un 422.
    """
    columnas_marcadas = [c["name"] for c in report.get("columns", [])]
    faltan = sorted(c for c in columnas_marcadas if c not in decisions)
    if faltan:
        raise ValueError(f"faltan decisiones de privacidad para: {faltan}")

    resultado = df.copy()
    aplicado: dict[str, str] = {}
    for columna in columnas_marcadas:
        decision = decisions[columna]
        if decision not in ("hashear", "descartar"):
            raise ValueError(f"decisión de privacidad no válida para {columna!r}: {decision!r}")
        if columna not in resultado.columns:
            continue
        if decision == "hashear":
            resultado[columna] = resultado[columna].map(lambda v: hmac_id(salt_hex, v))
        else:
            resultado = resultado.drop(columns=[columna])
        aplicado[columna] = decision
    return resultado, aplicado


def mask_preview(df: pd.DataFrame, report: dict[str, Any], n: int = 20) -> list[dict[str, Any]]:
    """Primeras `n` filas como dicts, con las columnas marcadas enmascaradas (`***`)."""
    columnas_marcadas = {c["name"] for c in report.get("columns", [])}
    filas: list[dict[str, Any]] = []
    for _, fila in df.head(n).iterrows():
        registro: dict[str, Any] = {}
        for columna, valor in fila.items():
            if columna in columnas_marcadas:
                registro[columna] = "***"
                continue
            registro[columna] = to_jsonable(valor)
        filas.append(registro)
    return filas


def to_jsonable(valor: Any) -> Any:
    if valor is None:
        return None
    if isinstance(valor, (str, int, bool)):
        return valor
    if isinstance(valor, float):
        return None if math.isnan(valor) else valor
    if hasattr(valor, "item"):
        try:
            return to_jsonable(valor.item())
        except (TypeError, ValueError):
            pass
    if hasattr(valor, "tolist"):
        try:
            return valor.tolist()
        except (TypeError, ValueError):
            pass
    return str(valor)
