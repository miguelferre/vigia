"""Texto del deskilling en español.

`telemetry.render_summary_md` y `telemetry.deskilling_signal` del paquete
producen texto en inglés. Hasta solo el frontend lo traducía
(`pages/capa-humana/razones.ts`); la API (`GET /deskilling`), el MCP
(`get_deskilling`) y el resumen que se anexa al dossier lo devolvían crudo.
Este módulo da la misma salida en español, con la estructura del paquete:

- `motivo_es(reason)`: la frase completa de `signal.reason`.
- `resumen_md_es(...)`: el resumen en markdown, línea por línea igual que
  `render_summary_md`, con el mismo cálculo de ventanas y avisos.

No importa el paquete: recibe sus objetos (`WindowMetrics`, `Trends`,
`DeskillingSignal`) por forma, así que no depende de dónde viva
`interaction_review`. `ir_adapter.deskilling_reason_es` sigue siendo el
fragmento en minúscula que CX-4 mete dentro de un mensaje compuesto; esta
tabla es la frase suelta.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

__all__ = ["MOTIVOS_ES", "MOTIVO_POCAS_VENTANAS", "motivo_es", "resumen_md_es"]

# Las seis salidas literales de `telemetry.deskilling_signal` (`telemetry.py`,
# la de «converging» tiene tres variantes por el `" and ".join(why)`), con la
# redacción de `razones.ts`.
# Clave propia de Vigía: con menos de 2 ventanas con `min_n` eventos
# la pendiente no se calcula y la causa es la celda mínima, no la verdad de
# referencia. El adaptador sustituye el motivo del paquete por esta clave.
MOTIVO_POCAS_VENTANAS = "vigia:ventanas-con-pocos-eventos"

MOTIVOS_ES: dict[str, str] = {
    MOTIVO_POCAS_VENTANAS: (
        "Quedan menos de 2 ventanas con eventos suficientes: las ventanas pequeñas no "
        "aportan punto a la pendiente y no se puede evaluar una tendencia. Amplía el "
        "periodo del diario o reduce el número de ventanas."
    ),
    "Insufficient windows with ground truth to assess a trend.": (
        "No hay ventanas suficientes con verdad de referencia para evaluar una tendencia."
    ),
    (
        "Human and model are converging while the human's own accuracy is not "
        "improving -- a pattern consistent with criterion erosion. Investigate; "
        "not a diagnosis."
    ): (
        "El profesional y el modelo están convergiendo mientras el acierto del "
        "profesional no mejora: un patrón compatible con erosión del criterio. "
        "Para investigar, no es una conclusión."
    ),
    (
        "Human and model are converging while the rescue rate is falling -- a "
        "pattern consistent with criterion erosion. Investigate; not a diagnosis."
    ): (
        "El profesional y el modelo están convergiendo mientras la tasa de rescate "
        "cae: un patrón compatible con erosión del criterio. Para investigar, no "
        "es una conclusión."
    ),
    (
        "Human and model are converging while the human's own accuracy is not "
        "improving and the rescue rate is falling -- a pattern consistent with "
        "criterion erosion. Investigate; not a diagnosis."
    ): (
        "El profesional y el modelo están convergiendo mientras el acierto del "
        "profesional no mejora y la tasa de rescate cae: un patrón compatible con "
        "erosión del criterio. Para investigar, no es una conclusión."
    ),
    "Human and model are not converging over the period.": (
        "El profesional y el modelo no están convergiendo en el periodo."
    ),
    "Convergence present, but the human's accuracy/rescue rate holds.": (
        "Hay convergencia, pero el acierto o la tasa de rescate del profesional se mantiene."
    ),
}

_MOTIVO_DESCONOCIDO = (
    "Señal de deskilling sin motivo reconocido en el catálogo de traducción "
    "(revisar la versión de interaction_review)."
)


def motivo_es(reason: str) -> str:
    """Traduce `DeskillingSignal.reason`. Una frase que no esté en el catálogo
    no deja pasar inglés: dice que hay que revisar la versión del paquete."""
    return MOTIVOS_ES.get(reason, _MOTIVO_DESCONOCIDO)


class _Ventana(Protocol):
    start: Any
    end: Any
    n: int
    n_with_gt: int
    agreement_rate: float | None
    human_accuracy: float | None
    model_accuracy: float | None
    rescue_rate: float | None


class _Tendencias(Protocol):
    agreement_slope: float | None
    human_accuracy_slope: float | None
    rescue_slope: float | None


class _Senal(Protocol):
    fired: bool
    reason: str


def _tasa(x: float | None) -> str:
    return f"{x:.2f}" if x is not None else "n/d"


def _pendiente(x: float | None) -> str:
    return f"{x:+.3f}/ventana" if x is not None else "n/d"


def _ventanas(numeros: list[int], singular: str, plural: str) -> str:
    """«la ventana 2 tiene», «las ventanas 1, 2 tienen»."""
    if len(numeros) == 1:
        return f"la ventana {numeros[0]} {singular}"
    return f"las ventanas {', '.join(str(n) for n in numeros)} {plural}"


def _lista_ventanas(numeros: list[int]) -> str:
    """«la ventana 2», «las ventanas 1, 2»."""
    if len(numeros) == 1:
        return f"la ventana {numeros[0]}"
    return f"las ventanas {', '.join(str(n) for n in numeros)}"


def resumen_md_es(
    windows: Sequence[_Ventana],
    trends: _Tendencias,
    signal: _Senal,
    *,
    source_label: str = "diario de uso",
    min_n: int = 30,
    excluidas: Sequence[int] | None = None,
    validas: int | None = None,
) -> str:
    """Resumen determinista en markdown, sin marca de tiempo: la misma
    entrada da la misma salida byte a byte (como `render_summary_md`).

    `excluidas` son los números de ventana (desde 1) que quedan
    fuera de la pendiente por tener menos de `min_n` eventos; `validas` es
    cuántas ventanas aportan punto. Sin `excluidas` el texto es el de siempre.

    Las cifras llevan punto decimal, igual que el resto del markdown que
    Vigía anexa a un dossier (es texto para un revisor, no una pantalla)."""
    lineas: list[str] = []
    lineas.append("# Resumen de telemetría de uso (determinista, agregado)")
    lineas.append("")
    lineas.append(f"- **Fuente:** {source_label}")
    lineas.append(f"- **Ventanas:** {len(windows)} (misma duración en calendario)")
    total = sum(w.n for w in windows)
    total_vt = sum(w.n_with_gt for w in windows)
    lineas.append(f"- **Eventos:** {total} ({total_vt} con verdad de referencia conocida)")
    lineas.append("")
    lineas.append(
        "| Ventana | Fechas | n | n(vr) | Acuerdo profesional<->modelo | "
        "Acierto profesional | Acierto modelo | Rescate |"
    )
    lineas.append("|---|---|---|---|---|---|---|---|")
    for i, w in enumerate(windows, 1):
        lineas.append(
            f"| {i} | {w.start.isoformat()}..{w.end.isoformat()} | {w.n} | {w.n_with_gt} | "
            f"{_tasa(w.agreement_rate)} | {_tasa(w.human_accuracy)} | {_tasa(w.model_accuracy)} | "
            f"{_tasa(w.rescue_rate)} |"
        )
    lineas.append("")
    lineas.append("**Tendencias (pendiente por mínimos cuadrados, por ventana):**")
    lineas.append(
        f"- Acuerdo profesional<->modelo: {_pendiente(trends.agreement_slope)} (convergencia si sube)"
    )
    lineas.append(
        f"- Acierto del profesional: {_pendiente(trends.human_accuracy_slope)} (la distancia con la realidad)"
    )
    lineas.append(
        f"- Tasa de rescate: {_pendiente(trends.rescue_slope)} (el profesional detecta un modelo equivocado)"
    )
    lineas.append("")
    veredicto = "SEÑAL" if signal.fired else "sin señal"
    lineas.append(f"**Señal de deskilling (IX-2): {veredicto}.** {motivo_es(signal.reason)}")

    pocas = [i + 1 for i, w in enumerate(windows) if w.n < min_n]
    sin_vr = [i + 1 for i, w in enumerate(windows) if w.n_with_gt == 0]
    if pocas:
        lineas.append("")
        lineas.append(
            f"> Precaución: {_ventanas(pocas, 'tiene', 'tienen')} menos de {min_n} eventos; "
            "sus tasas son ruidosas."
        )
    if sin_vr:
        lineas.append("")
        lineas.append(
            f"> Precaución: {_ventanas(sin_vr, 'no tiene', 'no tienen')} verdad de referencia; "
            "el acierto y el rescate no están definidos ahí."
        )
    if excluidas:
        un = len(excluidas) == 1
        lineas.append("")
        lineas.append(
            f"> Pendiente: se {'excluye 1 ventana' if un else f'excluyen {len(excluidas)} ventanas'} "
            f"con menos de {min_n} eventos ({_lista_ventanas(list(excluidas))}); "
            f"{'sigue' if un else 'siguen'} en la tabla, pero no {'aporta' if un else 'aportan'} "
            "punto a la pendiente."
        )
        if validas is not None and validas < 2:
            lineas.append("")
            lineas.append(
                f"> La pendiente no se calcula: {'queda' if validas == 1 else 'quedan'} "
                f"{validas} {'ventana' if validas == 1 else 'ventanas'} con al menos {min_n} "
                "eventos y hacen falta 2."
            )
    lineas.append("")
    lineas.append(
        "> Telemetría agregada, sin datos personales. Es un complemento objetivo del testimonio "
        "del usuario final, no un sustituto; la señal es algo que investigar, no una conclusión."
    )
    return "\n".join(lineas) + "\n"
