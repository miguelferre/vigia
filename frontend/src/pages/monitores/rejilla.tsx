/**
 * Rejilla de monitores: todas las métricas del monitor a la vez,
 * cada una con sus grupos, su umbral y su eje de fechas, en una sola
 * petición de `/timeline` (`metric_key` admite lista, hasta 20;
 * equidad tiene once métricas configuradas en `monitor.thresholds`, muy por
 * debajo del tope). Al pulsar una tarjeta, esa se amplía en el sitio
 * (`serie.tsx`) y las demás quedan debajo, sin diálogo.
 */

import { useMemo } from "react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/vigia";
import { mensajeDeError } from "@/api/client";
import { useBatches, useProject, useTimeline, type PeriodoTimeline } from "@/api/queries";
import type { Monitor } from "@/api/types";

import { TarjetaAmpliada } from "./serie";
import { TarjetaMetrica } from "./tarjeta-metrica";
import { useTipoTarea } from "@/hooks/useTipoTarea";

import { agruparPorMetrica, extraerUmbrales, mapaFaseDeLote, metricasDelMonitor, type SerieAgrupada } from "./tipos";
import { separarPorClase, umbralEfectivo } from "./umbrales-efectivos";
import { calidadSinFabrica, esEquidadError } from "./regresion-datos";
import { ordenarMetricas } from "./usar-etiqueta-metrica";

export interface RejillaMonitorProps {
  monitor: Monitor;
  projectId: number;
  periodo: PeriodoTimeline;
  /**
   * Métrica ampliada, controlada por `index.tsx`: "Cómo se ha
   * calculado" necesita saber cuál está ampliada, así que el estado ya no
   * vive aquí dentro.
   */
  metricaAmpliada: string | null;
  onCambiarMetricaAmpliada: (metrica: string | null) => void;
  /**
   * "Cómo se ha calculado" de la métrica ampliada: se pinta aquí
   * dentro, pegado a la gráfica y antes de las tarjetas minimizadas.
   * `CalculoMetricaAmpliada` decide si hay algo que pintar.
   */
  calculo: ReactNode;
}

/**
 * Rejilla adaptable a cualquier número de métricas:
 * `auto-fill` por ancho de columna se rompía igual que los breakpoints por
 * ventana con el panel de la demo abierto (la clase
 * `@container` en `<main>`); columnas por consulta de contenedor, no de
 * viewport.
 */
const CLASE_REJILLA = "grid gap-4 grid-cols-1 @md:grid-cols-2 @4xl:grid-cols-3";

