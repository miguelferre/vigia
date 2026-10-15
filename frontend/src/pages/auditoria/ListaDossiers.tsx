/**
 * Lista de dossiers de un proyecto y sus revisiones. El dossier seleccionado
 * (`?dossier=<id>` en la URL) es del padre (`index.tsx`, que también lo necesita para el lanzador de revisión): esta
 * pantalla solo lo pinta y avisa al elegir uno nuevo.
 */

import { DataTable, EmptyState, StateBadge } from "@/components/vigia";
import type { LegacyColumnDef } from "@/components/vigia";
import { formatoFecha } from "@/lib/metrics";
import type { Dossier, DossierConReviews, DossierReviewResumen } from "@/api/types";
import { useDossiers } from "@/api/queries-auditoria";

const ESTADO_A_MOTOR: Record<DossierReviewResumen["status"], "ok" | "aviso" | "alerta" | "inestable" | "sin_datos"> = {
  terminada: "ok",
  en_curso: "aviso",
  pendiente: "sin_datos",
  error: "alerta",
  cancelada: "inestable",
};

export interface ListaDossiersProps {
  projectId: number;
  dossierId: number | null;
  detalle: DossierConReviews | undefined;
  detalleCargando: boolean;
  onSeleccionarDossier: (dossierId: number) => void;
  reviewSeleccionada: number | null;
  onSeleccionarRevision: (reviewId: number) => void;
}

export function ListaDossiers({
  projectId,
  dossierId,
  detalle,
  detalleCargando,
  onSeleccionarDossier,
  reviewSeleccionada,
  onSeleccionarRevision,
}: ListaDossiersProps) {
  const dossiers = useDossiers(projectId);

  const columnas: LegacyColumnDef<Dossier, unknown>[] = [
    { id: "nombre", header: "Sistema", cell: ({ row }) => row.original.system_name },
    { id: "dominio", header: "Dominio", cell: ({ row }) => row.original.domain },
    {
      id: "telemetria",
      header: "Telemetría",
      cell: ({ row }) => (row.original.telemetry_included ? "Adjunta" : "No adjunta"),
    },
    { id: "fecha", header: "Fecha", cell: ({ row }) => formatoFecha(row.original.created_at) },
  ];

  return (
    <div className="flex flex-col gap-4">
      <DataTable
        data={dossiers.data?.items ?? []}
        columns={columnas}
        cargando={dossiers.isLoading}
        titulo="Dossiers del proyecto"
        onRowClick={(fila) => fila.id !== null && onSeleccionarDossier(fila.id)}
        claveFila={(fila) => fila.id ?? 0}
        filaResaltada={(fila) => fila.id === dossierId}
        vacio={
          <EmptyState
            titulo="Sin dossiers todavía"
            descripcion="Crea el primero con el formulario de arriba."
          />
        }
      />

      {dossierId !== null ? (
        <div className="flex flex-col gap-3 rounded-lg border border-border p-4">
          <h3 className="text-sm font-semibold">Revisiones de este dossier</h3>
          {detalleCargando ? (
            <p className="text-sm text-muted-foreground">Cargando…</p>
          ) : (detalle?.reviews.length ?? 0) === 0 ? (
            <p className="text-sm text-muted-foreground">
              Todavía no hay ninguna revisión lanzada sobre este dossier.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {detalle?.reviews.map((revision) => (
                <li key={revision.id}>
                  <button
                    type="button"
                    onClick={() => revision.id !== null && onSeleccionarRevision(revision.id)}
                    className="flex w-full items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-left text-sm hover:bg-accent"
                    data-activo={revision.id === reviewSeleccionada ? "true" : undefined}
                  >
                    <span>
                      {revision.approach === "b0"
                        ? "Rápida, sin modelo de lenguaje"
                        : revision.approach === "p3"
                          ? "Con modelo de lenguaje"
                          : "Automática"}
                      {" · "}
                      {formatoFecha(revision.created_at)}
                      {revision.n_findings !== null ? ` · ${revision.n_findings} hallazgos` : ""}
                    </span>
                    <StateBadge estado={ESTADO_A_MOTOR[revision.status]} texto={revision.status} size="sm" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
