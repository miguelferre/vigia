/**
 * Indicador de desbordamiento horizontal del violín «lote a lote»: `svgAncho` de `violin-svg.tsx` crece con el número de lotes sin
 * tope, y el `overflow-x-auto` no avisaba de que había más lotes fuera de
 * vista. Degradado y flecha a cada lado, solo cuando ese lado todavía
 * esconde contenido; partido a fichero propio para que `violin-svg.tsx`
 * no pase de 9 KB.
 */

import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";

export interface ViolinDesbordamientoProps {
  desborda: boolean;
  alInicio: boolean;
  alFinal: boolean;
}

export function ViolinDesbordamiento({ desborda, alInicio, alFinal }: ViolinDesbordamientoProps) {
  return (
    <>
      {desborda && !alInicio ? (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 left-0 flex w-8 items-center justify-start"
          style={{ background: "linear-gradient(to right, var(--card), transparent)" }}
        >
          <ChevronLeftIcon className="size-4 text-muted-foreground" strokeWidth={1.5} />
        </div>
      ) : null}
      {desborda && !alFinal ? (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 right-0 flex w-8 items-center justify-end"
          style={{ background: "linear-gradient(to left, var(--card), transparent)" }}
        >
          <ChevronRightIcon className="size-4 text-muted-foreground" strokeWidth={1.5} />
        </div>
      ) : null}
    </>
  );
}

export default ViolinDesbordamiento;
