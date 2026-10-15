/**
 * Selector de periodo: las seis opciones de `OPCIONES_PERIODO` (`lib/fechas.ts`);
 * con "Personalizado" aparecen dos campos de fecha, como el filtro "Desde"
 * del diario (`pages/diario/Filtros.tsx`).
 *
 * Componente controlado: `value` guarda el periodo elegido y, solo con
 * "personalizado", las fechas `aaaa-mm-dd` de los campos (sin resolver a
 * ISO: eso lo hace `resolverPeriodo` en quien consuma el valor).
 */

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { OPCIONES_PERIODO, type Periodo } from "@/lib/fechas";

export interface ValorPeriodo {
  periodo: Periodo;
  /** Solo con `periodo: "personalizado"`. */
  since?: string;
  until?: string;
}

export interface SelectorPeriodoProps {
  value: ValorPeriodo;
  onChange: (valor: ValorPeriodo) => void;
  /** Prefijo de los `id` de los controles, para que no choquen si hay más de uno en la página. */
  idBase?: string;
}

export function SelectorPeriodo({ value, onChange, idBase = "selector-periodo" }: SelectorPeriodoProps) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${idBase}-tipo`}>Periodo</Label>
        <Select
          value={value.periodo}
          onValueChange={(v) => onChange({ ...value, periodo: v as Periodo })}
        >
          <SelectTrigger id={`${idBase}-tipo`} size="sm" className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {OPCIONES_PERIODO.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {value.periodo === "personalizado" ? (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${idBase}-desde`}>Desde</Label>
            <Input
              id={`${idBase}-desde`}
              type="date"
              value={value.since ?? ""}
              onChange={(e) => onChange({ ...value, since: e.target.value })}
              className="h-8 w-40"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${idBase}-hasta`}>Hasta</Label>
            <Input
              id={`${idBase}-hasta`}
              type="date"
              value={value.until ?? ""}
              onChange={(e) => onChange({ ...value, until: e.target.value })}
              className="h-8 w-40"
            />
          </div>
        </>
      ) : null}
    </div>
  );
}
