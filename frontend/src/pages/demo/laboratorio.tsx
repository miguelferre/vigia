/**
 * Panel de laboratorio (paso de la demo guiada): mueve
 * parámetros demográficos y de sesgo de una fase del guion y enseña el
 * efecto sobre los monitores, sin avanzar el caso. Ancla `laboratorio`
 * (`/demo#laboratorio`, con `scroll-mt-20` como el resto de anclas).
 *
 * Se resuelve solo su capacidad (`useCan("laboratorio")`): si el rol no la
 * tiene, no renderiza nada. El historial de ensayos vive en el estado del
 * componente (cada lanzamiento ya queda en el diario como
 * `demo.lab_ejecutada`). Los controles y las etiquetas salen del contenido
 * (`useGuionDemo`) cruzados con `lab_params` de `GET /demo/scenarios`.
 */

import { useCallback, useState } from "react";

import { useGuionDemo } from "@/api/queries-contenido";
import { useGuiones } from "@/api/queries-demo";
import type { DemoRun } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/session/session";

import { FormularioLaboratorio } from "./laboratorio-formulario";
import type { ResultadoLab } from "./laboratorio-parametros";
import { ResultadoLaboratorio } from "./laboratorio-resultado";

export interface PanelLaboratorioProps {
  run: DemoRun;
}

/** Tope del historial en pantalla: los ensayos son de sesión, no hace falta más. */
const MAX_HISTORIAL = 20;

export function PanelLaboratorio({ run }: PanelLaboratorioProps) {
  const puedeLaboratorio = useCan("laboratorio");
  const guionesQ = useGuiones();
  const contenidoQ = useGuionDemo();
  const [resultados, setResultados] = useState<ResultadoLab[]>([]);
  // Memoizado: va en las dependencias del efecto de `useEnsayoLaboratorio`
  // que avisa al terminar el job; una función nueva por render lo dispararía
  // en bucle .
  const agregarResultado = useCallback((r: ResultadoLab) => {
    setResultados((prev) => [r, ...prev].slice(0, MAX_HISTORIAL));
  }, []);

  if (!puedeLaboratorio) return null;

  const escenario = guionesQ.data?.items.find((s) => s.key === run.scenario_key) ?? null;
  const fases = escenario?.phases ?? [];
  const contenido = contenidoQ.data;
  const parametros = contenido?.laboratorio.parametros ?? [];

  return (
    <Card id="laboratorio" className="scroll-mt-20">
      <CardHeader>
        <CardTitle>Ejecutar un ensayo</CardTitle>
        <CardDescription>
          Genera un lote con los parámetros que muevas aquí y lo evalúa sobre este mismo modelo. Cada
          ejecución queda en el diario con tu nombre y el motivo.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <Alert>
          <AlertTitle>El laboratorio no avanza el caso</AlertTitle>
          <AlertDescription>
            Es un ensayo aparte: el paso de la demo y lo ya cargado siguen donde estaban. Los lotes
            del laboratorio se etiquetan «{contenido?.fases["lab:*"]?.etiqueta ?? "Laboratorio"}».
          </AlertDescription>
        </Alert>
        {guionesQ.isLoading || contenidoQ.isLoading || !contenido ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <FormularioLaboratorio
            runId={run.id as number}
            fases={fases}
            contenido={contenido}
            onResultado={agregarResultado}
          />
        )}
        <ResultadoLaboratorio projectId={run.project_id} resultados={resultados} parametros={parametros} />
      </CardContent>
    </Card>
  );
}
