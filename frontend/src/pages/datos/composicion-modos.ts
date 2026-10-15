/** Tipos y configuración de la composición de `/datos/:batch` (partidos de `composicion.tsx` por tamaño). */

import type { ChartConfig } from "@/components/ui/chart";

export interface FilaComposicion {
  codigo: number;
  grupo: string;
  n: number;
  /** `pred_favorable_n`: recuento de favorables, primer segmento de la barra. */
  favorable: number;
  predRate: number | null;
  labelRate: number | null;
  /** `n - favorable`: segundo segmento, gris. */
  resto: number;
}

export const CONFIG_COMPOSICION: ChartConfig = {
  favorable: { label: "Favorables", color: "var(--chart-1)" },
  resto: { label: "Resto", color: "var(--line-2)" },
};

/** Con rango favorable «favorable» es «dentro del rango»; sin él no hay favorables. */
export type ModoComposicion = "favorable" | "rango" | "sin_rango";
