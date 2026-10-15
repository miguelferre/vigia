/**
 * `useExplanationsSummary`, partido de `queries.ts` para no superar 9 KB
 * (mismo criterio que `queries-timeline.ts`).
 *
 * `GET /projects/{id}/explanations/summary`, para la
 * tarjeta de explicabilidad del cuadro de mando. `ExplanationSummary` no
 * tiene alias en `types-events.ts` todavía (fuera de mi frontera): se lee
 * directamente de `Schemas`, el alias público de `components["schemas"]`
 * (`types-base.ts`), sin inventar un tipo a mano.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { qk, STALE_MS, type Opciones } from "./queries";
import type { Schemas } from "./types";

export function useExplanationsSummary(
  id: number | null,
  opciones?: Opciones<Schemas["ExplanationSummary"]>,
) {
  return useQuery({
    queryKey: qk.explanationsSummary(id),
    queryFn: () => api.get<Schemas["ExplanationSummary"]>(`/projects/${id}/explanations/summary`),
    enabled: id !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}
