/**
 * Cabecera de `/monitores/:tipo`.
 *
 * Reúne las piezas que abren la pantalla: el título con el estado, el chip
 * de grupos y las acciones (Glosario, Ver matriz de confusión, Configurar),
 * la frase que dice qué vigila este monitor (servida desde `content/`) y la
 * ventana de la última evaluación. Vive fuera de `index.tsx` porque ese
 * fichero ya estaba en 7,9 KB y el límite del proyecto son 9 KB: partir
 * primero, escribir después.
 *
 * La ventana sale de la evaluación LIGERA (`GET /evaluations`), que ya la trae
 * en la raíz: no hace falta pedir el detalle ni una ruta nueva.
 *
 * MN2a: chip "Supervisado: <attr> = <valor> ·
 * Referencia: <attr> = <valor>" desde `monitor.group_context`, solo en
 * equidad y solo si hay mapping. El generador tipa `group_context` como JSON
 * libre; `GroupContext` (`api/types-domain.ts`) da la forma real.
 *
 * MN4: el botón "Glosario" ya no vive en `frase-apertura.tsx` (se abría en
 * un sitio distinto en cada monitor porque el texto de apertura mide
 * distinto); sale de aquí, con el mismo sitio fijo en los tres monitores.
 */

import { PageHeader, StateBadge, CabeceraVentana } from "@/components/vigia";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ETIQUETA_MONITOR, metricLabel } from "@/lib/metrics";
import { GlosarioSheet } from "@/components/vigia/GlosarioSheet";
import { useGuionDemo } from "@/api/queries-contenido";
import { useProject } from "@/api/queries";
import { useAvisoLineaBase, useVersionActiva } from "@/api/queries-monitor-proyecto";
import { nombreVariable } from "@/lib/dominio-caracteristicas";
import { formatoEtiquetaGrupo } from "@/components/vigia/formato-grupo";
import { useCan } from "@/session/session";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import type { Evaluation, Monitor, MonitorType } from "@/api/types";
import type { GroupContext } from "@/api/types-domain";

import { useState } from "react";
import { Link } from "react-router";
import { AlertTriangleIcon, BookOpenIcon } from "lucide-react";

import { AvisoUmbralDeFabrica } from "./aviso-fabrica";
import { AvisoMetricasSinDatos } from "./aviso-sin-datos";
import { FraseAperturaMonitor } from "./frase-apertura";
import { EnlaceMatriz } from "./matriz-dialog";
import {
  etiquetaCriterio,
  extraerUmbrales,
  hayUmbralDeFabrica,
  origenesPorMetrica,
  type OrigenMetrica,
  type ThresholdOrigen,
} from "./tipos";
import { calidadSinFabrica } from "./regresion-datos";
import { umbralSinEfectoEnMulticlase } from "./umbrales-efectivos";

export interface CabeceraMonitorProps {
  monitorType: MonitorType;
  monitor: Monitor | undefined;
  ultimaEvaluacion: Evaluation | null;
  onConfigurar: () => void;
  /** Métrica ampliada o principal, para el cuerpo del glosario. `null` si no hay ninguna todavía. */
  metricKeyGlosario: string | null;
  /** Proyecto activo, para el aviso de línea base y el método del intervalo de la versión). */
  projectId: number;
}

/** `criterio_clinico` se llama «criterio del responsable». */
function etiquetaOrigen(origen: ThresholdOrigen, dominio: string | undefined): string {
  if (origen === "criterio_clinico") return etiquetaCriterio(dominio);
  return {
    linea_base: "línea base",
    fabricante: "fabricante",
    politica_organizacion: "política de la organización",
    fabrica: "fábrica",
  }[origen];
}

/**
 * Origen de cada umbral configurado en el monitor, con su nota;
 * si alguno queda en fábrica (sin calibrar para este modelo), el aviso fijo
 * una sola vez, no por métrica.
 */
