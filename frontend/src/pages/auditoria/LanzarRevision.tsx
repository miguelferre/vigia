/**
 * Lanzador de revisión sobre un dossier: selector
 * de `approach`, `dedup`, `crosswalk`, `MotivoDialog` y seguimiento por
 * `useJob`. El 409 (backend `none`) y el 422 (sin confirmación) se
 * enseñan con enlace a `/ajustes`.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon } from "lucide-react";
import { toast } from "sonner";

import { ApiError, api, mensajeDeError } from "@/api/client";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { MotivoDialog, textoErrorDeTrabajo } from "@/components/vigia";
import type { ActorBody, DossierApproach, DossierConReviews, Job } from "@/api/types";
import { useJob } from "@/realtime/useJob";
import { qkAuditoria } from "@/api/queries-auditoria";
import { useSettings } from "@/api/queries-ajustes";

export interface LanzarRevisionProps {
  dossierId: number;
  jobActivo: number | null;
  /**
   * Dossier con sus revisiones, ya cargado por la pantalla: el trabajo
   * encolado (`JobResumen`) no lleva `review_id` («el cliente ya conoce los
   * parámetros que acaba de enviar», pero la fila `dossier_review` nace en
   * el servidor con autoincremento); al terminar el trabajo se busca aquí
   * la revisión con ese `job_id`, no en `job.result` (solo trae `status` y
   * `n_findings`, `services/dossiers_review_job.py`).
   */
  dossier: DossierConReviews | undefined;
  onLanzada: (jobId: number) => void;
  onTerminada: (reviewId: number) => void;
}

