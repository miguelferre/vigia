/**
 * `useTimeline`, partido de `queries.ts` para no superar 9 KB.
 *
 * La API amplía `GET /projects/{id}/timeline`: `metric_key` y `group_code`
 * pasan de un único valor a listas separadas por comas (`metric_key` hasta
 * 20, vacía o de más es 422; `group_code` ausente sigue significando todos
 * los grupos), y admite `since`/`until` en ISO 8601 sobre la fecha de la
 * evaluación. `monitor_type` no cambia: sigue siendo obligatorio. La
 * respuesta sigue siendo `ListResponse<TimelinePoint>` plana.
 *
 * El hook serializa los arrays a las cadenas que espera la API, ordenándolos
 * antes para que el mismo conjunto en otro orden no genere dos entradas de
 * caché distintas.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { qk, STALE_MS, type Opciones } from "./queries";
import type { ListResponse, MonitorType, TimelineFilters, TimelinePoint } from "./types";

/** Rango de fechas ya resuelto a ISO 8601 (`lib/fechas.ts` hace la resolución). */
export interface PeriodoTimeline {
  since?: string;
  until?: string;
}

function serializarLista(valores?: string[]): string | null {
  if (!valores || valores.length === 0) return null;
  return [...valores].sort().join(",");
}

/**
 * Serie temporal de una o varias métricas (y, opcionalmente, uno o varios
 * grupos) de un monitor. Deshabilitado mientras `metricKeys` esté vacío, para
 * no lanzar una petición que la API rechazaría con 422.
 */
export function useTimeline(
  id: number | null,
  monitorType: MonitorType,
  metricKeys: string[],
  groupCodes?: string[],
  periodo?: PeriodoTimeline,
  opciones?: Opciones<ListResponse<TimelinePoint>>,
) {
  const metricKey = serializarLista(metricKeys);
  const groupCode = serializarLista(groupCodes);
  const f: TimelineFilters | undefined =
    metricKey !== null
      ? {
          monitor_type: monitorType,
          metric_key: metricKey,
          group_code: groupCode,
          since: periodo?.since ?? null,
          until: periodo?.until ?? null,
        }
      : undefined;

  return useQuery({
    queryKey: qk.timeline(id, f),
    queryFn: () => api.get<ListResponse<TimelinePoint>>(`/projects/${id}/timeline`, { params: { ...f } }),
    enabled: id !== null && metricKeys.length > 0,
    staleTime: STALE_MS,
    ...opciones,
  });
}
