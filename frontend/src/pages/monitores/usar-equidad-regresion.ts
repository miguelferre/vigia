/**
 * Evaluación de equidad de una regresión para las pantallas que enseñan el
 * error por grupo: la tabla de MAE y sesgo de Calidad y los
 * gráficos de Equidad. Elige la evaluación de equidad del mismo lote que la
 * de calidad (o la última) y pone nombre a los grupos con el `group_context`
 * del monitor de equidad, nunca «unpriv»/«priv».
 */

import { useMemo } from "react";

import { useEvaluations, useMonitors } from "@/api/queries";
import { useGuionDemo } from "@/api/queries-contenido";
import type { EvaluationDetail } from "@/api/types";
import { nombreReferencia, nombreSupervisado } from "@/components/vigia/contexto-grupos";
import { groupContextDeMonitor } from "./contexto-monitor";
import { useEvaluationDetail } from "./usarEvaluacion";
import type { GrupoRegresion } from "./regresion-equidad-datos";

export interface EquidadRegresion {
  evaluationId: number | null;
  detalle: EvaluationDetail | undefined;
  cargando: boolean;
  error: unknown;
  /** Nombre visible de cada grupo («tipo de discapacidad = paralisis_cerebral»). */
  nombres: Record<GrupoRegresion, string>;
}

/**
 * `batchId`: si hay una evaluación de equidad de ese lote, esa; si no, la
 * más reciente. Sin proyecto o sin evaluación de equidad, `evaluationId` es
 * `null`.
 */
export function useEquidadRegresion(projectId: number, batchId?: number | null): EquidadRegresion {
  const evaluacionesQ = useEvaluations(projectId, { monitor_type: "fairness", limit: 500 });
  const monitoresQ = useMonitors(projectId);
  const dominio = useGuionDemo().data?.dominio;
  const evaluationId = useMemo(() => {
    const todas = [...(evaluacionesQ.data?.items ?? [])].sort((a, b) => (b.id ?? 0) - (a.id ?? 0));
    const delLote = batchId == null ? undefined : todas.find((e) => e.batch_id === batchId);
    return (delLote ?? todas[0])?.id ?? null;
  }, [evaluacionesQ.data, batchId]);
  const detalleQ = useEvaluationDetail(evaluationId);
  const monitor = monitoresQ.data?.items.find((m) => m.type === "fairness");
  const ctx = groupContextDeMonitor(monitor);
  return {
    evaluationId,
    detalle: detalleQ.data,
    cargando: evaluacionesQ.isLoading || detalleQ.isLoading,
    error: evaluacionesQ.error ?? detalleQ.error,
    nombres: { unpriv: nombreSupervisado(ctx, dominio), priv: nombreReferencia(ctx, dominio) },
  };
}
