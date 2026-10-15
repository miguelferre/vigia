/**
 * Explicabilidad: selector de versión y lote, lanzador y lista de
 * explicaciones con su detalle (ruta `/explicabilidad`).
 */

import { useMemo, useState } from "react";
import { InfoIcon } from "lucide-react";

import { useBatches, useExplanations, useProject } from "@/api/queries";
import { useExplanationsSummary } from "@/api/queries-explicabilidad";
import type { Batch, Explanation } from "@/api/types";
import { useSession } from "@/session/session";
import { DataTable, EmptyState, ErrorDeConsulta, PageHeader, SinProyecto } from "@/components/vigia";
import type { LegacyColumnDef } from "@/components/vigia";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useTitulo } from "@/hooks/useTitulo";
import { formatoFecha } from "@/lib/metrics";
import { componerLote, etiquetaFase, numeroLote } from "@/lib/fases";
import { ETIQUETA_KIND, etiquetaVersion } from "./etiquetas";
import { Lanzar } from "./lanzar";
import { DetalleExplicacion } from "./detalle";
import { EstadoExplicabilidad } from "./Estado";

/** «#2 · lote-02.csv · Evento 1»: número, nombre del lote y fase, los que haya. */
function textoLote(b: Batch): string {
  return componerLote(numeroLote(b.seq), b.dataset_name, etiquetaFase(b.phase_label));
}