export function LanzarRevision({ dossierId, jobActivo, dossier, onLanzada, onTerminada }: LanzarRevisionProps) {
  const queryClient = useQueryClient();
  const [approach, setApproach] = useState<DossierApproach>("b0");
  const [dedup, setDedup] = useState(true);
  const [crosswalk, setCrosswalk] = useState(true);
  const [dialogoAbierto, setDialogoAbierto] = useState(false);
  const [avisoBackend, setAvisoBackend] = useState<string | null>(null);
  const job = useJob(jobActivo);
  // El backend rechaza p3 y auto con 409 si `llm.backend` es "none"
  // (`services/dossiers_review.py`); mientras los ajustes no han llegado no se
  // bloquea nada.
  const ajustes = useSettings();
  const sinBackendLlm = ajustes.data !== undefined && ajustes.data.llm.backend === "none";

  const lanzar = useMutation({
    mutationFn: (cuerpo: ActorBody) =>
      api.post<Job>(`/dossiers/${dossierId}/reviews`, {
        approach,
        dedup,
        crosswalk,
        actor: cuerpo.actor,
        role: cuerpo.role,
        motivo: cuerpo.motivo,
      }),
    onSuccess: (job_) => {
      setAvisoBackend(null);
      void queryClient.invalidateQueries({ queryKey: qkAuditoria.detalle(dossierId) });
      if (job_.id !== null) onLanzada(job_.id);
    },
    onError: (error: unknown) => {
      if (error instanceof ApiError && (error.status === 409 || error.status === 422)) {
        setAvisoBackend(mensajeDeError(error));
      } else {
        toast.error(mensajeDeError(error));
      }
    },
  });

  const cancelarTrabajo = useMutation({
    mutationFn: () => job.cancelar(),
    onSuccess: () => toast.success("Revisión cancelada."),
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  // Al terminar el trabajo se invalida el dossier para que traiga la
  // revisión nueva; el aviso solo se da una vez por trabajo (`avisado`).
  // Derivado en el render, no en un efecto (patrón de `explicabilidad/index.tsx`):
  // el linter del repo rechaza `setState` síncrono dentro de `useEffect`.
  const [avisado, setAvisado] = useState<number | null>(null);
  if (job.terminado && jobActivo !== null && avisado !== jobActivo) {
    setAvisado(jobActivo);
    void queryClient.invalidateQueries({ queryKey: qkAuditoria.detalle(dossierId) });
    if (job.status === "terminado") {
      toast.success("Revisión terminada.");
    } else if (job.status === "error") {
      toast.error(textoErrorDeTrabajo(job.error, "La revisión"));
    }
  }

  // La revisión con este `job_id` aparece en `dossier.reviews` en cuanto el
  // dossier se refetchea (efecto de arriba); se selecciona sola al llegar.
  useEffect(() => {
    if (jobActivo === null || job.status !== "terminado" || !dossier) return;
    const revision = dossier.reviews.find((r) => r.job_id === jobActivo);
    if (revision && revision.id !== null && revision.status !== "pendiente" && revision.status !== "en_curso") {
      onTerminada(revision.id);
    }
  }, [dossier, jobActivo, job.status, onTerminada]);

  const enCurso = jobActivo !== null && !job.terminado;

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border p-4">
      <h3 className="text-sm font-semibold">Lanzar revisión</h3>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="revision-approach">Método</Label>
          <Select value={approach} onValueChange={(v) => setApproach(v as DossierApproach)}>
            <SelectTrigger id="revision-approach" className="w-64">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="b0">Rápida, sin modelo de lenguaje</SelectItem>
              <SelectItem value="p3" disabled={sinBackendLlm}>
                Con modelo de lenguaje
              </SelectItem>
              <SelectItem value="auto" disabled={sinBackendLlm}>
                Automática
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2.5">
          <Switch id="revision-dedup" checked={dedup} onCheckedChange={setDedup} />
          <Label htmlFor="revision-dedup">Agrupar hallazgos repetidos</Label>
        </div>
        <div className="flex items-center gap-2.5">
          <Switch id="revision-crosswalk" checked={crosswalk} onCheckedChange={setCrosswalk} />
          <Label htmlFor="revision-crosswalk">Crosswalk regulatorio</Label>
        </div>
        <Button disabled={enCurso} onClick={() => setDialogoAbierto(true)}>
          Lanzar revisión
        </Button>
        {enCurso ? (
          <Button variant="outline" onClick={() => cancelarTrabajo.mutate()} disabled={cancelarTrabajo.isPending}>
            Cancelar
          </Button>
        ) : null}
      </div>

      {approach === "b0" ? (
        <p className="text-xs text-muted-foreground">
          La revisión rápida es una lista de comprobación fija: no lee lo que escribiste en el
          dossier, así que sus hallazgos son genéricos y sin anclaje. Para un análisis de tu
          texto, usa el método con modelo de lenguaje.
        </p>
      ) : null}

      {sinBackendLlm ? (
        <p className="text-xs text-muted-foreground">
          Configura un modelo de lenguaje en Ajustes para usar este enfoque.{" "}
          <Link to="/ajustes" className="text-link underline">
            Ir a Ajustes
          </Link>
        </p>
      ) : null}

      {enCurso ? (
        <div className="flex flex-col gap-1.5">
          <Progress value={job.progress * 100} className={job.progress === 0 ? "animate-pulse" : undefined} />
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2Icon className="size-4 animate-spin" aria-hidden="true" />
            {job.message || "En curso…"}
          </span>
        </div>
      ) : null}

      {avisoBackend ? (
        <Alert>
          <AlertTitle>No se puede lanzar esta revisión</AlertTitle>
          <AlertDescription className="flex flex-col gap-1">
            <span>{avisoBackend}</span>
            <Link to="/ajustes" className="underline">
              Activa un backend en Ajustes
            </Link>
          </AlertDescription>
        </Alert>
      ) : null}

      <MotivoDialog
        open={dialogoAbierto}
        onOpenChange={setDialogoAbierto}
        titulo="Lanzar revisión"
        etiquetaConfirmar="Lanzar"
        onConfirm={async (cuerpo) => {
          await lanzar.mutateAsync(cuerpo);
        }}
      />
    </div>
  );
}
