/**
 * Panel «Alertas por lote» (`Main.dc.html`).
 * Controles de granularidad y rango, dos gráficas sobre el mismo eje
 * temporal (alertas por monitor y reparto por severidad), navegador y clic
 * para filtrar la tabla de abajo. Sustituye a `GraficoAlertasPorLote` y
 * `GraficoMetricaPorLote` («Exactitud por lote» no vuelve).
 *
 * Las bandas de fase traducidas en proyecto demo dependen del guion
 * (`lib/fases.ts`, `etiquetaLote()`); lo pide `DemoGuiadaProvider` en la
 * raíz de la app, sin necesidad de pedirlo también aquí.
 */

import { useMemo, useState } from "react";
import { InboxIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/vigia";
import { mensajeDeError } from "@/api/client";
import { useAlertsSeries } from "@/api/queries-alertas-series";
import { useProjectsSummary } from "@/api/queries";
import { Controles } from "./Controles";
import { GraficaMonitores } from "./GraficaMonitores";
import { GraficaSeveridad } from "./GraficaSeveridad";
import { Navegador } from "./Navegador";
import { construirFilas } from "./formato";
import { useEstadoPanel } from "./useEstadoPanel";

export function PanelAlertasPorLote({ projectId }: { projectId: number | null }) {
  const estado = useEstadoPanel();
  const { data: resumen } = useProjectsSummary();
  const esDemo = resumen?.items.find((p) => p.id === projectId)?.is_demo ?? false;

  const { data, isPending, isError, error, refetch } = useAlertsSeries(projectId, {
    granularity: estado.granularidad,
    since: estado.desde,
    until: estado.hasta,
  });

  // Memoizado: el Brush del navegador dispara onChange en cada píxel del
  // arrastre y eso re-renderiza este componente sin que data.items cambie.
  const filas = useMemo(
    () => construirFilas(data?.items ?? [], estado.granularidad),
    [data?.items, estado.granularidad],
  );

  // Ventana del navegador: estado local que guarda para qué datos se fijó
  // (granularidad, rango de servidor y número de filas); si los datos cambian,
  // vuelve a todo el rango sin necesidad de un efecto que la reinicie.
  const claveDatos = `${estado.granularidad}|${estado.desde ?? ""}|${estado.hasta ?? ""}|${filas.length}`;
  const [ventanaGuardada, setVentanaGuardada] = useState<{ clave: string; rango: [number, number] } | null>(null);
  const ventana: [number, number] =
    ventanaGuardada && ventanaGuardada.clave === claveDatos
      ? ventanaGuardada.rango
      : [0, Math.max(filas.length - 1, 0)];
  const setVentana = (rango: [number, number]) => setVentanaGuardada({ clave: claveDatos, rango });

  const filasVisibles = filas.slice(ventana[0], ventana[1] + 1);

  return (
    <Card className="flex flex-col gap-4 p-4" data-loading={isPending || undefined}>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-4 space-y-0 p-0">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-lg font-semibold">Alertas por lote</h2>
          <p className="text-xs text-muted-foreground">
            Evolución por monitor y reparto por severidad sobre el mismo eje temporal · clic en un lote para filtrar
            la tabla · arrastra en el navegador para acotar el rango
          </p>
        </div>
        <Controles
          granularidad={estado.granularidad}
          onGranularidad={estado.setGranularidad}
          chipActivo={estado.chipActivo}
          onChip={estado.setChip}
          desde={estado.desde}
          hasta={estado.hasta}
          onRangoPersonalizado={estado.setRangoPersonalizado}
        />
      </CardHeader>

      <CardContent className="flex flex-col gap-4 p-0">
        {isError ? (
          <div className="flex flex-col items-start gap-2 py-6">
            <p className="text-sm text-destructive">{mensajeDeError(error)}</p>
            <Button type="button" variant="outline" size="sm" onClick={() => void refetch()}>
              Reintentar
            </Button>
          </div>
        ) : isPending ? (
          // Nunca se montan las gráficas con `filas` vacío mientras la
          // consulta está en curso (cambio de granularidad o rango): un
          // `BarChart`/`LineChart` sin filas calcula dominios y rejillas con
          // NaN (`<rect>`/`<line>` sueltos en la consola).
          <div className="flex flex-col gap-4">
            <Skeleton className="h-[200px] w-full" />
            <Skeleton className="h-[130px] w-full" />
            <Skeleton className="h-11 w-full" />
          </div>
        ) : filas.length === 0 ? (
          <EmptyState titulo="Sin alertas en el rango" icono={InboxIcon} />
        ) : (
          <>
            <GraficaMonitores
              filas={filasVisibles}
              granularidad={estado.granularidad}
              esDemo={esDemo}
              tramo={estado.tramo}
              onClicTramo={estado.setTramo}
              crossUnbatched={data?.cross_unbatched}
            />
            <GraficaSeveridad
              filas={filasVisibles}
              tramo={estado.tramo}
              onClicTramo={estado.setTramo}
            />
            <Navegador
              filas={filas}
              granularidad={estado.granularidad}
              inicio={ventana[0]}
              fin={ventana[1]}
              onCambio={(i, f) => setVentana([i, f])}
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}
