/**
 * Distintivo de trabajos vivos en la cabecera: la tarjeta
 * del cuadro no se gana su sitio, el indicador de cabecera sí.
 * Solo pinta algo si hay trabajos `pendiente`/`en_curso`; al abrir, detalle
 * de progreso y cancelación.
 *
 * `useJobs` ya vivía en `api/queries.ts` (no en `pages/dashboard/`): nada que
 * mover, `JobsCard.tsx` lo usa igual para la tarjeta del cuadro de mando.
 *
 * El flujo global de `/api/events/stream` solo reparte mensajes de tipo
 * `event`, así que el avance fino de un trabajo no llega por ahí. Mientras haya trabajos vivos se refresca cada
 * dos segundos; en reposo, no se refresca.
 */

import { Loader2Icon } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { api } from "@/api/client";
import { mensajeDeError } from "@/api/client";
import { useJobs } from "@/api/queries";
import { useQueryClient } from "@tanstack/react-query";

const EN_CURSO = "pendiente,en_curso";

export function JobsBadge() {
  const queryClient = useQueryClient();
  const { data } = useJobs(EN_CURSO, { refetchInterval: (q) => (leerVivos(q.state.data) ? 2000 : false) });
  const trabajos = data?.items ?? [];
  const n = trabajos.length;

  const cancelar = async (jobId: number | null) => {
    if (jobId === null) return;
    try {
      await api.post(`/jobs/${jobId}/cancel`);
      toast.success("Cancelación pedida");
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (error) {
      toast.error(mensajeDeError(error));
    }
  };

  if (n === 0) return null;

  const tipos = [...new Set(trabajos.map((j) => j.kind))].join(", ");
  const texto = n === 1 ? "1 trabajo en curso" : `${n} trabajos en curso`;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2" title={tipos} aria-label={texto}>
          <Loader2Icon className="size-4 animate-spin" aria-hidden="true" />
          <span>{texto}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <p className="mb-2 text-sm font-semibold">Trabajos en curso</p>
        <ul className="flex flex-col gap-3">
          {trabajos.map((job) => (
            <li key={job.id} className="flex flex-col gap-1">
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate">
                  {job.kind} · {job.status}
                </span>
                <Button size="sm" variant="ghost" onClick={() => void cancelar(job.id)}>
                  Cancelar
                </Button>
              </div>
              <Progress value={Math.round((job.progress ?? 0) * 100)} />
              {job.message ? <p className="text-xs text-muted-foreground">{job.message}</p> : null}
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

function leerVivos(data: unknown): boolean {
  if (!data || typeof data !== "object" || !("items" in data)) return false;
  const items = (data as { items?: unknown[] }).items;
  return Array.isArray(items) && items.length > 0;
}
