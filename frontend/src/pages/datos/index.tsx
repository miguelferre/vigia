/**
 * `/datos/:batch`: cabecera del lote, composición, registros y acciones.
 * `etiquetaFase` enseña el nombre traducido en proyecto demo gracias al
 * guion que pide `DemoGuiadaProvider` en la raíz de la app, aunque
 * no se haya pasado por `/cuadro`.
 */

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { qk } from "@/api/queries";
import type { ActorBody, Batch, Dataset, Job, ProjectDetail } from "@/api/types";
import { useJob } from "@/realtime/useJob";
import {
  BotonVolver,
  EmptyState,
  ErrorDeTrabajo,
  MotivoDialog,
  PageHeader,
  StateBadge,
  textoErrorDeTrabajo,
} from "@/components/vigia";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { formatoFecha } from "@/lib/metrics";
import { etiquetaFase, numeroLote } from "@/lib/fases";

import ComposicionLote from "./composicion";
import { FicheroLote } from "./lote-fichero";
import RegistrosLote from "./registros";

export default function DatosIndex() {
  const { batch } = useParams();
  const batchId = batch ? Number(batch) : null;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // Mientras se borra (y hasta salir de la página) nada de este lote se
  // vuelve a pedir: el evento SSE de borrado invalida "batches" y los
  // refetch de un lote inexistente serían 404 en consola.
  const [borrando, setBorrando] = useState(false);

  const { data: lote, isLoading } = useQuery({
    queryKey: qk.batch(batchId),
    queryFn: () => api.get<Batch>(`/batches/${batchId}`),
    enabled: batchId !== null && !Number.isNaN(batchId) && !borrando,
  });
  const { data: dataset } = useQuery({
    queryKey: qk.dataset(lote?.dataset_id ?? null),
    queryFn: () => api.get<Dataset>(`/datasets/${lote?.dataset_id}`),
    enabled: !!lote?.dataset_id && !borrando,
  });
  const { data: proyecto } = useQuery({
    queryKey: qk.project(lote?.project_id ?? null),
    queryFn: () => api.get<ProjectDetail>(`/projects/${lote?.project_id}`),
    enabled: !!lote?.project_id && !borrando,
  });

  const [evalJobId, setEvalJobId] = useState<number | null>(null);
  const [borrarAbierto, setBorrarAbierto] = useState(false);
  const evalJob = useJob(evalJobId);

  useEffect(() => {
    if (evalJob.terminado && evalJobId !== null) {
      void queryClient.invalidateQueries({ queryKey: ["evaluations"] });
      void queryClient.invalidateQueries({ queryKey: ["state"] });
      if (evalJob.status === "error") {
        toast.error(textoErrorDeTrabajo(evalJob.error, "La evaluación"));
      }
    }
  }, [evalJob.terminado, evalJob.status, evalJob.error, evalJobId, queryClient]);

  if (batchId === null || Number.isNaN(batchId)) return null;

  const evaluarDeNuevo = async () => {
    try {
      const trabajo = await api.post<Job>(`/batches/${batchId}/evaluate`, { trigger: "manual" });
      if (trabajo.id !== null) setEvalJobId(trabajo.id);
      toast.success("Evaluación en curso");
    } catch (error) {
      toast.error(mensajeDeError(error));
    }
  };

  const borrarLote = async (cuerpo: ActorBody) => {
    const destino = lote ? `/modelos/${lote.project_id}` : "/modelos";
    setBorrando(true);
    try {
      await queryClient.cancelQueries({ queryKey: ["batches"] });
      await api.del<void>(`/batches/${batchId}?confirm=true`, cuerpo);
      queryClient.removeQueries({
        predicate: (q) => q.queryKey[0] === "batches" && q.queryKey[2] === batchId,
      });
      toast.success("Lote borrado");
      navigate(destino, { replace: true });
    } catch (error) {
      setBorrando(false);
      toast.error(mensajeDeError(error));
    }
  };

  const version = proyecto?.versions.find((v) => v.id === lote?.model_version_id);
  // Sin etiqueta, el número de lote (`seq`), nunca el `id` de la fila.
  const nombreLote = etiquetaFase(lote?.phase_label) ?? (lote ? `Lote ${numeroLote(lote.seq)}` : "Lote");

  if (borrando) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Borrando el lote…
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-6" data-loading={isLoading || undefined}>
      <BotonVolver rutaPadre="/modelos" etiquetaPadre="Modelos" className="w-fit" />
      {!isLoading && !lote ? (
        <EmptyState titulo="Lote no encontrado" descripcion="Puede que se haya borrado." />
      ) : (
        <>
          <PageHeader
            titulo={nombreLote}
            migas={
              lote
                ? [
                    { etiqueta: "Modelos", a: "/modelos" },
                    { etiqueta: proyecto?.name ?? String(lote.project_id), a: `/modelos/${lote.project_id}` },
                    { etiqueta: nombreLote },
                  ]
                : undefined
            }
            descripcion={
              lote ? (
                <span className="flex flex-col gap-1">
                  {/* «Lote #7 · lote-06.csv», el número y el fichero juntos. */}
                  <span className="flex min-w-0 items-baseline gap-1">
                    <span className="shrink-0">Lote {numeroLote(lote.seq)}</span>
                    {lote.dataset_name ?? dataset?.name ? <span aria-hidden="true">·</span> : null}
                    <FicheroLote nombre={lote.dataset_name ?? dataset?.name} />
                  </span>
                  <span>
                    Versión {version?.label ?? lote.model_version_id} · {lote.n_rows} filas (
                    {lote.n_labeled} etiquetadas) · {formatoFecha(lote.created_at)}
                  </span>
                  {dataset?.sha256_privado ? (
                    <span className="font-mono text-xs">hash {dataset.sha256_privado.slice(0, 16)}…</span>
                  ) : null}
                </span>
              ) : null
            }
            acciones={
              <>
                <Button size="sm" variant="outline" onClick={() => void evaluarDeNuevo()}>
                  Evaluar de nuevo
                </Button>
                <Button size="sm" variant="destructive" onClick={() => setBorrarAbierto(true)}>
                  Borrar lote
                </Button>
              </>
            }
          />

          {lote?.orden_manipulado ? (
            <div className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm">
              <StateBadge estado="aviso" texto="Orden manipulado" size="sm" />
              <p className="mt-1 text-muted-foreground">{lote.motivo_manipulacion}</p>
            </div>
          ) : null}

          {evalJobId !== null && (!evalJob.terminado || evalJob.status === "error") ? (
            <div className="flex flex-col gap-1">
              <Progress value={evalJob.progress * 100} />
              {evalJob.status === "error" ? (
                <div className="flex items-center justify-between gap-2">
                  <ErrorDeTrabajo error={evalJob.error} accion="La evaluación" className="text-xs" />
                  <Button size="sm" variant="outline" onClick={() => setEvalJobId(null)}>
                    Cerrar
                  </Button>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">{evalJob.message || "Evaluando…"}</p>
              )}
            </div>
          ) : null}

          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-semibold">Composición por grupo</h2>
            <ComposicionLote batchId={batchId} mapping={dataset?.mapping} projectId={lote?.project_id ?? null} />
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-semibold">Registros</h2>
            <RegistrosLote batchId={batchId} mapping={dataset?.mapping} projectId={lote?.project_id ?? null} />
          </section>
        </>
      )}

      <MotivoDialog
        open={borrarAbierto}
        onOpenChange={setBorrarAbierto}
        titulo="Borrar lote"
        descripcion="Esta acción no se puede deshacer: el lote y sus registros desaparecen."
        etiquetaConfirmar="Borrar"
        onConfirm={borrarLote}
      />
    </div>
  );
}
