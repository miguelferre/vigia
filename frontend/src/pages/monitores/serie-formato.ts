/**
 * Formato de los valores de una serie ampliada: en regresión el
 * valor, el tooltip y los límites llevan la unidad del proyecto y el eje Y es
 * libre (nunca 0 a 1). En binario y multiclase devuelve `undefined` y la
 * serie sale como siempre. Partido de `serie.tsx` por tamaño.
 */

import { useFormatoMetrica } from "@/components/vigia/useFormatoMetrica";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { esMedidaEnUnidad } from "@/lib/metrics";

import { textoUnidadMedida } from "./regresion-datos";

export interface FormatoSerie {
  formatoValor: ((valor: number | null) => string) | undefined;
  formatoLimite: ((valor: number) => string) | undefined;
  /** «Eje vertical en horas por semana.» solo en una medida en la unidad. */
  ejeEnUnidad: string | null;
}

export function useFormatoSerie(metrica: string): FormatoSerie {
  const { caps } = useTipoTarea();
  const { formato, unidad } = useFormatoMetrica();
  if (caps?.metricas !== "regresion") return { formatoValor: undefined, formatoLimite: undefined, ejeEnUnidad: null };
  return {
    formatoValor: (v) => formato(metrica, v),
    formatoLimite: (v) => formato(metrica, v),
    ejeEnUnidad: unidad !== null && esMedidaEnUnidad(metrica) ? textoUnidadMedida(metrica, unidad) : null,
  };
}
