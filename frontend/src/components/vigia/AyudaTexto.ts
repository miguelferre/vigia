/**
 * `que_mide` y `como_se_lee` de una entrada de `metricas-ayuda.json`, por
 * separado. Antes `textoQueMide` concatenaba
 * los dos en el único párrafo que esperaba `InfoTooltip.queMide`; ahora el párrafo de arriba de un bloque de cálculo es
 * solo `que_mide`, y `como_se_lee` pasa al segundo párrafo del ⓘ
 * (`InfoTooltip.comoSeLee`) y al glosario.
 */

import type { AyudaMetrica } from "@/api/queries-contenido";

/** Qué mide la métrica, una frase. Nunca incluye `como_se_lee`. */
export function textoQueMide(
  ayuda: AyudaMetrica | undefined,
  fallback = "Ayuda no disponible.",
): string {
  if (!ayuda) return fallback;
  return ayuda.que_mide;
}

/** Cómo se lee el valor (sentido, escala); `null` sin ayuda cargada para esta métrica. */
export function textoComoSeLee(ayuda: AyudaMetrica | undefined): string | null {
  return ayuda?.como_se_lee ?? null;
}
