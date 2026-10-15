/**
 * Datos puros de las pantallas de regresión de los monitores: claves de los titulares, lectura defensiva de `details` de calidad y
 * de deriva, y las frases con palabras del sesgo. Sin React. Los
 * lectores de equidad viven en `regresion-equidad-datos.ts`.
 *
 * `details` es JSON libre en el OpenAPI: cada lector devuelve `null` si falta
 * lo que la pantalla necesita, y la pantalla dice por qué no hay gráfico.
 */

import { formatoMetrica } from "@/lib/metrics";
import type { CapacidadesTarea } from "@/lib/tipo-tarea";

/** Titulares de la calidad de regresión, en el orden de la rejilla. */
export const TITULARES_REGRESION = ["mean_absolute_error", "root_mean_squared_error", "r2", "mean_error"] as const;

/** Medidas de equidad por el error de cada grupo: las que siempre existen en regresión. */
export const EQUIDAD_ERROR = ["mean_absolute_error_difference", "mean_absolute_error_ratio", "mean_error_difference"] as const;

export function esEquidadError(clave: string): boolean {
  return (EQUIDAD_ERROR as readonly string[]).includes(clave);
}

export type Obj = Record<string, unknown>;

export function obj(v: unknown): Obj | null {
  return v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : null;
}

export function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function numeros(v: unknown): number[] | null {
  if (!Array.isArray(v)) return null;
  const lista = v.map(num);
  return lista.every((x) => x !== null) ? (lista as number[]) : null;
}

export function detallesDe(result: unknown): Obj | null {
  return obj(obj(result)?.details);
}

/** Histograma con `bin_edges` (k + 1 cortes) y `counts` (k recuentos). */
export interface HistogramaNumerico {
  binEdges: number[];
  counts: number[];
}

export function leerHistograma(v: unknown): HistogramaNumerico | null {
  const o = obj(v);
  const binEdges = numeros(o?.bin_edges);
  const counts = numeros(o?.counts);
  if (!binEdges || !counts || binEdges.length !== counts.length + 1) return null;
  return { binEdges, counts };
}

export interface ResiduosLote {
  histograma: HistogramaNumerico;
  media: number | null;
  desviacion: number | null;
  n: number | null;
}

export interface TramoPredVsReal {
  decil: number;
  predMedia: number;
  realMedia: number;
  realP10: number;
  realP90: number;
  n: number;
}

export interface DetalleCalidadRegresion {
  unidad: string | null;
  residuos: ResiduosLote | null;
  predVsReal: TramoPredVsReal[];
}

/** `details` de calidad de regresión; `null` si la evaluación no trae `details`. */
export function leerCalidadRegresion(result: unknown): DetalleCalidadRegresion | null {
  const d = detallesDe(result);
  if (!d) return null;
  const r = obj(d.residuos);
  const h = leerHistograma(r);
  const tramos: TramoPredVsReal[] = [];
  if (Array.isArray(d.pred_vs_real)) {
    for (const t of d.pred_vs_real) {
      const o = obj(t);
      const predMedia = num(o?.pred_media);
      const realMedia = num(o?.real_media);
      const realP10 = num(o?.real_p10);
      const realP90 = num(o?.real_p90);
      if (o === null || predMedia === null || realMedia === null || realP10 === null || realP90 === null) continue;
      tramos.push({ decil: num(o.decil) ?? tramos.length + 1, predMedia, realMedia, realP10, realP90, n: num(o.n) ?? 0 });
    }
  }
  return {
    unidad: typeof d.unidad === "string" ? d.unidad : null,
    residuos: h && r ? { histograma: h, media: num(r.media), desviacion: num(r.desviacion), n: num(r.n) } : null,
    predVsReal: tramos,
  };
}

/** Media y desviación del residuo de una evaluación, para comparar la línea base con el lote. */
export function leerResumenResiduos(result: unknown): { media: number; desviacion: number | null } | null {
  const r = obj(detallesDe(result)?.residuos);
  const media = num(r?.media);
  return media === null ? null : { media, desviacion: num(r?.desviacion) };
}

export interface PrediccionDeriva {
  ks: number | null;
  ksP: number | null;
  psi: number | null;
  psiMotivo: string | null;
  binEdges: number[];
  base: number[];
  actual: number[];
  mediaBase: number | null;
  mediaActual: number | null;
  diferenciaMedias: number | null;
}

