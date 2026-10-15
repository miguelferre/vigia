/**
 * Bloque «Distribuciones» de `/monitores/deriva`:
 * confianza del modelo, clases predichas y variables, línea base frente a
 * lote, en la forma B (`HistogramaBaseLote`). Fijo entre la
 * rejilla de métricas y «Cómo se ha calculado»; usa la misma clave de caché
 * que esa sección (`useEvaluationDetail`), una sola petición.
 *
 * `lotes`: se construye aquí a partir de
 * `evaluaciones` (las del monitor, ya cargadas por `index.tsx`) y de
 * `batchesQ`, y se pasa a `DerivaVariables` para la pestaña «Lote a lote».
 *
 * `dominio`/`favorableLabel`: se pasan a
 * `HistogramaConfianza` desde `proyectoQ.data` para nombrar las clases del
 * selector de confianza por clase predicha («Derivar»/«No derivar» en
 * dominios de derivación).
 */

import { useMemo } from "react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorDeConsulta, InfoTooltip } from "@/components/vigia";
import { medida } from "@/components/vigia/calculo-datos";
import { useBatches, useProject } from "@/api/queries";
import { useContenidoMetricasPorTipo, useGlosario } from "@/api/queries-contenido";
import type { Batch, Evaluation, JsonObject } from "@/api/types";
import { etiquetaLote, numeroLote } from "@/lib/fases";

import { useEvaluationDetail } from "./usarEvaluacion";
import { TarjetaDistribucion } from "./TarjetaDistribucion";
import { TarjetaClasesPredichas } from "./TarjetaClasesPredichas";
import { TarjetaPrediccion } from "./DerivaPrediccion";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { HistogramaConfianza } from "./histograma-confianza";
import { favorableNumerico } from "./confianza-por-clase";
import { DerivaVariables } from "./deriva-variables";
import { TOPE_DETALLE } from "./tipos";
import type { LoteDeriva } from "./violin-lote-a-lote-datos";

const AYUDA_FALLBACK =
  "Cómo se repartían los datos en la línea base y cómo se reparten en el lote, tramo a tramo.";

export interface DistribucionesDerivaProps {
  evaluationId: number | null;
  projectId: number;
  /** Evaluaciones del monitor (ya cargadas por `index.tsx`), para el violín lote a lote. */
  evaluaciones: Evaluation[];
}

