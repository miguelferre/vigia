/**
 * Al confirmar el paso «Umbrales» del alta, la línea base se evalúa
 * con los umbrales recién guardados (la ingesta de una línea base ya no
 * evalúa por sí sola). Este gancho lanza `POST /batches/{id}/evaluate`, sigue
 * el trabajo y avisa al terminar. Aparte de `alta-umbrales.tsx` para no
 * superar 9 KB.
 */

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/api/client";
import { textoErrorDeTrabajo } from "@/components/vigia";
import type { Job } from "@/api/types";
import { useJob } from "@/realtime/useJob";

export interface EvaluacionLineaBase {
  /** Encola la evaluación del lote de línea base; lanza si la API la rechaza. */
  lanzar: (batchId: number) => Promise<void>;
  /** Texto de estado para enseñar bajo el botón, o `null` sin evaluación en curso. */
  estado: string | null;
}

export function useEvaluarLineaBase(): EvaluacionLineaBase {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<number | null>(null);
  const job = useJob(jobId);

  useEffect(() => {
    if (jobId === null || !job.terminado) return;
    void queryClient.invalidateQueries({ queryKey: ["state"] });
    void queryClient.invalidateQueries({ queryKey: ["batches"] });
    void queryClient.invalidateQueries({ queryKey: ["evaluations"] });
    void queryClient.invalidateQueries({ queryKey: ["alerts"] });
    if (job.status === "error") toast.error(textoErrorDeTrabajo(job.error, "La evaluación de la línea base"));
    else toast.success("Línea base evaluada con los umbrales guardados");
  }, [jobId, job.terminado, job.status, job.error, queryClient]);

  const lanzar = async (batchId: number) => {
    const trabajo = await api.post<Job>(`/batches/${batchId}/evaluate`, { trigger: "manual" });
    setJobId(trabajo.id ?? null);
  };

  const enCurso = jobId !== null && !job.terminado;
  const estado = enCurso
    ? "Evaluando la línea base con los umbrales guardados…"
    : jobId !== null && job.status === "terminado"
      ? "La línea base se ha evaluado con estos umbrales."
      : null;
  return { lanzar, estado };
}
