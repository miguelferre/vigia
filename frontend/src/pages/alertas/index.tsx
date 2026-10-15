/**
 * Lista de alertas del proyecto (artboard `Alertas`, ruta `/alertas`).
 *
 * Estado y severidad se filtran en servidor (`GET /projects/{id}/alerts?
 * status=&severity=`); monitor y búsqueda son cliente, sobre esa misma
 * página (la API no filtra por texto). El chip "Abierta" incluye también
 * `reconocida`. `?panel=<id>` abre el panel lateral de detalle
 * (enlace directo); `?resaltar=<id>` marca una
 * fila al llegar desde fuera (onboarding, CX-1 y el paso de la demo guiada
 * que enseña una alerta): la desplaza a la vista y la
 * resalta unos segundos, sin abrir la hoja, que abre el usuario con un clic.
 *
 * Columnas en `columnas.tsx`, filtros en `Filtros.tsx`, panel lateral en
 * `AlertaPanel.tsx`, acciones en lote en `SeleccionAcciones.tsx`, diálogos
 * en `DialogosAlertas.tsx`; el resto del estado vive en los hooks
 * `useFiltrosAlertas.ts`, `useAlertasUrl.ts`, `useEvaluacionesDeAlertas.ts`
 * y `useAccionesAlertas.ts` (aparte para no pasar de 9 KB aquí). `?monitor=`
 * inicializa el selector al montar (enlace «Ver alertas» de la
 * tarjeta de cruzadas del cuadro), igual que `?estado=`.
 */

