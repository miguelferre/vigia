/**
 * Métrica principal de cada monitor en la tarjeta de `/modelos/:id` y texto
 * de sus umbrales. Decide con `caps`: clasificación mira
 * la matriz (`2x2` exactitud, `kxk` F1 macro) y regresión mira el monitor
 * (calidad: MAE; deriva: puntuación de deriva de la predicción; equidad:
 * diferencia de MAE entre grupos). Aparte de `monitor-tarjeta.tsx` por el
 * límite de 9 KB.
 */

import type { MonitorType } from "@/api/types";
import { esMedidaEnUnidad, formatoMetrica } from "@/lib/metrics";
import type { CapacidadesTarea } from "@/lib/tipo-tarea";
import type { ThresholdEntry } from "@/pages/monitores/tipos";
import { textoUmbralConfigurado } from "@/pages/monitores/umbrales-efectivos";

function principalDeRegresion(tipo: MonitorType): string | null {
  switch (tipo) {
    case "quality":
      return "mean_absolute_error";
    case "drift":
      return "prediction_drift_score";
    case "fairness":
      return "mean_absolute_error_difference";
    default:
      return null;
  }
}

/** Clave de la métrica principal del monitor, o `null` si la tarjeta no marca ninguna. */
export function metricaPrincipal(
  tipo: MonitorType,
  caps: CapacidadesTarea,
  principalDelBackend: string | undefined,
): string | null {
  switch (caps.metricas) {
    case "clasificacion":
      return tipo === "quality" ? (principalDelBackend ?? (caps.matriz === "kxk" ? "f1_measure" : "accuracy")) : null;
    case "regresion":
      return tipo === "quality" ? (principalDelBackend ?? principalDeRegresion(tipo)) : principalDeRegresion(tipo);
    default: {
      const _exhaustivo: never = caps.metricas;
      throw new Error(`familia de métricas no reconocida: ${String(_exhaustivo)}`);
    }
  }
}

/** En regresión, la principal va primero para que quepa en las líneas que enseña la tarjeta. */
export function ordenarPorPrincipal(umbrales: ThresholdEntry[], principal: string | null, caps: CapacidadesTarea): ThresholdEntry[] {
  if (caps.metricas !== "regresion" || principal === null) return umbrales;
  return [...umbrales].sort((a, b) => Number(b.metric_key === principal) - Number(a.metric_key === principal));
}

/** «máximo 5,7 horas por semana» para una medida de error de regresión; el resto, el texto de siempre. */
export function textoUmbral(u: ThresholdEntry, unidad: string | null | undefined): string {
  if (unidad === undefined || !esMedidaEnUnidad(u.metric_key) || u.relativo_a) return textoUmbralConfigurado(u);
  return `${u.kind === "lower_limit" ? "mínimo" : "máximo"} ${formatoMetrica(u.metric_key, u.value, unidad)}`;
}
