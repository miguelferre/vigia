/**
 * Lanzador de explicaciones: global (permutación o SHAP) y local (LIME).
 *
 * `POST /model-versions/{id}/explain/global|local` crea un job (`kind:
 * "explicacion"`); se sigue con `useJob` y, al terminar, se invalida la
 * lista de explicaciones y se avisa al contenedor con el id calculado.
 */

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon } from "lucide-react";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { qk, useProject } from "@/api/queries";
import { useGlosario } from "@/api/queries-contenido";
import type { Job } from "@/api/types";
import { useJob } from "@/realtime/useJob";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InfoTooltip, textoErrorDeTrabajo } from "@/components/vigia";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { valorDeClase } from "@/pages/modelos/clases-multiclase";
import { cn } from "@/lib/utils";
import { AyudaLanzar } from "./AyudaLanzar";
import { CLASE_POR_DEFECTO, ClaseGlobal, ClaseLocal } from "./lanzar-clases";
import { useRangoSeq } from "./lanzar-rango";
import { CampoFilaLocal } from "./lanzar-fila";
import { AYUDA_METODO_RESPALDO, avisoNoDisponible } from "./lanzar-textos";
import type { ResultadoExplicacion } from "./lanzar-textos";

export interface LanzarProps {
  versionId: number;
  batchId: number | null;
  /** Para invalidar el resumen de explicaciones al terminar (ver más abajo). */
  projectId: number | null;
  onFinished: (explanationId: number) => void;
}

