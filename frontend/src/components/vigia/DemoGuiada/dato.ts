/**
 * El dato real de un paso de la demo guiada: el paso
 * declara `metric_key`/`esperado`/`umbral`/`estado` y aquí se resuelve el
 * valor que de verdad salió de la reproducción, mismo principio que
 * `matches_expected` en `core/engine.py`. Heredero de
 * `pages/onboarding/dato.ts`, adaptado a `PasoDemo`.
 *
 * `fase_minima` cuenta fases desde 1 (1 a 5 = las cinco semanas de línea
 * base; 6 = casos nuevos; 7 = tras las medidas) y `run.result`
 * crece en orden de reproducción, así que el lote del paso es
 * `result[fase_minima - 1]` (`result[4]` es la semana 5, `result[5]` el
 * lote de casos nuevos). De ahí:
 * - casi todas las métricas son una `Measurement` global de la evaluación de
 *   ese lote (`GET /projects/{id}/evaluations` filtrado, luego el detalle);
 * - `composicion_grupo_supervisado_pct` no es medida del motor: sale de
 *   `GET /batches/{id}/composition` (grupo 0 = supervisado);
 * - si el detalle no trae la medida (el monitor `explain` no persiste
 *   `Measurement` para la línea base), el estado cae al `states` del resumen
 *   de fase, que es lo mismo que compara `matches_expected`.
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { qk, useEvaluations } from "@/api/queries";
import type { PasoDemo } from "@/api/queries-contenido";
import type { BatchComposition, EstadoMotor, MonitorType } from "@/api/types";
import { useEvaluationDetail } from "@/pages/monitores/usarEvaluacion";
import type { FaseResumen } from "@/pages/demo/tipos";

/** A qué monitor pertenece cada `metric_key` que puede traer un paso. */
export const MONITOR_DE_METRICA: Readonly<Record<string, MonitorType>> = {
  accuracy: "quality",
  false_negative_rate_difference: "fairness",
  fairness_value: "fairness",
  confidence_drift_score: "drift",
  feature_drift_score: "drift",
  explain_stability_ndcg: "explain",
};

/**
 * Misma regla de equivalencia que `matches_expected` en `core/engine.py`
 * (el motor, no se reinventa aquí): con igualdad estricta el paso 4 saldría
 * «no coincide» cuando el producto acierta.
 * - esperado "ok": coinciden "ok" y "aviso" (banda del 10 % sobre el umbral).
 * - esperado "alerta" en equidad: coinciden "alerta" e "inestable"
 *   (la ventana de últimos N puede caer en el borde).
 * - resto: igualdad estricta.
 */
export function coincideConEsperado(metricKey: string, esperado: EstadoMotor, real: EstadoMotor): boolean {
  if (esperado === "ok") return real === "ok" || real === "aviso";
  if (MONITOR_DE_METRICA[metricKey] === "fairness" && esperado === "alerta") {
    return real === "alerta" || real === "inestable";
  }
  return real === esperado;
}

export const CLAVE_COMPOSICION = "composicion_grupo_supervisado_pct";
/** 0 es el grupo supervisado, 1 el de referencia. */
export const GRUPO_SUPERVISADO = 0;

/** El resumen de la fase que el paso necesita, o `null` si aún no se ha reproducido. */
export function resumenDeFase(resultado: FaseResumen[], paso: PasoDemo | null): FaseResumen | null {
  if (!paso || paso.fase_minima < 1) return null;
  const r = resultado[paso.fase_minima - 1];
  return r && typeof r.batch_id === "number" ? r : null;
}

export interface DatoResuelto {
  cargando: boolean;
  valorReal: number | null;
  estadoReal: EstadoMotor | null;
  composicion: BatchComposition | null;
  batchId: number | null;
}

const VACIO: DatoResuelto = { cargando: false, valorReal: null, estadoReal: null, composicion: null, batchId: null };

/** Resuelve el dato real del paso activo. Sin proyecto o sin fase alcanzada, no pide nada. */
export function useDatoPaso(projectId: number | null, resultado: FaseResumen[], paso: PasoDemo | null): DatoResuelto {
  const resumen = resumenDeFase(resultado, paso);
  const batchId = resumen?.batch_id ?? null;
  const metricKey = paso?.dato.metric_key ?? null;
  const esComposicion = metricKey === CLAVE_COMPOSICION;
  const monitorType = metricKey ? (MONITOR_DE_METRICA[metricKey] ?? null) : null;

  const puedeEvaluacion = !esComposicion && monitorType !== null && batchId !== null && projectId !== null;
  const evaluacionesQ = useEvaluations(puedeEvaluacion ? projectId : null, {
    monitor_type: monitorType,
    batch_id: batchId,
  });
  const evaluacionId = evaluacionesQ.data?.items[0]?.id ?? null;
  const detalleQ = useEvaluationDetail(evaluacionId);

  const composicionQ = useQuery({
    queryKey: qk.composition(esComposicion && batchId !== null ? batchId : null),
    queryFn: () => api.get<BatchComposition>(`/batches/${batchId}/composition`),
    enabled: esComposicion && batchId !== null,
    staleTime: 30_000,
  });

  const estadoResumen = monitorType ? (resumen?.states?.[monitorType] ?? null) : null;

  return useMemo(() => {
    if (batchId === null || metricKey === null) return { ...VACIO, batchId };

    if (esComposicion) {
      const grupo = composicionQ.data?.groups.find((g) => g.group_code === GRUPO_SUPERVISADO);
      const total = composicionQ.data?.total.n ?? 0;
      return {
        cargando: composicionQ.isLoading,
        valorReal: grupo && total > 0 ? (grupo.n / total) * 100 : null,
        estadoReal: null,
        composicion: composicionQ.data ?? null,
        batchId,
      };
    }

    const medida = detalleQ.data?.measurements.find((m) => m.metric_key === metricKey) ?? null;
    return {
      cargando: evaluacionesQ.isLoading || (evaluacionId !== null && detalleQ.isLoading),
      valorReal: medida?.value ?? null,
      estadoReal: medida?.state ?? estadoResumen,
      composicion: null,
      batchId,
    };
  }, [
    batchId,
    metricKey,
    esComposicion,
    composicionQ.data,
    composicionQ.isLoading,
    detalleQ.data,
    detalleQ.isLoading,
    evaluacionId,
    evaluacionesQ.isLoading,
    estadoResumen,
  ]);
}
