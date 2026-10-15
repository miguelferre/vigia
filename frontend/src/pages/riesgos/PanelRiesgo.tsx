/**
 * Panel lateral de un riesgo (`?riesgo=<id>`): cabecera, origen, celda actual, acciones (`AccionesRiesgo.tsx`) e
 * historial (`HistorialRiesgo.tsx`). Mismo `Sheet` no modal que
 * `AlertaPanel.tsx`.
 *
 * El panel pide su propio riesgo con `GET /risks/{id}` en vez de
 * depender de la lista sin filtrar que carga la matriz o el registro.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import type { Risk } from "@/api/types";
import { api } from "@/api/client";
import { STALE_MS } from "@/api/queries";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { InfoTooltip } from "@/components/vigia";
import { useGlosario } from "@/api/queries-contenido";
import { useCan } from "@/session/session";
import { formatoFechaLarga, formatoRelativo } from "@/lib/fechas";
import { AccionesRiesgo } from "./AccionesRiesgo";
import { HistorialRiesgo } from "./HistorialRiesgo";
import { ETIQUETA_ESTADO_RIESGO, ETIQUETA_NIVEL, IMPACTO_LABELS, PROBABILIDAD_LABELS, TOKEN_NIVEL } from "./niveles";

export interface PanelRiesgoProps {
  riesgoId: number | null;
  onClose: () => void;
}

export function PanelRiesgo({ riesgoId, onClose }: PanelRiesgoProps) {
  const puedeConfig = useCan("config");
  const glosarioQ = useGlosario();
  const g = glosarioQ.data;
  const riesgoQ = useQuery({
    queryKey: ["risks", "porId", riesgoId],
    queryFn: () => api.get<Risk>(`/risks/${riesgoId}`),
    enabled: riesgoId !== null,
    staleTime: STALE_MS,
  });
  const riesgo = riesgoQ.data ?? null;

  return (
    <Sheet modal={false} open={riesgoId !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-4 overflow-y-auto p-5 sm:max-w-lg"
        onInteractOutside={(e) => e.preventDefault()}
      >
        <SheetHeader className="sr-only">
          <SheetTitle>Detalle del riesgo</SheetTitle>
        </SheetHeader>
        {riesgoId === null ? null : !riesgo ? (
          <p className="text-sm text-muted-foreground">Cargando…</p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm text-muted-foreground">{riesgo.code}</span>
              <span
                className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-sm font-semibold"
                style={{ borderColor: TOKEN_NIVEL[riesgo.level], color: TOKEN_NIVEL[riesgo.level] }}
              >
                {ETIQUETA_NIVEL[riesgo.level]}
              </span>
              <span className="text-sm text-muted-foreground">{ETIQUETA_ESTADO_RIESGO[riesgo.status]}</span>
              {g?.riesgo ? <InfoTooltip titulo="Riesgo" queMide={g.riesgo.definicion} comoSeLee={null} /> : null}
            </div>
            <h1 className="font-display text-xl font-semibold tracking-[-0.15px] leading-tight">{riesgo.title}</h1>
            {riesgo.description ? <p className="text-md text-tertiary">{riesgo.description}</p> : null}

            <div className="flex flex-col gap-1 rounded-lg bg-muted p-3 text-sm">
              <p>
                <span className="text-tertiary">Origen: </span>
                {riesgo.origin_alert_id ? (
                  <Link to={`/alertas?panel=${riesgo.origin_alert_id}`} className="text-link hover:underline">
                    {riesgo.origin_alert_title ?? `Alerta #${riesgo.origin_alert_id}`}
                  </Link>
                ) : (
                  "a mano"
                )}
              </p>
              <p>
                <span className="text-tertiary">Celda actual: </span>
                {IMPACTO_LABELS[riesgo.impact_level]} × {PROBABILIDAD_LABELS[riesgo.probability_level]}
              </p>
              <p title={formatoFechaLarga(riesgo.created_at)}>
                <span className="text-tertiary">Creado: </span>
                {formatoRelativo(riesgo.created_at)}
              </p>
            </div>

            {puedeConfig ? <AccionesRiesgo riesgo={riesgo} /> : null}
            <HistorialRiesgo riskId={riesgo.id} />
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
