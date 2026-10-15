/**
 * `/monitores/:tipo` — serie temporal, tabla de evaluaciones, detalle y
 * configuración de un monitor.
 */

import { useMemo } from "react";
import { useParams, useSearchParams } from "react-router";

import { BotonVolver, SelectorPeriodo, EmptyState } from "@/components/vigia";
import { mensajeDeError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMonitors, useEvaluations } from "@/api/queries";
import { useSession } from "@/session/session";
import { useTitulo } from "@/hooks/useTitulo";
import { ETIQUETA_MONITOR, RUTA_MONITOR } from "@/lib/metrics";
import { GroupContextProvider } from "@/components/vigia/contexto-grupos";

import { CabeceraMonitor } from "./cabecera";
import { CalculoMetricaAmpliada } from "./calculo";
import { DistribucionesDeriva } from "./DistribucionesDeriva";
import { CalidadClases } from "./CalidadClases";
import { EquidadClases } from "./EquidadClases";
import { RegresionAbajo, RegresionArriba } from "./bloques-regresion";
import { RejillaMonitor } from "./rejilla";
import { EvaluacionesMonitor } from "./evaluaciones";
import { DetalleEvaluacion } from "./detalle-evaluacion";
import { ConfiguracionMonitor } from "./configuracion";
import { AvisoEvaluacionNoCargada, AvisoPeriodoInvalido } from "./avisos";
import { groupContextDeMonitor, useMetricKeyGlosario } from "./contexto-monitor";
import { MonitorDesconocido, SinProyectoActivo } from "./estados-vacios";
import { useConfigAbierta, useMetricaAmpliada, usePeriodoMonitor } from "./usar-estado-pantalla";
import { useSeleccionEvaluacion } from "./usar-seleccion-evaluacion";
import { useUltimaEvaluacion } from "./usar-ultima-evaluacion";