export function DistribucionesDeriva({ evaluationId, projectId, evaluaciones }: DistribucionesDerivaProps) {
  const detalleQ = useEvaluationDetail(evaluationId);
  // Misma llamada que `rejilla.tsx` y `evaluaciones.tsx` (misma clave): sin petición nueva.
  const batchesQ = useBatches(projectId);
  const proyectoQ = useProject(projectId);
  // Sin `caps.confianza` (regresión) no hay tarjeta de confianza ni de clases predichas.
  const { caps, unidad } = useTipoTarea(projectId);
  const ayudaQ = useContenidoMetricasPorTipo(projectId);
  const glosarioQ = useGlosario();

  const ayudaBloque = glosarioQ.data?.distribuciones_deriva?.definicion ?? AYUDA_FALLBACK;

  // Lotes para el violín lote a lote: una
  // evaluación por lote (la de mayor id), limitada a las TOPE_DETALLE más
  // recientes por id (mismo tope que la tabla, para compartir caché de
  // detalle) y solo entonces ordenada por `seq` ascendente para el eje.
  const lotes = useMemo<LoteDeriva[]>(() => {
    // Mismo patrón que `evaluaciones.tsx:batchesPorId`: un solo acceso a
    // `batchesQ.data` aquí arriba, para que la dependencia se pueda inferir.
    const batchPorId = new Map<number, Batch>();
    for (const b of batchesQ.data?.items ?? []) {
      if (b.id !== null) batchPorId.set(b.id, b);
    }
    const porBatch = new Map<number, { id: number; batchId: number }>();
    for (const e of evaluaciones) {
      const batchId = e.batch_id;
      const id = e.id;
      if (batchId === null || id === null) continue;
      const previa = porBatch.get(batchId);
      if (!previa || previa.id < id) porBatch.set(batchId, { id, batchId });
    }
    return Array.from(porBatch.values())
      .sort((a, b) => b.id - a.id)
      .slice(0, TOPE_DETALLE)
      .map(({ id, batchId }) => {
        const batch = batchPorId.get(batchId);
        return {
          evaluationId: id,
          batchId,
          seq: batch ? batch.seq : batchId,
          // Nunca `batch.id` como número de lote.
          numero: numeroLote(batch?.seq),
          fase: etiquetaLote(batch?.phase_label),
        };
      })
      .sort((a, b) => a.seq - b.seq);
  }, [evaluaciones, batchesQ.data]);

  if (evaluationId === null) {
    return (
      <Card className="p-4">
        <p className="text-sm text-muted-foreground">
          Sin evaluación de deriva todavía: las distribuciones aparecen con el primer lote evaluado.
        </p>
      </Card>
    );
  }

  const evaluacion = detalleQ.data;
  const batch = evaluacion ? batchesQ.data?.items.find((b) => b.id === evaluacion.batch_id) : undefined;
  const numero = evaluacion ? numeroLote(batch?.seq) : "#";
  // El nombre del lote junto a su número.
  const numeroConNombre = batch?.dataset_name ? `${numero} (${batch.dataset_name})` : numero;
  const subtituloBase =
    caps?.confianza === null
      ? `Línea base frente a lote ${numeroConNombre}: dónde ha cambiado el reparto de la predicción y de las variables.`
      : `Línea base frente a lote ${numeroConNombre}: dónde ha cambiado el reparto de la confianza del modelo, de las clases predichas y de las variables.`;

  const details = evaluacion ? ((evaluacion.result?.details as JsonObject | undefined) ?? null) : null;
  const nVariables = Array.isArray(details?.features) ? details.features.length : 0;

  return (
    <section id="distribuciones" className="flex scroll-mt-20 flex-col gap-4">
      <div className="flex flex-col gap-0.5">
        <span className="inline-flex items-center gap-1.5">
          <h3 className="text-md font-semibold">Distribuciones</h3>
          <InfoTooltip titulo="Distribuciones" queMide={ayudaBloque} />
        </span>
        <span className="text-xs text-muted-foreground">{subtituloBase}</span>
      </div>

      {detalleQ.isLoading || caps === undefined ? (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Skeleton className="h-56 w-full" />
          <Skeleton className="h-56 w-full" />
        </div>
      ) : detalleQ.isError ? (
        <ErrorDeConsulta
          que="la evaluación"
          error={detalleQ.error}
          onReintentar={() => void detalleQ.refetch()}
        />
      ) : evaluacion ? (
        <>
          {caps.confianza === null ? (
            <TarjetaPrediccion
              evaluacion={evaluacion}
              unidad={unidad}
              numeroLote={numero}
              ayuda={ayudaQ.data?.prediction_drift_score}
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <TarjetaDistribucion
                titulo="Confianza del modelo"
                subtitulo={`Probabilidad de la clase predicha, línea base frente a lote ${numero}`}
                metricKey="confidence_drift_score"
                estado={medida(evaluacion, "confidence_drift_score")?.state}
                ayuda={ayudaQ.data?.confidence_drift_score}
              >
                <HistogramaConfianza
                  evaluacion={evaluacion}
                  sinTitulo
                  dominio={proyectoQ.data?.domain}
                  favorableLabel={favorableNumerico(proyectoQ.data?.favorable_label)}
                />
              </TarjetaDistribucion>
              <TarjetaDistribucion
                titulo="Clases predichas"
                subtitulo={`Frecuencia de cada clase, línea base frente a lote ${numero}`}
                metricKey="prediction_drift_score"
                estado={medida(evaluacion, "prediction_drift_score")?.state}
                ayuda={ayudaQ.data?.prediction_drift_score}
              >
                <TarjetaClasesPredichas
                  evaluacion={evaluacion}
                  favorableLabel={favorableNumerico(proyectoQ.data?.favorable_label)}
                  medida={medida(evaluacion, "prediction_drift_score")}
                  dominio={proyectoQ.data?.domain}
                />
              </TarjetaDistribucion>
            </div>
          )}
          <TarjetaDistribucion
            id="ranking-deriva"
            titulo="Variables: línea base frente a lote"
            subtitulo={
              nVariables > 0
                ? `${nVariables} variables ordenadas por puntuación de deriva · pulsa una para verla`
                : "Sin variables en esta evaluación"
            }
            metricKey="feature_drift_score"
            estado={medida(evaluacion, "feature_drift_score")?.state}
            ayuda={ayudaQ.data?.feature_drift_score}
          >
            <DerivaVariables evaluacion={evaluacion} lotes={lotes} />
          </TarjetaDistribucion>
        </>
      ) : null}
    </section>
  );
}

export default DistribucionesDeriva;
