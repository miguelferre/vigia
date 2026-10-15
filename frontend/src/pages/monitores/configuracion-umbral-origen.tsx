/**
 * Origen y nota de un umbral cuyo valor se ha cambiado en la configuración del
 * monitor. Mismo selector y mismos textos que el paso «Umbrales»
 * del alta (`alta-umbrales-fila.tsx`): un valor cambiado a mano nunca queda
 * como «fábrica». Una fila sin cambio no pasa por aquí y conserva su origen.
 */

import type { ThresholdOrigen } from "@/api/queries-alta";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { etiquetaOrigenUmbral } from "@/pages/modelos/alta-umbrales-textos";

import type { ThresholdEntry } from "./tipos";

/** Los orígenes que una persona puede dar a un valor propio, en el orden del alta. */
const ORIGENES_PROPIOS: readonly ThresholdOrigen[] = ["fabricante", "criterio_clinico", "politica_organizacion"];

export interface OrigenUmbralEditorProps {
  umbral: ThresholdEntry;
  /** Nombre de la métrica tal como la ve la persona, para los nombres accesibles. */
  etiqueta: string;
  /** `Project.domain`, para el nombre del criterio. */
  dominio?: string;
  onOrigen: (origen: ThresholdOrigen) => void;
  onNota: (nota: string) => void;
}

export function OrigenUmbralEditor({ umbral, etiqueta, dominio, onOrigen, onNota }: OrigenUmbralEditorProps) {
  const origen = ORIGENES_PROPIOS.includes(umbral.origen as ThresholdOrigen) ? (umbral.origen as ThresholdOrigen) : "criterio_clinico";
  const nombre = `${etiqueta} (${umbral.kind === "lower_limit" ? "límite inferior" : "límite superior"})`;
  return (
    <div className="flex flex-col gap-1.5 rounded-md bg-muted/40 p-2" data-testid="origen-umbral-cambiado">
      <p className="text-xs text-muted-foreground">
        Has cambiado este valor: di de dónde sale. Queda en el diario con su nota.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={origen} onValueChange={(v) => onOrigen(v as ThresholdOrigen)}>
          <SelectTrigger className="w-56" aria-label={`Origen del umbral ${nombre}`}>
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
          placeholder="Nota (obligatoria)"
          aria-label={`Nota del umbral ${nombre}`}
          value={umbral.nota ?? ""}
          onChange={(e) => onNota(e.target.value)}
        />
      </div>
    </div>
  );
}