import { lazy, Suspense, useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "react-router";
import { DownloadIcon } from "lucide-react";

import { useAlerts, useBatches } from "@/api/queries";
import { useSession } from "@/session/session";
import { Button } from "@/components/ui/button";
import { DataTable, PageHeader, SinProyecto } from "@/components/vigia";
import { useTitulo } from "@/hooks/useTitulo";
import { formatoRelativo } from "@/lib/fechas";
import { useFormatoMetrica } from "@/components/vigia/useFormatoMetrica";
import { columnasAlertas } from "./columnas";
import { Filtros } from "./Filtros";
import { LIMITE_PAGINA, contarPorSegmento, esRetirada, exportarAlertas, normaliza, resumenFilas } from "./alertas-utils";
import { usePanelAlerta, useResaltadoAlerta } from "./useAlertasUrl";
import { useFiltrosAlertas, useSeleccionAlertas } from "./useFiltrosAlertas";
import { useEvaluacionesDeAlertas } from "./useEvaluacionesDeAlertas";
import { useAccionesAlertas } from "./useAccionesAlertas";
import { DialogosAlertas } from "./DialogosAlertas";
import { VacioAlertas } from "./VacioAlertas";

const AlertaPanel = lazy(() => import("./AlertaPanel"));
const SeleccionAcciones = lazy(() => import("./SeleccionAcciones"));

export default function AlertasIndex() {
  useTitulo("Alertas");
  const { projectId } = useSession();
  const [params, setParams] = useSearchParams();

  const { panelAlertId, abrirPanel, cerrarPanel } = usePanelAlerta(params, setParams);
  const { seleccion, setSeleccion, alternarSeleccion, alternarTodas } = useSeleccionAlertas();
  const {
    segmento, setSegmento,
    severidades, alternarSeveridad,
    monitor, setMonitor,
    busqueda, setBusqueda,
    offset, setOffset,
    statusQuery, severityQuery, sinSeveridades,
  } = useFiltrosAlertas(params, setSeleccion);

  const refBusqueda = useRef<HTMLInputElement>(null);

  // Ctrl K enfoca el buscador (artboard `Alertas`): igual que el "Ctrl K" de
  // la barra lateral de `/cuadro`, solo dentro de esta pantalla.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        refBusqueda.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const todas = useAlerts(projectId, null);
  const filtradas = useAlerts(
    projectId,
    { status: statusQuery, severity: severityQuery, offset, limit: LIMITE_PAGINA },
    { enabled: projectId !== null && !sinSeveridades },
  );
  // Las retiradas no vienen por defecto; su recuento es el total de otra consulta.
  const retiradas = useAlerts(projectId, { status: "retirada", limit: 1 });
  const batches = useBatches(projectId);

  const filasPagina = useMemo(
    () => (sinSeveridades ? [] : (filtradas.data?.items ?? [])),
    [filtradas.data, sinSeveridades],
  );
  const filas = useMemo(() => {
    const q = normaliza(busqueda.trim());
    return filasPagina.filter((a) => {
      if (monitor !== "todos" && a.monitor_type !== monitor) return false;
      if (q.length > 0 && !normaliza(`${a.title} ${a.metric_key}`).includes(q)) return false;
      return true;
    });
  }, [filasPagina, monitor, busqueda]);

  const { idResaltado, resaltadoApagado } = useResaltadoAlerta(params, filas);
  const { formato } = useFormatoMetrica(projectId);
  const { loteDeAlerta, medidaDeAlerta, ficheroDeAlerta } = useEvaluacionesDeAlertas(filasPagina, batches.data?.items);
  const { cerrarIndividual, setCerrarIndividual, accionLote, setAccionLote, cerrarIndividualMut, bulkMut } =
    useAccionesAlertas(projectId, seleccion, setSeleccion);

  const conteo = useMemo(
    () => ({ ...contarPorSegmento(todas.data?.items ?? []), retirada: retiradas.data?.total ?? 0 }),
    [todas.data, retiradas.data],
  );

  if (projectId === null) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader titulo="Alertas" />
        <SinProyecto que="sus alertas" />
      </div>
    );
  }

  const columnas = columnasAlertas({
    formato,
    loteDeAlerta,
    ficheroDeAlerta,
    medidaDeAlerta,
    seleccionadas: seleccion,
    onToggleSeleccion: alternarSeleccion,
    onToggleTodas: () => alternarTodas(filas.filter((a) => !esRetirada(a)).map((a) => a.id).filter((id): id is number => id !== null)),
    onAbrirPanel: abrirPanel,
    onCerrarConMotivo: setCerrarIndividual,
  });
  const { ultimaActualizacion, porSeveridad } = resumenFilas(filas);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        titulo="Alertas"
        descripcion="Ningún monitor las cierra: el cierre siempre tiene actor y motivo."
        acciones={
          <Button type="button" variant="outline" size="sm" onClick={() => exportarAlertas(filas, projectId)} disabled={filas.length === 0}>
            <DownloadIcon className="size-4" aria-hidden="true" />
            Exportar
          </Button>
        }
      />
      <Filtros
        ref={refBusqueda}
        segmento={segmento}
        onSegmentoChange={(seg) => {
          setSegmento(seg);
          setOffset(0);
        }}
        conteo={conteo}
        severidades={severidades}
        onToggleSeveridad={alternarSeveridad}
        monitor={monitor}
        onMonitorChange={setMonitor}
        busqueda={busqueda}
        onBusquedaChange={setBusqueda}
      />
      <div id="cx1" className="scroll-mt-20">
        <DataTable
          data={filas}
          columns={columnas}
          total={monitor === "todos" && busqueda.trim() === "" ? filtradas.data?.total : undefined}
          offset={offset}
          limit={LIMITE_PAGINA}
          onPageChange={setOffset}
          cargando={!sinSeveridades && filtradas.isLoading}
          titulo="Alertas del proyecto"
          claveFila={(fila) => fila.id ?? 0}
          onRowClick={(fila) => (fila.id !== null ? abrirPanel(fila.id) : undefined)}
          filaResaltada={(fila) => idResaltado !== null && !resaltadoApagado && fila.id === idResaltado}
          vacio={<VacioAlertas sinSeveridades={sinSeveridades} error={filtradas.isError} errorDetalle={filtradas.error} onReintentar={() => void filtradas.refetch()} />}
        />
        <div className="flex flex-wrap items-center gap-4 border-t border-border px-1 pt-3 text-md text-tertiary">
          <span>{filas.length} alertas en vista</span>
          <span>
            {porSeveridad.alta} Alta · {porSeveridad.media} Media
          </span>
          {ultimaActualizacion ? <span className="ml-auto">Actualizado {formatoRelativo(ultimaActualizacion)}</span> : null}
        </div>
      </div>
      {seleccion.size > 0 ? (
        <div className="sticky bottom-4 z-10 flex justify-center">
          <Suspense fallback={null}>
            <SeleccionAcciones
              seleccionadas={seleccion.size}
              onLimpiar={() => setSeleccion(new Set())}
              onPonerEnObservacion={() => setAccionLote("acknowledge")}
              onCerrarConMotivo={() => setAccionLote("close")}
              onExportar={() => exportarAlertas(filas.filter((a) => a.id !== null && seleccion.has(a.id)), projectId)}
            />
          </Suspense>
        </div>
      ) : null}

      <Suspense fallback={null}>
        <AlertaPanel alertId={panelAlertId} onClose={cerrarPanel} />
      </Suspense>

      <DialogosAlertas
        cerrarIndividual={cerrarIndividual}
        onCerrarIndividualOpenChange={(open) => !open && setCerrarIndividual(null)}
        onConfirmCerrarIndividual={async (cuerpo) => {
          await cerrarIndividualMut.mutateAsync(cuerpo);
          setCerrarIndividual(null);
        }}
        accionLote={accionLote}
        onAccionLoteOpenChange={(open) => !open && setAccionLote(null)}
        onConfirmAccionLote={async (cuerpo) => {
          await bulkMut.mutateAsync(cuerpo);
        }}
        seleccionSize={seleccion.size}
      />
    </div>
  );
}
