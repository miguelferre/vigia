/**
 * Tabla de evaluaciones de un monitor (fecha, lote/fase, estado
 * global, n, medidas por estado). La `n` sale de `evaluation.window.n`, ya
 * presente en la lista ligera (`GET /evaluations`), sin petición extra. Los
 * recuentos por estado sí exigen el detalle de cada fila: para no disparar
 * una petición sin tope, solo se piden para las primeras `TOPE_DETALLE`
 * filas (la tabla no pagina en cliente todavía).
 */

import { useMemo } from "react";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";

import { DataTable, StateBadge } from "@/components/vigia";
import { useBatches } from "@/api/queries";
import { formatoFecha } from "@/lib/metrics";
import type { Batch, EstadoMotor, Evaluation } from "@/api/types";

import { numeroLote } from "@/lib/fases";
import { FicheroLote } from "@/pages/datos/lote-fichero";
import { esGrupoClase } from "@/lib/tipo-tarea";
import { etiquetaLote } from "./etiquetas";
import { useEvaluationDetails } from "./usarEvaluacion";
import { nDeVentana, TOPE_DETALLE } from "./tipos";
import { filasPorLote } from "./filas-evaluaciones";

export interface EvaluacionesMonitorProps {
  evaluaciones: Evaluation[];
  projectId: number;
  cargando: boolean;
  onSeleccionar: (id: number) => void;
}

const ORDEN_ESTADOS: EstadoMotor[] = ["alerta", "inestable", "aviso", "sin_datos", "ok"];

export function EvaluacionesMonitor({ evaluaciones: todas, projectId, cargando, onSeleccionar }: EvaluacionesMonitorProps) {
  const batchesQ = useBatches(projectId);
  // Una fila por lote con su evaluación más reciente, ordenada por lote.
  const filas = useMemo(
    () => filasPorLote(todas, (id) => (batchesQ.data?.items ?? []).find((b) => b.id === id)?.seq ?? null),
    [todas, batchesQ.data],
  );
  const evaluaciones = useMemo(() => filas.map((f) => f.evaluacion), [filas]);
  const reevaluadas = useMemo(
    () => new Set(filas.filter((f) => f.reevaluado).map((f) => f.evaluacion.id)),
    [filas],
  );
  const idsConDetalle = evaluaciones
    .map((e) => e.id)
    .filter((id): id is number => id !== null)
    .slice(0, TOPE_DETALLE);
  const detalles = useEvaluationDetails(idsConDetalle);

  const batchesPorId = useMemo(() => {
    const mapa = new Map<number, Batch>();
    for (const b of batchesQ.data?.items ?? []) {
      if (b.id !== null) mapa.set(b.id, b);
    }
    return mapa;
  }, [batchesQ.data]);
  const porEstadoPorId = useMemo(() => {
    const mapa = new Map<number, Partial<Record<EstadoMotor, number>>>();
    for (const q of detalles) {
      const d = q.data;
      if (!d || d.id === null) continue;
      const porEstado: Partial<Record<EstadoMotor, number>> = {};
      // Una medida por clase no tiene umbral; no cuenta en «Medidas por estado».
      for (const m of d.measurements) {
        if (esGrupoClase(m.group_code)) continue;
        porEstado[m.state] = (porEstado[m.state] ?? 0) + 1;
      }
      mapa.set(d.id, porEstado);
    }
    return mapa;
  }, [detalles]);
  const erroresPorId = useMemo(() => {
    const set = new Set<number>();
    idsConDetalle.forEach((id, idx) => {
      if (detalles[idx]?.isError) set.add(id);
    });
    return set;
  }, [detalles, idsConDetalle]);

  const columns: LegacyColumnDef<Evaluation, unknown>[] = [
    {
      id: "fecha",
      header: "Fecha",
      accessorFn: (e) => e.created_at,
      cell: (info) => formatoFecha(info.getValue() as string),
    },
    {
      id: "lote",
      header: "Lote",
      accessorFn: (e) => e.id,
      cell: (info) => {
        const ev = evaluaciones.find((e) => e.id === info.getValue());
        const batchId = ev?.batch_id ?? null;
        const marca = reevaluadas.has(ev?.id ?? null) ? (
          <span className="text-xs text-tertiary">reevaluado</span>
        ) : null;
        if (batchId === null) return <div className="flex flex-col"><span>Acumulado</span>{marca}</div>;
        const b = batchesPorId.get(batchId);
        // Nunca `batch.id` como número de lote.
        if (!b) return <div className="flex flex-col"><span>Lote {numeroLote(undefined)}</span>{marca}</div>;
        // «Lote #6 · fase» o, sin fase, con el nombre del fichero.
        const fase = etiquetaLote(b.phase_label);
        // El nombre del fichero junto al número, recortado y entero en `title`.
        return (
          <div className="flex flex-col">
            <span className="flex min-w-0 items-baseline gap-1">
              <span className="shrink-0">
                Lote {numeroLote(b.seq)}
                {fase ? ` · ${fase}` : ""}
              </span>
              {!fase && b.dataset_name ? <span aria-hidden="true">·</span> : null}
              {!fase ? <FicheroLote nombre={b.dataset_name} /> : null}
            </span>
            {fase ? <FicheroLote nombre={b.dataset_name} className="text-xs text-tertiary" /> : null}
            {marca}
          </div>
        );
      },
    },
    // #269b: sin columna «Etiqueta del lote»; la fase ya sale en «Lote #6 · fase».
    {
      id: "estado",
      header: "Estado global",
      accessorFn: (e) => e.worst_state,
      cell: (info) => <StateBadge estado={info.getValue() as EstadoMotor | null} size="sm" />,
    },
    {
      id: "n",
      header: "N (tamaño de la ventana)",
      accessorFn: (e) => e.window,
      cell: (info) => {
        const n = nDeVentana(info.getValue() as Evaluation["window"]);
        return n === null ? "n/d" : n.toLocaleString("es-ES");
      },
    },
    {
      id: "por_estado",
      header: "Medidas por estado",
      accessorFn: (e) => e.id,
      cell: (info) => {
        const id = info.getValue() as number;
        if (erroresPorId.has(id)) return <span className="text-destructive">error al cargar</span>;
        const porEstado = porEstadoPorId.get(id);
        if (!porEstado) return idsConDetalle.includes(id) ? "…" : "n/d";
        const presentes = ORDEN_ESTADOS.filter((s) => (porEstado[s] ?? 0) > 0);
        if (presentes.length === 0) return "—";
        return (
          <div className="flex flex-wrap gap-1">
            {presentes.map((s) => (
              <StateBadge key={s} estado={s} size="sm" texto={String(porEstado[s])} />
            ))}
          </div>
        );
      },
    },
  ];

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm text-muted-foreground">Evaluaciones</h2>
      <DataTable
        data={evaluaciones}
        columns={columns}
        cargando={cargando}
        onRowClick={(e) => e.id !== null && onSeleccionar(e.id)}
        titulo="Evaluaciones del monitor"
      />
    </section>
  );
}
