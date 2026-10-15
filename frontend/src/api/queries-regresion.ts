/**
 * Consultas de la regresión (alta, explicabilidad, capa humana y
 * comparar en regresión). Mismo patrón que `queries-humana.ts`: la raíz
 * `"humana"` se invalida con el proyecto, el dataset y la evaluación.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { STALE_MS, type Opciones } from "./queries";
import type { components } from "./schema";

/** `GET /projects/{id}/overrides/cambios`: salida del modelo frente a decisión del profesional. */
export type OverridesCambiosResponse = components["schemas"]["OverridesCambiosResponse"];
export type OverridesCambiosFila = components["schemas"]["OverridesCambiosFila"];

export function useOverridesCambios(
  projectId: number | null,
  modelVersionId?: number | null,
  opciones?: Opciones<OverridesCambiosResponse>,
) {
  return useQuery({
    queryKey: ["humana", projectId, "overrides-cambios", modelVersionId ?? null],
    queryFn: () =>
      api.get<OverridesCambiosResponse>(`/projects/${projectId}/overrides/cambios`, {
        params: { model_version_id: modelVersionId ?? null },
      }),
    enabled: projectId !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}
