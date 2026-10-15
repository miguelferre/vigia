/**
 * Barra de filtros de `alertas/index.tsx` (artboard `Alertas`):
 * control segmentado de estado (un solo valor activo, no chips de toggle),
 * chips de severidad, selector de monitor y buscador con
 * atajo "Ctrl K" (el foco lo pone `index.tsx`, aquí solo se pinta el `kbd`).
 */

import { forwardRef } from "react";
import { SearchIcon } from "lucide-react";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { ETIQUETA_MONITOR } from "@/lib/metrics";
import type { MonitorType } from "@/api/types";
import { etiquetaSeveridad } from "./severidad";
import { ETIQUETA_SEGMENTO, SEGMENTOS_ESTADO, SEVERIDADES, type SegmentoEstado } from "./filtros-constantes";

const MONITORES: MonitorType[] = ["fairness", "quality", "drift", "explain", "cross"];

export interface FiltrosProps {
  segmento: SegmentoEstado;
  onSegmentoChange: (segmento: SegmentoEstado) => void;
  conteo: Record<SegmentoEstado, number>;
  severidades: Set<string>;
  onToggleSeveridad: (severidad: string) => void;
  monitor: MonitorType | "todos";
  onMonitorChange: (monitor: MonitorType | "todos") => void;
  busqueda: string;
  onBusquedaChange: (busqueda: string) => void;
}

export const Filtros = forwardRef<HTMLInputElement, FiltrosProps>(function Filtros(
  { segmento, onSegmentoChange, conteo, severidades, onToggleSeveridad, monitor, onMonitorChange, busqueda, onBusquedaChange },
  refBusqueda,
) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex max-w-full items-center gap-0.5 overflow-x-auto rounded-lg bg-muted p-0.5" role="group" aria-label="Filtro por estado">
        {SEGMENTOS_ESTADO.map((seg) => (
          <button
            key={seg}
            type="button"
            aria-pressed={segmento === seg}
            onClick={() => onSegmentoChange(seg)}
            className={cn(
              "flex h-7 items-center rounded-md px-2.5 text-md transition-colors",
              segmento === seg
                ? "bg-card font-semibold shadow-card"
                : "text-tertiary hover:text-foreground",
            )}
          >
            {ETIQUETA_SEGMENTO[seg]}
            <span className="ml-1 tabular-nums">{conteo[seg]}</span>
          </button>
        ))}
      </div>
      <span aria-hidden="true" className="h-5 w-px bg-border" />
      <div className="flex items-center gap-1.5" role="group" aria-label="Filtro por severidad">
        {/* Chip de filtro (la píldora queda para estado y filtro), con
            el punto de severidad del artboard `Alertas`; no es un `Button`. */}
        {SEVERIDADES.map((sev) => {
          const activo = severidades.has(sev);
          return (
            <button
              key={sev}
              type="button"
              aria-pressed={activo}
              onClick={() => onToggleSeveridad(sev)}
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-semibold transition-colors",
                activo ? "border-border bg-card text-foreground" : "border-transparent text-tertiary hover:text-foreground",
              )}
            >
              <span
                aria-hidden="true"
                className={cn("size-1.5 rounded-full", sev === "alta" ? "bg-state-alert" : sev === "media" ? "bg-state-warn" : "bg-state-nodata")}
              />
              {etiquetaSeveridad(sev)}
            </button>
          );
        })}
      </div>
      <Select value={monitor} onValueChange={(v) => onMonitorChange(v as MonitorType | "todos")}>
        <SelectTrigger size="sm" className="h-8 w-auto gap-1.5 text-md text-tertiary">
          <SelectValue placeholder="Monitor: Todos" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="todos">Monitor: Todos</SelectItem>
          {MONITORES.map((m) => (
            <SelectItem key={m} value={m}>
              {ETIQUETA_MONITOR[m]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className="ml-auto flex h-8 w-60 items-center gap-2 rounded-lg border border-border bg-card px-2.5 text-md text-tertiary">
        <SearchIcon className="size-4 flex-none" aria-hidden="true" />
        <input
          ref={refBusqueda}
          type="text"
          value={busqueda}
          onChange={(e) => onBusquedaChange(e.target.value)}
          placeholder="Buscar alerta o métrica"
          className="min-w-0 flex-1 bg-transparent text-foreground outline-none placeholder:text-tertiary"
        />
        <kbd className="hidden flex-none rounded border border-border px-1 text-xs sm:inline">Ctrl K</kbd>
      </div>
    </div>
  );
});

export default Filtros;
