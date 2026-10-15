/**
 * Valores distintos de cada columna leyendo el fichero de ejemplo hasta 5 MB
 * para proponer las clases de un modelo multiclase. `alta-sniff.ts`
 * solo lee 64 KB para la vista previa y las variables, y una clase rara que
 * aparece al final del fichero no salía. Aquí se recorre más fichero, sin
 * guardar filas: solo los valores distintos (topados) de cada columna.
 * Si el fichero es mayor, `parcial` lo dice y la interfaz pide añadir a mano
 * las clases que falten. Funciones puras, sin estado.
 */

import { partirLinea, type Separador } from "./alta-sniff";

/** Tope de lectura para proponer las clases. */
export const LIMITE_LECTURA_CLASES = 5 * 1024 * 1024;
/** Por columna se guardan como mucho tantos valores distintos: las clases son 20 como mucho. */
const TOPE_DISTINTOS = 200;

export interface ValoresClases {
  /** Valores distintos no vacíos de cada columna, en orden de aparición. */
  valores: Record<string, string[]>;
  /** El fichero es mayor que el tope: solo se ha leído el principio. */
  parcial: boolean;
}

/** Valores distintos por columna de un texto ya leído; `parcial` descarta la última línea, que puede venir cortada. */
export function valoresPorColumna(
  texto: string,
  columnas: string[],
  separador: Separador,
  parcial: boolean,
): Record<string, string[]> {
  const sinBom = texto.charCodeAt(0) === 0xfeff ? texto.slice(1) : texto;
  let lineas = sinBom.split(/\r\n|\r|\n/).filter((l) => l.length > 0);
  if (parcial && lineas.length > 1) lineas = lineas.slice(0, -1);
  const conjuntos: Set<string>[] = columnas.map(() => new Set<string>());
  for (let i = 1; i < lineas.length; i++) {
    const valores = partirLinea(lineas[i], separador);
    for (let c = 0; c < columnas.length; c++) {
      const v = valores[c];
      if (v !== undefined && v !== "" && conjuntos[c].size < TOPE_DISTINTOS) conjuntos[c].add(v);
    }
  }
  return Object.fromEntries(columnas.map((col, c) => [col, Array.from(conjuntos[c])]));
}

/** Lee `file` hasta 5 MB y devuelve los valores distintos de cada columna. */
export async function leerValoresClases(
  file: File,
  columnas: string[],
  separador: Separador,
): Promise<ValoresClases> {
  const parcial = file.size > LIMITE_LECTURA_CLASES;
  const texto = await file.slice(0, LIMITE_LECTURA_CLASES).text();
  return { valores: valoresPorColumna(texto, columnas, separador, parcial), parcial };
}
