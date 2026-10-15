/**
 * «Qué significa» y «Cómo se ha calculado» de `/alertas/:id`: mismas piezas que `AlertaPanel.tsx` (`CalculoMetrica`, `textoQueMide`)
 * para que panel y página den la misma fórmula instanciada. Aparte para no
 * hacer crecer `detalle.tsx` por encima de 10 KB.
 */

import { Link } from "react-router";

import { useContenidoMetricasPorTipo } from "@/api/queries-contenido";
import type { EvaluationDetail } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { CalculoCruzada, CalculoMetrica } from "@/components/vigia/CalculoMetrica";
import { esReglaCruzada } from "@/components/vigia/calculo-datos";
import { textoQueMide } from "@/components/vigia/AyudaTexto";

export interface QueSignificaCalculoProps {
  metricKey: string;
  evaluacion: EvaluationDetail | undefined;
  evaluacionCargando: boolean;
  /** Proyecto de la alerta: la ayuda sale resuelta por su tipo, no por el de la sesión. */
  projectId?: number | null;
}

export function QueSignificaCalculo({ metricKey, evaluacion, evaluacionCargando, projectId }: QueSignificaCalculoProps) {
  const ayudaQ = useContenidoMetricasPorTipo(projectId);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5 rounded-lg bg-muted p-3">
        <div className="flex items-center gap-1.5">
          <span className="text-md font-semibold">Qué significa</span>
          <Link to="/ayuda" className="ml-auto text-md text-link hover:underline">
            Glosario
          </Link>
        </div>
        <p className="text-md">{textoQueMide(ayudaQ.data?.[metricKey])}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-md">Cómo se ha calculado</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {esReglaCruzada(metricKey, ayudaQ.data?.[metricKey]) ? (
            // Una alerta cruzada no sale de una evaluación de lote: solo texto.
            <CalculoCruzada ayuda={ayudaQ.data?.[metricKey]} sinDefinicion />
          ) : evaluacionCargando ? (
            <Skeleton className="h-32 w-full" />
          ) : evaluacion ? (
            <CalculoMetrica
              metricKey={metricKey}
              ayuda={ayudaQ.data?.[metricKey]}
              evaluacion={evaluacion}
              todaAyuda={ayudaQ.data}
              sinDefinicion
            />
          ) : (
            <p className="text-md text-tertiary">Sin evaluación asociada a esta alerta.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default QueSignificaCalculo;
