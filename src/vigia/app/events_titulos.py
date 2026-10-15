"""Títulos legibles del diario de eventos.

Un evento por sí solo no dice nada a quien no conoce el esquema
(«vigia.app · demo.fase_reproducida»). `titulo_evento` traduce cada
acción que emite `src/vigia/app` a una frase en español, sin códigos
internos (`metric_key`, claves de acción, `cx1`...) en el texto.

La tabla `_PLANTILLAS` es la fuente de verdad: `tests/app/test_events_titulos.py`
la contrasta con un grep de `action=` sobre el propio código (mismo criterio
que usó esta sesión para inventariarla) y falla si aparece una acción nueva
sin plantilla. Para añadir una acción: darle una entrada aquí y volver a
correr ese test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vigia.app.content_loader import fase_label

if TYPE_CHECKING:
    from vigia.app.models import Event

_ETIQUETA_MONITOR: dict[str, str] = {
    "fairness": "equidad",
    "quality": "calidad",
    "drift": "deriva",
    "explain": "explicabilidad",
    "cross": "cruzadas",
}

_ETIQUETA_EXPLICACION: dict[str, str] = {
    "global_permutation": "por permutación",
    "global_shap": "SHAP",
    "local_lime": "local (LIME)",
}

_ETIQUETA_SOLICITUD: dict[str, str] = {
    "next": "la siguiente fase",
    "play": "el guion completo",
}

# Revisión del dossier y niveles de la matriz.
_ETIQUETA_REVISION: dict[str, str] = {
    "b0": "lista de comprobación, sin LLM",
    "p3": "canalización con LLM",
    "auto": "ruta automática con LLM",
}

_ETIQUETA_ESTADO_REVISION: dict[str, str] = {
    "terminada": "terminada",
    "error": "fallida",
    "cancelada": "cancelada",
}

_ETIQUETA_NIVEL_RIESGO: dict[str, str] = {
    "bajo": "bajo",
    "medio": "medio",
    "alto": "alto",
    "critico": "crítico",
}


def _label_accion_alerta(clave: str) -> str:
    # Import diferido: evita el ciclo app.events -> events_titulos ->
    # services.alerting -> app.events (ACTOR_MODELO, record_event).
    from vigia.app.services.alerting import ETIQUETAS_ACCION

    return ETIQUETAS_ACCION.get(clave, clave)


def _af(e: Event) -> dict:
    return e.after_json or {}

_FASES_DEMO = {
    "b1": "Línea base 1",
    "b2": "Línea base 2",
    "b3": "Línea base 3",
    "b4": "Línea base 4",
    "b5": "Línea base 5",
    "e1_evento": "Evento 1",
    "e1_recovery": "Recuperación 1",
    "e2_evento": "Evento 2",
    "e2_recovery": "Recuperación 2",
}


def _fase(clave: str | None) -> str:
    """Clave de fase del guion a texto; espejo de `frontend/src/lib/fases.ts`.

    Primero el contenido (`fases` de `demo-digestivo.json`, «Línea
    base», «Casos nuevos», «Tras las medidas»), después el mapa fijo de
    los guiones antiguos (`timeline_completo`, `consejeria_regional`)."""
    if not clave:
        return "?"
    if clave.startswith("lab:"):
        return f"Laboratorio: {_fase(clave[4:])}"
    return fase_label(clave) or _FASES_DEMO.get(clave, clave)



def _lista_texto(valor: object) -> str:
    """Lista de clases o de textos a «A, B, C»."""
    if isinstance(valor, (list, tuple)):
        return ", ".join(str(v) for v in valor) or "?"
    return str(valor) if valor not in (None, "") else "?"


def _titulo_tipo_tarea(task_type: object, unidad: object = None) -> str:
    """«Tipo de tarea: multiclase», «Tipo de tarea: regresión (unidad: horas por
    semana)». La unidad solo viene en una regresión."""
    nombre = {"multiclass": "multiclase", "binary": "binario", "regression": "regresión"}.get(
        str(task_type), str(task_type)
    )
    sufijo = f" (unidad: {unidad})" if unidad else ""
    return f"Tipo de tarea: {nombre}{sufijo}"


def _cola_tipo_de_tarea(e: Event) -> str:
    """Lo que `proyecto.creado` añade sobre el tipo de tarea: nada en binario, el tipo
    en multiclase y el tipo con su unidad en regresión."""
    tipo = _af(e).get("task_type")
    match tipo:
        case "multiclass" | "regression":
            return f". {_titulo_tipo_tarea(tipo, _af(e).get('target_unit'))}"
        case _:
            return ""


def _titulo_rango_favorable(e: Event) -> str:
    """«Rango favorable fijado: de 40 a 81 horas por semana»."""
    texto = _af(e).get("texto")
    if not texto:
        rangos = _af(e).get("favorable_ranges")
        if isinstance(rangos, (list, tuple)) and rangos:
            from vigia.core.schema import texto_rangos

            texto = texto_rangos([tuple(r) for r in rangos], _af(e).get("target_unit"))
    return f"Rango favorable fijado: {texto or '?'}"


def _titulo_favorable(valor: object) -> str:
    """Con más de una clase favorable, «Clases favorables fijadas: A, B»."""
    if isinstance(valor, (list, tuple)) and len(valor) > 1:
        return f"Clases favorables fijadas: {_lista_texto(valor)}"
    if isinstance(valor, (list, tuple)) and len(valor) == 1:
        valor = valor[0]
    return f"Clase favorable del modelo fijada en «{valor if valor is not None else '?'}»"


def _combinacion_riesgo(e: Event) -> str:
    """« (Moderado × Probable)» si el evento trae los dos ejes."""
    from vigia.human.risk_levels import IMPACTO_LABELS, PROBABILIDAD_LABELS

    impacto = IMPACTO_LABELS.get(_af(e).get("impact_level"))
    probabilidad = PROBABILIDAD_LABELS.get(_af(e).get("probability_level"))
    return f" ({impacto} × {probabilidad})" if impacto and probabilidad else ""


def _bf(e: Event) -> dict:
    return e.before_json or {}


_PLANTILLAS = {
    "anotacion.manual": lambda e: "Anotación humana",
    # La exportación del diario deja constancia de sí misma.
    "diario.exportado": lambda e: (
        f"Diario exportado en {str(_af(e).get('formato', '?')).upper()} "
        + (
            f"desde {_af(e).get('desde_local') or _af(e).get('desde')}"
            if _af(e).get("desde")
            else "completo"
        )
        + f" ({_af(e).get('n_eventos', '?')} eventos)"
    ),
    "proyecto.creado": lambda e: f"Proyecto «{_af(e).get('name', '?')}» creado{_cola_tipo_de_tarea(e)}",
    "proyecto.rango_favorable_fijado": _titulo_rango_favorable,
    "proyecto.actualizado": lambda e: "Configuración del proyecto actualizada",
    "proyecto.borrado": lambda e: f"Proyecto «{_bf(e).get('name', '?')}» borrado",
    "proyecto.reiniciado": lambda e: "Proyecto reiniciado, datos borrados",
    "version.creada": lambda e: f"Versión «{_af(e).get('label', '?')}» creada",
    "version.activada": lambda e: "Versión de modelo activada",
    "version.baseline_congelado": lambda e: (
        f"Línea base congelada{' automáticamente' if _af(e).get('automatico') else ''} "
        f"en el lote {_af(e).get('baseline_batch_id', '?')}"
    ),
    "version.referencia_cruzadas": lambda e: "Referencia de alertas cruzadas calculada",
    "dataset.subido": lambda e: f"Datos subidos ({_af(e).get('n_rows', '?')} filas)",
    "dataset.mapeado": lambda e: "Mapeo de columnas guardado",
    "dataset.borrado": lambda e: "Dataset borrado",
    "dataset.ingesta_fallida": lambda e: (
        f"La ingesta del dataset ha fallado: {_af(e).get('error', 'error desconocido')}"
    ),
    "batch.ingerido": lambda e: f"Lote ingerido ({_af(e).get('n_rows', '?')} filas)",
    "batch.borrado": lambda e: "Lote borrado",
    "monitor.configurado": lambda e: "Configuración del monitor actualizada",
    # Plantilla de mapeo, sincronía de
    # la clase favorable y artefacto del modelo ejecutable.
    "proyecto.plantilla_actualizada": lambda e: "Plantilla de mapeo del modelo actualizada",
    "proyecto.favorable_sincronizado": lambda e: _titulo_favorable(_af(e).get("favorable_label")),
    "proyecto.positive_label_ignorado": lambda e: (
        "La plantilla de mapeo traía una etiqueta positiva («positive_label») que Vigía ya no "
        "usa: se ignora; el conjunto de clases favorables cubre su uso"
    ),
    "proyecto.clases_fijadas": lambda e: (
        f"Clases del modelo fijadas: {_lista_texto(_af(e).get('classes'))}"
    ),
    "proyecto.umbrales_linea_base_fallidos": lambda e: (
        "No se pudieron proponer los umbrales desde la línea base: "
        f"{_af(e).get('error', 'motivo desconocido')}"
    ),
    # El título dice cuántos, no la lista de claves crudas
    # («mean_absolute_error quality 0.7424»); la lista sigue en `after`.
    "proyecto.umbrales_linea_base_aplicados": lambda e: (
        "Umbrales propuestos desde la línea base aplicados"
        + (
            f" ({len(_af(e)['umbrales'])} umbrales)"
            if isinstance(_af(e).get("umbrales"), list) and _af(e)["umbrales"]
            else ""
        )
    ),
    "dataset.mapeo_distinto_plantilla": lambda e: (
        "El mapeo de este fichero se aparta de la plantilla del modelo"
    ),
    "version.artefacto_subido": lambda e: (
        f"Modelo ejecutable subido ({_af(e).get('artifact_kind', '?')})"
    ),
    # La petición que encola una evaluación o una explicación
    # queda en el diario con el actor de la cabecera (humano o agente), como
    # `demo.avance_solicitado`; el resultado sigue siendo del carril `modelo`.
    "evaluacion.solicitada": lambda e: (
        f"Ha pedido evaluar el lote #{_af(e).get('batch_seq', _af(e).get('batch_id', '?'))}"
    ),
    "cruzadas.solicitadas": lambda e: "Ha pedido evaluar las alertas cruzadas",
    "explicacion.solicitada": lambda e: (
        "Ha pedido la explicación "
        f"{_ETIQUETA_EXPLICACION.get(_af(e).get('kind', ''), _af(e).get('kind', '?'))}"
        + (" de una fila" if _af(e).get("scope") == "local" else "")
    ),
    "evaluacion.completada": lambda e: (
        "Evaluación de "
        f"{_ETIQUETA_MONITOR.get(_af(e).get('monitor_type', ''), _af(e).get('monitor_type', '?'))}"
        " completada"
    ),
    "explicacion.calculada": lambda e: (
        "Explicación "
        f"{_ETIQUETA_EXPLICACION.get(_af(e).get('kind', ''), _af(e).get('kind', '?'))} calculada"
    ),
    "explicacion.fallida": lambda e: (
        f"Explicación automática fallida ({e.motivo or 'motivo desconocido'})"
    ),
    "usage_log.ingerido": lambda e: f"Diario de uso ingerido ({_af(e).get('n_rows', '?')} filas)",
    "outcome.ingerido": lambda e: (
        f"Resultados ingeridos ({_af(e).get('n_creados', '?')} nuevos, "
        f"{_af(e).get('n_actualizados', '?')} actualizados)"
    ),
    "feedback.emparejado": lambda e: (
        f"Feedback emparejado ({_af(e).get('n_matched', '?')} de "
        f"{(_af(e).get('n_matched') or 0) + (_af(e).get('n_unmatched') or 0)} filas)"
    ),
    "alerta.abierta": lambda e: f"Alerta {e.object_id} abierta",
    "alerta.reabierta": lambda e: f"Alerta {e.object_id} reabierta",
    "alerta.actualizada": lambda e: f"Alerta {e.object_id} actualizada",
    "alerta.en_observacion": lambda e: f"Alerta {e.object_id} en seguimiento: la métrica vuelve dentro del umbral",
    "alerta.reconocida": lambda e: f"Triaje hecho: alerta {e.object_id} en observación",
    "alerta.investigada": lambda e: f"Investigación registrada en la alerta {e.object_id}",
    "alerta.decidida": lambda e: (
        f"Decisión registrada en la alerta {e.object_id}: "
        + ", ".join(_label_accion_alerta(clave) for clave in _af(e).get("acciones", []))
    ),
    "alerta.accion": lambda e: (
        f"Acción registrada en la alerta {e.object_id}: "
        f"{_label_accion_alerta(_af(e).get('action', ''))}"
    ),
    "alerta.cerrada": lambda e: f"Alerta {e.object_id} cerrada",
    # Borrar un lote retira las alertas que
    # nacieron en él; el motivo («lote N borrado») viaja en `motivo`.
    "alerta.retirada": lambda e: (
        f"Alerta {e.object_id} retirada: {e.motivo or _af(e).get('retired_reason') or 'motivo no registrado'}"
    ),
    "alerta.protocolo_editado": lambda e: f"Protocolo de la alerta {e.object_id} editado",
    "demo.run_creada": lambda e: f"Reproducción de demo creada ({_af(e).get('scenario_key', '?')})",
    "demo.fase_reproducida": lambda e: f"Fase «{_fase(_af(e).get('phase_key'))}» del guion reproducida",
    "demo.reiniciada": lambda e: "Demo reiniciada, proyecto vaciado",
    "demo.lab_ejecutada": lambda e: (
        f"Laboratorio ejecutado sobre la fase «{_fase(_af(e).get('phase_key'))}»"
    ),
    "demo.avance_solicitado": lambda e: (
        f"Ha pedido reproducir {_ETIQUETA_SOLICITUD.get(_af(e).get('solicitud', ''), 'el guion')}"
        + (f" («{_fase(_af(e).get('phase_key'))}»)" if _af(e).get("phase_key") else "")
    ),
    "job.cancelado": lambda e: f"Trabajo {e.object_id} cancelado",
    "ajuste.cambiado": lambda e: "Ajustes de la aplicación actualizados",
    # Activar un backend LLM no local exige una
    # confirmación explícita que solo queda en el diario, nunca en `setting`.
    "ajuste.llm_confirmado": lambda e: (
        f"Backend LLM «{_af(e).get('backend', '?')}» activado con confirmación explícita "
        "de que el dossier no lleva datos de personas afectadas"
    ),
    # Dossier de auditoría y sus revisiones. Nunca las
    # respuestas de los formularios en el texto.
    "dossier.creado": lambda e: (
        f"Dossier de auditoría «{_af(e).get('system_name', '?')}» creado"
        + (" con el resumen del diario de uso" if _af(e).get("telemetry_included") else "")
    ),
    "dossier.revision_lanzada": lambda e: (
        f"Revisión del dossier {_af(e).get('dossier_id', '?')} lanzada "
        f"({_ETIQUETA_REVISION.get(_af(e).get('approach', ''), _af(e).get('approach', '?'))})"
    ),
    "dossier.revision_terminada": lambda e: (
        f"Revisión del dossier {_af(e).get('dossier_id', '?')} "
        f"{_ETIQUETA_ESTADO_REVISION.get(_af(e).get('status', ''), _af(e).get('status', '?'))}"
        + (
            f" con {_af(e).get('n_findings')} hallazgos"
            if _af(e).get("n_findings") is not None
            else ""
        )
    ),
    # Matriz de riesgos. `level` en texto además de
    # la celda, (color y texto).
    "riesgo.creado": lambda e: (
        f"Riesgo {_af(e).get('code', '?')} registrado en nivel "
        f"{_ETIQUETA_NIVEL_RIESGO.get(_af(e).get('level', ''), _af(e).get('level', '?'))}"
        + _combinacion_riesgo(e)
        + (
            f" desde la alerta {_af(e).get('origin_alert_id')}"
            if _af(e).get("origin_alert_id") is not None
            else " a mano"
        )
    ),
    "riesgo.movido": lambda e: (
        f"Riesgo {_af(e).get('code', '?')} movido a impacto {_af(e).get('to_impact', '?')} y "
        f"probabilidad {_af(e).get('to_probability', '?')}: nivel "
        f"{_ETIQUETA_NIVEL_RIESGO.get(_af(e).get('level', ''), _af(e).get('level', '?'))}"
    ),
    "riesgo.en_seguimiento": lambda e: f"Riesgo {_af(e).get('code', '?')} en seguimiento",
    "riesgo.cerrado": lambda e: f"Riesgo {_af(e).get('code', '?')} cerrado",
    "sistema.arranque": lambda e: f"Vigía arrancado (versión {_af(e).get('version', '?')})",
    "sistema.apagado": lambda e: "Vigía apagado",
    # Borrar o reiniciar un proyecto no pudo retirar algún fichero.
    "sistema.limpieza_incompleta": lambda e: (
        f"Quedaron {len(_af(e).get('ficheros_sin_retirar', []))} fichero(s) sin retirar "
        f"tras el {_af(e).get('origen', 'borrado')} del proyecto"
    ),
    "sistema.migracion": lambda e: (
        f"Esquema de base de datos migrado a la versión {_af(e).get('schema_version', '?')}"
    ),
}

__all__ = ["ACCIONES_CON_PLANTILLA", "titulo_evento"]

ACCIONES_CON_PLANTILLA: frozenset[str] = frozenset(_PLANTILLAS)


def titulo_evento(evento: Event) -> str:
    """Título legible en español de `evento`, o su código de acción si no hay
    plantilla todavía (no debería ocurrir: lo prueba `test_events_titulos.py`)."""
    plantilla = _PLANTILLAS.get(evento.action)
    if plantilla is None:
        return evento.action
    try:
        return plantilla(evento)
    except Exception:  # noqa: BLE001 - un evento antiguo con after_json incompleto no debe romper el diario
        return evento.action
