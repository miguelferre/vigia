/**
 * Extracción de `result.details.prediction` (`{rate_base, rate_cur, diff,
 * score}`, `core/drift.py:88-93`). Movido desde `clases-predichas.tsx`
 *  para que `TarjetaClasesPredichas` y el onboarding lo
 * compartan sin duplicar la lectura de `details`.
 *
 * `n_base`/`n_actual`: tamaño de
 * cada ventana, para pasar de tasa a recuento en la tarjeta de clases
 * predichas. Lectura tolerante porque `api/schema.d.ts` (generado) todavía no
 * los tiene el día que se escribe esto: `null` en evaluaciones anteriores al
 * cambio de backend, no solo si falta el campo.
 *
 * En multiclase `details.prediction` trae además
 * `por_clase` (`{base, actual, diff}` por clase, indexado con `claveClase`),
 * `clase_mayor_cambio` y `cambio_mayor`; `score` es la distancia de
 * Jensen-Shannon entre los repartos por clase y `rate_*` la tasa del
 * conjunto favorable. En binario esos campos no existen y `porClase` es
 * `null`.
 */

import type { JsonObject } from "@/api/types";
import { claveClase } from "@/lib/tipo-tarea";

function numeroONulo(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

export interface FilaPrediccionClase {
  clase: string;
  /** Reparto de la clase predicha en la línea base, 0 a 1. */
  base: number | null;
  /** Reparto de la clase predicha en el lote, 0 a 1. */
  actual: number | null;
  /** `actual - base`, en puntos de reparto (0 a 1). */
  diff: number | null;
}

export interface Prediccion {
  rate_base: number | null;
  rate_cur: number | null;
  diff: number | null;
  n_base: number | null;
  n_actual: number | null;
  /** Multiclase: reparto por clase predicha, en el orden de `details`; `null` en binario. */
  porClase: FilaPrediccionClase[] | null;
  /** Multiclase: la clase con el mayor cambio de reparto y ese cambio (0 a 1). */
  claseMayorCambio: string | null;
  cambioMayor: number | null;
}

export function extraerPrediccion(details: JsonObject | null): Prediccion | null {
  if (!details) return null;
  const prediction = details.prediction;
  if (!prediction || typeof prediction !== "object" || Array.isArray(prediction)) return null;
  const p = prediction as JsonObject;
  const porClaseObj = p.por_clase;
  const porClase =
    porClaseObj && typeof porClaseObj === "object" && !Array.isArray(porClaseObj)
      ? Object.entries(porClaseObj as JsonObject).flatMap(([claseCruda, v]) =>
          v && typeof v === "object" && !Array.isArray(v)
            ? [
                {
                  clase: claveClase(claseCruda),
                  base: numeroONulo((v as JsonObject).base),
                  actual: numeroONulo((v as JsonObject).actual),
                  diff: numeroONulo((v as JsonObject).diff),
                },
              ]
            : [],
        )
      : null;
  return {
    rate_base: numeroONulo(p.rate_base),
    rate_cur: numeroONulo(p.rate_cur),
    diff: numeroONulo(p.diff),
    n_base: numeroONulo(p.n_base),
    n_actual: numeroONulo(p.n_actual),
    porClase: porClase && porClase.length > 0 ? porClase : null,
    claseMayorCambio: typeof p.clase_mayor_cambio === "string" ? claveClase(p.clase_mayor_cambio) : null,
    cambioMayor: numeroONulo(p.cambio_mayor),
  };
}
