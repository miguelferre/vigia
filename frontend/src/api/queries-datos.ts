/**
 * `useBatches` y `useDatasets`, partidos de `queries.ts` para no superar 9 KB
 * Ningún nombre exportado cambia al mover.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { LIMITE_MAX, qk, STALE_MS, type Opciones } from "./queries";
import type { Batch, Dataset, ListResponse, Paginacion } from "./types";

/** Lotes del proyecto. Sin `limit` explícito se piden 500, el tope de la API. */
export function useBatches(
  id: number | null,
  p?: Paginacion,
  opciones?: Opciones<ListResponse<Batch>>,
) {
  return useQuery({
    queryKey: qk.batches(id, p),
    queryFn: () =>
      api.get<ListResponse<Batch>>(`/projects/${id}/batches`, {
        params: { offset: p?.offset ?? null, limit: p?.limit ?? LIMITE_MAX },
      }),
    enabled: id !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

export function useDatasets(
  id: number | null,
  p?: Paginacion,
  opciones?: Opciones<ListResponse<Dataset>>,
) {
  return useQuery({
    queryKey: qk.datasets(id, p),
    queryFn: () =>
      api.get<ListResponse<Dataset>>(`/projects/${id}/datasets`, {
        params: { offset: p?.offset ?? null, limit: p?.limit ?? null },
      }),
    enabled: id !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}
