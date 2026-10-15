/**
 * Tipos, agrupación y textos del violín «lote a lote»: sin React ni recharts. El cálculo numérico (densidad, mediana,
 * PCHIP, ticks) vive en `violin-silueta.ts`, fichero hermano; `caminoViolin`
 * y `lineasTooltip` viven aquí y no en `violin-svg.tsx` para que ningún
 * fichero pase de 9 KB. `ViolinLoteALote.tsx` consume `prepararViolines`;
 * `violin-svg.tsx`, el resto.
 */

import { formatoCorto, formatoNumero } from "@/lib/metrics";

import { densidadPorTramo, medianaDeTramos, siluetaMonotona } from "./violin-silueta";

/** Un lote a dibujar, ya resuelto por el llamador (F2: `DistribucionesDeriva.tsx`). */
export interface LoteDeriva {
  evaluationId: number;
  batchId: number;
  seq: number;
  /** Ya formateado, p.ej. «#6». */
  numero: string;
  /** Ya traducida, p.ej. «Evento 1»; `null` si el lote no tiene fase. */
  fase: string | null;
}

/** Tramos de una variable numérica en un lote concreto (línea base y actual comparten `edges`). */
export interface VariableEnLote {
  edges: number[];
  countsBase: number[];
  countsActual: number[];
  psi: number | null;
  ksStat: number | null;
  ksP: number | null;
  /** `window.n` de la evaluación: puede ser mayor que la suma de `countsActual`. */
  nVentana: number | null;
  modelVersion: string | null;
}

export type LecturaPsi = "estable" | "cambio moderado" | "cambio fuerte";

/** Un violín ya listo para `violin-svg.tsx`, en el mismo orden que los huecos del eje X. */
export interface ViolinPreparado {
  clave: string;
  tipo: "base" | "lote";
  /** «Línea base», «Línea base · v2» o «#6». */
  etiqueta: string;
  fase: string | null;
  /** Índice del grupo de línea base al que pertenece (0, 1, ...). */
  grupo: number;
  silueta: { valor: number; densidad: number }[];
  mediana: number | null;
  n: number;
  /** Filas de `nVentana` que no entraron en `n` (fuera del rango de la línea base). */
  fuera: number;
  psi: number | null;
  lectura: LecturaPsi | null;
  ksStat: number | null;
  ksP: number | null;
}

/** Tramo de la línea discontinua de la mediana de una línea base, por índice de hueco. */
export interface TramoMediana {
  grupo: number;
  desde: number;
  hasta: number;
  mediana: number;
  etiqueta: string;
}

/** Entrada de `prepararViolines`: el lote y su variable ya extraída (`null` si no se pudo). */
export interface EntradaViolin {
  lote: LoteDeriva;
  variable: VariableEnLote | null;
}

export interface ViolinesPreparados {
  violines: ViolinPreparado[];
  tramosMediana: TramoMediana[];
  densidadMax: number;
  min: number;
  max: number;
  omitidos: number;
}

/** Lectura del PSI (glosario): menos de 0,10 estable, hasta 0,25 moderado, desde ahí fuerte. */
export function lecturaPsi(psi: number | null): LecturaPsi | null {
  if (psi === null) return null;
  if (psi >= 0.25) return "cambio fuerte";
  if (psi >= 0.1) return "cambio moderado";
  return "estable";
}

/**
 * Agrupa por firma de línea base (`edges` + `countsBase`), inserta el violín
 * teal de cada grupo antes de su primer lote y calcula la escala y los tramos
 * de la mediana discontinua. Descarta entradas sin variable o sin densidad.
 */
