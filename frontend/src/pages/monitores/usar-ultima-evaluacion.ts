/**
 * Qué evaluación enseñan los bloques de detalle de `/monitores/:tipo`:
 * la más reciente por fecha, que es la del último punto de
 * la serie (la API publica `ts = created_at`). Con el id máximo, una
 * reevaluación manual de un lote antiguo (id mayor, fecha anterior) hacía que
 * la tarjeta y el detalle enseñaran dos cifras distintas para lo mismo.
 */

import { useMemo } from "react";

import type { Evaluation } from "@/api/types";

/** La más reciente por `created_at`; a igual fecha, la de id mayor. */
export function evaluacionMasReciente(evaluaciones: readonly Evaluation[]): Evaluation | null {
  let mejor: Evaluation | null = null;
  for (const e of evaluaciones) {
    if (
      mejor === null ||
      e.created_at > mejor.created_at ||
      (e.created_at === mejor.created_at && (e.id ?? 0) > (mejor.id ?? 0))
    ) {
      mejor = e;
    }
  }
  return mejor;
}

/**
 * `?lote=<batch_id>`: la demo guiada abre la pantalla con la
 * evaluación del lote que narra el paso. Sin el parámetro, o con un lote sin
 * evaluación de este monitor, manda la más reciente.
 */
export function useUltimaEvaluacion(evaluaciones: readonly Evaluation[], loteParam: string | null): Evaluation | null {
  return useMemo(() => {
    const id = loteParam === null ? null : Number(loteParam);
    if (id !== null && Number.isFinite(id)) {
      const delLote = evaluacionMasReciente(evaluaciones.filter((e) => e.batch_id === id));
      if (delLote) return delLote;
    }
    return evaluacionMasReciente(evaluaciones);
  }, [evaluaciones, loteParam]);
}
