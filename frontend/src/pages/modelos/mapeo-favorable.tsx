/**
 * Campo «Valor favorable» del mapeo (partido de `mapeo-campos.tsx`
 * para quedar por debajo de 9 KB): se elige entre los valores detectados de
 * la columna de etiqueta, no se escribe. Vacío hereda de la plantilla o de
 * la línea base.
 */

import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AYUDA_MAPEO } from "./etiquetas";

const HEREDAR = "__heredar__";

interface Props {
  valor: string;
  onChange: (v: string) => void;
  /** Valores distintos vistos en la columna de etiqueta (puede estar vacío si no hay muestra). */
  valores: string[];
}

export function CampoFavorable({ valor, onChange, valores }: Props) {
  // Sin muestra de la columna, el valor sugerido sigue siendo elegible para
  // que el campo no se quede en blanco.
  const opciones = valores.length === 0 && valor !== "" ? [valor] : valores;
  const desconocido = valor !== "" && valores.length > 0 && !valores.includes(valor);
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="mc-favorable">Valor favorable</Label>
      <p id="mc-favorable-ayuda" className="text-xs text-muted-foreground">
        {AYUDA_MAPEO.favorable}
      </p>
      <Select value={valor === "" ? HEREDAR : valor} onValueChange={(v) => onChange(v === HEREDAR ? "" : v)}>
        <SelectTrigger id="mc-favorable" aria-describedby="mc-favorable-ayuda">
          <SelectValue placeholder="Elige un valor" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={HEREDAR}>Heredar de la plantilla o de la línea base</SelectItem>
          {opciones.map((v) => (
            <SelectItem key={v} value={v}>
              {v}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {desconocido ? (
        <p role="alert" className="text-xs text-destructive">
          «{valor}» no aparece en la columna de etiqueta (valores vistos: {valores.slice(0, 10).join(", ")}).
          Elige uno de la lista.
        </p>
      ) : null}
    </div>
  );
}