/** `details.prediction` de la deriva de regresión. */
export function leerPrediccionDeriva(result: unknown): PrediccionDeriva | null {
  const p = obj(detallesDe(result)?.prediction);
  if (!p) return null;
  const binEdges = numeros(p.bin_edges);
  const base = numeros(p.bin_counts_base);
  const actual = numeros(p.bin_counts_actual);
  if (!binEdges || !base || !actual || base.length !== actual.length || binEdges.length !== base.length + 1) return null;
  return {
    ks: num(p.ks),
    ksP: num(p.ks_p),
    psi: num(p.psi),
    psiMotivo: typeof p.psi_motivo === "string" ? p.psi_motivo : null,
    binEdges,
    base,
    actual,
    mediaBase: num(p.media_base),
    mediaActual: num(p.media_actual),
    diferenciaMedias: num(p.diferencia_medias),
  };
}

/** Deriva del valor real (sin umbral), solo si los dos lados tienen etiqueta. */
export function leerEtiquetaDeriva(result: unknown): { ks: number; ksP: number | null; diferenciaMedias: number | null } | null {
  const e = obj(detallesDe(result)?.etiqueta);
  const ks = num(e?.ks);
  return ks === null ? null : { ks, ksP: num(e?.ks_p), diferenciaMedias: num(e?.diferencia_medias) };
}

/**
 * Frase del sesgo con palabras: «El modelo asigna de media 6,2 horas por
 * semana menos que la referencia». El signo del sesgo es predicción menos
 * real: negativo infraestima. `referencia` es lo que se compara («el valor
 * real», «el grupo de referencia»).
 */
export function fraseSesgo(valor: number | null, unidad: string | null, referencia: string): string {
  if (valor === null) return "Sin valor.";
  if (Math.abs(valor) < 5e-4) return `El modelo acierta de media con ${referencia}.`;
  const cuanto = formatoMetrica("mean_absolute_error", Math.abs(valor), unidad);
  return valor < 0
    ? `El modelo asigna de media ${cuanto} menos que ${referencia}.`
    : `El modelo asigna de media ${cuanto} más que ${referencia}.`;
}

/** Misma frase para la diferencia de medias de la deriva: lo de hoy frente a la línea base. */
export function fraseDiferenciaMedias(valor: number | null, unidad: string | null): string {
  if (valor === null) return "Sin diferencia de medias.";
  if (Math.abs(valor) < 5e-4) return "El lote predice de media lo mismo que la línea base.";
  const cuanto = formatoMetrica("mean_absolute_error", Math.abs(valor), unidad);
  return valor < 0
    ? `El lote predice de media ${cuanto} menos que la línea base.`
    : `El lote predice de media ${cuanto} más que la línea base.`;
}

/**
 * La calidad no evalúa umbrales de fábrica (ni en multiclase ni en
 * regresión): solo valen los de la línea base o los de una persona.
 */
export function calidadSinFabrica(caps: CapacidadesTarea | undefined, monitorType: string): boolean {
  return monitorType === "quality" && caps !== undefined && (caps.matriz === "kxk" || caps.metricas === "regresion");
}

/** Unidad con la que se escribe una medida: la de la salida, o su cuadrado en el MSE. */
export function textoUnidadMedida(clave: string, unidad: string): string {
  if (clave !== "mean_squared_error") return unidad;
  return /\s/.test(unidad) ? `(${unidad})²` : `${unidad}²`;
}

/** Ticks redondos (paso 1, 2, 2,5 o 5 por 10^k) entre `min` y `max`: de 4 a 7 marcas. */
export function ticksRedondos(min: number, max: number): number[] {
  if (!(max > min)) return [];
  const rango = max - min;
  const exp = Math.floor(Math.log10(rango));
  const pasos: number[] = [];
  for (let k = exp - 2; k <= exp + 1; k++) for (const b of [1, 2, 2.5, 5]) pasos.push(b * 10 ** k);
  for (const paso of pasos.sort((a, b) => a - b)) {
    const primero = Math.ceil(min / paso - 1e-9) * paso;
    const cuenta = Math.floor((max - primero) / paso + 1e-9) + 1;
    if (cuenta >= 4 && cuenta <= 7) {
      return Array.from({ length: cuenta }, (_, i) => Math.round((primero + i * paso) * 1e9) / 1e9);
    }
  }
  return [];
}