export function Lanzar({ versionId, batchId, projectId, onFinished }: LanzarProps) {
  const queryClient = useQueryClient();
  // La interfaz no sabe si SHAP está instalado, así que
  // el tipo de partida es el que el modelo tiene configurado (por defecto, la
  // permutación, que siempre está). Elegir SHAP a mano sigue siendo posible: si
  // falta, el job termina con `available: false` y se sugiere la permutación.
  const proyecto = useProject(projectId);
  const [kindElegido, setKind] = useState<"permutation" | "shap" | null>(null);
  const kind = kindElegido ?? (proyecto.data?.explain_method === "shap" ? "shap" : "permutation");
  const [rowSeq, setRowSeq] = useState("");
  // Clase a explicar; por defecto, el conjunto favorable (global) o la clase predicha (local).
  const tarea = useTipoTarea(projectId);
  const conSelectorClase = tarea.caps?.selectorClaseExplicacion === true;
  const [claseGlobal, setClaseGlobal] = useState(CLASE_POR_DEFECTO);
  const [claseLocal, setClaseLocal] = useState(CLASE_POR_DEFECTO);
  const [jobId, setJobId] = useState<number | null>(null);
  const job = useJob(jobId);
  const glosario = useGlosario();
  const claveMetodo = kind === "shap" ? "metodo_shap" : "metodo_permutacion";
  const entradaMetodo = glosario.data?.[claveMetodo];

  // Cambiar de lote invalida cualquier row_seq escrito para el anterior; se
  // ajusta en el render (no en un efecto), siguiendo el mismo patrón que la
  // versión por defecto de explicabilidad/index.tsx.
  const [batchVisto, setBatchVisto] = useState(batchId);
  if (batchId !== batchVisto) {
    setBatchVisto(batchId);
    setRowSeq("");
  }

  const rangoSeq = useRangoSeq(batchId);

  const global_ = useMutation({
    mutationFn: () =>
      api.post<Job>(`/model-versions/${versionId}/explain/global`, {
        kind,
        batch_id: batchId,
        ...(conSelectorClase && claseGlobal !== CLASE_POR_DEFECTO ? { clase: valorDeClase(claseGlobal) } : {}),
      }),
    onSuccess: (j) => setJobId(j.id),
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  const local_ = useMutation({
    mutationFn: () =>
      api.post<Job>(`/model-versions/${versionId}/explain/local`, {
        batch_id: batchId,
        row_seq: Number(rowSeq),
        ...(conSelectorClase && claseLocal !== CLASE_POR_DEFECTO ? { clase: valorDeClase(claseLocal) } : {}),
      }),
    onSuccess: (j) => setJobId(j.id),
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  // Efecto puro (sin setState): avisa y refresca la lista cuando el job
  // termina. `useJob` resetea su propio estado en el siguiente lanzamiento,
  // así que no hace falta anular `jobId` aquí.
  useEffect(() => {
    if (!job.terminado || jobId === null) return;
    if (job.status === "terminado") {
      void queryClient.invalidateQueries({ queryKey: qk.explanations(versionId) });
      // Sin esto, el resumen quedaba con la referencia vieja tras dos
      // explicaciones seguidas (una variable a la vez como actual y salida).
      void queryClient.invalidateQueries({ queryKey: qk.explanationsSummary(projectId) });
      const resultado = job.result as ResultadoExplicacion | null;
      if (resultado && typeof resultado.id === "number") onFinished(resultado.id);
      const aviso = avisoNoDisponible(resultado);
      if (aviso) toast.error(aviso);
      else toast.success("Explicación calculada.");
    } else {
      toast.error(textoErrorDeTrabajo(job.error, "El trabajo de explicación"));
    }
  }, [job.terminado, job.status, job.result, job.error, jobId, onFinished, queryClient, versionId, projectId]);

  const rowSeqValido =
    rowSeq.trim() !== "" &&
    Number.isInteger(Number(rowSeq)) &&
    Number(rowSeq) >= 0 &&
    (rangoSeq === null || (Number(rowSeq) >= rangoSeq.min && Number(rowSeq) <= rangoSeq.max));
  const enCurso = global_.isPending || local_.isPending || (jobId !== null && !job.terminado);

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
    <Card>
      <CardHeader>
        <CardTitle>Lanzar explicación</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5">
              <Label htmlFor="kind-select">Tipo (global)</Label>
              <InfoTooltip
                titulo={entradaMetodo?.etiqueta ?? (kind === "shap" ? "SHAP" : "Importancia por permutación")}
                queMide={entradaMetodo?.definicion ?? AYUDA_METODO_RESPALDO}
              />
            </div>
            <Select value={kind} onValueChange={(v) => setKind(v as "permutation" | "shap")}>
              <SelectTrigger id="kind-select" className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="permutation">Permutación</SelectItem>
                <SelectItem value="shap">SHAP</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {conSelectorClase ? (
            <ClaseGlobal clases={tarea.clases} favorables={tarea.favorables} valor={claseGlobal} onChange={setClaseGlobal} />
          ) : null}
          <Button type="button" disabled={enCurso} onClick={() => global_.mutate()}>
            Explicación global
          </Button>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <CampoFilaLocal key={batchId} batchId={batchId} rowSeq={rowSeq} onRowSeq={setRowSeq} rango={rangoSeq} />
          {conSelectorClase ? (
            <ClaseLocal clases={tarea.clases} valor={claseLocal} onChange={setClaseLocal} />
          ) : null}
          <Button
            type="button"
            variant="secondary"
            disabled={enCurso || batchId === null || !rowSeqValido}
            onClick={() => local_.mutate()}
          >
            Explicación local
          </Button>
          {batchId === null ? (
            <span className="text-xs text-muted-foreground">Elige un lote para la explicación local.</span>
          ) : null}
        </div>
        {jobId !== null ? (
          <div className="flex flex-col gap-1.5" data-loading={enCurso ? "true" : undefined}>
            <Progress
              value={job.progress * 100}
              className={cn(job.progress === 0 && enCurso && "animate-pulse")}
            />
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {job.progress === 0 && enCurso ? (
                <Loader2Icon className="size-4 animate-spin" aria-hidden="true" />
              ) : null}
              {job.message || (enCurso ? "Calculando…" : "Terminado")}
            </span>
          </div>
        ) : null}
      </CardContent>
    </Card>
    <AyudaLanzar />
    </div>
  );
}

export default Lanzar;
