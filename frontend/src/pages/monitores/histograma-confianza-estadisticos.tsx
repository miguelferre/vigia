/**
 * Fila de estadísticos (PSI, KS, Jensen-Shannon, n) del histograma de
 * confianza: extraída de `histograma-confianza.tsx` para
 * no pasar de los 9 KB por fichero, mismo motivo que
 * `selector-clase-confianza.tsx`. Sin lectura propia de
 * `result.details.confidence`: recibe los valores ya extraídos.
 */

import { AYUDA_ESTADISTICO, CabeceraEstadistico, type CabeceraEstadisticoProps } from "./deriva-estadisticos";
import { formatoNumero } from "@/lib/metrics";

export interface FilaEstadisticosConfianzaProps {
  psi: number | null;
  ksStat: number | null;
  ksP: number | null;
  jsDistance: number | null;
  nBase: number;
  nActual: number;
}

// La ayuda del estadístico dice «JS»; en la línea de cifras se escribe el nombre entero, como en el lienzo.
const AYUDA_JS: CabeceraEstadisticoProps = { ...AYUDA_ESTADISTICO.js, titulo: "Jensen-Shannon" };

export function FilaEstadisticosConfianza({ psi, ksStat, ksP, jsDistance, nBase, nActual }: FilaEstadisticosConfianzaProps) {
  return (
    <div className="flex flex-wrap items-center gap-3.5 text-xs text-muted-foreground tabular-nums">
      <span className="inline-flex items-center gap-1">
        <CabeceraEstadistico {...AYUDA_ESTADISTICO.psi} />
        <b className="font-semibold text-foreground">{formatoNumero(psi, 2)}</b>
      </span>
      <span className="inline-flex items-center gap-1">
        <CabeceraEstadistico {...AYUDA_ESTADISTICO.ks} />
        <b className="font-semibold text-foreground">{formatoNumero(ksStat, 2)}</b> (p {formatoNumero(ksP, 3)})
      </span>
      <span className="inline-flex items-center gap-1">
        <CabeceraEstadistico {...AYUDA_JS} />
        <b className="font-semibold text-foreground">{formatoNumero(jsDistance, 2)}</b>
      </span>
      <span>
        n base <b className="font-semibold text-foreground">{formatoNumero(nBase, 0)}</b>
      </span>
      <span>
        n lote <b className="font-semibold text-foreground">{formatoNumero(nActual, 0)}</b>
      </span>
    </div>
  );
}

export default FilaEstadisticosConfianza;
