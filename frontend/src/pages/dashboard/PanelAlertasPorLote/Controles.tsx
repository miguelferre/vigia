/**
 * Controles del panel (`Main.dc.html`): segmentado de granularidad (Lote ·
 * Día · Hora), segmentado de rango (24 h · 7 d · 30 d · Todo) y el botón de
 * rango personalizado, que despliega dos `input type="date"`. Carril F3.
 */

import { useState, type ReactNode } from "react";
import { CalendarIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import type { SeriesGranularity } from "@/api/types";
import type { Chip24h7d30dTodo } from "./useEstadoPanel";

const GRANULARIDADES: { valor: SeriesGranularity; etiqueta: string }[] = [
  { valor: "batch", etiqueta: "Lote" },
  { valor: "day", etiqueta: "Día" },
  { valor: "hour", etiqueta: "Hora" },
];

const CHIPS: { valor: Chip24h7d30dTodo; etiqueta: string }[] = [
  { valor: "24h", etiqueta: "24 h" },
  { valor: "7d", etiqueta: "7 d" },
  { valor: "30d", etiqueta: "30 d" },
  { valor: "todo", etiqueta: "Todo" },
];

function BotonSegmento({ activo, onClick, children }: { activo: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={activo}
      onClick={onClick}
      className={cn(
        "flex h-7 items-center rounded-md px-2.5 text-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        activo ? "bg-card font-semibold shadow-card" : "text-tertiary hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

export interface ControlesProps {
  granularidad: SeriesGranularity;
  onGranularidad: (g: SeriesGranularity) => void;
  chipActivo: Chip24h7d30dTodo | null;
  onChip: (chip: Chip24h7d30dTodo) => void;
  desde: string | null;
  hasta: string | null;
  onRangoPersonalizado: (desde: string | null, hasta: string | null) => void;
}

export function Controles({ granularidad, onGranularidad, chipActivo, onChip, desde, hasta, onRangoPersonalizado }: ControlesProps) {
  const [personalizadoAbierto, setPersonalizadoAbierto] = useState(false);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-0.5 rounded-lg bg-muted p-0.5" role="group" aria-label="Granularidad">
        {GRANULARIDADES.map((g) => (
          <BotonSegmento key={g.valor} activo={granularidad === g.valor} onClick={() => onGranularidad(g.valor)}>
            {g.etiqueta}
          </BotonSegmento>
        ))}
      </div>
      <div className="flex items-center gap-0.5 rounded-lg bg-muted p-0.5" role="group" aria-label="Rango">
        {CHIPS.map((c) => (
          <BotonSegmento key={c.valor} activo={chipActivo === c.valor} onClick={() => onChip(c.valor)}>
            {c.etiqueta}
          </BotonSegmento>
        ))}
      </div>
      <div className="relative">
        <button
          type="button"
          aria-pressed={chipActivo === null}
          aria-label="Rango personalizado"
          title="Rango personalizado"
          onClick={() => setPersonalizadoAbierto((v) => !v)}
          className={cn(
            "flex size-7 items-center justify-center rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            chipActivo === null ? "bg-card shadow-card text-foreground" : "text-tertiary hover:text-foreground",
          )}
        >
          <CalendarIcon className="size-4" aria-hidden="true" />
        </button>
        {personalizadoAbierto ? (
          <div className="absolute right-0 top-9 z-10 flex flex-col gap-2 rounded-lg border border-border bg-card p-3 shadow-card">
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              Desde
              <input
                type="date"
                defaultValue={desde ? desde.slice(0, 10) : ""}
                onChange={(e) => onRangoPersonalizado(e.target.value ? new Date(e.target.value).toISOString() : null, hasta)}
                className="rounded-md border border-border bg-transparent px-2 py-1 text-sm text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              Hasta
              <input
                type="date"
                defaultValue={hasta ? hasta.slice(0, 10) : ""}
                onChange={(e) => onRangoPersonalizado(desde, e.target.value ? new Date(e.target.value).toISOString() : null)}
                className="rounded-md border border-border bg-transparent px-2 py-1 text-sm text-foreground"
              />
            </label>
          </div>
        ) : null}
      </div>
    </div>
  );
}
