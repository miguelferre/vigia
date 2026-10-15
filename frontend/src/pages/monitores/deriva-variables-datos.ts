/**
 * Datos de `deriva-variables.tsx` (criterio de cierre §5):
 * partido a fichero `.ts` propio para que ese `.tsx` exporte solo el
 * componente y no dispare `react-refresh/only-export-components`.
 */

import type { JsonObject } from "@/api/types";
import { etiquetaValorCategoria, nombreVariable } from "@/lib/dominio-caracteristicas";
import { formatoCorto, formatoNumero } from "@/lib/metrics";

export interface FilaVariable {
  feature: string;
  featureLabel: string;
  kind: string;
  psi: number | null;
  ksStat: number | null;
  ksP: number | null;
  chi2: number | null;
  p: number | null;
  js: number | null;
  /** Puntuación que entra en `feature_drift_score` (KS si es numérica, JS si es categórica). */
  score: number | null;
  /** Categórica sin ningún valor compartido entre la línea base y el lote (el score sigue contando). */
  sinValoresComunes: boolean;
  binEdges: number[];
  countsBase: number[];
  countsActual: number[];
  categories: string[];
}

function numeroONulo(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

function arrayDeNumeros(v: unknown): number[] {
  return Array.isArray(v) ? v.filter((x): x is number => typeof x === "number") : [];
}

function arrayDeStrings(v: unknown): string[] {
  return Array.isArray(v) ? v.map((x) => String(x)) : [];
}

export function extraerVariables(
  details: JsonObject | null,
  dominio: Record<string, string> | undefined,
): FilaVariable[] {
  if (!details) return [];
  const features = details.features;
  if (!Array.isArray(features)) return [];
  const filas = features
    .filter((f): f is JsonObject => f !== null && typeof f === "object" && !Array.isArray(f))
    .map((f) => {
      const feature = typeof f.feature === "string" ? f.feature : String(f.feature ?? "");
      return {
        feature,
        featureLabel: nombreVariable(feature, dominio),
        kind: typeof f.kind === "string" ? f.kind : "",
        psi: numeroONulo(f.psi),
        ksStat: numeroONulo(f.ks_stat),
        ksP: numeroONulo(f.ks_p),
        chi2: numeroONulo(f.chi2),
        p: numeroONulo(f.p),
        js: numeroONulo(f.js),
        score: numeroONulo(f.score),
        sinValoresComunes: f.sin_valores_comunes === true,
        binEdges: arrayDeNumeros(f.bin_edges),
        countsBase: arrayDeNumeros(f.bin_counts_base),
        countsActual: arrayDeNumeros(f.bin_counts_actual),
        // Valores binarios ("0"/"1") traducidos a ausencia/presencia.
        categories: arrayDeStrings(f.categories).map(etiquetaValorCategoria),
      };
    });
  // Por la puntuación que entra en `feature_drift_score` (KS o JS), no
  // por PSI: la variable del máximo, la que dispara la alerta, queda la
  // primera aunque sea categórica (sin PSI). Sin puntuación, al final. A igual
  // puntuación, PSI y después chi².
  return filas.sort(
    (a, b) =>
      (b.score ?? -Infinity) - (a.score ?? -Infinity) ||
      (b.psi ?? -Infinity) - (a.psi ?? -Infinity) ||
      (b.chi2 ?? -Infinity) - (a.chi2 ?? -Infinity),
  );
}

/** Lo que significa la marca «Sin categorías comunes con la base». */
export const TEXTO_SIN_COMUNES =
  "La línea base y el lote no comparten ninguna categoría de esta variable (un identificador, un texto libre o una fecha); su puntuación está cerca de 1 y cuenta igualmente para la deriva de características.";

/**
 * La variable que da el máximo del `feature_drift_score`: la primera tras
 * `extraerVariables` si tiene puntuación (el orden ya es por puntuación).
 */
export function claveDelMaximo(filas: FilaVariable[]): string | null {
  const primera = filas[0];
  return primera && primera.score !== null ? primera.feature : null;
}

/** Numérica: mismos tramos en bordes y recuentos (`core/drift.py`); categórica no trae `bin_edges`. */
export function esNumerica(variable: FilaVariable): boolean {
  return variable.binEdges.length === variable.countsBase.length + 1 && variable.binEdges.length > 0;
}

/** «18 a 96» con bordes enteros, «0,50 a 1,00» con decimales, o «N categorías» si no es numérica. */
export function rangoDeVariable(variable: FilaVariable): string {
  if (!esNumerica(variable)) return `${variable.categories.length} categorías`;
  const bordeInicial = variable.binEdges[0];
  const bordeFinal = variable.binEdges[variable.binEdges.length - 1];
  const bordesEnteros = Number.isInteger(bordeInicial) && Number.isInteger(bordeFinal);
  return bordesEnteros
    ? `${formatoCorto(bordeInicial, 0)} a ${formatoCorto(bordeFinal, 0)}`
    : `${formatoNumero(bordeInicial, 2)} a ${formatoNumero(bordeFinal, 2)}`;
}
