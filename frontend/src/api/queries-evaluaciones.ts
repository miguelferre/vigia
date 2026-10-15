/**
 * `useEvaluations` y `useExplanations`, partidos de `queries.ts` para no
 * superar 9 KB (mismo criterio que `queries-timeline.ts`). Sus claves
 * (`qk.evaluations`, `qk.explanations`) nacen en `queries.ts` con las demás.
 * Ningún nombre exportado cambia al mover.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { qk, STALE_MS, type Opciones } from "./queries";
import type { Evaluation, EvaluationFilters, Explanation, ListResponse } from "./types";

export function useEvaluations(
  id: number | null,
  f?: EvaluationFilters,
  opciones?: Opciones<ListResponse<Evaluation>>,
) {
  return useQuery({
    queryKey: qk.evaluations(id, f),
    queryFn: () => api.get<ListResponse<Evaluation>>(`/projects/${id}/evaluations`, { params: { ...f } }),
    enabled: id !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

export function useExplanations(
  versionId: number | null,
  opciones?: Opciones<ListResponse<Explanation>>,
) {
  return useQuery({
    queryKey: qk.explanations(versionId),
    queryFn: () => api.get<ListResponse<Explanation>>(`/model-versions/${versionId}/explanations`),
    enabled: versionId !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}
