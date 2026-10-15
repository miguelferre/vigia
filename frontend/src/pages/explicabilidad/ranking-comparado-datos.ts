/**
 * Tipos y cálculo puro de «Línea base frente a ahora»: las filas del dumbbell que dibuja `RankingComparado.tsx`. Sin
 * React, para que ningún fichero de este bloque pase de 9 KB; las frases
 * calculadas sobre estas filas viven aparte, en
 * `frase-comparada.ts`, por el mismo motivo de tamaño.
 *
 * `reference_top_features`/`ranking_delta` (`ExplanationSummary`) ya vienen
 * recortados al top 10 por el backend, con el mismo `p` que
 * `explain_stability_ndcg`: estas funciones no reordenan ni
 * recalculan ese recorte, solo casan nombres de variable contra el top 10
 * actual (`extraerFilas` sobre la última explicación completa).
 */

import type { JsonObject } from "@/api/types";
import type { ExplanationSummary } from "@/api/types-domain";
import { nombreVariable } from "@/lib/dominio-caracteristicas";

export type FeatureResumen = NonNullable<ExplanationSummary["reference_top_features"]>[number];
export type DeltaFila = ExplanationSummary["ranking_delta"][number];

export interface FilaActual {
  /** Etiqueta clínica (`nombreVariable`). */
  feature: string;
  /** Nombre técnico de la columna: enlaza a `/monitores/deriva`. */
  featureTecnico: string;
  valor: number;
  rule: string | null;
}

export interface FilaComparada {
  featureTecnico: string;
  label: string;
  base: number | null;
  actual: number | null;
  puestoBase: number | null;
  puestoActual: number | null;
  /** Salió del top 10 actual: se añade al final, con la etiqueta atenuada. */
  marcada: boolean;
}

function featuresDe(result: JsonObject | null): JsonObject[] {
  if (!result || typeof result !== "object" || Array.isArray(result)) return [];
  const features = (result as JsonObject).features;
  if (!Array.isArray(features)) return [];
  return features.filter((f): f is JsonObject => f !== null && typeof f === "object" && !Array.isArray(f));
}

/** Top 10 de la última explicación completa, igual que `RankingBarras`. */
export function extraerFilas(result: JsonObject | null, dominio: Record<string, string> | undefined): FilaActual[] {
  return featuresDe(result)
    .map((f) => {
      const tecnico = typeof f.feature === "string" ? f.feature : String(f.feature ?? "");
      return {
        feature: nombreVariable(tecnico, dominio),
        featureTecnico: tecnico,
        valor: typeof f.importance === "number" ? f.importance : 0,
        rule: typeof f.rule === "string" ? f.rule : null,
      };
    })
    .sort((a, b) => Math.abs(b.valor) - Math.abs(a.valor))
    .slice(0, 10);
}

/** Importancia actual de una variable en el resultado SIN recortar (para las «salidas»). */
function buscarImportancia(result: JsonObject | null, featureTecnico: string): number | null {
  const f = featuresDe(result).find((x) => x.feature === featureTecnico);
  const v = f?.importance;
  return typeof v === "number" ? v : null;
}

/**
 * Filas del dumbbell: el top 10 actual (orden = peso actual) más las
 * variables que salieron de él pero estaban en la referencia, al final,
 * ordenadas por su puesto de referencia.
 */
export function prepararFilasComparadas(
  actuales: FilaActual[],
  resultActual: JsonObject | null,
  referenciaTop: FeatureResumen[],
  delta: DeltaFila[],
  dominio: Record<string, string> | undefined,
): FilaComparada[] {
  const puestoBase = new Map(referenciaTop.map((f, i) => [f.feature, i + 1]));
  const valorBase = new Map(referenciaTop.map((f) => [f.feature, f.importance]));
  const salidas = new Set(delta.filter((d) => d.to === null).map((d) => d.feature));

  const filasTop: FilaComparada[] = actuales.map((fila, i) => ({
    featureTecnico: fila.featureTecnico,
    label: fila.feature,
    actual: fila.valor,
    puestoActual: i + 1,
    base: valorBase.get(fila.featureTecnico) ?? null,
    puestoBase: puestoBase.get(fila.featureTecnico) ?? null,
    marcada: false,
  }));

  const filasSalidas: FilaComparada[] = Array.from(salidas)
    .map((featureTecnico) => ({
      featureTecnico,
      label: nombreVariable(featureTecnico, dominio),
      actual: buscarImportancia(resultActual, featureTecnico),
      puestoActual: null,
      base: valorBase.get(featureTecnico) ?? null,
      puestoBase: puestoBase.get(featureTecnico) ?? null,
      marcada: true,
    }))
    .sort((a, b) => (a.puestoBase ?? 99) - (b.puestoBase ?? 99));

  return [...filasTop, ...filasSalidas];
}
