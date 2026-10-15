/**
 * Consultas de la matriz de riesgos. Claves propias, con raíz `"risks"`, que
 * `RAICES_POR_OBJETO.risk` (`api/queries.ts`)
 * invalida por prefijo tras `riesgo.creado`, `riesgo.movido`,
 * `riesgo.en_seguimiento` y `riesgo.cerrado`.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { STALE_MS, type Opciones } from "./queries";
import type { Risk, RiskMovementsListResponse, RisksListResponse } from "./types";

export interface FiltrosRiesgos {
  /** Coma-separado, mismo patrón que `list_alerts` (`status=abierto,en_seguimiento`). */
  status?: string | null;
  impact?: number | null;
  probability?: number | null;
  limit?: number;
}

export const qkRiesgos = {
  list: (projectId: number | null, f: FiltrosRiesgos) => ["risks", projectId, f] as const,
  movimientosRiesgo: (riskId: number | null) => ["risks", "movimientos", "riesgo", riskId] as const,
  movimientosProyecto: (projectId: number | null, days: number) =>
    ["risks", "movimientos", "proyecto", projectId, days] as const,
};

export function useRisks(
  projectId: number | null,
  filtros: FiltrosRiesgos = {},
  opciones?: Opciones<RisksListResponse>,
) {
  return useQuery({
    queryKey: qkRiesgos.list(projectId, filtros),
    queryFn: () =>
      api.get<RisksListResponse>(`/projects/${projectId}/risks`, {
        params: {
          status: filtros.status ?? null,
          impact: filtros.impact ?? null,
          probability: filtros.probability ?? null,
          limit: filtros.limit ?? 500,
        },
      }),
    enabled: projectId !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

/** Busca un riesgo por id dentro de una lista ya cargada (sin `GET` propio: no existe). */
export function riesgoPorId(items: Risk[] | undefined, id: number | null): Risk | null {
  if (!items || id === null) return null;
  return items.find((r) => r.id === id) ?? null;
}

export function useRiskMovements(riskId: number | null, opciones?: Opciones<RiskMovementsListResponse>) {
  return useQuery({
    queryKey: qkRiesgos.movimientosRiesgo(riskId),
    queryFn: () => api.get<RiskMovementsListResponse>(`/risks/${riskId}/movements`),
    enabled: riskId !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

export function useProjectRiskMovements(
  projectId: number | null,
  days: number,
  opciones?: Opciones<RiskMovementsListResponse>,
) {
  return useQuery({
    queryKey: qkRiesgos.movimientosProyecto(projectId, days),
    queryFn: () =>
      api.get<RiskMovementsListResponse>(`/projects/${projectId}/risks/movements`, {
        params: { days },
      }),
    enabled: projectId !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}
