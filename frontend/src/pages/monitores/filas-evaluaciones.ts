/**
 * Filas de la tabla «Evaluaciones» de un monitor:
 * una fila por lote con su evaluación más reciente por `created_at` (la misma
 * regla que el detalle), ordenada por lote. Una reevaluación
 * (etiquetas tardías) sustituye a la vieja en su fila y la fila lo dice.
 */

import type { Evaluation } from "@/api/types";
import { evaluacionMasReciente } from "./usar-ultima-evaluacion";

export interface FilaEvaluacion {
  evaluacion: Evaluation;
  /** `true` si el lote tiene más de una evaluación de este monitor. */
  reevaluado: boolean;
}

/** Una fila por lote (las evaluaciones acumuladas, sin lote, forman una sola). */
export function filasPorLote(
  evaluaciones: readonly Evaluation[],
  seqDeLote: (batchId: number) => number | null,
): FilaEvaluacion[] {
  const grupos = new Map<number | null, Evaluation[]>();
  for (const e of evaluaciones) {
    const lista = grupos.get(e.batch_id) ?? [];
    lista.push(e);
    grupos.set(e.batch_id, lista);
  }
  const filas: { clave: number; fila: FilaEvaluacion }[] = [];
  for (const [batchId, lista] of grupos) {
    const ultima = evaluacionMasReciente(lista);
    if (!ultima) continue;
    const seq = batchId === null ? null : seqDeLote(batchId);
    // Sin lote (acumulado) y lotes sin `seq` conocido van al final.
    const clave = seq ?? Number.MAX_SAFE_INTEGER;
    filas.push({ clave, fila: { evaluacion: ultima, reevaluado: lista.length > 1 } });
  }
  filas.sort((a, b) => a.clave - b.clave || (a.fila.evaluacion.id ?? 0) - (b.fila.evaluacion.id ?? 0));
  return filas.map((f) => f.fila);
}
