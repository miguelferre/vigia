/** Columnas de la tabla de versiones (partido de `versiones.tsx` para no superar 9 KB). */

import type { Batch, ModelVersion } from "@/api/types";
import type { Glosario } from "@/api/queries-contenido";
import { InfoTooltip } from "@/components/vigia";
import type { LegacyColumnDef } from "@/components/vigia";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArtefactoDetalle } from "./artefacto-detalle";
import { numeroLote } from "@/lib/fases";
import { etiquetaLote } from "./etiquetas";
import { AYUDA_TIPO_MODELO, LINEA_BASE_FIJADA, etiquetaTipoModelo } from "./versiones-textos";

export interface ColumnasVersionesArgs {
  lotes: readonly Batch[] | undefined;
  glosario: Glosario | undefined;
  onActivar: (v: ModelVersion) => void;
  onFijarLineaBase: (v: ModelVersion) => void;
  onSubirArtefacto: (v: ModelVersion) => void;
}

export function columnasVersiones({
  lotes,
  glosario,
  onActivar,
  onFijarLineaBase,
  onSubirArtefacto,
}: ColumnasVersionesArgs): LegacyColumnDef<ModelVersion, unknown>[] {
  return [
    { header: "Etiqueta", accessorKey: "label" },
    {
      id: "tipo",
      header: () => (
        <span className="inline-flex items-center gap-1">
          Tipo de modelo
          <InfoTooltip titulo="Tipo de modelo" queMide={AYUDA_TIPO_MODELO} />
        </span>
      ),
      cell: ({ row }) => etiquetaTipoModelo(row.original.model_kind),
    },
    {
      id: "activa",
      header: "Activa",
      cell: ({ row }) =>
        row.original.is_active ? <Badge>Activa</Badge> : <span className="text-muted-foreground">—</span>,
    },
    {
      id: "baseline",
      header: () => (
        <span className="inline-flex items-center gap-1">
          Línea base
          <InfoTooltip
            titulo="Línea base"
            queMide={glosario?.linea_base.definicion ?? "El lote contra el que se mide la deriva."}
          />
        </span>
      ),
      cell: ({ row }) => {
        const v = row.original;
        if (!v.baseline_batch_id) return <span className="text-muted-foreground">sin fijar</span>;
        const lote = lotes?.find((b) => b.id === v.baseline_batch_id);
        return lote ? (etiquetaLote(lote.phase_label) ?? `lote ${numeroLote(lote.seq)}`) : "lote no disponible";
      },
    },
    {
      id: "artefacto",
      header: () => (
        <span className="inline-flex items-center gap-1">
          Artefacto
          <InfoTooltip
            titulo="Artefacto del modelo"
            queMide="El fichero del modelo (ONNX o pickle) que Vigía usa para predecir y explicar. Sin subirlo, la explicabilidad no está disponible."
          />
        </span>
      ),
      cell: ({ row }) => <ArtefactoDetalle version={row.original} />,
    },
    {
      id: "ventana",
      header: () => (
        <span className="inline-flex items-center gap-1">
          Ventana de equidad
          <InfoTooltip
            titulo="Ventana de equidad"
            queMide={`${glosario?.ventana.definicion ?? "El conjunto de filas sobre el que se calcula una evaluación."} Fija al crear la versión: no se puede editar después.`}
          />
        </span>
      ),
      accessorKey: "fairness_window_n",
    },
    {
      id: "acciones",
      header: "",
      cell: ({ row }) => {
        const v = row.original;
        return (
          <div className="flex flex-wrap gap-2">
            {!v.is_active ? (
              <Button size="sm" variant="outline" onClick={() => onActivar(v)}>
                Activar
              </Button>
            ) : null}
            {v.frozen_at === null ? (
              <Button size="sm" variant="outline" onClick={() => onFijarLineaBase(v)}>
                Fijar línea base
              </Button>
            ) : (
              <span className="self-center text-xs text-muted-foreground">{LINEA_BASE_FIJADA}</span>
            )}
            <Button size="sm" variant="outline" onClick={() => onSubirArtefacto(v)}>
              Subir modelo
            </Button>
          </div>
        );
      },
    },
  ];
}
