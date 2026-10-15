/**
 * Los pasos 11 y 24 de la demo guiada cargan un lote: `POST /demo/runs/{id}/next`
 * encola la fase siguiente y `useJob` sigue el progreso por SSE, que el
 * panel pinta como barra y mensaje (el paso se da por hecho cuando
 * el trabajo termina). Es la parte del reproductor por fases que
 * sobrevive dentro de la demo guiada.
 *
 * `next` invalida la raíz `demo` al encolar, no al terminar (el resultado
 * llega por SSE); al ver el trabajo en estado final se invalidan las raíces
 * que la evaluación del lote toca y que el evento `demo_run` del SSE no
 * cubre (`RAICES_POR_OBJETO`, `api/queries.ts`), mismo patrón que
 * `explicabilidad/lanzar.tsx`.
 */

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { mensajeDeError } from "@/api/client";
import { useSiguienteFase } from "@/api/queries-demo";
import { useJob } from "@/realtime/useJob";

import { textoErrorDeTrabajo } from "../ErrorDeTrabajo";

import type { TrabajoFase } from "./contexto";

/** Raíces que refrescar cuando termina un `next`: las de `demo_run` y las de la evaluación. */
const RAICES_AL_TERMINAR = [
  "demo",
  "projects",
  "batches",
  "datasets",
  "state",
  "evaluations",
  "timeline",
  "monitors",
  "alerts",
  "explanations",
] as const;

export function useTrabajoFase(runId: number | null, alTerminar: (paso: number) => void): TrabajoFase {
  const queryClient = useQueryClient();
  const next = useSiguienteFase();
  const [jobId, setJobId] = useState<number | null>(null);
  const [pasoLanzado, setPasoLanzado] = useState<number | null>(null);
  const job = useJob(jobId);

  useEffect(() => {
    if (jobId === null || !job.terminado) return;
    for (const raiz of RAICES_AL_TERMINAR) void queryClient.invalidateQueries({ queryKey: [raiz] });
    if (job.status === "terminado") {
      if (pasoLanzado !== null) alTerminar(pasoLanzado);
    } else {
      toast.error(textoErrorDeTrabajo(job.error, "La carga del lote"));
    }
  }, [jobId, job.terminado, job.status, job.error, pasoLanzado, alTerminar, queryClient]);

  const lanzar = async (paso: number) => {
    if (runId === null) return;
    try {
      const resumen = await next.mutateAsync(runId);
      if (resumen.id !== null) {
        setPasoLanzado(paso);
        setJobId(resumen.id);
      }
    } catch (error) {
      toast.error(mensajeDeError(error));
    }
  };

  return {
    enCurso: next.isPending || (jobId !== null && !job.terminado),
    progreso: job.progress,
    mensaje: job.message,
    pasoLanzado,
    lanzar,
  };
}
