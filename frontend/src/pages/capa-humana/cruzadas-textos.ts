/**
 * Textos de la tarjeta «Cruzadas». Aparte de `Cruzadas.tsx`, que
 * ya pasa de 9 KB, para que los lea el test de textos.
 */

/** Antes de evaluar: la primera evaluación de cada versión solo calibra. */
export const DESCRIPCION_EVALUAR_CRUZADAS =
  "Lanza una evaluación de las seis reglas cruzadas sobre la versión activa. " +
  "La primera evaluación de cada versión solo calibra: fija la referencia y no trae reglas. " +
  "Si es tu primera vez, evalúa otra vez después de esta para ver las seis reglas.";

/**
 * Junto al botón, antes de pulsar: la primera evaluación de una
 * versión no trae reglas. Se enseña mientras la tarjeta no tenga las seis.
 */
export const AVISO_PRIMERA_CRUZADA =
  "La primera evaluación de cada versión solo calibra y no trae reglas. Pulsa «Evaluar ahora» dos veces para verlas.";

/** Igual, pero cuando la versión ya tiene su evaluación de calibración: basta una vez. */
export const AVISO_YA_CALIBRADA =
  "Esta versión ya está calibrada. Pulsa «Evaluar ahora» una vez para ver las seis reglas.";

/** Al terminar una evaluación de calibración, sin reglas todavía. */
export const TITULO_CALIBRACION_CRUZADAS = "Evaluación de calibración: todavía sin reglas";
export const DESCRIPCION_CALIBRACION_CRUZADAS =
  "Esta evaluación solo ha fijado la referencia de esta versión del modelo; las seis reglas se calculan en la siguiente. " +
  "Qué hacer: pulsa «Evaluar ahora» otra vez para verlas.";

/** Sin evaluación: la API da el motivo cuando no es solo que falte el diario (p. ej. regresión sin rango). */
export function descripcionSinCruzadas(motivo: string | null | undefined): string {
  if (!motivo) return "Este proyecto todavía no tiene ninguna evaluación de las reglas cruzadas.";
  return descripcionSinRango(motivo);
}

/** Regresión sin rango favorable: el motivo de la API con mayúscula inicial y qué hacer. */
export function descripcionSinRango(motivo: string): string {
  return `${motivo.replace(/^./, (c) => c.toUpperCase()).replace(/\.$/, "")}. Qué hacer: crea un modelo nuevo con rango favorable.`;
}
