/** Registros paginados de `/datos/:batch`, ocultos para el rol cliente. */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { ColumnMappingOut, ListResponse, Record_ } from "@/api/types";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { useCan } from "@/session/session";
import { DataTable, EmptyState, JsonView } from "@/components/vigia";
import type { LegacyColumnDef } from "@/components/vigia";
import { formatoFecha } from "@/lib/metrics";

import { etiquetaGrupo, etiquetaGrupoConPapel } from "./grupo";
import { columnasPrediccion } from "./registros-columnas";

interface Props {
  batchId: number;
  mapping?: ColumnMappingOut | null;
  /** Proyecto del lote: el tipo de tarea sale de él, no del proyecto de la sesión. */
  projectId: number | null;
}

const LIMITE = 50;

export default function RegistrosLote({ batchId, mapping, projectId }: Props) {
  const puedeVer = useCan("registros");
  // La predicción y la etiqueta salen según lo que da el modelo (probabilidad,
  // una por clase o un valor con su unidad); `registros-columnas.tsx` decide con `caps`.
  const tarea = useTipoTarea(projectId);
  const [offset, setOffset] = useState(0);
  const [conFeatures, setConFeatures] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: qk.records(batchId, { offset, limit: LIMITE, with_features: conFeatures }),
    queryFn: () =>
      api.get<ListResponse<Record_>>(`/batches/${batchId}/records`, {
        params: { offset, limit: LIMITE, with_features: conFeatures },
      }),
    enabled: puedeVer,
  });

  if (!puedeVer) {
    return (
      <EmptyState
        titulo="Registros no disponibles"
        descripcion="El rol cliente no ve los registros crudos de un lote."
      />
    );
  }

  // Sin el tipo de tarea no se eligen columnas (no parpadea de binario a multiclase).
  if (tarea.cargando) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Cargando los registros…
      </p>
    );
  }

  const columnas: LegacyColumnDef<Record_, unknown>[] = [
    { header: "Seq", accessorKey: "seq" },
    { header: "Id externo", accessorKey: "external_id" },
    {
      id: "fecha_registro",
      header: "Fecha",
      cell: ({ row }) => formatoFecha(row.original.timestamp),
    },
    ...columnasPrediccion(tarea),
    { header: "Valor protegido", accessorKey: "protected_value" },
    {
      id: "grupo",
      header: "Grupo",
      cell: ({ row }) => {
        const codigo = row.original.group_code;
        const etiqueta = row.original.group_label ?? (mapping ? etiquetaGrupo(codigo, mapping) : null);
        return etiquetaGrupoConPapel(codigo, etiqueta);
      },
    },
    ...(conFeatures
      ? ([
          {
            id: "features",
            header: "Features",
            cell: ({ row }) =>
              row.original.features ? (
                <JsonView valor={row.original.features} abiertoHasta={0} className="max-w-xs" />
              ) : (
                "—"
              ),
          },
        ] satisfies LegacyColumnDef<Record_, unknown>[])
      : []),
  ];

  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={conFeatures}
          onChange={(e) => {
            setConFeatures(e.target.checked);
            setOffset(0);
          }}
        />
        Incluir features
      </label>
      <DataTable
        data={data?.items ?? []}
        columns={columnas}
        total={data?.total}
        offset={offset}
        limit={LIMITE}
        onPageChange={setOffset}
        cargando={isLoading}
        titulo="Registros del lote"
      />
    </div>
  );
}
