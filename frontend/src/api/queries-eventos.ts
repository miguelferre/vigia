/**
 * `useEvents`, partido de `queries.ts` para no superar 9 KB (mismo criterio
 * que `queries-explicabilidad.ts`). Su clave (`qk.events`) nace en `queries.ts`
 * con las demás. Ningún nombre exportado cambia al mover.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { qk, STALE_MS, type Opciones } from "./queries";
import type { Event, EventFilters, ListResponse } from "./types";

export function useEvents(f?: EventFilters, opciones?: Opciones<ListResponse<Event>>) {
  return useQuery({
    queryKey: qk.events(f),
    queryFn: () => api.get<ListResponse<Event>>("/events", { params: { ...f } }),
    staleTime: STALE_MS,
    ...opciones,
  });
}
