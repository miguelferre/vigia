/**
 * Formato de la probabilidad (escalar o lista) y su índice en el mapeo de un
 * dataset binario. Sale de `mapeo-campos.tsx` por el límite de 9 KB; en
 * multiclase lo sustituye `mapeo-multiclase.tsx`.
 */

import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AYUDA_MAPEO } from "./etiquetas";
import { Ayuda, Campo } from "./mapeo-controles";

interface Props {
  formato: "scalar" | "list";
  onFormato: (v: "scalar" | "list") => void;
  indice: string;
  onIndice: (v: string) => void;
}

export function FormatoProbabilidad({ formato, onFormato, indice, onIndice }: Props) {
  return (
    <div className="grid grid-cols-1 items-start gap-3 sm:grid-cols-2">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="mc-formato-probabilidad">Formato de la probabilidad</Label>
        <Select value={formato} onValueChange={(v) => onFormato(v as "scalar" | "list")}>
          <SelectTrigger id="mc-formato-probabilidad" aria-describedby="mc-formato-probabilidad-ayuda">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="scalar">Escalar</SelectItem>
            <SelectItem value="list">Lista</SelectItem>
          </SelectContent>
        </Select>
        <Ayuda id="mc-formato-probabilidad-ayuda">{AYUDA_MAPEO.formatoProbabilidad}</Ayuda>
      </div>
      {formato === "list" ? <Campo etiqueta="Índice en la lista" valor={indice} onChange={onIndice} tipo="number" /> : null}
    </div>
  );
}
