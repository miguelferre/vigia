/**
 * Utilidades sin dependencias de vuelta para los bloques de "Cómo se ha
 * calculado": `medida`, `numero` y los formateadores vivían en
 * `DrillImpactoDispar.tsx`, que a su vez importaba de `CalculoFormula.tsx` y
 * de `DrillTasasError.tsx`, cerrando dos ciclos de import. Este módulo es
 * hoja: solo importa tipos de `@/api/types`, nunca de `CalculoFormula.tsx`,
 * `DrillImpactoDispar.tsx`, `DrillTasasError.tsx` ni `EscalaCociente.tsx`.
 *
 * `EtiquetaConAyuda` está en su propio fichero porque es un componente.
 */

import type { EvaluationDetail, Measurement } from "@/api/types";

export function medida(evaluacion: EvaluationDetail, clave: string): Measurement | undefined {
  return evaluacion.measurements.find((m) => m.metric_key === clave);
}

export function numero(valor: unknown): number | null {
  return typeof valor === "number" ? valor : null;
}

export function formatoPorcentaje(valor: number | null, decimales = 1): string {
  if (valor === null || Number.isNaN(valor)) return "n/d";
  return valor.toLocaleString("es-ES", {
    style: "percent",
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });
}

export function formatoCorto(valor: number | null | undefined, decimales = 1): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "n/d";
  return valor.toLocaleString("es-ES", { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
}

/** Reglas cruzadas (`CX-1` a `CX-6`): sus medidas se llaman `cx6_override_z:<grupo>`, no `CX-6`, así que no hay caja de resultado. */
export function esReglaCruzada(metricKey: string, ayuda?: { monitor: string }): boolean {
  return ayuda?.monitor === "cross" || /^CX-\d+$/.test(metricKey);
}
