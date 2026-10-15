/**
 * Tarjeta de la rejilla de `/modelos` (sobre
 * `Modelos.dc.html`): nombre y chip de estado de despliegue en la cabecera,
 * versión activa y dominio, cuatro luces de monitor (`LucesMonitor`), meta
 * de fechas y pie con descripción y el botón de configurar. Sin sparkline
 * (se retiró del cuadro; aquí ya sobraba) y sin `useAlerts` ni
 * `useTimeline` por tarjeta: todo sale de `p.summary` (una sola consulta
 * para toda la rejilla, `index.tsx`).
 */

import { Link } from "react-router";
import { SettingsIcon } from "lucide-react";

import type { Project } from "@/api/types";
import { ChipDespliegue, LucesMonitor } from "@/components/vigia";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { formatoFechaCorta, formatoFechaLarga, formatoRelativo } from "@/lib/fechas";

import { ETIQUETA_DOMINIO, ETIQUETA_TAREA } from "./etiquetas";

export interface TarjetaModeloProps {
  proyecto: Project;
  onAbrir: (p: Project) => void;
}

export function TarjetaModelo({ proyecto: p, onAbrir }: TarjetaModeloProps) {
  const s = p.summary;
  const activar = () => onAbrir(p);
  const version = s?.active_version_label ?? "sin modelo";
  const sinLotes = !s?.first_batch_at;
  const sinEvaluar = !s?.last_evaluation_at;

  return (
    <Card
      role="link"
      tabIndex={0}
      aria-label={`Abrir el cuadro de mando de ${p.name}`}
      onClick={activar}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          activar();
        }
      }}
      className="flex cursor-pointer flex-col gap-3 p-4 transition-colors hover:border-ring/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <div className="flex flex-col gap-1.5">
        <div className="flex items-start justify-between gap-2">
          <span className="min-w-0 truncate text-base font-semibold tracking-[-0.01em]" title={p.name}>
            {p.name}
          </span>
          <ChipDespliegue estado={p.deployment_stage} />
        </div>
        <div className="flex items-center gap-2 text-xs text-[var(--foreground-tertiary)]">
          <span className="inline-flex h-[18px] items-center rounded px-1.5 text-[11px] font-semibold tabular-nums ring-1 ring-[var(--border)]">
            {version}
          </span>
          <span className="truncate">
            {ETIQUETA_DOMINIO[p.domain] ?? p.domain} · {ETIQUETA_TAREA[p.task_type] ?? p.task_type}
            {p.is_demo ? " · sintético" : ""}
          </span>
        </div>
      </div>

      <LucesMonitor summary={s} projectId={p.id} />

      <div className="grid grid-cols-2 gap-2 border-t border-[var(--line)] pt-2.5">
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">Inicio</span>
          {sinLotes ? (
            <span className="text-sm font-semibold text-[var(--state-nodata)]">Sin lotes</span>
          ) : (
            <span className="text-sm font-semibold tabular-nums">{formatoFechaCorta(s?.first_batch_at)}</span>
          )}
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">
            Última evaluación
          </span>
          {sinEvaluar ? (
            <span className="text-sm font-semibold text-[var(--state-nodata)]">Sin evaluar</span>
          ) : (
            <span className="text-sm font-semibold tabular-nums" title={formatoFechaLarga(s?.last_evaluation_at)}>
              {formatoRelativo(s?.last_evaluation_at)}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between gap-2">
        {p.description ? (
          <span className="min-w-0 truncate text-sm text-muted-foreground" title={p.description}>
            {p.description}
          </span>
        ) : (
          <span className="min-w-0 truncate text-sm text-muted-foreground">
            Sin descripción del despliegue ·{" "}
            <Link
              to={`/modelos/${p.id}#configuracion`}
              onClick={(e) => e.stopPropagation()}
              className="underline underline-offset-2 hover:text-foreground"
            >
              añadir
            </Link>
          </span>
        )}
        <Button
          asChild
          size="icon"
          variant="ghost"
          className="size-7 flex-none"
          onClick={(e) => e.stopPropagation()}
        >
          <Link to={`/modelos/${p.id}`} aria-label="Configurar">
            <SettingsIcon className="size-4" aria-hidden="true" />
          </Link>
        </Button>
      </div>
    </Card>
  );
}
