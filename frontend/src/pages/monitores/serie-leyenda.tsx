/** Leyenda de los límites bajo la gráfica ampliada (partida de `serie.tsx`). */

import { formatoCorto } from "@/lib/metrics";

import { LEYENDA_CAMBIO_VERSION } from "./serie-textos";
import type { UmbralesMetrica } from "./tipos";

export function LeyendaUmbrales({
  umbral,
  hayCambioVersion,
  formatoLimite = formatoCorto,
}: {
  umbral: UmbralesMetrica;
  hayCambioVersion: boolean;
  /** Formato del límite con la unidad del proyecto; sin él, `formatoCorto`. */
  formatoLimite?: (valor: number) => string;
}) {
  if (umbral.low === null && umbral.high === null && !hayCambioVersion) return null;
  return (
    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
      {umbral.low !== null ? (
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4" style={{ background: "var(--state-warn)" }} aria-hidden="true" />
          Límite inferior ({formatoLimite(umbral.low)})
        </span>
      ) : null}
      {umbral.high !== null ? (
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4" style={{ background: "var(--state-alert)" }} aria-hidden="true" />
          Límite superior ({formatoLimite(umbral.high)})
        </span>
      ) : null}
      {hayCambioVersion ? (
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-3 w-0 border-l-[1.5px] border-dashed"
            style={{ borderColor: "var(--foreground)" }}
            aria-hidden="true"
          />
          {LEYENDA_CAMBIO_VERSION}
        </span>
      ) : null}
    </div>
  );
}
