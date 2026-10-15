/**
 * Piezas puras de `RankingComparado.tsx` (partido para quedar por debajo de
 * 9 KB): el trazado de la barra, las etiquetas, el ancho de la columna
 * de nombres y las líneas del tooltip. El formato del número lo pone quien
 * llama (en regresión, con la unidad de la salida).
 */

import { formatoNumero } from "@/lib/metrics";
import { decimalesDelEje } from "@/pages/monitores/violin-silueta";
import type { FilaComparada } from "./ranking-comparado-datos";

const BAR_H = 14;
const BAR_R = 4;

/** Barra desde `x0` (línea base del eje, esquina cuadrada) hasta `x1` (dato, esquina redondeada). */
export function pathBarra(x0: number, x1: number, y: number): string {
  const alto = BAR_H;
  const r = Math.max(0, Math.min(BAR_R, alto / 2, x1 - x0));
  const yTop = y - alto / 2;
  const yBot = y + alto / 2;
  if (x1 - x0 <= r) return `M${x0},${yTop} H${x1} V${yBot} H${x0} Z`;
  return `M${x0},${yTop} H${x1 - r} Q${x1},${yTop} ${x1},${yTop + r} V${yBot - r} Q${x1},${yBot} ${x1 - r},${yBot} H${x0} Z`;
}

/** Etiqueta con la marca de «salió»/«nueva» incluida, para medir y dibujar lo mismo (nunca se recorta). */
export function textoEtiqueta(f: FilaComparada): string {
  if (f.marcada) return `${f.label} (fuera del top 10)`;
  if (f.base === null) return `${f.label} (nueva)`;
  return f.label;
}

export function anchoEtiquetas(filas: FilaComparada[]): number {
  const maxLargo = Math.max(0, ...filas.map((f) => textoEtiqueta(f).length));
  return Math.min(260, Math.max(130, 8 + maxLargo * 6));
}

export function puesto(p: number | null): string {
  return p === null ? "fuera del top 10" : `${p}.º`;
}

/** Más decimales que `decimalesDelEje` (violín): en [0,1] con 1 decimal 0,05 y 0,1 se leen igual. */
export function decimalesImportancia(dominioMax: number): number {
  if (dominioMax < 0.1) return 3;
  if (dominioMax < 1) return 2;
  return decimalesDelEje(0, dominioMax);
}

/** «Ahora 0,189 · Línea base 0,102 · 3.º → 2.º», en una sola línea bajo el nombre. */
export function lineasTooltip(f: FilaComparada, formato: (v: number) => string = formatoNumero): string[] {
  const ahora = f.actual === null ? "Ahora sin dato" : `Ahora ${formato(f.actual)}`;
  const base = f.base === null ? "Línea base sin dato" : `Línea base ${formato(f.base)}`;
  const rango = `${puesto(f.puestoBase)} → ${puesto(f.puestoActual)}`;
  return [f.label, `${ahora} · ${base} · ${rango}`];
}
