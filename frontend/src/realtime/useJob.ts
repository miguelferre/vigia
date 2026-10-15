/**
 * Seguimiento de un trabajo por SSE.
 *
 * `/api/jobs/{id}/stream` manda primero el estado actual y luego cada avance;
 * el backend cierra el flujo al llegar a un estado final. Al cerrarse se
 * invalidan las queries de trabajos para que la cabecera se ponga al día.
 */

import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api, API_BASE } from "@/api/client";
import type { JobStatus } from "@/api/types";

export const ESTADOS_FINALES: readonly JobStatus[] = ["terminado", "error", "cancelado"];

export function esFinal(status: JobStatus | null): boolean {
  return status !== null && ESTADOS_FINALES.includes(status);
}

export interface JobStreamMessage {
  id?: number | null;
  job_id?: number;
  status: JobStatus;
  progress: number;
  message: string;
  result?: unknown;
  error?: string | null;
}

export interface JobSeguido {
  status: JobStatus | null;
  progress: number;
  message: string;
  result: unknown;
  error: string | null;
  terminado: boolean;
  cancelar: () => Promise<void>;
}

/** Sigue un trabajo hasta su estado final. Con `jobId` nulo no hace nada. */
export function useJob(jobId: number | null): JobSeguido {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);

  // Al cambiar de trabajo se limpia el estado en el render, no en el efecto.
  const [seguido, setSeguido] = useState<number | null>(jobId);
  if (seguido !== jobId) {
    setSeguido(jobId);
    setStatus(null);
    setProgress(0);
    setMessage("");
    setResult(null);
    setError(null);
  }

  useEffect(() => {
    if (jobId === null) return;
    const fuente = new EventSource(`${API_BASE}/jobs/${jobId}/stream`);
    const alMensaje = (data: string) => {
      if (!data) return;
      let msg: JobStreamMessage;
      try {
        msg = JSON.parse(data) as JobStreamMessage;
      } catch {
        return;
      }
      setStatus(msg.status);
      setProgress(typeof msg.progress === "number" ? msg.progress : 0);
      setMessage(msg.message ?? "");
      if (msg.result !== undefined) setResult(msg.result);
      if (msg.error !== undefined) setError(msg.error);
      if (esFinal(msg.status)) {
        fuente.close();
        void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      }
    };
    fuente.addEventListener("job", (e) => alMensaje((e as MessageEvent<string>).data));
    fuente.onmessage = (e) => alMensaje(e.data);
    fuente.onerror = () => fuente.close();
    return () => fuente.close();
  }, [jobId, queryClient]);

  const cancelar = useCallback(async () => {
    if (jobId === null) return;
    await api.post(`/jobs/${jobId}/cancel`);
    await queryClient.invalidateQueries({ queryKey: ["jobs"] });
  }, [jobId, queryClient]);

  return {
    status,
    progress,
    message,
    result,
    error,
    terminado: esFinal(status),
    cancelar,
  };
}
