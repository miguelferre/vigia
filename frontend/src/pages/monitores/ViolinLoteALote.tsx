/**
 * Segunda pestaña del panel de variables de deriva: un violín por lote para la variable numérica elegida, con la línea
 * base destacada. Datos vía `useEvaluationDetails`; el dibujo vive en
 * `violin-svg.tsx`. `deriva-variables.tsx` la monta solo con `lotes`.
 */

import { useMemo } from "react";
import type { ReactElement } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useAnchoContenedor } from "@/hooks/useAnchoContenedor";
import type { EvaluationDetail, JsonObject } from "@/api/types";

import { extraerVariables } from "./deriva-variables-datos";
import { nDeVentana } from "./tipos";
import { useEvaluationDetails } from "./usarEvaluacion";
import { ViolinSvg } from "./violin-svg";
import { prepararViolines } from "./violin-lote-a-lote-datos";
import type { LoteDeriva, VariableEnLote } from "./violin-lote-a-lote-datos";

export interface ViolinLoteALoteProps {
  feature: string;
  featureLabel: string;
  lotes: LoteDeriva[];
}

/** Tramos de `feature` en el detalle de una evaluación de deriva, o `null` si no se pueden usar. */
function variableDeDetalle(detalle: EvaluationDetail | undefined, feature: string): VariableEnLote | null {
  if (!detalle) return null;
  const details = (detalle.result?.details as JsonObject | undefined) ?? null;
  const fila = extraerVariables(details, undefined).find((f) => f.feature === feature);
  if (!fila) return null;
  const ventana = detalle.window;
  const version = ventana ? ventana.model_version : undefined;
  return {
    edges: fila.binEdges,
    countsBase: fila.countsBase,
    countsActual: fila.countsActual,
    psi: fila.psi,
    ksStat: fila.ksStat,
    ksP: fila.ksP,
    nVentana: nDeVentana(detalle.window),
    modelVersion: typeof version === "string" ? version : null,
  };
}

export function ViolinLoteALote({ feature, featureLabel, lotes }: ViolinLoteALoteProps): ReactElement {
  const queries = useEvaluationDetails(lotes.map((l) => l.evaluationId));
  const [ref, ancho] = useAnchoContenedor<HTMLDivElement>();

  const cargando = queries.some((q) => q.isLoading);
  const errores = queries.filter((q) => q.isError).length;

  const preparado = useMemo(() => {
    const entradas = lotes
      .map((lote, i) => ({ lote, query: queries[i] }))
      .filter(({ query }) => !query?.isError)
      .map(({ lote, query }) => ({ lote, variable: variableDeDetalle(query?.data, feature) }));
    return prepararViolines(entradas);
  }, [lotes, feature, queries]);

  if (cargando) return <Skeleton className="h-[300px] w-full" />;

  if (preparado.violines.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Sin tramos para esta variable: el motor no pudo cortar la línea base en tramos (menos de tres valores
        distintos).
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div ref={ref} className="min-h-[300px]">
        {ancho > 0 ? (
          <ViolinSvg
            violines={preparado.violines}
            tramosMediana={preparado.tramosMediana}
            densidadMax={preparado.densidadMax}
            min={preparado.min}
            max={preparado.max}
            ancho={ancho}
            featureLabel={featureLabel}
          />
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-3.5 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block size-2.5 rounded-[2px]"
            style={{ background: "var(--chart-3)" }}
          />
          Línea base
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block size-2.5 rounded-[2px]"
            style={{ background: "var(--chart-1)" }}
          />
          Lotes siguientes
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg aria-hidden="true" width="18" height="6" className="shrink-0">
            <line x1="0" y1="3" x2="18" y2="3" stroke="var(--chart-3)" strokeWidth="1" strokeDasharray="4 3" />
          </svg>
          mediana de la línea base
        </span>
        <span>el punto es la mediana de cada lote; el PSI, contra la línea base</span>
      </div>

      {errores > 0 ? (
        <p className="text-xs text-muted-foreground">
          {errores === 1 ? "1 lote no se pudo cargar" : `${errores} lotes no se pudieron cargar`}
        </p>
      ) : null}
      {preparado.omitidos > 0 ? (
        <p className="text-xs text-muted-foreground">
          {preparado.omitidos === 1
            ? "1 lote sin tramos para esta variable"
            : `${preparado.omitidos} lotes sin tramos para esta variable`}
        </p>
      ) : null}
    </div>
  );
}

export default ViolinLoteALote;
