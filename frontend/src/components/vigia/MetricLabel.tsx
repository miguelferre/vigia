/**
 * Etiqueta en español de una métrica, con su clave técnica en el `title`.
 * El diccionario es copia del backend (`src/lib/metrics.ts`).
 */

import { etiquetaConRango } from "@/lib/formato-metrica";
import { metricLabelPorTipo } from "@/lib/metrics";
import { cn } from "@/lib/utils";

export interface MetricLabelProps {
  metrica: string;
  /** Añade el código de grupo entre paréntesis cuando la métrica es por grupo. */
  grupo?: string | null;
  /** Muestra también la clave técnica en pequeño. */
  conClave?: boolean;
  /** Tipo de tarea: en multiclase, las claves de calidad llevan «macro» en la etiqueta. */
  tipo?: string | null;
  /** Regresión con rango favorable: las medidas de pertenencia lo dicen. */
  conRango?: boolean;
  className?: string;
}

export function MetricLabel({ metrica, grupo, conClave = false, tipo, conRango, className }: MetricLabelProps) {
  const etiqueta = etiquetaConRango(metricLabelPorTipo(metrica, tipo), metrica, conRango);
  return (
    <span className={cn("inline-flex items-baseline gap-1.5", className)} title={metrica}>
      <span>
        {etiqueta}
        {grupo ? ` (grupo ${grupo})` : ""}
      </span>
      {conClave && etiqueta !== metrica ? (
        <code className="text-xs text-muted-foreground">{metrica}</code>
      ) : null}
    </span>
  );
}
