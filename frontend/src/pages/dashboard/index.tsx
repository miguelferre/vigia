/**
 * Cuadro de mando (`/cuadro`, artboard `Main`).
 *
 * La tarjeta de pestañas se
 * sustituye por `TarjetasMonitor`, cuatro tarjetas siempre visibles; las dos
 * gráficas («Alertas por lote y monitor» y «Métrica por lote») por el panel
 * `PanelAlertasPorLote` con eje temporal compartido; y la tabla «Alertas que
 * requieren acción» pasa a cinco filas con criterio visible y filtro por el
 * tramo pulsado en el panel. Se mantiene la cabecera con migas y el último
 * lote evaluado.
 *
 * El `SelectorPeriodo` sigue fuera: ninguno de los widgets depende
 * del periodo (las gráficas son "todos los lotes", no un rango de fechas).
 */

import { DownloadIcon, UploadIcon } from "lucide-react";
import { Link } from "react-router";

import { mensajeDeError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/vigia";
import { useBatches, useProjectState } from "@/api/queries";
import { componerLote, etiquetaLote, numeroLote } from "@/lib/fases";
import { formatoRelativo } from "@/lib/fechas";
import { useTitulo } from "@/hooks/useTitulo";
import { useCan, useSession } from "@/session/session";
import { EmptyDashboard } from "./EmptyDashboard";
import { PanelAlertasPorLote } from "./PanelAlertasPorLote";
import { SinEvaluaciones } from "./SinEvaluaciones";
import { TablaAlertasAccion } from "./TablaAlertasAccion";
import { TarjetasMonitor } from "./TarjetasMonitor";

// `ProjectState.first_batch` (backend `services/projects.py:project_state`):
// tipo tolerante hasta que `npm run api:types` regenere `schema.d.ts` con el
// campo nuevo (`api/schema.d.ts` es generado y no se edita a mano).
interface PrimerLoteResumen {
  id: number | null;
  seq: number;
  phase_label: string | null;
}

function DescripcionCabecera({ projectId }: { projectId: number }) {
  const { data: state } = useProjectState(projectId);
  const primero =
    (state as { first_batch?: PrimerLoteResumen | null } | undefined)?.first_batch ?? null;
  const ultimo = state?.last_batch;
  // El nombre del lote junto a su número (`ProjectState` solo trae el id).
  const lotes = useBatches(projectId).data?.items;
  const nombreDe = (id: number | null | undefined): string =>
    id != null ? (lotes?.find((b) => b.id === id)?.dataset_name ?? "") : "";

  if (!ultimo) return null;
  return (
    <span>
      Último lote evaluado: {componerLote(numeroLote(ultimo.seq), nombreDe(ultimo.id), etiquetaLote(ultimo.phase_label))}{" "}
      · {formatoRelativo(ultimo.created_at)}
      {primero ? ` · línea base: lote ${componerLote(numeroLote(primero.seq), nombreDe(primero.id))}` : ""}
    </span>
  );
}

export default function Dashboard() {
  useTitulo("Cuadro de mando");
  const { projectId } = useSession();
  const { data: state, isPending, isError, error, refetch } = useProjectState(projectId);
  const puedeSubir = useCan("mapeos");

  if (projectId === null) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader titulo="Cuadro de mando" descripcion="Vigilancia de modelos de IA en producción." />
        <EmptyDashboard />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader titulo="Cuadro de mando" descripcion="Vigilancia de modelos de IA en producción." />
        <div className="flex flex-col items-start gap-2 rounded-lg border border-dashed border-destructive/50 px-4 py-8">
          <p className="text-sm text-destructive">
            No se ha podido cargar el estado del proyecto: {mensajeDeError(error)}
          </p>
          <Button type="button" variant="outline" size="sm" onClick={() => void refetch()}>
            Reintentar
          </Button>
        </div>
      </div>
    );
  }

  // "Sin evaluaciones" = ningún monitor configurado se ha evaluado nunca.
  const sinEvaluaciones =
    !isPending && (state?.monitors.length ?? 0) > 0 && state!.monitors.every((m) => m.last_evaluated_at === null);

  return (
    <div className="flex flex-col gap-6" data-loading={isPending ? "true" : undefined}>
      <PageHeader
        titulo="Cuadro de mando"
        migas={[{ etiqueta: "Vigilancia" }, { etiqueta: "Cuadro de mando" }]}
        descripcion={!sinEvaluaciones ? <DescripcionCabecera projectId={projectId} /> : undefined}
        acciones={
          <>
            <Button asChild type="button" variant="outline" size="sm">
              <Link to="/diario">
                <DownloadIcon className="size-4" aria-hidden="true" />
                Exportar el diario
              </Link>
            </Button>
            {puedeSubir ? (
              <Button asChild size="sm">
                <Link to={`/modelos/${projectId}#datos`}>
                  <UploadIcon className="size-4" aria-hidden="true" />
                  Subir lote
                </Link>
              </Button>
            ) : null}
          </>
        }
      />

      {sinEvaluaciones ? (
        <SinEvaluaciones projectId={projectId} />
      ) : (
        <>
          <TarjetasMonitor projectId={projectId} />
          <PanelAlertasPorLote projectId={projectId} />
          <TablaAlertasAccion projectId={projectId} />
        </>
      )}
    </div>
  );
}