export default function Monitores() {
  const { tipo } = useParams<{ tipo: string }>();
  const { projectId } = useSession();
  const monitorType = tipo ? RUTA_MONITOR[tipo] : undefined;
  // El registro de las fases del guion de la demo
  // ya no se dispara aquí; `DemoGuiadaProvider` (montado dentro de
  // `BrowserRouter`, fuera de esta pantalla) ya llama a `useGuionDemo()` sin
  // condición, y cualquier componente de esta página que necesite `dominio`
  // (`cabecera.tsx`, `DrillImpactoDispar.tsx`, `deriva-variables.tsx`...) lo
  // pide con su propio `useGuionDemo()`, que comparte la misma caché.
  useTitulo(monitorType ? `Monitor de ${ETIQUETA_MONITOR[monitorType].toLowerCase()}` : "Monitor");

  const [searchParams] = useSearchParams();
  // Estado local sin datos del servidor, partido a `usar-estado-pantalla.ts`
  // por tamaño: la hoja «Configurar» (con el hash `#configurar`), la métrica
  // ampliada de la rejilla ("Cómo se ha calculado" la necesita fuera de
  // `RejillaMonitor") y el periodo, que se pasa a la
  // rejilla para pedir `/timeline`.
  const [configAbierta, setConfigAbierta] = useConfigAbierta();
  const [metricaAmpliada, setMetricaAmpliada] = useMetricaAmpliada(monitorType);
  const { periodoValor, setPeriodoValor, periodo, periodoInvalido } = usePeriodoMonitor();
  // `?variable=<col>` ya no amplía `feature_drift_score`:
  // el panel de variables está siempre visible en el bloque
  // «Distribuciones» y `DerivaVariables` lee `?variable` por su cuenta
  // (self-contained, en `deriva-variables.tsx`) para seleccionar la fila.

  const monitoresQ = useMonitors(projectId);
  const evaluacionesQ = useEvaluations(
    projectId,
    monitorType ? { monitor_type: monitorType, limit: 500 } : undefined,
    { enabled: projectId !== null && monitorType !== undefined },
  );

  const monitor = useMemo(
    () => monitoresQ.data?.items.find((m) => m.type === monitorType),
    [monitoresQ.data, monitorType],
  );

  // MN3 y MN2a (`contexto-monitor.ts`, partido de aquí por tamaño).
  const metricKeyGlosario = useMetricKeyGlosario(monitor, metricaAmpliada);
  const groupContext = groupContextDeMonitor(monitor);

  const evaluaciones = useMemo(
    () => [...(evaluacionesQ.data?.items ?? [])].sort((a, b) => (b.id ?? 0) - (a.id ?? 0)),
    [evaluacionesQ.data],
  );
  // `?lote=<batch_id>`: la demo guiada lo pone en los pasos de
  // monitor para que la pantalla abra con la evaluación del lote que narra el
  // paso, no con la última del proyecto. Sin el parámetro, o con un lote sin
  // evaluación de este monitor, manda la última, como siempre.
  // `usar-ultima-evaluacion.ts`: la más reciente por fecha (la del último punto de la serie).
  const ultimaEvaluacion = useUltimaEvaluacion(evaluaciones, searchParams.get("lote"));

  // `usar-seleccion-evaluacion.ts`: `?evaluacion=<id>` (enlazada desde el
  // diario) selecciona la fila y abre el detalle en el panel lateral; aviso
  // breve si el id no está entre las evaluaciones cargadas.
  const { evaluacionId, avisoEvaluacion, seleccionarEvaluacion, cerrarEvaluacion } = useSeleccionEvaluacion(
    evaluaciones,
    evaluacionesQ.isLoading,
  );

  if (!monitorType) {
    return <MonitorDesconocido tipo={tipo} />;
  }

  if (projectId === null) {
    return <SinProyectoActivo monitorType={monitorType} />;
  }

  return (
    <GroupContextProvider value={groupContext}>
    <div className="flex flex-col gap-8" data-loading={monitoresQ.isLoading || undefined}>
      {searchParams.get("evaluacion") !== null ? (
        <BotonVolver rutaPadre="/diario" etiquetaPadre="el diario" className="self-start" />
      ) : null}
      <CabeceraMonitor
        monitorType={monitorType}
        monitor={monitor}
        ultimaEvaluacion={ultimaEvaluacion}
        onConfigurar={() => setConfigAbierta(true)}
        metricKeyGlosario={metricKeyGlosario}
        projectId={projectId}
      />

      {monitoresQ.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : monitoresQ.isError ? (
        <EmptyState
          titulo="No se pudieron cargar los monitores"
          descripcion={mensajeDeError(monitoresQ.error)}
          accion={
            <Button size="sm" variant="outline" onClick={() => monitoresQ.refetch()}>
              Reintentar
            </Button>
          }
        />
      ) : !monitor ? (
        <EmptyState
          titulo="Este monitor no está configurado en el proyecto"
          descripcion="No hay ningún monitor de este tipo en el proyecto activo."
        />
      ) : (
        <>
          {avisoEvaluacion !== null ? <AvisoEvaluacionNoCargada id={avisoEvaluacion} /> : null}
          {/* En multiclase, qué clases cuentan como favorables y la tabla por clase, plegada. */}
          {monitorType === "fairness" ? (
            <EquidadClases evaluationId={ultimaEvaluacion?.id ?? null} projectId={projectId} />
          ) : null}
          <RegresionArriba monitorType={monitorType} evaluationId={ultimaEvaluacion?.id ?? null} projectId={projectId} />
          <SelectorPeriodo value={periodoValor} onChange={setPeriodoValor} idBase="monitor-periodo" />
          {periodoInvalido ? (
            <AvisoPeriodoInvalido />
          ) : (
            <RejillaMonitor
              monitor={monitor}
              projectId={projectId}
              periodo={periodo}
              metricaAmpliada={metricaAmpliada}
              onCambiarMetricaAmpliada={setMetricaAmpliada}
              calculo={
                <CalculoMetricaAmpliada
                  evaluationId={ultimaEvaluacion?.id ?? null}
                  metricKey={metricaAmpliada}
                  distribucionesEnPantalla={monitorType === "drift"}
                />
              }
            />
          )}
          <RegresionAbajo
            monitorType={monitorType}
            evaluationId={ultimaEvaluacion?.id ?? null}
            projectId={projectId}
            evaluaciones={evaluaciones}
          />
          {/* En multiclase, la matriz `k x k` y la tabla por clase de la última evaluación. */}
          {monitorType === "quality" ? (
            <CalidadClases evaluationId={ultimaEvaluacion?.id ?? null} projectId={projectId} />
          ) : null}
          {monitorType === "drift" ? (
            <DistribucionesDeriva
              evaluationId={ultimaEvaluacion?.id ?? null}
              projectId={projectId}
              evaluaciones={evaluaciones}
            />
          ) : null}
          <EvaluacionesMonitor
            evaluaciones={evaluaciones}
            projectId={projectId}
            cargando={evaluacionesQ.isLoading}
            onSeleccionar={seleccionarEvaluacion}
          />
          <DetalleEvaluacion
            evaluacionId={evaluacionId}
            open={evaluacionId !== null}
            onOpenChange={(open) => !open && cerrarEvaluacion()}
          />
          <ConfiguracionMonitor
            monitor={monitor}
            projectId={projectId}
            open={configAbierta}
            onOpenChange={setConfigAbierta}
          />
        </>
      )}
    </div>
    </GroupContextProvider>
  );
}
