/**
 * Textos de motivo de «Cómo se ha calculado» (parte de `CalculoFormula`):
 * umbral relativo a la prevalencia y medida `sin_datos` con su motivo.
 */

import type { Measurement } from "@/api/types";
import { formatoNumero } from "@/lib/metrics";

/**
 * un umbral resuelto desde la prevalencia lo dice. El límite que
 * se enseña es el de la medida (el que trae `threshold_low`), no el 0,8 de
 * fábrica, que es una fracción de la mejora de la línea base sobre la
 * prevalencia.
 */
export function textoUmbralRelativo(texto: string | null, propia: Measurement | undefined): string | null {
  if (texto === null || !propia?.extra?.umbral_relativo) return texto;
  return `${texto} (relativo a la prevalencia)`;
}

/**
 * Multiclase y regresión: una medida `sin_datos` dice por qué
 * («umbral pendiente de la línea base») y, si el motor lo guardó, el valor que
 * sí calculó. Es un motivo, no un fallo: el estado sigue siendo «Sin datos».
 * `formato`: en regresión, el valor con la unidad del proyecto.
 */
export function motivoMulticlase(
  propia: Measurement | undefined,
  tieneValor: boolean,
  formato: (v: number) => string = (v) => formatoNumero(v, 3),
): string | null {
  if (!propia || tieneValor || !propia.motivo) return null;
  const calculado = propia.extra?.valor_calculado;
  return typeof calculado === "number"
    ? `${propia.motivo}. Valor calculado en esta ventana: ${formato(calculado)}, sin umbral con el que compararlo todavía.`
    : propia.motivo;
}
