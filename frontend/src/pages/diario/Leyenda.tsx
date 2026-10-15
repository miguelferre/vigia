/**
 * Leyenda compacta de los cuatro carriles del diario, bajo los filtros.
 * Un punto con el color
 * del carril, su nombre y una descripción corta de qué entra en él.
 * La forma `compacta` murió con la línea de tiempo.
 */

import { CARRILES, TOKEN_CARRIL } from "./etiquetas";
import { DESCRIPCION_CARRIL, ETIQUETA_CARRIL } from "@/lib/metrics";
import { TITULO_LEYENDA } from "./diario-textos";

export function Leyenda() {
  return (
    <div
      className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted-foreground"
      aria-label="Leyenda de carriles del diario"
    >
      <span className="w-full font-semibold text-foreground">{TITULO_LEYENDA}</span>
      {CARRILES.map((carril) => (
        <div key={carril} className="flex items-center gap-1.5" title={DESCRIPCION_CARRIL[carril]}>
          <span
            className="size-2 shrink-0 rounded-full"
            style={{ backgroundColor: `var(${TOKEN_CARRIL[carril]})` }}
            aria-hidden="true"
          />
          <span className="font-semibold text-foreground">{ETIQUETA_CARRIL[carril]}</span>
          <span>{DESCRIPCION_CARRIL[carril]}</span>
        </div>
      ))}
    </div>
  );
}
