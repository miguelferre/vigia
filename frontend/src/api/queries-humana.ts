/**
 * `/capa-humana`: deskilling, overrides, cruzadas y outcomes.
 *
 * Las claves nacen aquí (patrón de
 * `api/queries-alertas-series.ts`), bajo la raíz `"humana"` que
 * `RAICES_POR_OBJETO` (`api/queries.ts`) ya invalida por `dataset`,
 * `evaluation`, `project` y `demo_run`.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { STALE_MS, type Opciones } from "./queries";
import type {
  CrossLatest,
  DeskillingResponse,
  OutcomesListResponse,
  OverridesByClinicianResponse,
  OverridesByGroupResponse,
  OverridesClinicianList,
  OverridesMeResponse,
} from "./types";

export function useDeskilling(
  projectId: number | null,
  filtros: { clinician?: string | null; subgroup?: string | null; modelVersionId?: number | null; nWindows?: number },
  opciones?: Opciones<DeskillingResponse>,
) {
  return useQuery({
    queryKey: ["humana", projectId, "deskilling", filtros],
    queryFn: () =>
      api.get<DeskillingResponse>(`/projects/${projectId}/deskilling`, {
        params: {
          clinician: filtros.clinician ?? null,
          subgroup: filtros.subgroup ?? null,
          model_version_id: filtros.modelVersionId ?? null,
          n_windows: filtros.nWindows ?? null,
        },
      }),
    enabled: projectId !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

export function useOverrides(
  projectId: number | null,
  by: "subgroup" | "phase" | "clinician",
  modelVersionId: number | null | undefined,
  opciones?: Opciones<OverridesByGroupResponse | OverridesByClinicianResponse>,
) {
  return useQuery({
    queryKey: ["humana", projectId, "overrides", by, modelVersionId ?? null],
    queryFn: () =>
      api.get<OverridesByGroupResponse | OverridesByClinicianResponse>(`/projects/${projectId}/overrides`, {
        params: { by, model_version_id: modelVersionId ?? null },
      }),
    enabled: projectId !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

export function useOverridesClinicians(
  projectId: number | null,
  modelVersionId: number | null | undefined,
  opciones?: Opciones<OverridesClinicianList>,
) {
  return useQuery({
    queryKey: ["humana", projectId, "overrides-clinicians", modelVersionId ?? null],
    queryFn: () =>
      api.get<OverridesClinicianList>(`/projects/${projectId}/overrides/clinicians`, {
        params: { model_version_id: modelVersionId ?? null },
      }),
    enabled: projectId !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

export function useOverridesMe(
  projectId: number | null,
  clinician: string | null,
  modelVersionId: number | null | undefined,
  opciones?: Opciones<OverridesMeResponse>,
) {
  return useQuery({
    queryKey: ["humana", projectId, "overrides-me", clinician, modelVersionId ?? null],
    queryFn: () =>
      api.get<OverridesMeResponse>(`/projects/${projectId}/overrides/me`, {
        params: { clinician, model_version_id: modelVersionId ?? null },
      }),
    enabled: projectId !== null && !!clinician,
    staleTime: STALE_MS,
    ...opciones,
  });
}

/**
 * `GET /projects/{id}/cross/latest`: un proyecto sin diario de
 * uso subido todavía (sin monitor cruzado, o con el monitor pero sin ninguna
 * evaluación) responde 200 con `estado: "sin_datos"`, no 404; es el estado
 * normal de un proyecto sin capa humana, no un fallo, y el navegador ya no
 * lo apunta como error de consola. El llamador distingue
 * `data?.estado === "sin_datos"` para pintarlo como «sin datos». Se conserva
 * `retry: false` porque un fallo real de este endpoint no mejora reintentando
 * y así no duplica la entrada de red fallida en consola (el `retry: 1` por
 * defecto de `App.tsx`).
 */
export function useCrossLatest(projectId: number | null, opciones?: Opciones<CrossLatest>) {
  return useQuery({
    queryKey: ["humana", projectId, "cross-latest"],
    queryFn: () => api.get<CrossLatest>(`/projects/${projectId}/cross/latest`),
    enabled: projectId !== null,
    staleTime: STALE_MS,
    retry: false,
    ...opciones,
  });
}

export function useOutcomes(
  projectId: number | null,
  metricKey: string | null | undefined,
  opciones?: Opciones<OutcomesListResponse>,
) {
  return useQuery({
    queryKey: ["humana", projectId, "outcomes", metricKey ?? null],
    queryFn: () =>
      api.get<OutcomesListResponse>(`/projects/${projectId}/outcomes`, {
        params: { metric_key: metricKey ?? null },
      }),
    enabled: projectId !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}
