/**
 * Aviso visible en la cabecera del monitor: alguna métrica
 * sigue con el umbral de fábrica aunque la versión activa ya tiene la línea
 * base congelada, es decir, hay con qué calibrarlo y no se ha hecho. Antes
 * solo vivía dentro del `<details>` cerrado «Origen de los umbrales». Sin
 * línea base congelada no se enseña: el aviso de línea base ya cubre ese caso.
 */

import { AlertTriangleIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useVersionActiva } from "@/api/queries-monitor-proyecto";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { metricLabel } from "@/lib/metrics";
import type { Monitor } from "@/api/types";

import { calidadSinFabrica } from "./regresion-datos";
import { extraerUmbrales, metricasDelMonitor } from "./tipos";

export function AvisoUmbralDeFabrica({
  projectId,
  monitor,
  onConfigurar,
  puedeConfigurar,
}: {
  projectId: number;
  monitor: Monitor;
  onConfigurar: () => void;
  puedeConfigurar: boolean;
}) {
  const { version } = useVersionActiva(projectId);
  const { caps } = useTipoTarea(projectId);
  // En calidad multiclase y de regresión el umbral de fábrica no se evalúa; no hay «umbral de fábrica en uso».
  if (calidadSinFabrica(caps, monitor.type)) return null;
  if (monitor.type === "drift") {
    return (
      <p data-testid="nota-umbral-deriva" className="text-xs text-muted-foreground">
        Umbrales estándar de deriva.
      </p>
    );
  }
  if (!version?.frozen_at) return null;
  const entradas = extraerUmbrales(monitor.thresholds);
  const deFabrica = entradas.filter((e) => (e.origen ?? "fabrica") === "fabrica");
  if (deFabrica.length === 0) return null;
  const metricas = metricasDelMonitor(deFabrica).map((m) => metricLabel(m));
  return (
    <div
      role="status"
      data-testid="aviso-umbral-fabrica"
      className="flex flex-wrap items-start gap-2 rounded-md border border-border bg-[var(--state-warn)]/10 p-3 text-sm"
    >
      <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" style={{ color: "var(--state-warn)" }} aria-hidden="true" />
      <p className="min-w-0 flex-1">
        <span className="font-semibold">Umbral de fábrica en uso.</span> La línea base ya está congelada, pero{" "}
        {metricas.length === 1
          ? `la métrica ${metricas[0]} sigue`
          : metricas.length <= 3
            ? `las métricas ${metricas.join(", ")} siguen`
            : `${metricas.length} métricas de este monitor siguen`}{" "}
        con el umbral de fábrica, sin calibrar para este modelo.
      </p>
      {puedeConfigurar ? (
        <Button size="sm" variant="outline" onClick={onConfigurar}>
          Revisar umbrales
        </Button>
      ) : null}
    </div>
  );
}
