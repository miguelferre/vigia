/**
 * «Alertas que requieren acción» (artboard `Main` punto 4; la fila vive en
 * `FilaAlertaAccion.tsx`): 5 filas, abiertas primero, luego en observación, por
 * severidad; cabecera «n de total» y «Ver las N alertas» con el total tras
 * los filtros. Filtra por el tramo pulsado en `PanelAlertasPorLote`
 * (`?tramo=`) y por el monitor de una luz o tarjeta (`?monitor=`), cada uno
 * con su chip para quitarlo.
 *
 * El botón «Revisar» abre `AlertaPanel` (`pages/alertas/AlertaPanel.tsx`):
 * se importa con `React.lazy` para que esta pantalla cargue sin él.
 */

import { Suspense, lazy, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { mensajeDeError } from "@/api/client";
import { useAlerts } from "@/api/queries";
import { useAlertsSeries } from "@/api/queries-alertas-series";
import { StateBadge } from "@/components/vigia";
import { ETIQUETA_MONITOR } from "@/lib/metrics";
import { numeroLote } from "@/lib/fases";
import { FilaAlerta } from "./FilaAlertaAccion";
import { useEstadoPanel } from "./PanelAlertasPorLote/useEstadoPanel";
import { ORDEN_ETAPA } from "@/pages/alertas/etapa";
import type { Alert, MonitorType } from "@/api/types";

const AlertaPanel = lazy(() =>
  import("@/pages/alertas/AlertaPanel").then((m) => ({ default: m.AlertaPanel })),
);

const TOPE = 5;
const MONITORES_VALIDOS: MonitorType[] = ["fairness", "quality", "drift", "explain", "cross"];

const RANGO_SEVERIDAD: Record<string, number> = { alta: 0, media: 1 };

/**
 * Orden por urgencia: la etapa menos avanzada primero (nada
 * hecho pesa más que una decisión ya tomada), sobre `Alert.stage` en vez del
 * `status` crudo del motor (`RANGO_ESTADO` de antes de esta sesión mezclaba
 * "en seguimiento" antes que "en observación", al revés de la urgencia real).
 */
function ordenar(alertas: Alert[]): Alert[] {
  return [...alertas].sort((a, b) => {
    const porEtapa = ORDEN_ETAPA.indexOf(a.stage) - ORDEN_ETAPA.indexOf(b.stage);
    if (porEtapa !== 0) return porEtapa;
    const porSeveridad = (RANGO_SEVERIDAD[a.severity] ?? 2) - (RANGO_SEVERIDAD[b.severity] ?? 2);
    if (porSeveridad !== 0) return porSeveridad;
    return a.opened_at.localeCompare(b.opened_at);
  });
}

function Chip({ etiqueta, onQuitar }: { etiqueta: string; onQuitar: () => void }) {
  return (
    <button
      type="button"
      onClick={onQuitar}
      className="inline-flex h-6 items-center gap-1 rounded-full border border-border bg-card px-2 text-xs font-medium text-foreground"
    >
      {etiqueta}
      <XIcon className="size-3" aria-hidden="true" />
      <span className="sr-only">Quitar el filtro</span>
    </button>
  );
}

export function TablaAlertasAccion({ projectId }: { projectId: number | null }) {
  const [params, setParams] = useSearchParams();
  const monitorParam = params.get("monitor");
  const monitor = MONITORES_VALIDOS.includes(monitorParam as MonitorType) ? (monitorParam as MonitorType) : null;

  const estadoPanel = useEstadoPanel();
  const { data: serie } = useAlertsSeries(projectId, {
    granularity: estadoPanel.granularidad,
    since: estadoPanel.desde,
    until: estadoPanel.hasta,
  });
  const tramoItem = estadoPanel.tramo ? serie?.items.find((i) => i.key === estadoPanel.tramo) : undefined;

  const { data, isPending, isError, error, refetch } = useAlerts(projectId, {
    status: "abierta,en_observacion,reconocida",
    monitor_type: monitor,
  });
  const [alertaAbierta, setAlertaAbierta] = useState<number | null>(null);

  // Filtro por tramo con la misma semántica que la gráfica: `alert_ids` del
  // ítem (alertas activas en ese lote o tramo). `Alert.batch_id` solo diría
  // el último lote de cada alerta y vaciaba la tabla al pulsar un lote con
  // siete alertas en el tooltip.
  let alertas = data?.items ?? [];
  if (tramoItem) {
    const ids = new Set(tramoItem.alert_ids);
    alertas = alertas.filter((a) => a.id !== null && ids.has(a.id));
  }
  alertas = ordenar(alertas);
  const visibles = alertas.slice(0, TOPE);

  function quitarMonitor() {
    const siguiente = new URLSearchParams(params);
    siguiente.delete("monitor");
    setParams(siguiente, { replace: true });
  }

  // Chip del filtro: «Lote #8 · lote-08.csv» por lote (con el nombre
  // cuando lo trae); «15/09» o «15/09 15:00» por tramo.
  const loteTramo = tramoItem?.batches[0];
  const etiquetaTramo = tramoItem
    ? estadoPanel.granularidad === "batch"
      ? `Lote ${numeroLote(loteTramo?.seq)}${loteTramo?.name?.trim() ? ` · ${loteTramo.name.trim()}` : ""}`
      : tramoItem.label
    : null;
  const hrefTodas = monitor ? `/alertas?monitor=${monitor}` : "/alertas";

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <div className="flex flex-col gap-1">
          <CardTitle className="text-sm">
            Alertas que requieren acción{" "}
            {alertas.length > 0 ? (
              <span className="font-normal text-muted-foreground">
                {visibles.length} de {alertas.length}
              </span>
            ) : null}
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Orden: por etapa (detectada, en observación, en investigación, en seguimiento), por severidad (alta
            antes que media) y por fecha de apertura (la más antigua primero)
          </p>
          {tramoItem || monitor ? (
            <div className="flex items-center gap-1.5 pt-1">
              {tramoItem ? <Chip etiqueta={`${etiquetaTramo} ×`} onQuitar={() => estadoPanel.setTramo(tramoItem.key)} /> : null}
              {monitor ? <Chip etiqueta={`${ETIQUETA_MONITOR[monitor]} ×`} onQuitar={quitarMonitor} /> : null}
            </div>
          ) : null}
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to={hrefTodas}>Ver las {alertas.length} alertas</Link>
        </Button>
      </CardHeader>
      <CardContent>
        {isError ? (
          <div className="flex flex-col items-start gap-2">
            <p className="text-sm text-destructive">{mensajeDeError(error)}</p>
            <Button type="button" variant="outline" size="sm" onClick={() => void refetch()}>
              Reintentar
            </Button>
          </div>
        ) : !isPending && alertas.length === 0 ? (
          <div className="flex items-center gap-2 rounded-lg border border-dashed border-border px-4 py-6 text-sm text-muted-foreground">
            <StateBadge
              estado="ok"
              texto={tramoItem ? "Ninguna alerta requiere acción en este tramo" : "Sin alertas que requieran acción"}
            />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Severidad</TableHead>
                <TableHead>Alerta</TableHead>
                <TableHead>Monitor</TableHead>
                <TableHead>Lote</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Abierta</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibles.map((alerta) => (
                <FilaAlerta key={alerta.id} alerta={alerta} onRevisar={() => setAlertaAbierta(alerta.id)} />
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <Suspense fallback={null}>
        <AlertaPanel alertId={alertaAbierta} onClose={() => setAlertaAbierta(null)} />
      </Suspense>
    </Card>
  );
}
