/**
 * Parámetros del laboratorio: los controles
 * salen de `laboratorio.parametros` de `GET /content/demo` (etiqueta, rango,
 * paso y valor por defecto en español) cruzados con `lab_params` de la fase
 * elegida (`GET /demo/scenarios`, las claves que el generador acepta de
 * verdad): solo se ofrece lo que existe en ambos. Queda el monitor y la medida clave con
 * los que la tabla de resultados resume cada ensayo.
 */

import type { ParametroLaboratorio } from "@/api/queries-contenido";
import type { MonitorType } from "@/api/types";

import type { FaseGuion } from "./tipos";

export interface DefinicionParametro {
  clave: string;
  etiqueta: string;
  tipo: "int" | "float";
  min: number;
  max: number;
  paso: number;
  porDefecto: number;
}

/**
 * Entero solo cuando rango, paso y valor por defecto lo son: «Edad media»
 * tiene rango y paso enteros pero un valor por defecto de 62,4, y un campo
 * entero rechazaría su propio valor inicial.
 */
function tipoDe(p: ParametroLaboratorio): DefinicionParametro["tipo"] {
  return [p.min, p.max, p.paso, p.por_defecto].every(Number.isInteger) ? "int" : "float";
}

/** Los controles de una fase: el contenido en el orden del contenido, filtrado por lo que la fase acepta. */
export function parametrosDeFase(contenido: ParametroLaboratorio[], fase: FaseGuion | null): DefinicionParametro[] {
  if (!fase) return [];
  return contenido
    .filter((p) => fase.lab_params.includes(p.clave))
    .map((p) => ({
      clave: p.clave,
      etiqueta: p.etiqueta,
      tipo: tipoDe(p),
      min: p.min,
      max: p.max,
      paso: p.paso,
      porDefecto: p.por_defecto,
    }));
}

const ORDEN_MONITORES: MonitorType[] = ["fairness", "quality", "drift"];

/**
 * Monitor que cuenta la historia de la fase: el primero, en el orden fijo de
 * arriba, cuyo `expected` no sea `ok`. Con todo en `ok` (la línea base) cae
 * a equidad.
 */
export function monitorClave(expected: Record<string, string> | null | undefined): MonitorType {
  if (expected) {
    for (const m of ORDEN_MONITORES) {
      if (expected[m] && expected[m] !== "ok") return m;
    }
  }
  return "fairness";
}

/**
 * La medida que resume el monitor clave: para equidad la del checklist de
 * aceptación (FNRD); para calidad `accuracy`; para deriva la de predicción,
 * igual que el resumen del cuadro (`lib/metrics.ts:METRICA_PRINCIPAL`).
 */
export const METRICA_CLAVE_POR_MONITOR: Record<MonitorType, string> = {
  fairness: "false_negative_rate_difference",
  quality: "accuracy",
  drift: "prediction_drift_score",
  explain: "explain_stability_ndcg",
  cross: "cx5_chi2_p",
};

/** Un ensayo de laboratorio ya resuelto, para la lista de resultados. */
export interface ResultadoLab {
  ts: number;
  faseKey: string;
  faseTitulo: string;
  /** `expected` de la fase ensayada: fija su monitor y medida clave en la tabla de resultados. */
  expected: Record<string, string> | null;
  batchId: number;
  params: Record<string, unknown>;
  states: Partial<Record<MonitorType, string>>;
}
