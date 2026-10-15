"""Ayudas del mapeo por plantilla de `upload_dataset`."""

from __future__ import annotations

from typing import Any

from vigia.mcp.client import CLAVES_COLUMN_MAPPING

# Campos de `ColumnMapping` (core/schema.py): `PUT /datasets/{id}/mapping` los
# rechaza todos los demás (`extra="forbid"`), por ejemplo `positive_label` de la plantilla.
_CAMPOS_MAPEO = CLAVES_COLUMN_MAPPING

# Columnas que dan contenido a una plantilla: con solo `favorable_label` o el tipo
# de atributo protegido (que tiene valor por defecto) la ingesta no tiene qué mapear.
_COLUMNAS_PLANTILLA = (
    "prediction_col",
    "probability_col",
    "probability_cols",
    "label_col",
    "id_col",
    "timestamp_col",
    "feature_cols",
    "protected_attr_col",
)


def _plantilla_utilizable(plantilla: Any) -> bool:
    return isinstance(plantilla, dict) and any(plantilla.get(c) for c in _COLUMNAS_PLANTILLA)


def _mapeo_desde_plantilla(sugerido: Any) -> dict[str, Any]:
    """Mapeo para `PUT /datasets/{id}/mapping` a partir de `suggested_mapping` de la
    subida, que la API ya rellena con la plantilla del proyecto (lo que la
    plantilla fija manda y sus columnas solo entran si el fichero las trae). Se
    quitan los campos que `ColumnMapping` no admite, las columnas vacías que deja
    la sugerencia y un atributo protegido sin grupos (una conjetura que el
    validador rechazaría)."""
    mapeo = {c: v for c, v in (sugerido or {}).items() if c in _CAMPOS_MAPEO}
    for campo in ("prediction_col", "probability_col", "label_col", "id_col", "timestamp_col"):
        if mapeo.get(campo) == "":
            mapeo[campo] = None
    if mapeo.get("protected_attr_col") and not (mapeo.get("unpriv_groups") and mapeo.get("priv_groups")):
        mapeo["protected_attr_col"] = None
    return mapeo
