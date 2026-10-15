/**
 * Cerrar una alerta y la acción en lote de `alertas/index.tsx`:
 * el estado de qué diálogo está abierto junto con su propia mutación, para
 * que `index.tsx` solo decida cuándo abrirlos. Aparte para que ese fichero
 * quede por debajo de 9 KB.
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { qk } from "@/api/queries";
import type { ActorBody, Alert, Schemas } from "@/api/types";

export function useAccionesAlertas(
  projectId: number | null,
  seleccion: ReadonlySet<number>,
  setSeleccion: (v: ReadonlySet<number>) => void,
) {
  const queryClient = useQueryClient();
  const [cerrarIndividual, setCerrarIndividual] = useState<Alert | null>(null);
  const [accionLote, setAccionLote] = useState<"acknowledge" | "close" | null>(null);

  const cerrarIndividualMut = useMutation({
    mutationFn: (cuerpo: ActorBody) => api.post<Alert>(`/alerts/${cerrarIndividual?.id}/close`, cuerpo),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["alerts"] });
      await queryClient.invalidateQueries({ queryKey: qk.alert(cerrarIndividual?.id ?? null) });
      toast.success("Alerta cerrada.");
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  const bulkMut = useMutation({
    mutationFn: (cuerpo: ActorBody) =>
      api.post<Schemas["AlertsBulkResult"]>(`/projects/${projectId}/alerts/bulk`, {
        alert_ids: Array.from(seleccion),
        action: accionLote as "acknowledge" | "close",
        ...cuerpo,
      } satisfies Schemas["AlertsBulkBody"]),
    onSuccess: async (resultado) => {
      await queryClient.invalidateQueries({ queryKey: ["alerts"] });
      setSeleccion(new Set());
      if (resultado.skipped.length === 0) {
        toast.success(`${resultado.applied} alertas actualizadas.`);
      } else {
        toast.warning(
          `${resultado.applied} aplicadas, ${resultado.skipped.length} saltadas: ${resultado.skipped
            .map((s) => `#${s.alert_id} (${s.reason})`)
            .join(", ")}`,
        );
      }
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  return { cerrarIndividual, setCerrarIndividual, accionLote, setAccionLote, cerrarIndividualMut, bulkMut };
}

export default useAccionesAlertas;