export function prepararViolines(entradas: EntradaViolin[]): ViolinesPreparados {
  let omitidos = 0;
  const firmas = new Set<string>();
  for (const { variable } of entradas) {
    if (!variable) continue;
    if (densidadPorTramo(variable.edges, variable.countsActual).length === 0) continue;
    if (densidadPorTramo(variable.edges, variable.countsBase).length === 0) continue;
    firmas.add(JSON.stringify([variable.edges, variable.countsBase]));
  }
  const variasLineasBase = firmas.size > 1;

  const violines: ViolinPreparado[] = [];
  const tramosMediana: TramoMediana[] = [];
  let densidadMax = 0;
  let min = Infinity;
  let max = -Infinity;
  let grupo = -1;
  let firmaActual: string | null = null;

  for (const { lote, variable } of entradas) {
    if (!variable) {
      omitidos++;
      continue;
    }
    const densActual = densidadPorTramo(variable.edges, variable.countsActual);
    const densBase = densidadPorTramo(variable.edges, variable.countsBase);
    if (densActual.length === 0 || densBase.length === 0) {
      omitidos++;
      continue;
    }
    const firma = JSON.stringify([variable.edges, variable.countsBase]);
    if (firma !== firmaActual) {
      firmaActual = firma;
      grupo++;
      const siluetaBase = siluetaMonotona(variable.edges, densBase);
      const medianaBase = medianaDeTramos(variable.edges, variable.countsBase);
      violines.push({
        clave: `base-${grupo}`,
        tipo: "base",
        etiqueta: variasLineasBase && variable.modelVersion ? `Línea base · ${variable.modelVersion}` : "Línea base",
        fase: null,
        grupo,
        silueta: siluetaBase,
        mediana: medianaBase,
        n: variable.countsBase.reduce((a, b) => a + b, 0),
        fuera: 0,
        psi: null,
        lectura: null,
        ksStat: null,
        ksP: null,
      });
      for (const p of siluetaBase) densidadMax = Math.max(densidadMax, p.densidad);
      min = Math.min(min, variable.edges[0]);
      max = Math.max(max, variable.edges[variable.edges.length - 1]);
      tramosMediana.push({
        grupo,
        desde: violines.length - 1,
        hasta: violines.length - 1,
        mediana: medianaBase ?? variable.edges[0],
        etiqueta: "mediana de la línea base",
      });
    }
    const siluetaActual = siluetaMonotona(variable.edges, densActual);
    const nActual = variable.countsActual.reduce((a, b) => a + b, 0);
    violines.push({
      clave: `lote-${lote.evaluationId}`,
      tipo: "lote",
      etiqueta: lote.numero,
      fase: lote.fase,
      grupo,
      silueta: siluetaActual,
      mediana: medianaDeTramos(variable.edges, variable.countsActual),
      n: nActual,
      fuera: Math.max(0, (variable.nVentana ?? nActual) - nActual),
      psi: variable.psi,
      lectura: lecturaPsi(variable.psi),
      ksStat: variable.ksStat,
      ksP: variable.ksP,
    });
    for (const p of siluetaActual) densidadMax = Math.max(densidadMax, p.densidad);
    min = Math.min(min, variable.edges[0]);
    max = Math.max(max, variable.edges[variable.edges.length - 1]);
    const tramo = tramosMediana[tramosMediana.length - 1];
    if (tramo && tramo.grupo === grupo) tramo.hasta = violines.length - 1;
  }

  if (violines.length === 0) return { violines: [], tramosMediana: [], densidadMax: 0, min: 0, max: 0, omitidos };
  return { violines, tramosMediana, densidadMax, min, max, omitidos };
}

/** Contorno cerrado del violín (mitad izquierda y derecha) centrado en `cx`. */
export function caminoViolin(cx: number, puntos: { x: number; y: number }[]): string {
  if (puntos.length === 0) return "";
  const izq = puntos.map((p) => `${(cx - p.x).toFixed(1)},${p.y.toFixed(1)}`);
  const der = [...puntos].reverse().map((p) => `${(cx + p.x).toFixed(1)},${p.y.toFixed(1)}`);
  return `M${izq.join(" L")} L${der.join(" L")} Z`;
}

/** Líneas del tooltip; unidas con ". " sirven también de `aria-label`. */
export function lineasTooltip(v: ViolinPreparado, medianaBase: number | null, decimales: number): string[] {
  if (v.tipo === "base") {
    return [v.etiqueta, `n ${formatoNumero(v.n, 0)}`, `Mediana ${formatoCorto(v.mediana, decimales)}`];
  }
  const titulo = `Lote ${v.etiqueta}${v.fase ? ` · ${v.fase}` : ""}`;
  const nLinea = `n ${formatoNumero(v.n, 0)}${v.fuera > 0 ? ` · ${v.fuera} fuera del rango de la línea base o sin valor` : ""}`;
  const medianaLinea = `Mediana ${formatoCorto(v.mediana, decimales)} (línea base ${formatoCorto(medianaBase, decimales)})`;
  const psiLinea = v.psi === null ? "PSI n/d" : `PSI ${formatoNumero(v.psi, 2)} · ${v.lectura}`;
  const lineas = [titulo, nLinea, medianaLinea, psiLinea];
  if (v.ksStat !== null) lineas.push(`KS ${formatoNumero(v.ksStat, 2)} (p ${formatoNumero(v.ksP)})`);
  return lineas;
}
