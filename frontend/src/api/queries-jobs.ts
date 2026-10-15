/**
 * `useJobs`, partido de `queries.ts` para no superar 9 KB (mismo criterio
 * que `queries-explicabilidad.ts`). Su clave (`qk.jobs`) nace en `queries.ts` con
 * las demás. Ningún nombre exportado cambia al mover.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { qk, STALE_MS, type Opciones } from "./queries";
import type { Job, ListResponse } from "./types";

export function useJobs(status?: string | null, opciones?: Opciones<ListResponse<Job>>) {
  return useQuery({
    queryKey: qk.jobs(status),
    queryFn: () =>
      api.get<ListResponse<Job>>("/jobs", { params: { status: status ?? null, limit: 50 } }),
    staleTime: STALE_MS,
    ...opciones,
  });
}
