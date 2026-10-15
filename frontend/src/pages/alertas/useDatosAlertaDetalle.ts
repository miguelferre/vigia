/**
 * Datos y mutación de `detalle.tsx` (separado para bajar de
 * 9 KB): la alerta, su última evaluación, su lote (solo para el chip «Orden
 * manipulado»: H1c da `batch_id`/`batch_seq`/`batch_phase_label`, pero no
 * `orden_manipulado`; mismo patrón que `pages/datos/index.tsx`), el
 * `correlation_id` más antiguo del diario y el cierre con motivo.
 */

import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { qk, useEvents } from "@/api/queries";
import type { ActorBody, Alert, AlertDetail, Batch, EvaluationDetail } from "@/api/types";

export function useDatosAlertaDetalle(alertId: number) {
  const queryClient = useQueryClient();
  const valido = Number.isFinite(alertId);

  const alerta = useQuery({
    queryKey: qk.alert(alertId),
    queryFn: () => api.get<AlertDetail>(`/alerts/${alertId}`),
    enabled: valido,
  });

  const evaluacionId = alerta.data?.last_evaluation_id ?? null;
  const evaluacion = useQuery({
    queryKey: qk.evaluation(evaluacionId),
    queryFn: () => api.get<EvaluationDetail>(`/evaluations/${evaluacionId}`),
    enabled: evaluacionId !== null,
  });

  const batchId = alerta.data?.batch_id ?? null;
  const lote = useQuery({
    queryKey: qk.batch(batchId),
    queryFn: () => api.get<Batch>(`/batches/${batchId}`),
    enabled: batchId !== null,
  });

  const eventos = useEvents({ object_type: "alert", object_id: alertId, limit: 100 }, { enabled: valido });
  const correlationId = useMemo(() => {
    const items = eventos.data?.items ?? [];
    const conCorrelacion = items.filter((e) => e.correlation_id);
    if (conCorrelacion.length === 0) return null;
    return conCorrelacion.reduce((a, b) => (a.ts < b.ts ? a : b)).correlation_id;
  }, [eventos.data]);

  const cerrar = useMutation({
    mutationFn: (cuerpo: ActorBody) => api.post<Alert>(`/alerts/${alertId}/close`, cuerpo),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: qk.alert(alertId) });
      await queryClient.invalidateQueries({ queryKey: ["alerts"] });
      toast.success("Alerta cerrada.");
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  return { alerta, evaluacion, lote, correlationId, cerrar };
}
