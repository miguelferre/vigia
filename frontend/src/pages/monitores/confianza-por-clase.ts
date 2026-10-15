/**
 * Confianza por clase predicha:
 * lectura pura de `details.confidence.by_class`
 * (`core/drift.py:_confidence_by_class`, mismos `bin_edges` que el
 * histograma global) para el selector de `histograma-confianza.tsx`.
 * Ausente en evaluaciones anteriores: el selector no aparece y la
 * tarjeta sigue en el histograma global de siempre.
 *
 * `psi`/`ksStat`/`ksP`/`jsDistance` por clase: antes `FilaEstadisticosConfianza` enseñaba siempre el
 * estadístico GLOBAL aunque la pestaña activa fuera «Derivar» o «No derivar».
 * Lectura tolerante: `null` en evaluaciones anteriores al cambio de backend,
 * `api/schema.d.ts` (generado) todavía no los tipa.
 */

import type { JsonObject } from "@/api/types";
import { claveClase } from "@/lib/tipo-tarea";
import { formatoNumero } from "@/lib/metrics";
import { sumaDesdeBorde } from "@/components/vigia/histograma-base-lote-datos";

/**
 * "todas" usa el histograma global (suma de las clases); si no, la clave de la
 * clase (`claveClase`): "1" y "0" en binario, el nombre de la clase en
 * multiclase.
 */
export type SeleccionClase = string;

/** Opción del selector: la clave de la clase y su nombre para quien lee. */
export interface OpcionClase {
  valor: string;
  etiqueta: string;
}

/** Con tantas clases o más, el selector es un `Select` y no unas pestañas. */
export const CLASES_PARA_SELECT = 5;

/**
 * Opciones del selector de confianza en multiclase: las clases del proyecto
 * en su orden que traen `by_class`, y al final las que traiga la evaluación y
 * el proyecto no declare. El conjunto favorable se marca en el nombre.
 */
export function opcionesClasesConfianza(
  porClase: Record<string, ConfianzaClase>,
  clasesProyecto: string[],
  favorables: string[],
): OpcionClase[] {
  // Ambos lados por `claveClase`; `valor` conserva la clave cruda para indexar `porClase`.
  const presentes = Object.keys(porClase).map((cruda) => ({ cruda, clave: claveClase(cruda) }));
  const claves = new Set(clasesProyecto.map(claveClase));
  const porClave = new Map(presentes.map((p) => [p.clave, p.cruda]));
  const orden = [
    ...clasesProyecto.map(claveClase).filter((c) => porClave.has(c)),
    ...presentes.map((p) => p.clave).filter((c) => !claves.has(c)),
  ];
  const fav = new Set(favorables.map(claveClase));
  return orden.map((c) => ({ valor: porClave.get(c) ?? c, etiqueta: fav.has(c) ? `${c} (favorable)` : c }));
}

export interface EstadisticosConfianza {
  psi: number | null;
  ksStat: number | null;
  ksP: number | null;
  jsDistance: number | null;
}

export interface ConfianzaClase extends EstadisticosConfianza {
  countsBase: number[];
  countsActual: number[];
}

function arrayDeNumeros(v: unknown): number[] {
  return Array.isArray(v) ? v.filter((x): x is number => typeof x === "number") : [];
}

