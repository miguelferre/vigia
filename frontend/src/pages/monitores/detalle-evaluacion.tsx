/**
 * Detalle de una evaluación en panel lateral (medidas, `window` y
 * `config_snapshot` plegados, enlace al lote). `result_json` no se repite
 * (se usan `measurements` de primer
 * nivel.
 */

import { Link } from "react-router";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  CabeceraVentana,
  DataTable,
  EmptyState,
  JsonView,
  MetricLabel,
  StateBadge,
} from "@/components/vigia";
import { mensajeDeError } from "@/api/client";
import { formatoFecha, formatoMetrica, formatoNumero } from "@/lib/metrics";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { claseDeGrupo, esGrupoClase } from "@/lib/tipo-tarea";
import type { Measurement } from "@/api/types";

import { filasConfigConocidas } from "./etiquetas";
import { detalleFairness } from "./tipos";
import { useEvaluationDetail } from "./usarEvaluacion";

/** Medidas que son recuentos enteros (calidad): sin decimales, la coma no es de miles. */
const RECUENTOS = new Set(["n", "tp", "fp", "fn", "tn"]);

export interface DetalleEvaluacionProps {
  evaluacionId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DetalleEvaluacion({ evaluacionId, open, onOpenChange }: DetalleEvaluacionProps) {
  const detalleQ = useEvaluationDetail(evaluacionId);
  const d = detalleQ.data;
  const { tipo, caps, unidad } = useTipoTarea(d?.project_id ?? null);
  const conjuntoFavorable = caps?.favorables === "conjunto";
  const regresion = caps?.metricas === "regresion";
  // En regresión cada valor lleva su unidad y su signo; lo demás, como siempre.
  const f = (clave: string, v: number | null, decimales = 3) =>
    regresion && !RECUENTOS.has(clave) ? formatoMetrica(clave, v, unidad) : formatoNumero(v, decimales);

  const columns: LegacyColumnDef<Measurement, unknown>[] = [
    {
      id: "metrica",
      header: "Métrica",
      accessorFn: (m) => m,
      cell: (info) => {
        const m = info.getValue() as Measurement;
        // Un valor de una sola clase no es un macro: etiqueta sin «(macro)».
        return <MetricLabel metrica={m.metric_key} tipo={esGrupoClase(m.group_code) ? undefined : tipo} />;
      },
    },
    {
      id: "grupo",
      header: "Grupo",
      accessorFn: (m) => m.group_code,
      cell: (info) => {
        const grupo = info.getValue() as string | null;
        // `clase:<valor>` es una medida por clase, no un grupo protegido.
        const clase = claseDeGrupo(grupo);
        if (clase !== null) return `Clase: ${clase}`;
        // En multiclase, los recuentos y tasas globales son «clases favorables contra el resto».
        if (conjuntoFavorable && grupo === null && (RECUENTOS.has(info.row.original.metric_key) || ["label_rate", "prediction_rate"].includes(info.row.original.metric_key)))
          return "favorables contra el resto";
        return grupo ?? "global";
      },
    },
    {
      id: "valor",
      header: "Valor",
      accessorFn: (m) => m,
      cell: (info) => {
        const m = info.getValue() as Measurement;
        return f(m.metric_key, m.value, RECUENTOS.has(m.metric_key) ? 0 : 3);
      },
    },
    {
      id: "intervalo",
      header: "Intervalo",
      accessorFn: (m) => m,
      cell: (info) => {
        const m = info.getValue() as Measurement;
        if (m.interval_low === null || m.interval_high === null) return "—";
        return `${f(m.metric_key, m.interval_low)} – ${f(m.metric_key, m.interval_high)}`;
      },
    },
    {
      id: "umbral",
      header: "Umbral",
      accessorFn: (m) => m,
      cell: (info) => {
        const m = info.getValue() as Measurement;
        if (m.threshold_low === null && m.threshold_high === null) return "—";
        const partes: string[] = [];
        if (m.threshold_low !== null) partes.push(`≥ ${f(m.metric_key, m.threshold_low)}`);
        if (m.threshold_high !== null) partes.push(`≤ ${f(m.metric_key, m.threshold_high)}`);
        return partes.join(" / ");
      },
    },
    {
      id: "estado",
      header: "Estado",
      accessorFn: (m) => m,
      cell: (info) => {
        const m = info.getValue() as Measurement;
        // Una medida por clase no tiene umbral: sin estado de umbral, solo el «sin datos» con su motivo.
        if (
          m.state !== "sin_datos" &&
          (esGrupoClase(m.group_code) ||
            ((conjuntoFavorable || regresion) && m.threshold_low === null && m.threshold_high === null))
        )
          return "sin umbral";
        return (
          <div className="flex flex-col gap-0.5">
            <StateBadge estado={m.state} size="sm" />
            {m.motivo && <span className="text-xs text-muted-foreground whitespace-normal">{m.motivo}</span>}
          </div>
        );
      },
    },
  ];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>{d ? `Evaluación #${d.id}` : "Evaluación"}</SheetTitle>
          <SheetDescription>
            {d ? (
              <>
                {formatoFecha(d.created_at)} · disparada por {d.trigger}
                {d.batch_id !== null ? (
                  <>
                    {" "}
                    ·{" "}
                    <Button asChild variant="link" size="sm" className="h-auto p-0">
                      <Link to={`/datos/${d.batch_id}`}>ver lote</Link>
                    </Button>
                  </>
                ) : null}
              </>
            ) : (
              "Cargando la evaluación…"
            )}
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-6 px-4 pb-4">
          {detalleQ.isLoading ? (
            <Skeleton className="h-64 w-full" data-loading="true" />
          ) : detalleQ.isError || !d ? (
            <EmptyState
              titulo="No se pudo cargar la evaluación"
              descripcion={mensajeDeError(detalleQ.error)}
              accion={
                <Button size="sm" variant="outline" onClick={() => detalleQ.refetch()}>
                  Reintentar
                </Button>
              }
            />
          ) : (
            <>
              <div className="flex flex-col gap-2">
                <h3 className="text-sm text-muted-foreground">Ventana</h3>
                {(() => {
                  // Solo en equidad.
                  // (ventana de etiquetas acumuladas): en equidad desde
                  // `result.details.label_window`; en calidad, desde la
                  // propia `window` cuando acumula más de un lote
                  // (`tipos.ts`).
                  const { labelWindow, intervalMethod } = detalleFairness(d.result, d.monitor_type, d.window);
                  return (
                    <CabeceraVentana window={d.window} labelWindow={labelWindow} intervalMethod={intervalMethod} />
                  );
                })()}
              </div>

              {/* "Cómo se ha calculado" ya no se repite aquí: sigue a
                  la métrica ampliada en `/monitores/:tipo`, no al monitor. */}

              <DataTable data={d.measurements} columns={columns} titulo="Medidas de la evaluación" />

              <div className="flex flex-col gap-2">
                <h3 className="text-sm text-muted-foreground">Configuración usada</h3>
                {(() => {
                  const filas = filasConfigConocidas(d.config_snapshot);
                  return filas.length > 0 ? (
                    <table className="w-full text-sm">
                      <tbody>
                        {filas.map((f) => (
                          <tr key={f.clave} className="border-b last:border-0">
                            <td className="py-1.5 pr-3 align-top text-muted-foreground">{f.etiqueta}</td>
                            <td className="py-1.5 align-top tabular-nums">{f.valor}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <p className="text-sm text-muted-foreground">Sin configuración traducible en esta evaluación.</p>
                  );
                })()}
                <details className="text-xs">
                  <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                    Ver configuración técnica
                  </summary>
                  <div className="mt-2">
                    <JsonView valor={d.config_snapshot} />
                  </div>
                </details>
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