export default function ExplicabilidadIndex() {
  useTitulo("Explicabilidad");
  const { projectId } = useSession();
  const proyecto = useProject(projectId);
  const batches = useBatches(projectId);

  const [versionId, setVersionId] = useState<number | null>(null);
  const [batchId, setBatchId] = useState<number | null>(null);
  const [seleccionada, setSeleccionada] = useState<number | null>(null);

  // Versión por defecto: se calcula en el render (no en un efecto) al llegar
  // el proyecto, siguiendo el mismo patrón que `MotivoDialog`/`useJob`.
  const [proyectoVisto, setProyectoVisto] = useState<typeof proyecto.data>(undefined);
  if (proyecto.data && proyecto.data !== proyectoVisto) {
    setProyectoVisto(proyecto.data);
    const yaElegida = proyecto.data.versions.some((v) => v.id === versionId);
    if (!yaElegida) {
      const activa = proyecto.data.versions.find((v) => v.is_active) ?? proyecto.data.versions[0];
      if (activa) setVersionId(activa.id);
    }
  }

  const explicaciones = useExplanations(versionId);
  const lista = useMemo(
    () => [...(explicaciones.data?.items ?? [])].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
    [explicaciones.data],
  );
  const resumen = useExplanationsSummary(projectId);

  const batchLabel = (id: number | null) => {
    if (id === null) return "Línea base";
    if (!batches.data) return "…";
    const b = batches.data.items.find((bb) => bb.id === id);
    // Sin el lote en la lista (borrado o aún sin cargar) no se enseña el `id` de la fila como si fuera su número.
    return b ? textoLote(b) : "no disponible";
  };

  const explicacionSeleccionada = lista.find((e) => e.id === seleccionada) ?? null;
  // Corrección: el aviso de «modelo simulado» es de antes de C7, cuando
  // `/explicabilidad` solo existía para sim_logistic; con un modelo
  // executable real (ONNX/joblib subido) no aplica y no debe verse.
  const versionActivaProyecto = proyecto.data?.versions.find((v) => v.is_active);
  const esSimulado = !versionActivaProyecto || versionActivaProyecto.model_kind === "sim_logistic";

  const columnas: LegacyColumnDef<Explanation, unknown>[] = [
    { id: "tipo", header: "Tipo", cell: ({ row }) => ETIQUETA_KIND[row.original.kind] },
    { id: "version", header: "Versión", cell: ({ row }) => etiquetaVersion(proyecto.data?.versions, row.original.model_version_id) },
    { id: "lote", header: "Lote", cell: ({ row }) => batchLabel(row.original.batch_id) },
    { id: "fecha", header: "Fecha", cell: ({ row }) => formatoFecha(row.original.created_at) },
    {
      id: "estado",
      header: "Estado",
      cell: ({ row }) => (row.original.available ? "Disponible" : `No disponible: ${row.original.motivo ?? ""}`),
    },
  ];

  if (projectId === null) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader titulo="Explicabilidad" />
        <SinProyecto que="su explicabilidad" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        titulo="Explicabilidad"
        descripcion="Importancia de las variables del modelo, global o para una fila concreta."
      />
      {esSimulado ? (
        <Alert>
          <InfoIcon />
          <AlertTitle>Explicabilidad del modelo simulado (datos sintéticos)</AlertTitle>
          <AlertDescription>
            Las importancias vienen del simulador de Vigía, no de un modelo real.
          </AlertDescription>
        </Alert>
      ) : null}

      {proyecto.isError || batches.isError ? (
        <ErrorDeConsulta
          que={proyecto.isError ? "el modelo" : "los lotes"}
          error={proyecto.isError ? proyecto.error : batches.error}
          onReintentar={() => void (proyecto.isError ? proyecto.refetch() : batches.refetch())}
        />
      ) : null}

      <EstadoExplicabilidad
        proyecto={proyecto.data}
        batchesCargando={batches.isLoading}
        hayLotes={(batches.data?.items.length ?? 0) > 0}
        lista={lista}
        resumen={resumen.data}
        onVer={setSeleccionada}
      />

      <details className="flex flex-col gap-3">
        <summary className="cursor-pointer text-md font-semibold select-none">
          Lanzar explicación a mano
        </summary>
        <div className="mt-2 flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="version-select">Versión</Label>
              <Select
                value={versionId !== null ? String(versionId) : undefined}
                onValueChange={(v) => (setVersionId(Number(v)), setBatchId(null))}
              >
                <SelectTrigger id="version-select" className="w-40">
                  <SelectValue placeholder="Versión" />
                </SelectTrigger>
                <SelectContent>
                  {(proyecto.data?.versions ?? []).map((v) => (
                    <SelectItem key={v.id} value={String(v.id)}>
                      {v.label} {v.is_active ? "(activa)" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="batch-select">Lote (opcional en global, obligatorio en local)</Label>
              <Select
                value={batchId !== null ? String(batchId) : "baseline"}
                onValueChange={(v) => setBatchId(v === "baseline" ? null : Number(v))}
              >
                <SelectTrigger id="batch-select" className="w-56">
                  <SelectValue placeholder="Lote" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="baseline">Línea base de la versión</SelectItem>
                  {(batches.data?.items ?? []).filter((b) => b.model_version_id === versionId).map((b) => (
                    <SelectItem key={b.id} value={String(b.id)}>
                      {textoLote(b)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {versionId !== null ? (
            <Lanzar versionId={versionId} batchId={batchId} projectId={projectId} onFinished={setSeleccionada} />
          ) : (
            <p className="text-sm text-muted-foreground">Esperando la versión del proyecto…</p>
          )}
        </div>
      </details>

      {lista.length >= 50 ? (
        <Alert>
          <InfoIcon />
          <AlertTitle>El listado puede estar incompleto</AlertTitle>
          <AlertDescription>
            Se muestran como mucho 50 explicaciones; si esta versión tiene más, las más antiguas no
            aparecen aquí.
          </AlertDescription>
        </Alert>
      ) : null}
      <DataTable
        data={lista}
        columns={columnas}
        cargando={explicaciones.isLoading}
        titulo="Explicaciones calculadas"
        onRowClick={(fila) => setSeleccionada(fila.id)}
        vacio={
          explicaciones.isError ? (
            <ErrorDeConsulta
              que="las explicaciones"
              error={explicaciones.error}
              onReintentar={() => void explicaciones.refetch()}
            />
          ) : (
            <EmptyState
              titulo="No hay explicaciones todavía"
              descripcion="Lanza una explicación global o local con el panel de arriba."
            />
          )
        }
      />

      {explicacionSeleccionada ? (
        <DetalleExplicacion explicacion={explicacionSeleccionada} loteEtiqueta={batchLabel(explicacionSeleccionada.batch_id)} />
      ) : null}
    </div>
  );
}
