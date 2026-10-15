/** Selector de la versión del modelo a la que se sube el registro de uso (partido de `RegistroUso.tsx`). */

import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { ModelVersion } from "@/api/types";

interface Props {
  versiones: ModelVersion[];
  /** Id elegido como texto; vacío sigue a la versión activa. */
  valor: string;
  activaId: number | null;
  onCambiar: (id: string) => void;
}

export function SelectorVersionRegistro({ versiones, valor, activaId, onCambiar }: Props) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor="registro-version" className="text-sm">
        Versión del modelo
      </Label>
      <Select value={valor !== "" ? valor : activaId !== null ? String(activaId) : ""} onValueChange={onCambiar}>
        <SelectTrigger id="registro-version" className="w-48">
          <SelectValue placeholder="Versión activa" />
        </SelectTrigger>
        <SelectContent>
          {versiones.map((v) => (
            <SelectItem key={v.id ?? v.label} value={String(v.id)}>
              {v.label}
              {v.is_active ? " (activa)" : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
