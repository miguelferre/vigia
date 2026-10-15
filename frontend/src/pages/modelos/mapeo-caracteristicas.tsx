/**
 * Lista de columnas de características del formulario de mapeo (partido de
 * `mapeo-campos.tsx` para quedar por debajo de 9 KB).
 */

import { Label } from "@/components/ui/label";
import { AYUDA_MAPEO } from "./etiquetas";
import { Ayuda } from "./mapeo-controles";

interface Props {
  columnas: string[];
  features: Set<string>;
  alternar: (col: string) => void;
}

export function CaracteristicasMapeo({ columnas, features, alternar }: Props) {
  // Variables que la plantilla nombra y el fichero no trae: se listan, marcadas, para poder quitarlas.
  const variablesAusentes = Array.from(features).filter((c) => !columnas.includes(c));
  return (
    <div className="flex flex-col gap-1.5">
      <Label>Columnas de características ({features.size} elegidas)</Label>
      <Ayuda id="mc-caracteristicas-ayuda">{AYUDA_MAPEO.caracteristicas}</Ayuda>
      <div className="flex max-h-40 flex-col gap-1 overflow-y-auto rounded-md border border-border p-2 text-sm">
        {[...columnas, ...variablesAusentes].map((col) => (
          <label key={col} className="flex items-center gap-2">
            <input type="checkbox" checked={features.has(col)} onChange={() => alternar(col)} />
            {col}
            {variablesAusentes.includes(col) ? (
              <span className="text-xs text-destructive">(no está en el fichero)</span>
            ) : null}
          </label>
        ))}
      </div>
    </div>
  );
}
