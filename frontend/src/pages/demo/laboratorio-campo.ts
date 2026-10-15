/**
 * Interpretación de los campos numéricos del laboratorio: coma o punto como
 * decimal, tipo y rango del parámetro (definición del contenido) y
 * la semilla opcional. Separado de `laboratorio-campo-numero.tsx` para que
 * ese fichero exporte solo el componente.
 */

import type { DefinicionParametro } from "./laboratorio-parametros";

export interface Evaluacion {
  valor: number | null;
  error: string | null;
}

/** "," o "." como separador decimal; null si el texto no es un número. */
export function parseDecimal(texto: string): number | null {
  const t = texto.trim();
  if (!/^-?\d+([.,]\d+)?$/.test(t)) return null;
  return Number(t.replace(",", "."));
}

/** Valor y error de un parámetro del generador, contra su tipo y su rango. */
export function evaluarCampo(p: DefinicionParametro, texto: string): Evaluacion {
  const bruto = parseDecimal(texto);
  if (bruto === null) {
    return { valor: null, error: "Escribe un número: la coma y el punto valen como decimal." };
  }
  if (p.tipo === "int" && !Number.isInteger(bruto)) {
    return { valor: null, error: "Este campo es un número entero, sin decimales." };
  }
  if (bruto < p.min || bruto > p.max) {
    return { valor: null, error: `Debe estar entre ${p.min} y ${p.max}.` };
  }
  return { valor: bruto, error: null };
}

/** Semilla: entero opcional. Vacío es válido (semilla aleatoria). */
export function parseEnteroOpcional(texto: string): Evaluacion {
  const t = texto.trim();
  if (t === "") return { valor: null, error: null };
  if (!/^-?\d+$/.test(t)) {
    return { valor: null, error: "La semilla es un número entero, sin decimales." };
  }
  return { valor: Number(t), error: null };
}
