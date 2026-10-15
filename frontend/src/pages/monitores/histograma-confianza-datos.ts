/**
 * Lectura de `result.details.confidence` de una evaluación de deriva, sin
 * suponer forma (sale de `histograma-confianza.tsx` por el límite de 9 KB).
 */

import type { JsonObject } from "@/api/types";

export interface Confianza {
  binEdges: number[];
  countsBase: number[];
  countsActual: number[];
  ksStat: number | null;
  ksP: number | null;
  psi: number | null;
  jsDistance: number | null;
}

function numeroONulo(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

function arrayDeNumeros(v: unknown): number[] {
  return Array.isArray(v) ? v.filter((x): x is number => typeof x === "number") : [];
}

export function extraerConfianza(details: JsonObject | null): Confianza | null {
  if (!details) return null;
  const c = details.confidence;
  if (!c || typeof c !== "object" || Array.isArray(c)) return null;
  const obj = c as JsonObject;
  return {
    binEdges: arrayDeNumeros(obj.bin_edges),
    countsBase: arrayDeNumeros(obj.bin_counts_base),
    countsActual: arrayDeNumeros(obj.bin_counts_actual),
    ksStat: numeroONulo(obj.ks_stat),
    ksP: numeroONulo(obj.ks_p),
    psi: numeroONulo(obj.psi),
    jsDistance: numeroONulo(obj.jensen_shannon_distance),
  };
}
