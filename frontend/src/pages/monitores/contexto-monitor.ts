/**
 * Dos derivados de `monitor` para `index.tsx`: la métrica
 * para el cuerpo del glosario y el `group_context` del monitor.
 * Partido de `index.tsx` para no pasar de 10 KB (frontera
 * F2: piezas pequeñas por escritura).
 */

import { useMemo } from "react";

import type { Monitor } from "@/api/types";
import type { GroupContext } from "@/api/types-domain";

import { extraerUmbrales, metricasDelMonitor } from "./tipos";

/** La ampliada si hay una; si no, la primera con umbral configurado ("métrica principal"). */
export function useMetricKeyGlosario(monitor: Monitor | undefined, metricaAmpliada: string | null): string | null {
  const umbrales = useMemo(() => extraerUmbrales(monitor?.thresholds ?? null), [monitor]);
  const metricas = useMemo(() => metricasDelMonitor(umbrales), [umbrales]);
  return metricaAmpliada ?? metricas[0] ?? null;
}

/** `null` si el monitor no trae `group_context` (calidad, deriva, o equidad sin mapping). */
export function groupContextDeMonitor(monitor: Monitor | undefined): GroupContext {
  return (monitor?.group_context as GroupContext | undefined) ?? null;
}
