/**
 * Filas del panel «Alertas por lote» a partir de `AlertSeriesItem` (B3):
 * etiqueta del eje, valor por monitor (bruto en lote, alertas por lote
 * evaluado en día u hora) y los datos crudos que necesita el
 * tooltip.
 */

import { numeroLote } from "@/lib/fases";
import type { AlertSeriesItem, MonitorType, SeriesGranularity } from "@/api/types";

export interface Fila {
  key: string;
  etiqueta: string;
  fairness: number;
  quality: number;
  drift: number;
  total: number;
  alta: number;
  media: number;
  baja: number;
  nBatches: number;
  nChecks: number;
  faseLabel: string | null;
  item: AlertSeriesItem;
}

/** «dd/mm HH:mm» de una fecha ISO, sin año: cabe en el eje de lote. A mano
 * (no `toLocaleDateString`): Chromium no rellena el día con cero en es-ES. */
export function fechaHoraCorta(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const dos = (n: number) => String(n).padStart(2, "0");
  return `${dos(d.getDate())}/${dos(d.getMonth() + 1)} ${dos(d.getHours())}:${dos(d.getMinutes())}`;
}

const LARGO_MAXIMO_NOMBRE = 40;

/** Título del tooltip (`Main.dc.html`, `Escala.dc.html`): «Lote #8 · 15/09 15:08»
 * por lote, con el nombre del lote entre el número y la fecha cuando lo trae
 * («Lote #2 · lote-02.csv · 15/09 15:08»); «15/09 · 12 lotes · 65
 * alertas» por día u hora. */
export function tituloTramo(fila: Fila, granularidad: SeriesGranularity): string {
  if (granularidad === "batch") {
    const lote = fila.item.batches[0];
    const nombre = lote?.name?.trim();
    if (!lote || !nombre) return `Lote ${fila.etiqueta}`;
    const corto = nombre.length > LARGO_MAXIMO_NOMBRE ? `${nombre.slice(0, LARGO_MAXIMO_NOMBRE - 1)}…` : nombre;
    return `Lote ${numeroLote(lote.seq)} · ${corto} · ${fechaHoraCorta(fila.item.start)}`;
  }
  return `${fila.etiqueta} · ${plural(fila.total, "alerta", "alertas")}`;
}

/** Extremo del rango visible para el pie del navegador: fecha y hora del
 * lote, o la etiqueta del tramo en día u hora. */
export function extremoRango(fila: Fila, granularidad: SeriesGranularity): string {
  return granularidad === "batch" ? fechaHoraCorta(fila.item.start) : fila.item.label;
}

function plural(n: number, singular: string, plural_: string): string {
  return n === 1 ? `1 ${singular}` : `${n} ${plural_}`;
}

/** Etiqueta del eje: por lote `#seq · dd/mm HH:mm` (propia: el
 * label del servidor con «#N» no se usa en pantalla); por día u hora, el
 * label del servidor («dd/mm» o «dd/mm HH:00») más el número de lotes. */
export function etiquetaEje(item: AlertSeriesItem, granularidad: SeriesGranularity): string {
  if (granularidad === "batch") {
    const seq = item.batches[0]?.seq ?? null;
    return `${numeroLote(seq)} · ${fechaHoraCorta(item.start)}`;
  }
  return `${item.label} · ${plural(item.n_batches, "lote", "lotes")}`;
}

/** Valor de una serie de monitor: bruto por lote; alertas por lote
 * evaluado (redondeado a un decimal) en día u hora. */
export function valorMonitor(item: AlertSeriesItem, monitor: "fairness" | "quality" | "drift", granularidad: SeriesGranularity): number {
  const bruto = item.by_monitor[monitor];
  if (granularidad === "batch") return bruto;
  if (item.n_batches === 0) return 0;
  return Math.round((bruto / item.n_batches) * 10) / 10;
}

export function construirFilas(items: AlertSeriesItem[], granularidad: SeriesGranularity): Fila[] {
  return items.map((item) => ({
    key: item.key,
    etiqueta: etiquetaEje(item, granularidad),
    fairness: valorMonitor(item, "fairness", granularidad),
    quality: valorMonitor(item, "quality", granularidad),
    drift: valorMonitor(item, "drift", granularidad),
    total: item.total,
    alta: item.by_severity.alta,
    media: item.by_severity.media,
    baja: item.by_severity.baja,
    nBatches: item.n_batches,
    nChecks: item.n_checks,
    faseLabel: item.batches.every((b) => b.phase_label === item.batches[0]?.phase_label)
      ? (item.batches[0]?.phase_label ?? null)
      : null,
    item,
  }));
}

/** Cifra con coma decimal cuando la granularidad la necesita (día u hora);
 * entero seco por lote. Para el eje Y y los `LabelList`. */
export function formatoCifra(valor: number, granularidad: SeriesGranularity): string {
  const decimales = granularidad === "batch" ? 0 : 1;
  return valor.toLocaleString("es-ES", { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
}

export function formatoPorcentaje(valor: number): string {
  return `${Math.round(valor * 100)} %`;
}

/** Grupos de tramos consecutivos con la misma fase, para las `ReferenceArea`
 * (también en demo, con la etiqueta
 * traducida por `etiquetaLote()` en `GraficaMonitores`). Cada grupo guarda
 * el índice de inicio y fin (inclusive) sobre el array de filas visible. */
export function agruparFases(filas: Fila[]): { faseLabel: string; inicio: number; fin: number }[] {
  const grupos: { faseLabel: string; inicio: number; fin: number }[] = [];
  filas.forEach((fila, i) => {
    if (!fila.faseLabel) return;
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && ultimo.faseLabel === fila.faseLabel && ultimo.fin === i - 1) {
      ultimo.fin = i;
    } else {
      grupos.push({ faseLabel: fila.faseLabel, inicio: i, fin: i });
    }
  });
  return grupos;
}

export const CONFIG_MONITORES: Record<Exclude<MonitorType, "cross" | "explain">, { label: string; color: string }> = {
  // Equidad magenta, calidad teal,
  // deriva violeta; el mismo orden que la diapositiva 3 (`diagramas/D03.tsx`).
  fairness: { label: "Equidad", color: "var(--chart-2)" },
  quality: { label: "Calidad", color: "var(--chart-3)" },
  drift: { label: "Deriva", color: "var(--chart-1)" },
};
