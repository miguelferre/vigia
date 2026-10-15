/** Columnas de las tablas de datasets y lotes (partido de `datos.tsx` para no superar 9 KB). */

import { Link } from "react-router";

import type { Batch, Dataset, ProjectDetail } from "@/api/types";
import type { Glosario } from "@/api/queries-contenido";
import { InfoTooltip, StateBadge } from "@/components/vigia";
import type { LegacyColumnDef } from "@/components/vigia";
import { Button } from "@/components/ui/button";
import { formatoFecha } from "@/lib/metrics";
import { numeroLote } from "@/lib/fases";
import { ETIQUETA_KIND, ETIQUETA_ROLE, etiquetaLote } from "./etiquetas";

function CabeceraConAyuda({ titulo, ayuda }: { titulo: string; ayuda: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      {titulo}
      <InfoTooltip titulo={titulo} queMide={ayuda} />
    </span>
  );
}

const ETIQUETA_ESTADO_DATASET: Record<string, string> = {
  subido: "Subido",
  mapeado: "Mapeado",
  ingerido: "Ingerido",
  error: "Error en la ingesta",
};

export interface ColumnasDatasetArgs {
  glosario: Glosario | undefined;
  puedeMapear: boolean;
  onContinuar: (ds: Dataset) => void;
  onBorrar: (id: number) => Promise<void>;
}

export function columnasDataset({
  glosario,
  puedeMapear,
  onContinuar,
  onBorrar,
}: ColumnasDatasetArgs): LegacyColumnDef<Dataset, unknown>[] {
  return [
    { header: "Nombre", accessorKey: "name" },
    {
      id: "kind",
      header: () => (
        <CabeceraConAyuda
          titulo="Tipo"
          ayuda={
            glosario?.tipo_dataset.definicion ??
            "Qué contiene el dataset: predicciones, etiquetas reales, registro de uso, o varias cosas combinadas."
          }
        />
      ),
      cell: ({ row }) => ETIQUETA_KIND[row.original.kind] ?? row.original.kind,
    },
    {
      id: "role",
      header: () => (
        <CabeceraConAyuda
          titulo="Fase"
          ayuda={
            glosario?.fase_dataset.definicion ??
            "El momento del despliegue en que se recogieron los datos: línea base o producción."
          }
        />
      ),
      cell: ({ row }) => ETIQUETA_ROLE[row.original.role] ?? row.original.role,
    },
    {
      id: "estado",
      header: "Estado",
      cell: ({ row }) =>
        row.original.status === "error" ? (
          <div className="flex flex-col gap-0.5">
            <StateBadge estado="alerta" texto="Error en la ingesta" size="sm" />
            <span className="text-xs text-muted-foreground">Vuelve a subir el fichero.</span>
          </div>
        ) : (
          ETIQUETA_ESTADO_DATASET[row.original.status] ?? row.original.status
        ),
    },
    { header: "Filas", accessorKey: "n_rows" },
    {
      id: "fecha",
      header: "Fecha",
      cell: ({ row }) => formatoFecha(row.original.created_at),
    },
    {
      id: "acciones_dataset",
      header: "",
      cell: ({ row }) => {
        const ds = row.original;
        if (ds.id === null) return null;
        return (
          <div className="flex justify-end gap-2">
            {puedeMapear && (ds.status === "subido" || ds.status === "mapeado") ? (
              <Button size="sm" variant="outline" onClick={() => onContinuar(ds)}>
                {ds.status === "subido" ? "Mapear" : "Ingerir"}
              </Button>
            ) : null}
            {puedeMapear && ds.n_batches > 0 ? (
              // Un botón desactivado con su porqué en la ayuda, no una frase en cada fila.
              <span
                title={`Tiene ${ds.n_batches === 1 ? "1 lote" : `${ds.n_batches} lotes`}. Un dataset con lotes ingeridos no se puede borrar: borra antes ${ds.n_batches === 1 ? "su lote" : "sus lotes"} en la tabla Lotes (Ver lote, Borrar lote).`}
              >
                <Button size="sm" variant="destructive" disabled aria-label="Borrar (no disponible: borra antes sus lotes en la tabla Lotes)">
                  Borrar
                </Button>
              </span>
            ) : null}
            {puedeMapear && ds.n_batches === 0 ? (
              <Button size="sm" variant="destructive" onClick={() => void onBorrar(ds.id as number)}>
                Borrar
              </Button>
            ) : null}
          </div>
        );
      },
    },
  ];
}

export interface ColumnasLoteArgs {
  proyecto: ProjectDetail | undefined;
  glosario: Glosario | undefined;
  hayEtiquetasLote: boolean;
}

export function columnasLote({
  proyecto,
  glosario,
  hayEtiquetasLote,
}: ColumnasLoteArgs): LegacyColumnDef<Batch, unknown>[] {
  return [
    ...(hayEtiquetasLote
      ? [
          {
            id: "etiqueta_lote",
            header: () => (
              <CabeceraConAyuda
                titulo="Etiqueta del lote"
                ayuda={
                  glosario?.etiqueta_lote.definicion ??
                  "Nota de texto libre sobre el lote; no tiene efecto en ningún cálculo."
                }
              />
            ),
            cell: ({ row }) => etiquetaLote(row.original.phase_label) ?? "—",
          } satisfies LegacyColumnDef<Batch, unknown>,
        ]
      : []),
    {
      // El número de lote (desde 1) delante del fichero, para no confundir «Lote #7» con `lote-06`.
      id: "numero_lote",
      header: "Lote",
      cell: ({ row }) => numeroLote(row.original.seq),
    },
    {
      id: "fichero",
      header: "Fichero",
      cell: ({ row }) => row.original.dataset_name ?? <span className="text-muted-foreground">—</span>,
    },
    {
      id: "version",
      header: "Versión",
      cell: ({ row }) => {
        const v = proyecto?.versions.find((ver) => ver.id === row.original.model_version_id);
        return v?.label ?? row.original.model_version_id;
      },
    },
    { header: "Filas", accessorKey: "n_rows" },
    {
      id: "fecha_lote",
      header: "Fecha",
      cell: ({ row }) => formatoFecha(row.original.created_at),
    },
    {
      id: "orden",
      header: "Orden",
      cell: ({ row }) =>
        row.original.orden_manipulado ? (
          <StateBadge estado="aviso" texto="manipulado" size="sm" />
        ) : (
          <span className="text-muted-foreground">normal</span>
        ),
    },
    {
      id: "ver",
      header: "",
      cell: ({ row }) =>
        row.original.id !== null ? (
          <Button asChild size="sm" variant="outline">
            <Link to={`/datos/${row.original.id}`}>Ver lote</Link>
          </Button>
        ) : null,
    },
  ];
}
