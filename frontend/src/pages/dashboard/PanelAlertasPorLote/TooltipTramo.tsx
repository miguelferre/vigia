/**
 * Tooltip compartido de las dos gráficas del panel (`syncId`), carril F3 de
 * Título del tramo, alertas por lote evaluado en día u hora, cifra por
 * monitor, total con su reparto y «Clic: filtrar la tabla». En lote, si hay
 * cruzadas sin lote, una línea al pie.
 */

import { CONFIG_MONITORES, formatoCifra, tituloTramo, type Fila } from "./formato";
import type { AlertasAbiertasPorSeveridad, SeriesGranularity } from "@/api/types";

interface TooltipTramoProps {
  active?: boolean;
  payload?: { payload?: unknown }[];
  granularidad: SeriesGranularity;
  crossUnbatched?: AlertasAbiertasPorSeveridad;
}

function repartoSeveridad(alta: number, media: number, baja: number): string {
  const partes: string[] = [];
  if (alta > 0) partes.push(`${alta} alta${alta === 1 ? "" : "s"}`);
  if (media > 0) partes.push(`${media} media${media === 1 ? "" : "s"}`);
  if (baja > 0) partes.push(`${baja} baja${baja === 1 ? "" : "s"}`);
  return partes.join(", ");
}

export function TooltipTramo({ active, payload, granularidad, crossUnbatched }: TooltipTramoProps) {
  const fila = payload?.[0]?.payload as Fila | undefined;
  if (!active || !fila) return null;
  const totalCruzadas = (crossUnbatched?.alta ?? 0) + (crossUnbatched?.media ?? 0) + (crossUnbatched?.baja ?? 0);

  return (
    <div
      className="flex min-w-52 flex-col gap-1.5 rounded-md p-3 text-xs"
      style={{ background: "var(--card)", color: "var(--card-foreground)", boxShadow: "var(--elevation-pop)" }}
    >
      <span className="font-semibold">{tituloTramo(fila, granularidad)}</span>
      {granularidad !== "batch" && fila.nBatches > 0 ? (
        <span className="text-tertiary">
          {formatoCifra(fila.total / fila.nBatches, "day")} alertas por lote
        </span>
      ) : null}
      <div className="flex flex-col gap-1">
        {(Object.keys(CONFIG_MONITORES) as (keyof typeof CONFIG_MONITORES)[]).map((m) => (
          <span key={m} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-2 rounded-full"
              style={{ background: CONFIG_MONITORES[m].color }}
            />
            {CONFIG_MONITORES[m].label}
            <span className="ml-auto font-semibold tabular-nums">
              {formatoCifra(fila[m], granularidad)}
              {granularidad !== "batch" ? ` · ${fila.item.by_monitor[m]}` : ""}
            </span>
          </span>
        ))}
        {granularidad !== "batch" && fila.item.by_monitor.cross > 0 ? (
          <span className="flex items-center gap-1.5">
            <span aria-hidden="true" className="size-2 rounded-full" style={{ background: "var(--state-nodata)" }} />
            Cruzadas
            <span className="ml-auto font-semibold tabular-nums">{fila.item.by_monitor.cross}</span>
          </span>
        ) : null}
      </div>
      {fila.total > 0 ? (
        <span className="text-foreground">
          {fila.total} en total: {repartoSeveridad(fila.alta, fila.media, fila.baja)}
        </span>
      ) : null}
      {granularidad === "batch" && totalCruzadas > 0 ? (
        <span className="text-tertiary">cruzadas sin lote: {totalCruzadas}</span>
      ) : null}
      <span style={{ color: "var(--link)" }}>Clic: filtrar la tabla</span>
    </div>
  );
}
