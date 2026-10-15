"""Inventario de acciones del diario: ninguna se queda sin título.

Recorre `src/vigia/app` con el mismo grep con el que se escribió
`events_titulos.py` para inventariar las acciones (`action="..."` literal en
`record_event(...)`) y falla si aparece una acción nueva sin plantilla.
"""

from __future__ import annotations

import re
from pathlib import Path

from vigia.app.events_titulos import ACCIONES_CON_PLANTILLA, titulo_evento
from vigia.app.models import Event

_APP_DIR = Path(__file__).resolve().parents[2] / "src" / "vigia" / "app"

# Acciones que el código construye en una variable en vez de escribirlas en el
# propio `record_event(action=...)`, así que el grep de `action="..."` literal
# no las encuentra: hoy son las tres que toma la variable `accion` de
# `_sync_one` en `services/alerting.py`. Si esa función cambia sus valores
# posibles, actualizar este conjunto a mano.
_ACCIONES_DINAMICAS = {"alerta.abierta", "alerta.reabierta", "alerta.actualizada"}


def _acciones_literales() -> set[str]:
    patron = re.compile(r'action="([a-z_.]+)"')
    acciones: set[str] = set()
    for fichero in _APP_DIR.rglob("*.py"):
        acciones |= set(patron.findall(fichero.read_text(encoding="utf-8")))
    return acciones


def test_ninguna_accion_del_diario_se_queda_sin_plantilla():
    acciones = _acciones_literales() | _ACCIONES_DINAMICAS
    assert len(acciones) >= 30, f"el inventario de acciones se ha quedado corto: {sorted(acciones)}"
    sin_plantilla = acciones - ACCIONES_CON_PLANTILLA
    assert not sin_plantilla, f"acciones sin título en events_titulos.py: {sorted(sin_plantilla)}"


def test_titulo_evento_en_espanol_sin_codigos_internos():
    evento = Event(
        id=1,
        action="version.baseline_congelado",
        object_type="model_version",
        object_id=7,
        after_json={"baseline_batch_id": 4},
    )
    assert titulo_evento(evento) == "Línea base congelada en el lote 4"

    evento_alerta = Event(
        id=2, action="alerta.en_observacion", object_type="alert", object_id=12
    )
    assert titulo_evento(evento_alerta) == "Alerta 12 en seguimiento: la métrica vuelve dentro del umbral"

    evento_accion = Event(
        id=3,
        action="alerta.accion",
        object_type="alert",
        object_id=5,
        after_json={"action": "cambiar_umbral"},
    )
    titulo = titulo_evento(evento_accion)
    assert "cambiar_umbral" not in titulo
    assert "Cambiar el umbral" in titulo


def test_accion_desconocida_no_rompe_y_devuelve_su_codigo():
    evento = Event(id=4, action="algo.inventado", object_type="x")
    assert titulo_evento(evento) == "algo.inventado"


def test_after_json_incompleto_no_rompe_el_titulo():
    """Un evento antiguo sin las claves que hoy espera la plantilla no debe
    tirar la serialización del diario: vuelve al código de acción."""
    evento = Event(id=5, action="version.baseline_congelado", object_type="model_version")
    assert titulo_evento(evento)  # no lanza, y no viene vacío


def test_fase_del_guion_de_la_demo_con_la_etiqueta_del_contenido():
    """Las fases del guion `caso_digestivo` se nombran con `fases` de
    `content/demo-digestivo.json` («Casos nuevos», no «Evento 1»); las de
    los guiones antiguos conservan el mapa fijo, y el laboratorio antepone
    «Laboratorio:»."""
    reproducida = Event(
        id=6,
        action="demo.fase_reproducida",
        object_type="demo_run",
        object_id=1,
        after_json={"phase_key": "e1_evento"},
    )
    assert titulo_evento(reproducida) == "Fase «Casos nuevos» del guion reproducida"
    antigua = Event(
        id=7,
        action="demo.fase_reproducida",
        object_type="demo_run",
        object_id=1,
        after_json={"phase_key": "e2_recovery"},
    )
    assert "Recuperación 2" in titulo_evento(antigua)
    laboratorio = Event(
        id=8,
        action="demo.lab_ejecutada",
        object_type="demo_run",
        object_id=1,
        after_json={"phase_key": "e1_evento"},
    )
    titulo_lab = titulo_evento(laboratorio)
    assert "Laboratorio" in titulo_lab and "Casos nuevos" in titulo_lab
