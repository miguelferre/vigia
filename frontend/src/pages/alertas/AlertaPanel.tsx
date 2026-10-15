/**
 * Panel lateral de detalle de una alerta (artboard `PanelLateral`;
 * se carga con `React.lazy` desde donde se abra).
 *
 * Mismo `Sheet` que `GlosarioSheet` (`ui/sheet.tsx`), sin salir de la tabla
 * ni del cuadro de mando. Reutiliza `qk.alert` (misma clave que
 * `detalle.tsx` y `useProtocoloHitos`, sin petición duplicada), `Historial`
 * y `QueSignificaCalculo` (compartido con `detalle.tsx`) para
 * que el panel y el monitor den siempre la misma fórmula instanciada. El pie
 * (catálogo plegado y botón principal) vive en `PieAlertaPanel.tsx` y sus
 * diálogos en `DialogosAlertaPanel.tsx`, aparte para no pasar de 9 KB aquí.
 */

import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { qk } from "@/api/queries";
import type { ActorBody, Alert, AlertDetail, Batch } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { MONITOR_A_RUTA } from "@/lib/metrics";
import { useEvaluationDetail } from "@/pages/monitores/usarEvaluacion";
import { Historial } from "./historial";
import { useProtocoloHitos } from "./useProtocoloHitos";
import { AvisoRetirada, ChipsCabecera, Metadatos } from "./AlertaPanelCabecera";
import { QueSignificaCalculo } from "./QueSignificaCalculo";
import { PieAlertaPanel } from "./PieAlertaPanel";
import { DialogosAlertaPanel } from "./DialogosAlertaPanel";

const ProtocoloHitosCompacto = lazy(() => import("./ProtocoloHitosCompacto"));

export interface AlertaPanelProps {
  alertId: number | null;
  onClose: () => void;
}

export function AlertaPanel({ alertId, onClose }: AlertaPanelProps) {
  const queryClient = useQueryClient();
  const tituloRef = useRef<HTMLHeadingElement>(null);
  const [cerrarAbierto, setCerrarAbierto] = useState(false);
  // Qué diálogo del hito actual está abierto; los tres viven en
  // `HitoDialogos.tsx`/`DialogoDecidir.tsx`, con su propia mutación cada uno.
  const [dialogoHito, setDialogoHito] = useState<"triaje" | "investigacion" | "decision" | null>(null);

  const alerta = useQuery({
    queryKey: qk.alert(alertId),
    queryFn: () => api.get<AlertDetail>(`/alerts/${alertId}`),
    enabled: alertId !== null,
  });
  const evaluacion = useEvaluationDetail(alerta.data?.last_evaluation_id ?? null);
  const batchId = alerta.data?.batch_id ?? null;
  const lote = useQuery({
    queryKey: qk.batch(batchId),
    queryFn: () => api.get<Batch>(`/batches/${batchId}`),
    enabled: batchId !== null,
  });

  // `useProtocoloHitos` (lee los textos de `protocol_steps` de
  // esta misma alerta) también da `hitoActual`, que gobierna el botón
  // principal del pie: no se llama aparte, no es parte del
  // componente perezoso porque necesita correr aunque el `import()` de
  // `ProtocoloHitosCompacto` todavía no haya resuelto.
  const protocolo = useProtocoloHitos(alertId);

  const cerrar = useMutation({
    mutationFn: (cuerpo: ActorBody) => api.post<Alert>(`/alerts/${alertId}/close`, cuerpo),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: qk.alert(alertId) });
      await queryClient.invalidateQueries({ queryKey: ["alerts"] });
      toast.success("Alerta cerrada.");
      setCerrarAbierto(false);
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  useEffect(() => {
    if (alertId !== null) tituloRef.current?.focus();
  }, [alertId, alerta.data]);

  const a = alerta.data;
  const rutaMonitor = a ? MONITOR_A_RUTA[a.monitor_type] : undefined;

  return (
    // `modal={false}` y, con la demo guiada desplegada, la hoja se aparta 20 rem
    // del borde (`[data-demo-activa]` en `<html>`, AppShell) para no tapar el
    // panel de la demo (paso 21).
    <Sheet modal={false} open={alertId !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        id="panel"
        side="right"
        className="flex w-full scroll-mt-20 flex-col gap-4 overflow-y-auto p-5 sm:max-w-lg [[data-demo-activa]_&]:lg:right-80"
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          tituloRef.current?.focus();
        }}
        // Sin modal, un clic fuera (la tabla, el panel de la demo) no cierra la
        // hoja: solo Escape y la X. Si cerrara, su `onClose` quitaría `?panel=`
        // y pisaría la navegación que ese mismo clic acaba de pedir.
        onInteractOutside={(e) => e.preventDefault()}
      >
        <SheetHeader className="sr-only">
          <SheetTitle>Detalle de la alerta</SheetTitle>
        </SheetHeader>
        {alerta.isLoading ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : !a ? (
          <p className="text-md text-tertiary">No se ha podido cargar esta alerta.</p>
        ) : (
          <>
            <ChipsCabecera alerta={a} lote={lote.data} />
            <h1
              ref={tituloRef}
              tabIndex={-1}
              className="font-display text-2xl font-semibold tracking-[-0.15px] leading-tight outline-none"
            >
              {a.title}
            </h1>
            <Metadatos alerta={a} />
            <Link to={`/alertas/${a.id}`} className="text-md text-link hover:underline self-start">
              Abrir la página de la alerta
            </Link>
            <AvisoRetirada alerta={a} />

            <QueSignificaCalculo
              metricKey={a.metric_key}
              evaluacion={evaluacion.data}
              evaluacionCargando={evaluacion.isLoading}
              projectId={a.project_id}
            />

            <Card>
              <CardHeader className="flex flex-row items-center justify-between gap-2">
                <CardTitle className="text-md">
                  Protocolo ({protocolo.hechos}/{protocolo.total || 5})
                </CardTitle>
                <Link to={`/alertas/${a.id}`} className="text-md text-link hover:underline">
                  Ver protocolo
                </Link>
              </CardHeader>
              <CardContent>
                <Suspense fallback={<Skeleton className="h-24 w-full" />}>
                  <ProtocoloHitosCompacto pasos={protocolo.pasos} cargando={protocolo.cargando} />
                </Suspense>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-md">Historial ({a.history?.length ?? 0})</CardTitle>
              </CardHeader>
              <CardContent>
                <Historial entradas={a.history} alerta={a} />
              </CardContent>
            </Card>

            <PieAlertaPanel
              alerta={a}
              alertId={alertId}
              hitoActual={protocolo.hitoActual}
              rutaMonitor={rutaMonitor}
              onCerrarConMotivo={() => setCerrarAbierto(true)}
              onAbrirDialogoHito={setDialogoHito}
            />

            <DialogosAlertaPanel
              alertId={a.id ?? alertId}
              cerrarAbierto={cerrarAbierto}
              onCerrarAbiertoChange={setCerrarAbierto}
              onConfirmCerrar={async (cuerpo) => {
                await cerrar.mutateAsync(cuerpo);
              }}
              dialogoHito={dialogoHito}
              onDialogoHitoChange={setDialogoHito}
            />
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

export default AlertaPanel;