function numeroONulo(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

/**
 * `null` si `details.confidence.by_class` no existe o no trae las dos
 * clases completas (evaluación anterior): el selector solo se
 * enseña con sus tres opciones fijas, nunca a medias.
 */
export function extraerConfianzaPorClase(
  details: JsonObject | null,
  /** Claves que tienen que estar todas (binario: "1" y "0"); `null` toma las que traiga (multiclase). */
  esperadas: readonly string[] | null = ["1", "0"],
): Record<string, ConfianzaClase> | null {
  if (!details) return null;
  const confidence = details.confidence;
  if (!confidence || typeof confidence !== "object" || Array.isArray(confidence)) return null;
  const byClass = (confidence as JsonObject).by_class;
  if (!byClass || typeof byClass !== "object" || Array.isArray(byClass)) return null;
  const obj = byClass as JsonObject;
  const resultado: Record<string, ConfianzaClase> = {};
  const claves = esperadas ?? Object.keys(obj);
  for (const clave of claves) {
    const entrada = obj[clave];
    if (!entrada || typeof entrada !== "object" || Array.isArray(entrada)) continue;
    const e = entrada as JsonObject;
    resultado[clave] = {
      countsBase: arrayDeNumeros(e.bin_counts_base),
      countsActual: arrayDeNumeros(e.bin_counts_actual),
      psi: numeroONulo(e.psi),
      ksStat: numeroONulo(e.ks_stat),
      ksP: numeroONulo(e.ks_p),
      jsDistance: numeroONulo(e.jensen_shannon_distance),
    };
  }
  return claves.length > 0 && claves.every((c) => resultado[c]) ? resultado : null;
}

/** Serie de tramos de la selección: la de la clase elegida, o la global con «Todas». */
export function seriePorSeleccion(
  seleccion: SeleccionClase,
  global: { countsBase: number[]; countsActual: number[] } | null,
  porClase: Record<string, ConfianzaClase> | null,
): { base: number[]; actual: number[] } {
  const clase = seleccion !== "todas" && porClase ? porClase[seleccion] : undefined;
  if (clase) return { base: clase.countsBase, actual: clase.countsActual };
  return { base: global?.countsBase ?? [], actual: global?.countsActual ?? [] };
}

/**
 * Estadísticos (psi/ks/js) de la selección: los de la clase
 * elegida si `porClase` los trae, o los globales con «Todas» o sin
 * `by_class` en esta evaluación.
 */
export function estadisticosPorSeleccion(
  seleccion: SeleccionClase,
  global: EstadisticosConfianza | null,
  porClase: Record<string, ConfianzaClase> | null,
): EstadisticosConfianza {
  const c = seleccion !== "todas" && porClase ? porClase[seleccion] : undefined;
  if (c) return { psi: c.psi, ksStat: c.ksStat, ksP: c.ksP, jsDistance: c.jsDistance };
  return global ?? { psi: null, ksStat: null, ksP: null, jsDistance: null };
}

/** Dominios donde el modelo decide derivar o no. */
function esDominioDerivacion(dominio: string | null | undefined): boolean {
  return dominio === "digestivo" || dominio === "reuma";
}

/**
 * Nombre de una clase predicha para quien lee la tarjeta: en un dominio de
 * derivación, la clase favorable es «Derivar» y la otra «No derivar»; en
 * cualquier otro dominio, o sin `favorableLabel` conocido, «Clase 1
 * (favorable)» / «Clase 0», como en `TarjetaClasesPredichas`.
 */
/**
 * `ProjectOut.favorable_label` es la unión de la plantilla (número,
 * texto o lista). Las pantallas binarias de deriva leen solo una favorable
 * numérica; cualquier otra forma da `null` y el nombre genérico de la clase.
 */
export function favorableNumerico(valor: unknown): number | null {
  const v = Array.isArray(valor) && valor.length === 1 ? valor[0] : valor;
  return typeof v === "number" ? v : null;
}

export function nombreClasePredicha(
  dominio: string | null | undefined,
  clase: 0 | 1,
  favorableLabel: number | null | undefined,
): string {
  if (favorableLabel !== 0 && favorableLabel !== 1) return `Clase ${clase}`;
  const favorable = favorableLabel === clase;
  if (esDominioDerivacion(dominio)) return favorable ? "Derivar" : "No derivar";
  return `Clase ${clase}${favorable ? " (favorable)" : ""}`;
}

/** Lectura fija de contenido (no configurable): umbral de "confianza alta" de la frase calculada. */
export const UMBRAL_LECTURA_CONFIANZA = 0.8;

/**
 * «Por encima de 0,80: 0,4 % en la línea base, 40,5 % en el lote»:
 * porcentaje de decisiones con confianza >= `UMBRAL_LECTURA_CONFIANZA` sobre
 * el n de cada ventana de la selección; `null` si alguna ventana está vacía.
 */
export function fraseUmbralConfianza(binEdges: number[], countsBase: number[], countsActual: number[]): string | null {
  const totalBase = countsBase.reduce((a, b) => a + b, 0);
  const totalActual = countsActual.reduce((a, b) => a + b, 0);
  if (totalBase === 0 || totalActual === 0) return null;
  const pctBase = (sumaDesdeBorde(countsBase, binEdges, UMBRAL_LECTURA_CONFIANZA) / totalBase) * 100;
  const pctActual = (sumaDesdeBorde(countsActual, binEdges, UMBRAL_LECTURA_CONFIANZA) / totalActual) * 100;
  return `Por encima de ${formatoNumero(UMBRAL_LECTURA_CONFIANZA, 2)}: ${formatoNumero(pctBase, 1)} % en la línea base, ${formatoNumero(pctActual, 1)} % en el lote.`;
}
