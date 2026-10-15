/**
 * Datos puros del histograma «línea base frente a lote» (forma B): a partir de dos vectores de pesos por tramo (línea
 * base y lote), calcula porcentajes de cada ventana, la diferencia en puntos
 * porcentuales y los tramos que más cambian. Sin dependencia de React ni de
 * recharts para poder testear y reutilizar desde `HistogramaBaseLote.tsx`,
 * `histograma-variable.tsx` y `histograma-confianza.tsx`.
 *
 * `sumaDesdeBorde`: suma genérica por umbral de borde,
 * usada por `confianza-por-clase.ts` para la frase calculada del selector
 * de confianza por clase predicha.
 */

import { formatoCorto, formatoNumero } from "@/lib/metrics";

export interface FilaHistograma {
  tramo: string;
  /** % de la línea base en este tramo. */
  base: number;
  /** % del lote en este tramo. */
  actual: number;
  /** actual - base, en puntos porcentuales. */
  diff: number;
  /** Peso bruto de la línea base (recuento o tasa, según venga). */
  nBase: number;
  /** Peso bruto del lote. */
  nActual: number;
}

/** `[]` si las longitudes no casan o alguna ventana suma 0 (nada que repartir). */
export function construirFilasHistograma(tramos: string[], base: number[], actual: number[]): FilaHistograma[] {
  const n = tramos.length;
  if (n === 0 || base.length !== n || actual.length !== n) return [];
  const sumaBase = base.reduce((a, b) => a + b, 0);
  const sumaActual = actual.reduce((a, b) => a + b, 0);
  if (sumaBase === 0 || sumaActual === 0) return [];
  return tramos.map((tramo, i) => {
    const pctBase = (base[i]! / sumaBase) * 100;
    const pctActual = (actual[i]! / sumaActual) * 100;
    return {
      tramo,
      base: pctBase,
      actual: pctActual,
      diff: pctActual - pctBase,
      nBase: base[i]!,
      nActual: actual[i]!,
    };
  });
}

/** Índices de mayor |diff| primero, solo diferencia distinta de 0; `k` por defecto 3. */
export function indicesQueMasCambian(filas: FilaHistograma[], k = 3): number[] {
  return filas
    .map((f, i) => ({ i, delta: Math.abs(f.diff) }))
    .filter((f) => f.delta > 0)
    .sort((a, b) => b.delta - a.delta)
    .slice(0, k)
    .map((f) => f.i);
}

/**
 * Etiqueta de cada tramo a partir de los bordes: «20–42» (enteros) o
 * «0,500–0,525» (confianza). Decimales = el mínimo entre 0 y 3 con el que
 * todos los bordes se representan exactos (los `bin_edges` de la API llegan
 * con restos flotantes como `0.8500000000000001`).
 */
export function etiquetasDeBordes(binEdges: number[]): string[] {
  let decimales = 3;
  for (let d = 0; d <= 3; d++) {
    const factor = 10 ** d;
    const exacto = binEdges.every((b) => Math.abs(Math.round(b * factor) / factor - b) < 1e-6);
    if (exacto) {
      decimales = d;
      break;
    }
  }
  const etiquetas: string[] = [];
  for (let i = 0; i < binEdges.length - 1; i++) {
    etiquetas.push(`${formatoNumero(binEdges[i]!, decimales)}–${formatoNumero(binEdges[i + 1]!, decimales)}`);
  }
  return etiquetas;
}

/**
 * Etiqueta corta del eje X: solo el borde
 * izquierdo del tramo, con sus decimales mínimos («0,500–0,525» → «0,5»).
 * El tramo completo se queda en el tooltip (`TooltipHistograma`); las
 * etiquetas categóricas (sin guion en medio, p. ej. una clase o «otros») se
 * devuelven tal cual.
 */
export function etiquetaEjeDeTramo(tramo: string): string {
  const separador = tramo.indexOf("–");
  if (separador === -1) return tramo;
  const izquierda = tramo.slice(0, separador);
  const valor = Number.parseFloat(izquierda.replace(",", "."));
  if (Number.isNaN(valor)) return izquierda;
  return formatoCorto(valor, 3);
}

/** Signo siempre, con el menos tipográfico (U+2212) para el negativo. */
function formatoConSigno(valor: number, decimales = 1): string {
  if (valor > 0) return `+${formatoCorto(valor, decimales)}`;
  if (valor < 0) return `−${formatoCorto(Math.abs(valor), decimales)}`;
  return formatoCorto(0, decimales);
}

/** «Los tramos que más cambian: 66–70 (+4 pp), …»; `null` si ninguno cambia. */
export function fraseTramosQueMasCambian(filas: FilaHistograma[], k = 3): string | null {
  const indices = indicesQueMasCambian(filas, k);
  if (indices.length === 0) return null;
  const partes = indices.map((i) => `${filas[i]!.tramo} (${formatoConSigno(filas[i]!.diff, 1)} pp)`);
  return `Los tramos que más cambian: ${partes.join(", ")}.`;
}

/** Mismo reparto en las dos ventanas, tramo a tramo: no hay nada que enseñar. */
export function distribucionesIdenticas(filas: FilaHistograma[]): boolean {
  return filas.length > 0 && filas.every((f) => Math.abs(f.diff) < 1e-9);
}

/**
 * Suma de los recuentos en los tramos cuyo borde izquierdo es mayor o igual
 * que `desde` (frase calculada de un umbral fijo de
 * lectura en `confianza-por-clase.ts`). `binEdges` trae un elemento más que
 * `counts`, alineados por índice.
 */
export function sumaDesdeBorde(counts: number[], binEdges: number[], desde: number): number {
  let suma = 0;
  for (let i = 0; i < counts.length; i++) {
    if ((binEdges[i] ?? Number.NEGATIVE_INFINITY) >= desde - 1e-9) suma += counts[i]!;
  }
  return suma;
}
