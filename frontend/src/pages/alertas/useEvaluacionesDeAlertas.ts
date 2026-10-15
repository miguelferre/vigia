/**
 * Lote y medida de cada alerta visible de `alertas/index.tsx`, a partir de
 * las evaluaciones de sus `last_evaluation_id` (una petición por evaluación
 * distinta, no por fila). Aparte para que ese fichero quede por debajo de
 * 9 KB.
 */

import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import { api } from "@/api/client";
import { qk, STALE_MS } from "@/api/queries";
import type { Alert, Batch, EvaluationDetail } from "@/api/types";

export function useEvaluacionesDeAlertas(filasPagina: Alert[], batchItems: Batch[] | undefined) {
  const idsEvaluacion = useMemo(
    () => Array.from(new Set(filasPagina.map((a) => a.last_evaluation_id).filter((id): id is number => id !== null))),
    [filasPagina],
  );
  const evaluaciones = useQueries({
    queries: idsEvaluacion.map((id) => ({
      queryKey: qk.evaluation(id),
      queryFn: () => api.get<EvaluationDetail>(`/evaluations/${id}`),
      staleTime: STALE_MS,
    })),
  });
  const evaluacionPorId = useMemo(() => {
    const mapa = new Map<number, EvaluationDetail>();
    idsEvaluacion.forEach((id, i) => {
      const data = evaluaciones[i]?.data;
      if (data) mapa.set(id, data);
    });
    return mapa;
  }, [evaluaciones, idsEvaluacion]);
  const loteDeAlerta = useMemo(() => {
    const batchPorId = new Map((batchItems ?? []).map((b) => [b.id, b]));
    return (alerta: Alert) => {
      const ev = alerta.last_evaluation_id !== null ? evaluacionPorId.get(alerta.last_evaluation_id) : undefined;
      if (!ev || ev.batch_id === null) return null;
      return batchPorId.get(ev.batch_id) ?? null;
    };
  }, [evaluacionPorId, batchItems]);
  // Nombre del fichero del lote de origen (o del último si no hay origen):
  // el «#N» cuenta la línea base como lote 1, el fichero es lo que el usuario
  // reconoce.
  const ficheroDeAlerta = useMemo(() => {
    const batchPorId = new Map((batchItems ?? []).map((b) => [b.id, b]));
    return (alerta: Alert): string | null => {
      const id = alerta.origin_batch_id ?? alerta.batch_id;
      return id !== null ? (batchPorId.get(id)?.dataset_name ?? null) : null;
    };
  }, [batchItems]);
  const medidaDeAlerta = useMemo(
    () => (alerta: Alert) => {
      const ev = alerta.last_evaluation_id !== null ? evaluacionPorId.get(alerta.last_evaluation_id) : undefined;
      return ev?.measurements.find((m) => m.metric_key === alerta.metric_key && m.group_code === alerta.group_code);
    },
    [evaluacionPorId],
  );

  return { loteDeAlerta, medidaDeAlerta, ficheroDeAlerta };
}

export default useEvaluacionesDeAlertas;
