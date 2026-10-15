/**
 * Etiqueta de métrica según el tipo de tarea del proyecto: en
 * multiclase las claves de calidad llevan el promedio macro en el nombre.
 * Sin tipo conocido o en binario, `metricLabel` de siempre.
 */

import { etiquetaConRango } from "@/lib/formato-metrica";
import { metricLabelPorTipo } from "@/lib/metrics";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import type { CapacidadesTarea } from "@/lib/tipo-tarea";

import { EQUIDAD_ERROR, TITULARES_REGRESION } from "./regresion-datos";

export function useEtiquetaMetrica(projectId?: number | null): (clave: string) => string {
  const { tipo, rangos } = useTipoTarea(projectId);
  return (clave) => etiquetaConRango(metricLabelPorTipo(clave, tipo), clave, rangos.length > 0);
}

/** Métricas de calidad que van arriba en multiclase: los tres titulares. */
export const TITULARES_MULTICLASE = ["accuracy", "f1_measure", "area_under_roc"] as const;

/** Claves que van arriba en una calidad con titulares propios: multiclase o regresión. */
function titularesDeCalidad(caps: CapacidadesTarea): readonly string[] {
  switch (caps.metricas) {
    case "regresion":
      return TITULARES_REGRESION;
    case "clasificacion":
      return caps.matriz === "kxk" ? TITULARES_MULTICLASE : [];
    default: {
      const _exhaustivo: never = caps.metricas;
      throw new Error(`familia de métricas no reconocida: ${String(_exhaustivo)}`);
    }
  }
}

/**
 * Con los titulares primero y el resto en su orden; sin cambio en binario.
 * En la equidad de regresión van primero las tres medidas del error por grupo.
 * Con `caps` sin cargar, el orden de entrada.
 */
export function ordenarMetricas(metricas: string[], caps: CapacidadesTarea | undefined, monitorType: string): string[] {
  if (caps === undefined) return metricas;
  const primeras: readonly string[] =
    monitorType === "quality"
      ? titularesDeCalidad(caps)
      : monitorType === "fairness" && caps.metricas === "regresion"
        ? EQUIDAD_ERROR
        : [];
  if (primeras.length === 0) return metricas;
  const titulares = primeras.filter((t) => metricas.includes(t));
  return [...titulares, ...metricas.filter((m) => !titulares.includes(m))];
}
