/**
 * Bloque «Error del modelo» de `/monitores/calidad` en regresión:
 * lo que sustituye a la matriz de confusión. Bajo los cuatro titulares (MAE,
 * RMSE, R² y sesgo medio, en la rejilla) enseña cómo se reparte el error:
 * «predicho frente a real» por deciles, el histograma de residuos del lote y
 * la tabla de error por grupo. MSE y error absoluto mediano quedan solo en el
 * detalle de la evaluación. Solo se monta con `caps.matriz === null` y
 * `caps.metricas === "regresion"`. Hermano de `CalidadClases` (multiclase).
 */

import { useMemo } from "react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorDeConsulta } from "@/components/vigia";
import type { Evaluation } from "@/api/types";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { formatoMetrica } from "@/lib/metrics";

import { HistogramaResiduos } from "./HistogramaResiduos";
import { PredichoFrenteAReal } from "./PredichoFrenteAReal";
import { TablaErrorPorGrupo } from "./TablaErrorPorGrupo";
import { fraseSesgo, leerCalidadRegresion, leerResumenResiduos } from "./regresion-datos";
import { leerErrorPorGrupo } from "./regresion-equidad-datos";
import { useEquidadRegresion } from "./usar-equidad-regresion";
import { useEvaluationDetail } from "./usarEvaluacion";

export interface CalidadRegresionProps {
  evaluationId: number | null;
  projectId: number;
  /** Evaluaciones del monitor de calidad, para encontrar la de la línea base. */
  evaluaciones: Evaluation[];
}

/** Solo se monta con `caps.metricas === "regresion"`: en binario y multiclase no pide nada. */
export function CalidadRegresion(props: CalidadRegresionProps) {
  const { caps } = useTipoTarea(props.projectId);
  return caps?.metricas === "regresion" ? <ContenidoCalidadRegresion {...props} /> : null;
}

function ContenidoCalidadRegresion({ evaluationId, projectId, evaluaciones }: CalidadRegresionProps) {
  const { unidad } = useTipoTarea(projectId);
  const detalleQ = useEvaluationDetail(evaluationId);
  const lote = detalleQ.data?.batch_id ?? null;
  // La línea base es la primera evaluación del monitor (la de menor id), si no es la que se enseña.
  const baseId = useMemo(() => {
    const ids = evaluaciones.map((e) => e.id).filter((id): id is number => id !== null);
    const primera = ids.length > 0 ? Math.min(...ids) : null;
    return primera !== null && primera !== evaluationId ? primera : null;
  }, [evaluaciones, evaluationId]);
  const baseQ = useEvaluationDetail(baseId);
  const equidad = useEquidadRegresion(projectId, lote);

  const d = detalleQ.data ? leerCalidadRegresion(detalleQ.data.result) : null;
  const base = baseQ.data ? leerResumenResiduos(baseQ.data.result) : null;
  const filasGrupo = equidad.detalle ? leerErrorPorGrupo(equidad.detalle.result) : null;

  return (
    <section id="calidad-regresion" className="flex scroll-mt-20 flex-col gap-4" data-testid="calidad-regresion">
      <div className="flex flex-col gap-0.5">
        <h3 className="text-md font-semibold">Error del modelo</h3>
        <span className="text-xs text-muted-foreground">
          El modelo da un número, no una clase: no hay matriz de confusión. Los cuatro números de arriba resumen el
          error{unidad ? ` en ${unidad}` : ""}; aquí se ve cómo se reparte entre los casos y entre los grupos.
        </span>
      </div>
      {evaluationId === null ? (
        <Card className="p-4">
          <p className="text-sm text-muted-foreground">
            Sin evaluación de calidad todavía: el error aparece con el primer lote con valor real.
          </p>
        </Card>
      ) : detalleQ.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : detalleQ.isError ? (
        <ErrorDeConsulta que="la evaluación" error={detalleQ.error} onReintentar={() => void detalleQ.refetch()} />
      ) : d ? (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <h4 className="text-sm font-semibold">Predicho frente a real</h4>
            <p className="text-xs text-muted-foreground">
              Los casos se ordenan por lo que predice el modelo y se reparten en diez tramos. Si la línea del valor real
              medio sigue la diagonal, el modelo acierta en todo el rango; si se separa en un extremo, falla justo ahí.
            </p>
            {d.predVsReal.length > 0 ? (
              <PredichoFrenteAReal tramos={d.predVsReal} unidad={unidad} />
            ) : (
              <p className="text-sm text-muted-foreground" data-testid="sin-pred-vs-real">
                Sin datos de «predicho frente a real» en esta evaluación: hace falta más histórico con valor real.
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <h4 className="text-sm font-semibold">Residuos del lote</h4>
            {d.residuos ? (
              <>
                <HistogramaResiduos histograma={d.residuos.histograma} unidad={unidad} />
                <p className="text-xs text-muted-foreground" data-testid="residuos-resumen">
                  {fraseSesgo(d.residuos.media, unidad, "el valor real")} Dispersión del residuo:{" "}
                  {formatoMetrica("mean_absolute_error", d.residuos.desviacion, unidad)}.{" "}
                  {base
                    ? `En la línea base: sesgo ${formatoMetrica("mean_error", base.media, unidad)} y dispersión ${formatoMetrica("mean_absolute_error", base.desviacion, unidad)}.`
                    : "El histograma enseña solo el lote: la línea base se calculó con otros cortes."}
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground" data-testid="sin-residuos">
                Sin residuos en esta evaluación: hace falta más histórico con valor real.
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <h4 className="text-sm font-semibold">Error por grupo</h4>
            {equidad.cargando ? (
              <Skeleton className="h-24 w-full" />
            ) : filasGrupo ? (
              <TablaErrorPorGrupo filas={filasGrupo} nombres={equidad.nombres} unidad={unidad} />
            ) : (
              <p className="text-sm text-muted-foreground" data-testid="sin-error-por-grupo">
                Sin error por grupo todavía: lo calcula el monitor de equidad con el atributo protegido del modelo.
              </p>
            )}
          </div>
        </div>
      ) : (
        <Card className="p-4">
          <p className="text-sm text-muted-foreground">
            Esta evaluación no trae el detalle del error de una regresión: vuelve a evaluar el lote.
          </p>
        </Card>
      )}
    </section>
  );
}

export default CalidadRegresion;