export function RejillaMonitor({
  monitor,
  projectId,
  periodo,
  metricaAmpliada,
  onCambiarMetricaAmpliada,
  calculo,
}: RejillaMonitorProps) {
  const umbrales = useMemo(() => extraerUmbrales(monitor.thresholds), [monitor.thresholds]);
  // El tipo de tarea decide el orden (titulares primero en multiclase) y qué
  // umbral se dibuja; mientras carga no se pinta la rejilla (no se dibuja binario por defecto).
  const { caps, sinRango } = useTipoTarea(projectId);
  // Solo la calidad multiclase deja de evaluar los umbrales de fábrica; equidad y deriva, como siempre.
  const sinFabrica = calidadSinFabrica(caps, monitor.type);
  // Una regresión sin rango favorable solo mide el error por grupo; las medidas de
  // pertenencia no tienen valor y su motivo lo dice `EquidadRegresion`, no una tarjeta vacía por medida.
  const soloError = monitor.type === "fairness" && sinRango;
  const metricas = useMemo(() => {
    const todas = metricasDelMonitor(umbrales);
    return ordenarMetricas(soloError ? todas.filter(esEquidadError) : todas, caps, monitor.type);
  }, [umbrales, caps, monitor.type, soloError]);

  // Sin `group_code`: se piden todos los grupos y se agrupan en el cliente
  // (así una sola petición sirve tanto a las tarjetas contraídas como a la
  // ampliada, sin volver a pedir nada al cambiar de métrica dentro de ella).
  const timelineQ = useTimeline(projectId, monitor.type, metricas, undefined, periodo);
  const datos = useMemo(() => timelineQ.data?.items ?? [], [timelineQ.data]);
  // Las medidas por clase (`clase:<valor>`) no son grupos protegidos ni tienen umbral:
  // se separan de las series de siempre y van a su propia tabla en la tarjeta ampliada.
  const { porMetrica, porMetricaClase } = useMemo(() => {
    const todas = agruparPorMetrica(datos);
    const globales = new Map<string, SerieAgrupada[]>();
    const clases = new Map<string, SerieAgrupada[]>();
    for (const [m, series] of todas) {
      const partido = separarPorClase(series);
      globales.set(m, partido.globales);
      clases.set(m, partido.porClase);
    }
    return { porMetrica: globales, porMetricaClase: clases };
  }, [datos]);

  const batchesQ = useBatches(projectId);
  const faseDeLote = useMemo(() => mapaFaseDeLote(batchesQ.data?.items), [batchesQ.data]);
  // Etiqueta de cada versión, para rotular la línea de cambio de versión.
  const proyectoQ = useProject(projectId);
  const etiquetasVersion = useMemo(
    () => new Map((proyectoQ.data?.versions ?? []).flatMap((v) => (v.id === null ? [] : [[v.id, v.label] as const]))),
    [proyectoQ.data],
  );

  // Mientras `caps` carga no se sabe qué vacío toca: esqueleto, no «Sin métricas configuradas».
  if (metricas.length === 0 && caps === undefined) {
    return (
      <div className={CLASE_REJILLA} data-loading="true">
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (metricas.length === 0) {
    // En regresión la calidad nace sin umbrales; salen de la línea base. Lo mismo
    // la equidad sin rango favorable: solo mide el error por grupo y sus umbrales salen de allí.
    if (caps?.metricas === "regresion" && (monitor.type === "quality" || soloError)) {
      return (
        <EmptyState
          titulo="Umbral pendiente de la línea base"
          descripcion={
            soloError
              ? "Sin rango favorable, la equidad compara el error de cada grupo y esos umbrales salen de la línea base. Congela la línea base de la versión activa y las medidas aparecerán aquí."
              : "En una regresión los umbrales de calidad salen de la línea base. Congela la línea base de la versión activa y las métricas aparecerán aquí."
          }
        />
      );
    }
    return <EmptyState titulo="Sin métricas configuradas" descripcion="Este monitor no tiene umbrales definidos." />;
  }

  if (timelineQ.isLoading || caps === undefined) {
    return (
      <div className={CLASE_REJILLA} data-loading="true">
        {metricas.map((m) => (
          <Skeleton key={m} className="h-40 w-full" />
        ))}
      </div>
    );
  }

  if (timelineQ.isError) {
    return (
      <EmptyState
        titulo="No se pudo cargar la serie temporal"
        descripcion={mensajeDeError(timelineQ.error)}
        accion={
          <Button size="sm" variant="outline" onClick={() => timelineQ.refetch()}>
            Reintentar
          </Button>
        }
      />
    );
  }

  const seleccionada = metricaAmpliada && metricas.includes(metricaAmpliada) ? metricaAmpliada : null;
  const colapsadas = metricas.filter((m) => m !== seleccionada);

  return (
    <div id="rejilla" className="flex scroll-mt-20 flex-col gap-4">
      {seleccionada ? (
        <>
          <TarjetaAmpliada
            metrica={seleccionada}
            metricasDisponibles={metricas}
            series={porMetrica.get(seleccionada) ?? []}
            umbral={umbralEfectivo(umbrales, seleccionada, porMetrica.get(seleccionada) ?? [], sinFabrica)}
            seriesPorClase={porMetricaClase.get(seleccionada) ?? []}
            faseDeLote={faseDeLote}
            etiquetasVersion={etiquetasVersion}
            onCambiarMetrica={onCambiarMetricaAmpliada}
            onContraer={() => onCambiarMetricaAmpliada(null)}
          />
          {calculo}
        </>
      ) : null}
      <div className={CLASE_REJILLA}>
        {colapsadas.map((m) => (
          <TarjetaMetrica
            key={m}
            metrica={m}
            series={porMetrica.get(m) ?? []}
            umbral={umbralEfectivo(umbrales, m, porMetrica.get(m) ?? [], sinFabrica)}
            multiclase={sinFabrica}
            onExpandir={() => onCambiarMetricaAmpliada(m)}
            minimizada={seleccionada !== null}
          />
        ))}
      </div>
    </div>
  );
}
