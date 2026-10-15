/**
 * Pie del bloque «Registro de uso»: evaluar las reglas cruzadas y descargar
 * el registro acumulado (partido de `RegistroUso.tsx` por el límite de 9 KB).
 * Sin permiso de configuración o sin rango favorable, no se ofrece
 * evaluar.
 */

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { ErrorDeTrabajo, MotivoDialog } from "@/components/vigia";
import { api, mensajeDeError } from "@/api/client";
import { useJob } from "@/realtime/useJob";
import type { JobAccepted } from "@/api/types";

export function EvaluarYDescargar({ projectId, puedeEvaluar }: { projectId: number; puedeEvaluar: boolean }) {
  const queryClient = useQueryClient();
  const [abiertoEvaluar, setAbiertoEvaluar] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const job = useJob(jobId);
  const [errorEvaluar, setErrorEvaluar] = useState<string | null>(null);

  // Tras evaluar, la tarjeta de «Cruzadas» se refresca sola.
  useEffect(() => {
    if (job.terminado) {
      void queryClient.invalidateQueries({ queryKey: ["humana", projectId, "cross-latest"] });
    }
  }, [job.terminado, projectId, queryClient]);

  const evaluar = async () => {
    setErrorEvaluar(null);
    const aceptado = await api.post<JobAccepted>(`/projects/${projectId}/cross/evaluate`);
    setJobId(aceptado.id);
  };

  const descargar = async () => {
    try {
      await api.download(`/projects/${projectId}/usage-logs/export.csv`, "registro-de-uso-acumulado.csv");
    } catch (err) {
      setErrorEvaluar(mensajeDeError(err));
    }
  };

  const evaluando = job.status !== null && !job.terminado;

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        {puedeEvaluar ? (
          <Button size="sm" variant="outline" onClick={() => setAbiertoEvaluar(true)} disabled={evaluando}>
            Evaluar reglas cruzadas ahora
          </Button>
        ) : null}
        <Button size="sm" variant="link" className="px-0" onClick={() => void descargar()}>
          Descargar registro acumulado
        </Button>
        {evaluando ? <span className="text-xs text-muted-foreground">Evaluando… {job.message}</span> : null}
        {job.terminado && job.status === "terminado" ? (
          <span className="text-xs text-muted-foreground">Evaluación terminada: la tarjeta de Cruzadas ya está al día.</span>
        ) : null}
      </div>
      {job.terminado && job.status === "error" ? <ErrorDeTrabajo error={job.error} accion="La evaluación" /> : null}
      {errorEvaluar ? (
        <p className="text-sm text-destructive" role="alert">
          {errorEvaluar}
        </p>
      ) : null}
      <MotivoDialog
        open={abiertoEvaluar}
        onOpenChange={setAbiertoEvaluar}
        titulo="Evaluar las reglas cruzadas"
        descripcion="Lanza una evaluación de las reglas cruzadas sobre el registro acumulado de la versión activa."
        onConfirm={async () => {
          await evaluar();
        }}
      />
    </>
  );
}
