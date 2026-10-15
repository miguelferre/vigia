"""Plantillas CSV descargables de la guía de datos.

Cinco plantillas sintéticas y coherentes entre sí: los identificadores de
`etiquetas` están en `lote` y las fechas del registro de uso caen en las del
lote. Con el mapeo que sugiere `ingest._suggest_mapping` más las variables,
cada una entra sin error ni aviso (las de `linea-base` y `lote` con `kind`
`combined` y `payload`, `etiquetas` con `feedback`).

Una sexta, `multiclase`, es una línea base de un modelo de
tres clases: la clase predicha, la clase real y una columna `prob_<clase>` por
clase, en el orden de las clases. Con `task_type` multiclase, el mapeo sugerido
propone `probability_cols` y `classes`.

Una séptima, `regresion`, es una línea base de un modelo que predice
un número: la predicción y el valor real son numéricos, sin probabilidad ni clases.

Nombres fijados antes de implementarlos; se rellenan
`plantilla_csv`.

Los datos de ejemplo son sintéticos y lo dice el nombre del
fichero (`plantilla-<tipo>-sintetico.csv`), no un comentario en la primera
fila: los lectores de CSV de Vigía toman la primera fila como cabecera. La de
`registro-uso` sale de `registro-uso-ayuda.json`, la misma fuente que
`GET /api/content/registro-uso/ejemplo.csv`: sin texto duplicado.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Literal

__all__ = [
    "CLASES_PLANTILLA_MULTICLASE",
    "TIPOS_PLANTILLA",
    "UNIDAD_PLANTILLA_REGRESION",
    "TipoPlantilla",
    "nombre_plantilla",
    "plantilla_csv",
]

type TipoPlantilla = Literal[
    "linea-base", "lote", "etiquetas", "registro-uso", "outcomes", "multiclase", "regresion"
]

TIPOS_PLANTILLA: tuple[str, ...] = (
    "linea-base",
    "lote",
    "etiquetas",
    "registro-uso",
    "outcomes",
    "multiclase",
    "regresion",
)

# Línea base: febrero de 2026, con etiqueta (tipo «combinado»).
_LINEA_BASE = (
    "id,date,age_years,crp,esr,joint_count,prediction,probability,label\n"
    "B-001,2026-02-02,34,2.1,12,1,0,0.18,0\n"
    "B-002,2026-02-03,61,18.4,41,7,1,0.87,1\n"
    "B-003,2026-02-04,47,9.6,28,4,1,0.64,1\n"
    "B-004,2026-02-05,72,3.2,15,2,0,0.29,0\n"
    "B-005,2026-02-06,55,14.8,36,6,1,0.79,0\n"
)

# Lote de producción: marzo de 2026 (las fechas del registro de uso caen aquí),
# sin etiqueta (tipo «predicciones»): las etiquetas llegan después.
_LOTE = (
    "id,date,age_years,crp,esr,joint_count,prediction,probability\n"
    "L-001,2026-03-02,38,3.4,14,1,0,0.22\n"
    "L-002,2026-03-03,66,21.0,45,8,1,0.91\n"
    "L-003,2026-03-04,52,11.2,30,5,1,0.68\n"
    "L-004,2026-03-05,29,1.8,10,0,0,0.12\n"
    "L-005,2026-03-06,70,16.5,39,6,1,0.83\n"
)

# Etiquetas que llegan tarde: los identificadores son los del lote.
_ETIQUETAS = "id,label\nL-001,0\nL-002,1\nL-003,1\nL-004,0\nL-005,1\n"

# Resultado del sistema combinado por periodo: febrero y marzo de 2026.
_OUTCOMES = (
    "period,metric_key,value,source\n"
    "2026-02,tasa_decision_correcta,0.81,manual\n"
    "2026-02,tiempo_medio_dias,3.2,manual\n"
    "2026-03,tasa_decision_correcta,0.83,manual\n"
    "2026-03,tiempo_medio_dias,3.4,manual\n"
    "2026-03,reingresos_30d,0.06,manual\n"
)

# Las tres clases de la plantilla `multiclase`, en el orden de sus columnas de
# probabilidad. El ejemplo multiclase del registro de uso (# `build/gen_content_registro_uso.py`) usa las mismas, sin repetir el texto.
CLASES_PLANTILLA_MULTICLASE: tuple[str, ...] = ("leve", "moderada", "grave")

# Línea base multiclase: tres clases (leve, moderada, grave), una probabilidad
# por clase en el orden de las clases (las tres suman 1 en cada fila) y la
# clase real. Las tres clases salen en la predicción: Vigía las propone desde ahí.
_MULTICLASE = (
    "id,date,age_years,crp,esr,joint_count,prediction,"
    "prob_leve,prob_moderada,prob_grave,label\n"
    "M-001,2026-02-02,34,2.1,12,1,leve,0.72,0.20,0.08,leve\n"
    "M-002,2026-02-03,61,18.4,41,7,grave,0.06,0.24,0.70,grave\n"
    "M-003,2026-02-04,47,9.6,28,4,moderada,0.15,0.62,0.23,moderada\n"
    "M-004,2026-02-05,72,3.2,15,2,leve,0.66,0.25,0.09,moderada\n"
    "M-005,2026-02-06,55,14.8,36,6,grave,0.10,0.31,0.59,grave\n"
)

# Línea base de regresión: el modelo predice un número, aquí los
# días de estancia, y la etiqueta es el valor real en la misma unidad. Sin
# probabilidad ni clases. La unidad no va en las celdas: se declara al crear el modelo
# («días»). Números con punto decimal y sin unidad pegada.
UNIDAD_PLANTILLA_REGRESION = "días"
_REGRESION = (
    "id,date,age_years,crp,esr,joint_count,prediction,label\n"
    "R-001,2026-02-02,34,2.1,12,1,2.8,3.0\n"
    "R-002,2026-02-03,61,18.4,41,7,9.6,11.0\n"
    "R-003,2026-02-04,47,9.6,28,4,5.9,5.0\n"
    "R-004,2026-02-05,72,3.2,15,2,4.1,6.0\n"
    "R-005,2026-02-06,55,14.8,36,6,8.2,7.5\n"
)

_FIJAS = {
    "linea-base": _LINEA_BASE,
    "lote": _LOTE,
    "etiquetas": _ETIQUETAS,
    "outcomes": _OUTCOMES,
    "multiclase": _MULTICLASE,
    "regresion": _REGRESION,
}


def nombre_plantilla(tipo: str) -> str:
    """Nombre del fichero descargable: dice que los datos son sintéticos."""
    return f"plantilla-{tipo}-sintetico.csv"


def _csv_registro_uso() -> str:
    """El CSV de `registro-uso-ayuda.json` (fuente única del ejemplo)."""
    ref = resources.files("vigia.content").joinpath("registro-uso-ayuda.json")
    return json.loads(ref.read_text(encoding="utf-8"))["ejemplo"]["csv"]


def plantilla_csv(tipo: str) -> tuple[str, str]:
    """`(nombre_fichero, contenido_csv)` de la plantilla `tipo`.

    `tipo` es uno de `TIPOS_PLANTILLA`; el router responde 404 con otro valor.
    """
    if tipo not in TIPOS_PLANTILLA:
        raise ValueError(f"tipo de plantilla desconocido: {tipo!r}")
    contenido = _csv_registro_uso() if tipo == "registro-uso" else _FIJAS[tipo]
    return nombre_plantilla(tipo), contenido