function OrigenUmbrales({ monitor, dominio }: { monitor: Monitor; dominio: string | undefined }) {
  const { caps } = useTipoTarea(monitor.project_id);
  // En calidad multiclase y de regresión los umbrales de fábrica no se evalúan: no se listan como umbrales en uso.
  const sinFabrica = calidadSinFabrica(caps, monitor.type);
  const entradas = extraerUmbrales(monitor.thresholds).filter((e) => !(sinFabrica && umbralSinEfectoEnMulticlase(e)));
  const filas = origenesPorMetrica(entradas);
  if (filas.length === 0) return null;
  // Sobre las entradas crudas, no sobre `filas` ya agrupadas por
  // métrica (corrección de la lente de contrato: agrupar puede perder el
  // origen "fabrica" de un límite cuando el otro límite de la misma métrica
  // ya tiene un origen explícito).
  const hayFabrica = hayUmbralDeFabrica(entradas);
  return (
    <details className="text-xs">
      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Origen de los umbrales</summary>
      <div className="mt-2 flex flex-col gap-1">
        {filas.map((f) => (
          <FilaOrigenMetrica key={f.metricKey} fila={f} dominio={dominio} />
        ))}
      </div>
      {hayFabrica ? (
        <p className="mt-2 inline-flex items-start gap-1.5" style={{ color: "var(--state-warn)" }}>
          <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>umbral de fábrica: no calibrado para este modelo</span>
        </p>
      ) : null}
    </details>
  );
}

/**
 * Una fila de `OrigenUmbrales`. Si el límite inferior y el superior de la
 * misma métrica comparten origen y nota, una sola línea; si difieren (p. ej.
 * uno con línea base calibrada y el otro de fábrica sin calibrar), una
 * línea con los dos orígenes por separado para no esconder ninguno.
 */
function FilaOrigenMetrica({ fila, dominio }: { fila: OrigenMetrica; dominio: string | undefined }) {
  const { low, high } = fila;
  if (low && high && (low.origen !== high.origen || (low.nota ?? null) !== (high.nota ?? null))) {
    return (
      <p>
        <span className="font-medium">{metricLabel(fila.metricKey)}:</span> {etiquetaOrigen(low.origen, dominio)} (límite
        inferior)
        {low.nota ? <span className="text-muted-foreground"> · {low.nota}</span> : null}
        {" · "}
        {etiquetaOrigen(high.origen, dominio)} (límite superior)
        {high.nota ? <span className="text-muted-foreground"> · {high.nota}</span> : null}
      </p>
    );
  }
  const unico = low ?? high;
  if (!unico) return null;
  return (
    <p>
      <span className="font-medium">{metricLabel(fila.metricKey)}:</span> {etiquetaOrigen(unico.origen, dominio)}
      {unico.nota ? <span className="text-muted-foreground"> · {unico.nota}</span> : null}
    </p>
  );
}

/**
 * Si la versión activa no tiene línea base congelada, el
 * aviso exacto de `GET /projects/{id}` con enlace a congelar (pestaña
 * «Versiones» de `/modelos/{id}`; el botón de activar y congelar es de
 * h3-artefacto). Solo en el monitor de deriva.
 */
function AvisoLineaBaseSinCongelar({ projectId, monitorType }: { projectId: number; monitorType: MonitorType }) {
  const aviso = useAvisoLineaBase(projectId);
  if (monitorType !== "drift" || !aviso) return null;
  return (
    <p className="inline-flex items-start gap-1.5 text-xs" style={{ color: "var(--state-warn)" }}>
      <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>
        {aviso}{" "}
        <Link to={`/modelos/${projectId}#versiones`} className="font-medium underline">
          Congelar línea base
        </Link>
      </span>
    </p>
  );
}

/**
 * Chip de grupos: solo equidad, solo con `group_context` presente.
 * Exportado para reutilizarlo en la tarjeta de monitor
 * de `/modelos/:id#monitores` sin duplicar la lógica de `nombreVariable` y
 * `formatoEtiquetaGrupo`.
 */
