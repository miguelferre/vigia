/**
 * Origen y nota de un conjunto de umbrales cambiados a la vez:
 * con dos o más filas cambiadas, una sola nota vale para todas (la API guarda
 * la nota en cada umbral, así que el cliente la copia a cada fila cambiada).
 * Mismo selector y mismos textos que `OrigenUmbralEditor`.
 */

import type { ThresholdOrigen } from "@/api/queries-alta";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { etiquetaOrigenUmbral } from "@/pages/modelos/alta-umbrales-textos";

const ORIGENES_PROPIOS: readonly ThresholdOrigen[] = ["fabricante", "criterio_clinico", "politica_organizacion"];

export interface OrigenConjuntoUmbralesProps {
  edicion: {
    nCambiados: number;
    origenConjunto: ThresholdOrigen;
    notaConjunto: string;
    cambiarConjunto: (cambio: { origen?: ThresholdOrigen; nota?: string }) => void;
  };
  dominio?: string;
}

export function OrigenConjuntoUmbrales({ edicion, dominio }: OrigenConjuntoUmbralesProps) {
  const { nCambiados: cambiados, origenConjunto: origen, notaConjunto: nota, cambiarConjunto: onCambiar } = edicion;
  const origenValido = ORIGENES_PROPIOS.includes(origen) ? origen : "criterio_clinico";
  return (
    <div className="flex flex-col gap-1.5 rounded-md bg-muted/40 p-2" data-testid="origen-umbrales-conjunto">
      <p className="text-xs text-muted-foreground">
        Has cambiado {cambiados} umbrales: di de dónde salen. Una sola nota vale para todos y queda en el diario.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={origenValido} onValueChange={(v) => onCambiar({ origen: v as ThresholdOrigen })}>
          <SelectTrigger className="w-56" aria-label="Origen de los umbrales cambiados">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ORIGENES_PROPIOS.map((o) => (
              <SelectItem key={o} value={o}>
                {etiquetaOrigenUmbral(o, dominio)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          className="min-w-48 flex-1"
          placeholder="Nota para todos (obligatoria)"
          aria-label="Nota de los umbrales cambiados"
          value={nota}
          onChange={(e) => onCambiar({ nota: e.target.value })}
        />
      </div>
    </div>
  );
}
