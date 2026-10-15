/**
 * Rango de `row_seq` válido de un lote para la explicación local. `row_seq` es el seq global del
 * registro (no un índice 0..n dentro del lote): se pide el primer registro del lote para poder
 * mostrar el rango válido y sugerir un valor que no dé 404.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { ListResponse, Record_ } from "@/api/types";

export function useRangoSeq(batchId: number | null): { min: number; max: number } | null {
  const primerRegistro = useQuery({
    queryKey: qk.records(batchId, { limit: 1 }),
    queryFn: () => api.get<ListResponse<Record_>>(`/batches/${batchId}/records?limit=1`),
    enabled: batchId !== null,
    staleTime: 60_000,
  });
  return batchId !== null && primerRegistro.data && primerRegistro.data.items.length > 0
    ? {
        min: primerRegistro.data.items[0].seq,
        max: primerRegistro.data.items[0].seq + primerRegistro.data.total - 1,
      }
    : null;
}
