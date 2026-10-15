/**
 * Atributo protegido del paso «Datos» del alta (partido de `alta-datos.tsx`
 * para no superar 9 KB): columna, tipo (por rangos numéricos o por valores,
 * igual que el mapeo de dataset) y los dos grupos. Cada campo con su
 * ayuda; a 375 px las rejillas pasan a una columna.
 */

import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { ProtectedKind } from "@/api/types";
import { Checklist } from "./alta-datos-campos";
import { protegidoConColumna, type ProtegidoAlta } from "./alta-plantilla";
import { AYUDA_ALTA } from "./alta-textos";
import { Ayuda, RangoCampo, SelectorColumna } from "./mapeo-controles";

interface Props {
  columnas: string[];
  filas: Record<string, string>[];
  valor: ProtegidoAlta;
  onCambiar: (nuevo: ProtegidoAlta) => void;
  /** Valores distintos de la columna protegida, para los grupos por valores. */
  valoresProtegido: string[];
}

function alternar(set: Set<string>, v: string): Set<string> {
  const next = new Set(set);
  if (next.has(v)) next.delete(v);
  else next.add(v);
  return next;
}

export function CamposProtegido({ columnas, filas, valor, onCambiar, valoresProtegido }: Props) {
  const parche = (p: Partial<ProtegidoAlta>) => onCambiar({ ...valor, ...p });
  return (
    <div className="flex flex-col gap-3 rounded-md border border-border p-3">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={valor.activo} onChange={(e) => parche({ activo: e.target.checked })} />
        Atributo protegido (opcional, para vigilar la equidad)
      </label>
      {valor.activo ? (
        <>
          <SelectorColumna
            id="alta-protegido-col"
            etiqueta="Columna protegida"
            valor={valor.col}
            onChange={(v) => onCambiar(protegidoConColumna(valor, v, filas))}
            columnas={columnas}
            ayuda={AYUDA_ALTA.protegido}
          />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="alta-tipo-atributo">Tipo de atributo protegido</Label>
            <Select value={valor.tipo} onValueChange={(v) => parche({ tipo: v as ProtectedKind })}>
              <SelectTrigger id="alta-tipo-atributo" className="w-full" aria-describedby="alta-tipo-atributo-ayuda">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="numeric_ranges">Rangos numéricos</SelectItem>
                <SelectItem value="categorical">Categórico</SelectItem>
              </SelectContent>
            </Select>
            <Ayuda id="alta-tipo-atributo-ayuda">{AYUDA_ALTA.tipoAtributo}</Ayuda>
          </div>
          {valor.tipo === "numeric_ranges" ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <RangoCampo
                etiqueta="Grupo supervisado"
                idBase="alta-supervisado"
                min={valor.unprivMin}
                max={valor.unprivMax}
                onMin={(v) => parche({ unprivMin: v })}
                onMax={(v) => parche({ unprivMax: v })}
              />
              <RangoCampo
                etiqueta="Grupo de referencia"
                idBase="alta-referencia"
                min={valor.privMin}
                max={valor.privMax}
                onMin={(v) => parche({ privMin: v })}
                onMax={(v) => parche({ privMax: v })}
              />
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Checklist
                etiqueta="Grupo supervisado"
                opciones={valoresProtegido}
                elegidos={valor.unpriv}
                onAlternar={(v) => parche({ unpriv: alternar(valor.unpriv, v) })}
              />
              <Checklist
                etiqueta="Grupo de referencia"
                opciones={valoresProtegido}
                elegidos={valor.priv}
                onAlternar={(v) => parche({ priv: alternar(valor.priv, v) })}
              />
            </div>
          )}
          <Ayuda id="alta-grupos-ayuda">{AYUDA_ALTA.grupos}</Ayuda>
        </>
      ) : null}
    </div>
  );
}
