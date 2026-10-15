/**
 * Chips y metadatos de `AlertaPanel.tsx` (artboard `PanelLateral`):
 * partido del panel para no pasar de 9 KB en ese fichero.
 */

import type { ReactNode } from "react";

import { useBatches } from "@/api/queries-datos";
import type { Alert, AlertDetail, Batch } from "@/api/types";
import { StateBadge } from "@/components/vigia";
import { cn } from "@/lib/utils";
import { ETIQUETA_MONITOR, formatoFecha } from "@/lib/metrics";
import { componerLote, etiquetaFase, numeroLote } from "@/lib/fases";
import { estadoDeSeveridad, etiquetaSeveridad } from "./severidad";
import { etiquetaEtapa } from "./etapa";

/** Mismo tratamiento visual que `pages/alertas/detalle.tsx`: un solo look de chip de cabecera. */
export function ChipPanel({ tono, children }: { tono: "monitor" | "lote" | "aviso"; children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex h-[22px] items-center rounded-full px-2 text-xs font-semibold whitespace-nowrap",
        tono === "monitor" && "bg-primary/10 text-primary",
        tono === "lote" && "bg-muted text-tertiary",
        tono === "aviso" && "bg-[var(--state-warn)]/15 text-[var(--state-warn)]",
      )}
    >
      {children}
    </span>
  );
}

export interface ChipsCabeceraProps {
  alerta: Alert | AlertDetail;
  lote: Batch | null | undefined;
}

export function ChipsCabecera({ alerta, lote }: ChipsCabeceraProps) {
  // El nombre del lote junto a su número (la lista de lotes ya está en caché).
  const lotes = useBatches(alerta.project_id).data?.items;
  const nombreDe = (batchId: number | null): string =>
    batchId !== null ? ((lotes ?? []).find((b) => b.id === batchId)?.dataset_name ?? "") : "";
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <ChipPanel tono="monitor">{ETIQUETA_MONITOR[alerta.monitor_type]}</ChipPanel>
      {/* Primero el lote de origen (donde se abrió); el de la última
          evaluación solo si es otro. Sin origen (alertas anteriores), el de
          siempre. */}
      {alerta.origin_batch_id !== null && alerta.origin_batch_seq === null ? (
        <ChipPanel tono="lote">Lote de origen borrado</ChipPanel>
      ) : null}
      {alerta.origin_batch_seq !== null ? (
        <ChipPanel tono="lote">
          Abierta en lote{" "}
          {componerLote(
            numeroLote(alerta.origin_batch_seq),
            nombreDe(alerta.origin_batch_id),
            etiquetaFase(alerta.origin_phase_label),
          )}
        </ChipPanel>
      ) : null}
      {alerta.batch_id !== null && (alerta.origin_batch_id === null || alerta.batch_seq !== alerta.origin_batch_seq) ? (
        <ChipPanel tono="lote">
          {alerta.origin_batch_id !== null ? "Último lote" : "Lote"}{" "}
          {componerLote(
            // El número de lote, nunca `batch.id`; sin `batch_seq`, el de la lista.
            numeroLote(alerta.batch_seq ?? (lotes ?? []).find((b) => b.id === alerta.batch_id)?.seq),
            nombreDe(alerta.batch_id),
            etiquetaFase(alerta.batch_phase_label),
          )}
        </ChipPanel>
      ) : null}
      {alerta.status === "retirada" ? <ChipPanel tono="aviso">Retirada</ChipPanel> : null}
      {lote?.orden_manipulado ? <ChipPanel tono="aviso">Orden manipulado</ChipPanel> : null}
    </div>
  );
}

export interface MetadatosProps {
  alerta: Alert | AlertDetail;
}

export function Metadatos({ alerta }: MetadatosProps) {
  return (
    <div className="flex flex-wrap items-center gap-4 text-md text-tertiary">
      <span className="flex items-center gap-1.5">
        Severidad
        <StateBadge estado={estadoDeSeveridad(alerta.severity)} texto={etiquetaSeveridad(alerta.severity)} size="sm" />
      </span>
      <span className="flex items-center gap-1.5">
        Estado
        <span className="font-semibold text-foreground">{etiquetaEtapa(alerta)}</span>
      </span>
      <span className="flex items-center gap-1.5">
        Apertura
        <span className="text-foreground">{formatoFecha(alerta.opened_at)}</span>
      </span>
    </div>
  );
}

/** Una alerta retirada enseña su motivo y no ofrece acciones. */
export function AvisoRetirada({ alerta }: { alerta: Alert | AlertDetail }) {
  if (alerta.status !== "retirada") return null;
  const motivo = (alerta.retired_reason ?? "su lote de origen se borró").trim().replace(/\.$/, "");
  return (
    <p role="status" data-testid="aviso-retirada" className="rounded-md border border-border bg-muted/50 p-3 text-md">
      <span className="font-semibold">Alerta retirada.</span> Motivo: {motivo}. Se conserva como registro y ya no admite
      acciones.
    </p>
  );
}
