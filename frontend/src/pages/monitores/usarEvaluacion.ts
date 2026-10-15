/**
 * Detalle de una evaluación (`GET /evaluations/{id}`).
 *
 * `src/api/queries.ts` no expone este hook (solo la lista, `useEvaluations`);
 * se define aquí con la misma clave (`qk.evaluation`) para que la invalidación
 * por SSE (raíz `evaluations`) también lo alcance.
 */

import { useQueries, useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { qk, STALE_MS } from "@/api/queries";
import type { EvaluationDetail } from "@/api/types";

export function useEvaluationDetail(evaluationId: number | null) {
  return useQuery({
    queryKey: qk.evaluation(evaluationId),
    queryFn: () => api.get<EvaluationDetail>(`/evaluations/${evaluationId}`),
    enabled: evaluationId !== null,
    staleTime: STALE_MS,
  });
}

/** Varias evaluaciones a la vez, para la columna de recuento por estado de la tabla. */
export function useEvaluationDetails(ids: number[]) {
  return useQueries({
    queries: ids.map((id) => ({
      queryKey: qk.evaluation(id),
      queryFn: () => api.get<EvaluationDetail>(`/evaluations/${id}`),
      staleTime: STALE_MS,
    })),
  });
}
