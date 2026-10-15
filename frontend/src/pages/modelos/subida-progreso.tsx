/**
 * Paso «progreso» del asistente de subida, separado de `subida-dataset.tsx`
 * para no pasar de 9 KB. Tres estados según
 * `job` (`useJob`): en curso (barra, indicador giratorio junto al
 * mensaje y «Cancelar»), terminado (resumen de `job.result`, «Ver lote» y
 * «Cerrar») y error o cancelado (mensaje en rojo y «Cerrar»). Antes de esto
 * el paso se quedaba en «ingiriendo registros» con la barra llena y parecía
 * congelado: el mensaje final y `result` ya
 * llegan siempre por `_publish_job` (jobs.py) y `job.progress(1.0, …)`
 * (ingest.py).
 */

import { CircleCheckIcon, Loader2Icon, TriangleAlertIcon } from "lucide-react";
import { Link } from "react-router";

import type { JobSeguido } from "@/realtime/useJob";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ErrorDeTrabajo } from "@/components/vigia";
import { DialogFooter } from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { AvisoEtiquetasTardias } from "./subida-tardias";
import type { ResultadoTardias } from "./subida-tardias-textos";

interface ResultadoIngesta extends ResultadoTardias {
  batch_id?: number | null;
  n_rows?: number;
  n_labeled?: number;
  n_matched?: number;
  /** Textos que no bloquean la ingesta (p. ej. un registro de uso subido como datos). */
  avisos?: string[];
}

interface Props {
  job: JobSeguido;
  onCerrar: () => void;
  projectId: number;
}

function textoTerminado(result: unknown): string {
  if (!result || typeof result !== "object") return "Lote ingerido";
  const r = result as ResultadoIngesta;
  if (!r.batch_id && (r.n_matched ?? 0) > 0) {
    return `Etiquetas emparejadas: ${r.n_matched} de ${r.n_rows ?? 0}`;
  }
  return `Lote ingerido: ${r.n_rows ?? 0} filas, ${r.n_labeled ?? 0} con etiqueta`;
}

export function SubidaProgreso({ job, onCerrar, projectId }: Props) {
  if (!job.terminado) {
    return (
      <div className="flex flex-col gap-3">
        <Progress value={job.progress * 100} />
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Loader2Icon className="size-4 animate-spin" strokeWidth={1.5} aria-hidden="true" />
          {job.message || "Procesando…"}
        </p>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => void job.cancelar()}>
            Cancelar
          </Button>
        </DialogFooter>
      </div>
    );
  }

  if (job.status === "terminado") {
    const resultado = job.result as ResultadoIngesta | null;
    const batchId = resultado?.batch_id ?? null;
    const avisos = (resultado?.avisos ?? []).filter((a) => typeof a === "string" && a.trim() !== "");
    return (
      <div className="flex flex-col gap-3">
        <p className="flex items-center gap-1.5 text-sm">
          <CircleCheckIcon
            className="size-4 shrink-0"
            style={{ color: "var(--state-ok)" }}
            strokeWidth={1.5}
            aria-hidden="true"
          />
          {textoTerminado(job.result)}
        </p>
        {avisos.length > 0 ? (
          <Alert data-testid="avisos-ingesta">
            <TriangleAlertIcon style={{ color: "var(--state-warn)" }} aria-hidden="true" />
            <AlertTitle>{avisos.length === 1 ? "Un aviso de la ingesta" : `${avisos.length} avisos de la ingesta`}</AlertTitle>
            <AlertDescription>
              {avisos.map((aviso, i) => (
                <p key={i} className="[overflow-wrap:anywhere]">
                  {aviso}
                </p>
              ))}
            </AlertDescription>
          </Alert>
        ) : null}
        <AvisoEtiquetasTardias projectId={projectId} resultado={resultado} />
        <DialogFooter>
          {batchId !== null ? (
            <Button type="button" variant="outline" asChild>
              <Link to={`/datos/${batchId}`} onClick={onCerrar}>
                Ver lote
              </Link>
            </Button>
          ) : null}
          <Button type="button" onClick={onCerrar}>
            Cerrar
          </Button>
        </DialogFooter>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {job.status === "cancelado" ? (
        <p className="text-sm text-destructive">Ingesta cancelada</p>
      ) : (
        <ErrorDeTrabajo error={job.error} accion="La ingesta" />
      )}
      <DialogFooter>
        <Button type="button" onClick={onCerrar}>
          Cerrar
        </Button>
      </DialogFooter>
    </div>
  );
}

export default SubidaProgreso;
