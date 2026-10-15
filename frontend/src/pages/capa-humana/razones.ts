/**
 * Traducción de `signal.reason` (`interaction_review.telemetry.deskilling_signal`,
 * `telemetry.py:191-214`, solo lectura): el paquete siempre produce una de
 * estas frases en inglés (no texto libre), así que un mapa literal basta.
 * Si el paquete cambia y aparece una frase nueva, se enseña el original
 * (si no está en el mapa, enseña el original).
 */

const RAZONES: Record<string, string> = {
  "Insufficient windows with ground truth to assess a trend.":
    "No hay ventanas suficientes con verdad de referencia para evaluar una tendencia.",
  "Human and model are not converging over the period.":
    "El profesional y el modelo no están convergiendo en el periodo.",
  "Convergence present, but the human's accuracy/rescue rate holds.":
    "Hay convergencia, pero el acierto o la tasa de rescate del profesional se mantiene.",
  "Human and model are converging while the human's own accuracy is not improving -- a pattern consistent with criterion erosion. Investigate; not a diagnosis.":
    "El profesional y el modelo están convergiendo mientras el acierto del profesional no mejora: un patrón compatible con erosión del criterio. Para investigar, no es una conclusión.",
  "Human and model are converging while the rescue rate is falling -- a pattern consistent with criterion erosion. Investigate; not a diagnosis.":
    "El profesional y el modelo están convergiendo mientras la tasa de rescate cae: un patrón compatible con erosión del criterio. Para investigar, no es una conclusión.",
  "Human and model are converging while the human's own accuracy is not improving and the rescue rate is falling -- a pattern consistent with criterion erosion. Investigate; not a diagnosis.":
    "El profesional y el modelo están convergiendo mientras el acierto del profesional no mejora y la tasa de rescate cae: un patrón compatible con erosión del criterio. Para investigar, no es una conclusión.",
};

export function traducirRazon(reason: string): string {
  return RAZONES[reason] ?? reason;
}
