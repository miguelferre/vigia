/**
 * Sigue el job de un ensayo de laboratorio hasta que termina y entrega su
 * resultado. Factoriza `useJob` más la repesca del resultado
 * fuera de `laboratorio-formulario.tsx` para no pasar de 9 KB.
 *
 * `useJob` sigue el progreso por SSE, pero el mensaje que empuja la cola al
 * terminar un trabajo (`Jobs._publish_job`, `app/jobs.py`) solo lleva
 * `status`/`progress`/`message`: `result` no viaja por ahí, solo en la
 * instantánea inicial de la conexión (`job_to_dict`, `GET /jobs/{id}`).
 * Verificado en vivo: `job.result` se queda en `null` en el mensaje que pone
 * `terminado` (gap fuera de esta frontera). En vez de tocar `app/jobs.py`,
 * se pide el trabajo por REST en cuanto `useJob` marca `terminado`
 * (`GET /jobs/{id}` con `job_to_dict`, que sí trae `result`).
 */

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/api/client";
import { textoErrorDeTrabajo } from "@/components/vigia";
import type { Job, MonitorType } from "@/api/types";
import { useJob } from "@/realtime/useJob";

import type { ResultadoLab } from "./laboratorio-parametros";

interface LabJobResult {
  phase_key?: string;
  batch_id?: number;
  params?: Record<string, unknown>;
  states?: Partial<Record<MonitorType, string>>;
}

export interface PendienteLab {
  faseKey: string;
  faseTitulo: string;
  expected: Record<string, string> | null;
  params: Record<string, unknown>;
}

export function useEnsayoLaboratorio(
  jobId: number | null,
  pendiente: PendienteLab | null,
  onResultado: (r: ResultadoLab) => void,
) {
  const job = useJob(jobId);
  const jobDetalle = useQuery({
    queryKey: ["jobs", "detalle-lab", jobId],
    queryFn: () => api.get<Job>(`/jobs/${jobId}`),
    enabled: jobId !== null && job.terminado && job.status === "terminado",
    staleTime: 0,
  });

  // Efecto (no render): avisa y entrega el resultado cuando el job termina,
  // igual que `explicabilidad/lanzar.tsx`.
  useEffect(() => {
    if (!job.terminado || jobId === null || !pendiente) return;
    if (job.status !== "terminado") {
      toast.error(textoErrorDeTrabajo(job.error, "El ensayo del laboratorio"));
      return;
    }
    const r = jobDetalle.data?.result as LabJobResult | null | undefined;
    if (r && typeof r.batch_id === "number") {
      onResultado({
        ts: Date.now(),
        faseKey: pendiente.faseKey,
        faseTitulo: pendiente.faseTitulo,
        expected: pendiente.expected,
        batchId: r.batch_id,
        params: r.params ?? pendiente.params,
        states: r.states ?? {},
      });
      toast.success("Ensayo del laboratorio calculado.");
    }
    // No hace falta anular `jobId` ni `pendiente`: `useJob` resetea su propio
    // estado en el siguiente lanzamiento (compara `seguido` con `jobId` en el
    // render), así que estas dependencias no vuelven a cambiar hasta entonces.
  }, [job.terminado, job.status, job.error, jobId, pendiente, jobDetalle.data, onResultado]);

  return job;
}
