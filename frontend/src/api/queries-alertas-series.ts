/**
 * `useAlertsSeries`, hook de `GET /projects/{id}/alerts/series`: evolución de alertas por lote, día u hora para el
 * panel «Alertas por lote» y su tabla.
 *
 * La clave de consulta nace aquí, no en `qk` de `queries.ts`: empieza en `"alerts"` a propósito, para que la invalidación por
 * prefijo `["alerts"]` del flujo SSE (`RAICES_POR_OBJETO.alert`) la alcance
 * igual que a `qk.alerts`. `tz` no se manda: el backend usa Europe/Paris
 * por defecto.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { STALE_MS, type Opciones } from "./queries";
import type { AlertSeriesResponse, SeriesGranularity } from "./types";

export interface FiltrosSerieAlertas {
  granularity: SeriesGranularity;
  since?: string | null;
  until?: string | null;
}

export function qkAlertsSeries(id: number | null, f: FiltrosSerieAlertas) {
  return ["alerts", id, "series", f] as const;
}

export function useAlertsSeries(
  id: number | null,
  filtros: FiltrosSerieAlertas,
  opciones?: Opciones<AlertSeriesResponse>,
) {
  return useQuery({
    queryKey: qkAlertsSeries(id, filtros),
    queryFn: () =>
      api.get<AlertSeriesResponse>(`/projects/${id}/alerts/series`, {
        params: {
          granularity: filtros.granularity,
          since: filtros.since ?? null,
          until: filtros.until ?? null,
        },
      }),
    enabled: id !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}
