/**
 * Sección "Cómo se ha calculado": aparece SOLO con una
 * métrica ampliada en la rejilla y calcula esa métrica, nunca la del
 * `monitor_type` genérico (así se hacía antes). El
 * sheet de detalle de evaluación (`detalle-evaluacion.tsx`) ya no la repite.
 */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorDeConsulta } from "@/components/vigia";
import { useContenidoMetricasPorTipo } from "@/api/queries-contenido";
import { useEtiquetaMetrica } from "./usar-etiqueta-metrica";

import { CalculoMetrica } from "@/components/vigia/CalculoMetrica";
import { useEvaluationDetail } from "./usarEvaluacion";

export interface CalculoMetricaAmpliadaProps {
  evaluationId: number | null;
  /** `null` cuando ninguna métrica está ampliada: la sección no se pinta. */
  metricKey: string | null;
  /** `/monitores/deriva`: la confianza y las variables ya están en el bloque «Distribuciones». */
  distribucionesEnPantalla?: boolean;
}

export function CalculoMetricaAmpliada({ evaluationId, metricKey, distribucionesEnPantalla }: CalculoMetricaAmpliadaProps) {
  const detalleQ = useEvaluationDetail(evaluationId);
  const ayudaQ = useContenidoMetricasPorTipo();
  const metricLabel = useEtiquetaMetrica();

  if (metricKey === null || evaluationId === null) return null;

  return (
    <Card id="calculo" className="scroll-mt-20">
      <CardHeader>
        <CardTitle>Cómo se ha calculado: {metricLabel(metricKey)}</CardTitle>
      </CardHeader>
      <CardContent>
        {detalleQ.isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : detalleQ.isError ? (
          <ErrorDeConsulta
            que="el detalle de la evaluación"
            error={detalleQ.error}
            onReintentar={() => void detalleQ.refetch()}
          />
        ) : detalleQ.data ? (
          <CalculoMetrica
            metricKey={metricKey}
            ayuda={ayudaQ.data?.[metricKey]}
            evaluacion={detalleQ.data}
            todaAyuda={ayudaQ.data}
            distribucionesEnPantalla={distribucionesEnPantalla}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

export default CalculoMetricaAmpliada;
