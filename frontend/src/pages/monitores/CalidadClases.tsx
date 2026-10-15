/**
 * Bloque «Calidad por clase» de `/monitores/calidad` en multiclase: la matriz de confusión `k x k` y la tabla por clase de la última
 * evaluación, debajo de la rejilla de métricas (cuyos tres titulares van
 * primero: exactitud, F1 macro y AUC macro). Hermano de `DistribucionesDeriva`
 * en la pantalla de deriva. Solo se monta con `caps.matriz === "kxk"`.
 *
 * Además de las dos tablas, dice lo que el motor dejó fuera para que un valor
 * no se lea más sólido de lo que es: las clases que el AUC macro excluyó
 *  y las etiquetas reales de clases que el proyecto no declara.
 */

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorDeConsulta } from "@/components/vigia";
import { leerDetalleCalidadMulticlase } from "@/components/vigia/calidad-multiclase-datos";
import { MatrizConfusionK } from "@/components/vigia/MatrizConfusionK";
import { TablaPorClase } from "@/components/vigia/TablaPorClase";
import { useTipoTarea } from "@/hooks/useTipoTarea";

import { useEvaluationDetail } from "./usarEvaluacion";

export interface CalidadClasesProps {
  evaluationId: number | null;
  projectId: number;
}

export function CalidadClases({ evaluationId, projectId }: CalidadClasesProps) {
  const { caps, clases } = useTipoTarea(projectId);
  const detalleQ = useEvaluationDetail(evaluationId);
  if (caps?.matriz !== "kxk") return null;

  const d = detalleQ.data ? leerDetalleCalidadMulticlase(detalleQ.data.result) : null;

  return (
    <section id="calidad-clases" className="flex scroll-mt-20 flex-col gap-4" data-testid="calidad-clases">
      <div className="flex flex-col gap-0.5">
        <h3 className="text-md font-semibold">Calidad por clase</h3>
        <span className="text-xs text-muted-foreground">
          Los números de arriba promedian todas las clases por igual: una clase rara pesa lo mismo que una frecuente.
          «Macro» significa justo eso. Mira la tabla para ver qué clase baja el promedio.
        </span>
      </div>
      {evaluationId === null ? (
        <Card className="p-4">
          <p className="text-sm text-muted-foreground">Sin evaluación de calidad todavía: la matriz aparece con el primer lote con etiqueta.</p>
        </Card>
      ) : detalleQ.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : detalleQ.isError ? (
        <ErrorDeConsulta que="la evaluación" error={detalleQ.error} onReintentar={() => void detalleQ.refetch()} />
      ) : d ? (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <h4 className="text-sm font-semibold">Matriz de confusión</h4>
            {d.matriz ? (
              <MatrizConfusionK matriz={d.matriz} />
            ) : (
              <p className="text-sm text-muted-foreground">
                Sin datos de matriz de confusión en esta evaluación: hace falta más histórico con etiqueta.
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <h4 className="text-sm font-semibold">Tabla por clase</h4>
            <TablaPorClase filas={d.porClase} f1Ponderada={d.f1Ponderada} orden={clases} />
          </div>
          {d.aucExcluidas.length > 0 ? (
            <p className="text-xs text-muted-foreground" data-testid="auc-excluidas">
              <span className="font-semibold text-foreground">Fuera del AUC macro en esta ventana:</span>{" "}
              {d.aucExcluidas.map((e) => (e.motivo ? `${e.clase} (${e.motivo})` : e.clase)).join("; ")}.
            </p>
          ) : null}
          {d.clasesDesconocidas.length > 0 ? (
            <p className="text-xs text-muted-foreground" data-testid="clases-desconocidas">
              <span className="font-semibold text-foreground">Etiquetas de clases que el proyecto no declara:</span>{" "}
              {d.clasesDesconocidas.map((c) => (c.n === null ? c.clase : `${c.clase} (${c.n} filas)`)).join(", ")}. Esas
              filas se ingirieron, pero quedan fuera de la calidad.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default CalidadClases;
