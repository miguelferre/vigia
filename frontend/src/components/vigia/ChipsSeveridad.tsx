/**
 * Recuento de alertas abiertas por severidad, en chips. Pensado para la portada de `/modelos` (`alerts_open_by_severity`)
 * y para el cuadro de mando.
 *
 * La severidad se mapea a los tokens de estado como en
 * `pages/alertas/severidad.ts` (alta → alerta, media → aviso, baja →
 * inestable); no se importa ese módulo de `pages/**` desde `components/vigia`
 * (frontera entre capas), así que el mapeo se repite aquí, a propósito.
 */

import { StateBadge } from "./StateBadge";
import { cn } from "@/lib/utils";
import type { EstadoMotor } from "@/api/types";

export interface ChipsSeveridadProps {
  alta?: number;
  media?: number;
  baja?: number;
  className?: string;
}

const ESTADO_SEVERIDAD: Record<"alta" | "media" | "baja", EstadoMotor> = {
  alta: "alerta",
  media: "aviso",
  baja: "inestable",
};

const ORDEN: ReadonlyArray<"alta" | "media" | "baja"> = ["alta", "media", "baja"];

export function ChipsSeveridad({ alta = 0, media = 0, baja = 0, className }: ChipsSeveridadProps) {
  const valores: Record<"alta" | "media" | "baja", number> = { alta, media, baja };
  const activas = ORDEN.filter((clave) => valores[clave] > 0);

  if (activas.length === 0) {
    return <span className={cn("text-sm text-muted-foreground", className)}>Sin alertas</span>;
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {activas.map((clave) => (
        <span key={clave} aria-label={`${valores[clave]} alertas de severidad ${clave}`}>
          <StateBadge estado={ESTADO_SEVERIDAD[clave]} texto={String(valores[clave])} size="sm" />
        </span>
      ))}
    </div>
  );
}
