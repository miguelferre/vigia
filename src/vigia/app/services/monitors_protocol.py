"""Validación del protocolo de un monitor.

Separado de `services/monitors.py`
para no pasar de 9 KB en ese fichero: `patch_monitor` sigue siendo el único
llamador de `validar_protocol`.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from vigia.app.content_loader import CAMPOS_HITO_PROTOCOLO
from vigia.app.models import ACCIONES_ALERTA

__all__ = ["ORDEN_HITOS_PROTOCOLO", "intercalar_hitos_extra", "validar_protocol"]

# Orden fijo de los cinco hitos estándar del protocolo: la
# derivación de estado de la alerta sigue anclada a ellos. Se permite intercalar hitos extra entre ellos o después del
# último, nunca antes del primero ni reordenando los cinco entre sí.
ORDEN_HITOS_PROTOCOLO: tuple[str, ...] = (
    "deteccion",
    "triaje",
    "investigacion",
    "decision",
    "seguimiento",
)


def validar_protocol(protocol: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Valida el protocolo editado en la hoja «Configurar»:
    debe **contener** las cinco claves de `ORDEN_HITOS_PROTOCOLO`, en ese
    orden relativo (hitos extra intercalados entre ellas o después de la
    última, nunca antes de `deteccion` ni reordenando las cinco); 422 con
    mensaje claro si falta alguna estándar, si se repite una clave o si un
    hito extra la desordena. Las claves extra deben ser únicas y no
    coincidir con ninguna de las cinco estándar ni con `ACCIONES_ALERTA`
    (validación cruzada contra
    `ACCIONES_ALERTA`, sin prefijo obligatorio). `titulo`/`descripcion` se
    guardan sin espacios sobrantes, `entregables` sin cadenas vacías (se
    filtran, no se rechaza el PATCH) y `responsable` vacío se guarda como
    `None`. `plazo_dias` ya llega validado (`ge=0`) por
    `MonitorProtocolStepBody`. Devuelve la lista lista para
    `Monitor.protocol_json`, con las seis claves de `CAMPOS_HITO_PROTOCOLO`.
    """
    esperado = list(ORDEN_HITOS_PROTOCOLO)
    claves = [h.get("key") for h in protocol]

    # Claves repetidas (estándar o extra): siempre un error, se anuncia primero.
    repetidas = sorted({k for k in claves if claves.count(k) > 1})
    if repetidas:
        raise HTTPException(422, f"protocol tiene claves repetidas: {repetidas}")

    faltan = [k for k in esperado if k not in claves]
    if faltan:
        raise HTTPException(
            422,
            f"protocol debe traer los cinco hitos del protocolo: faltan {faltan}",
        )

    # Orden relativo de las cinco estándar entre sí, ignorando los extra.
    posiciones_estandar = [k for k in claves if k in esperado]
    if posiciones_estandar != esperado:
        raise HTTPException(
            422,
            "protocol debe traer los cinco hitos del protocolo en su orden relativo "
            f"{esperado}; se recibió {posiciones_estandar}",
        )

    extra = [k for k in claves if k not in esperado]
    colision_acciones = sorted(set(extra) & set(ACCIONES_ALERTA))
    if colision_acciones:
        raise HTTPException(
            422,
            "los hitos extra no pueden usar una clave del catálogo de acciones de "
            f"alerta (ACCIONES_ALERTA): {colision_acciones}",
        )

    validado: list[dict[str, Any]] = []
    for hito in protocol:
        titulo = str(hito.get("titulo") or "").strip()
        descripcion = str(hito.get("descripcion") or "").strip()
        entregables = [e.strip() for e in (hito.get("entregables") or []) if str(e).strip()]
        responsable = hito.get("responsable")
        responsable = responsable.strip() if isinstance(responsable, str) else responsable
        responsable = responsable or None
        valores = {
            "key": hito["key"],
            "titulo": titulo,
            "descripcion": descripcion,
            "entregables": entregables,
            "responsable": responsable,
            "plazo_dias": hito.get("plazo_dias"),
        }
        validado.append({campo: valores[campo] for campo in CAMPOS_HITO_PROTOCOLO})
    return validado


def intercalar_hitos_extra(
    pasos: list[dict[str, Any]], protocolo: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Intercala una entrada `status: "informativo"` por cada hito extra de
    `protocolo` en la posición que le corresponde según
    el orden guardado en `Monitor.protocol_json`; los cinco pasos fijos
    (`pasos`, ya con su `status` derivado de `protocol_steps._pasos`) no
    cambian de valor, solo de posición si el protocolo intercaló extras
    (nunca entre sí: lo impide `validar_protocol`). Sin protocolo guardado
    o sin hitos extra, el resultado es `pasos` en su orden original."""
    por_clave = {p["key"]: p for p in pasos}
    resultado: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for hito in protocolo:
        key = hito.get("key")
        if key in por_clave:
            resultado.append(por_clave[key])
            vistos.add(key)
        elif key not in ORDEN_HITOS_PROTOCOLO:
            resultado.append({"key": key, "status": "informativo", "target_date": None})
            vistos.add(key)
    # Cualquier paso fijo que no apareciera en `protocolo` (monitor sin
    # protocolo guardado, plantilla vieja) se añade al final en su orden
    # original: no debería pasar con la plantilla actual, es defensivo.
    for paso in pasos:
        if paso["key"] not in vistos:
            resultado.append(paso)
    return resultado
