/**
 * Cabecera común de las tres tarjetas del bloque «Distribuciones»:
 * título con ⓘ, subtítulo y estado con
 * glifo y palabra, mismo patrón que `TarjetaMonitor.tsx` (líneas
 * 69-83).
 */

import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { colorEstado, InfoTooltip } from "@/components/vigia";
import { GLIFO_ESTADO } from "@/lib/iconos";
import { ETIQUETA_ESTADO, metricLabel } from "@/lib/metrics";
import { textoComoSeLee, textoQueMide } from "@/components/vigia/AyudaTexto";
import type { AyudaMetrica } from "@/api/queries-contenido";
import type { EstadoMotor } from "@/api/types";

export interface TarjetaDistribucionProps {
  /** Ancla de la tarjeta (`ranking-deriva` en variables: destino de la escena 8 del onboarding). */
  id?: string;
  titulo: string;
  subtitulo: string;
  metricKey: string;
  estado: EstadoMotor | null | undefined;
  ayuda: AyudaMetrica | undefined;
  children: ReactNode;
}

export function TarjetaDistribucion({ id, titulo, subtitulo, metricKey, estado, ayuda, children }: TarjetaDistribucionProps) {
  const valorEstado: EstadoMotor = estado ?? "sin_datos";
  const Glifo = GLIFO_ESTADO[valorEstado];
  return (
    <Card id={id} className="flex scroll-mt-20 flex-col gap-2 px-4 pt-3.5 pb-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <span className="inline-flex items-center gap-1.5 text-[13px] font-semibold">
            {titulo}
            <InfoTooltip
              titulo={metricLabel(metricKey)}
              queMide={textoQueMide(ayuda)}
              comoSeLee={textoComoSeLee(ayuda)}
              formula={ayuda?.formula}
            />
          </span>
          <span className="text-xs text-muted-foreground">{subtitulo}</span>
        </div>
        <span
          className="inline-flex items-center gap-1.5 text-xs font-semibold whitespace-nowrap"
          style={{ color: colorEstado(valorEstado, "texto") }}
        >
          <Glifo className="size-4" strokeWidth={1.5} aria-hidden="true" />
          {ETIQUETA_ESTADO[valorEstado]}
        </span>
      </div>
      {children}
    </Card>
  );
}

export default TarjetaDistribucion;