export function ChipGrupos({ monitorType, monitor }: { monitorType: MonitorType; monitor: Monitor | undefined }) {
  const dominio = useGuionDemo().data?.dominio;
  if (monitorType !== "fairness") return null;
  const ctx = (monitor?.group_context as GroupContext | undefined) ?? null;
  if (!ctx) return null;
  const atributo = nombreVariable(ctx.protected_attr, dominio);
  return (
    <Badge variant="outline" className="w-fit max-w-full whitespace-normal text-left font-normal">
      Supervisado: {atributo} = {ctx.supervised.map(formatoEtiquetaGrupo).join(", ")} · Referencia: {atributo} ={" "}
      {ctx.reference.map(formatoEtiquetaGrupo).join(", ")}
    </Badge>
  );
}

export function CabeceraMonitor({
  monitorType,
  monitor,
  ultimaEvaluacion,
  onConfigurar,
  metricKeyGlosario,
  projectId,
}: CabeceraMonitorProps) {
  const [glosarioAbierto, setGlosarioAbierto] = useState(false);
  const puedeConfig = useCan("config");
  // El método del intervalo es de la versión, no de la evaluación
  // concreta; solo tiene sentido en equidad.
  const { version } = useVersionActiva(projectId);
  const dominio = useProject(projectId).data?.domain;
  // Una regresión no tiene matriz de confusión (`caps.matriz` es `null`).
  const { caps } = useTipoTarea(projectId);
  const intervalMethod = monitorType === "fairness" ? (version?.fairness_interval_method ?? null) : null;
  return (
    <div id="cabecera" className="flex scroll-mt-20 flex-col gap-3">
      <PageHeader
        titulo={`Monitor de ${ETIQUETA_MONITOR[monitorType].toLowerCase()}`}
        marcaTiempo={
          monitor && ultimaEvaluacion ? { etiqueta: "Última evaluación", iso: ultimaEvaluacion.created_at } : undefined
        }
        acciones={
          monitor ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted-foreground">
                {monitor.enabled ? "Activado" : "Desactivado"}
              </span>
              <StateBadge estado={ultimaEvaluacion?.worst_state ?? "sin_datos"} size="sm" />
              <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setGlosarioAbierto(true)}>
                <BookOpenIcon className="size-4" aria-hidden="true" />
                Glosario
              </Button>
              {monitorType === "quality" && caps?.matriz ? <EnlaceMatriz evaluationId={ultimaEvaluacion?.id ?? null} /> : null}
              {puedeConfig ? (
                <Button size="sm" variant="outline" onClick={onConfigurar}>
                  Configurar
                </Button>
              ) : null}
            </div>
          ) : undefined
        }
      />
      <ChipGrupos monitorType={monitorType} monitor={monitor} />
      <FraseAperturaMonitor monitorType={monitorType} projectId={projectId} />
      {monitor ? (
        <AvisoUmbralDeFabrica
          projectId={projectId}
          monitor={monitor}
          onConfigurar={onConfigurar}
          puedeConfigurar={puedeConfig}
        />
      ) : null}
      {monitor ? <OrigenUmbrales monitor={monitor} dominio={dominio} /> : null}
      <AvisoLineaBaseSinCongelar projectId={projectId} monitorType={monitorType} />
      <AvisoMetricasSinDatos evaluationId={ultimaEvaluacion?.id ?? null} />
      {ultimaEvaluacion?.window ? (
        <CabeceraVentana window={ultimaEvaluacion.window} intervalMethod={intervalMethod} />
      ) : null}
      <GlosarioSheet
        open={glosarioAbierto}
        onOpenChange={setGlosarioAbierto}
        monitorType={monitorType}
        metricKey={metricKeyGlosario}
      />
    </div>
  );
}

export default CabeceraMonitor;
