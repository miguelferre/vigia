/**
 * Formateador de valores de métrica con la unidad del proyecto.
 * `formatoMetrica` ya deja igual toda clave que no sea de la familia de
 * regresión (3 decimales, sin «%»), así que en binario y multiclase este hook
 * da lo de siempre.
 *
 * Sin argumento lee el proyecto de la sesión; con `projectId`, ese. Mientras
 * el proyecto carga la unidad es `null` y las medidas en la unidad salen sin
 * ella: la pantalla que depende de `caps` espera antes de dibujar valores.
 */

import { useCallback } from "react";

import { useTipoTarea } from "@/hooks/useTipoTarea";
import { formatoMetrica, formatoMetricaPartes, type PartesMetrica } from "@/lib/metrics";

export interface FormatoMetricaProyecto {
  /** `formatoMetrica(clave, valor, unidad)` con la unidad del proyecto. */
  formato: (clave: string, valor: number | null | undefined) => string;
  partes: (clave: string, valor: number | null | undefined) => PartesMetrica;
  /** Unidad de la salida (`target_unit`) o `null`. */
  unidad: string | null;
}

export function useFormatoMetrica(projectId?: number | null): FormatoMetricaProyecto {
  const { unidad } = useTipoTarea(projectId);
  const formato = useCallback(
    (clave: string, valor: number | null | undefined) => formatoMetrica(clave, valor, unidad),
    [unidad],
  );
  const partes = useCallback(
    (clave: string, valor: number | null | undefined) => formatoMetricaPartes(clave, valor, unidad),
    [unidad],
  );
  return { formato, partes, unidad };
}
