/**
 * Unidad y rango favorable del alta de una regresión: lógica
 * pura, sin React. Copia las reglas de `validar_rangos`, `validar_unidad` y
 * `en_rango` de `core/schema.py` para avisar en el formulario antes de crear;
 * el servidor sigue validando y sus mensajes mandan.
 */

import type { RangoFavorable } from "@/lib/metrics";

/** Un intervalo tal como se escribe: texto, con el extremo vacío como abierto. */
export interface FilaRango {
  min: string;
  max: string;
}

export const MAX_RANGOS = 3;
export const MAX_UNIDAD = 30;
export const FILA_VACIA: FilaRango = { min: "", max: "" };
export const EJEMPLOS_UNIDAD = ["días", "horas por semana", "€"] as const;

/** Número con coma o punto decimal; `null` si el texto no lo es. Con coma y punto a la vez («1.000,5») no se adivina cuál separa miles: no es un número. */
export function leerNumero(texto: string): number | null {
  const crudo = texto.trim();
  if (crudo.includes(",") && crudo.includes(".")) return null;
  const limpio = crudo.replace(",", ".");
  if (limpio === "" || !/^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i.test(limpio)) return null;
  const n = Number(limpio);
  return Number.isFinite(n) ? n : null;
}

export interface RangosLeidos {
  rangos: [number | null, number | null][];
  /** Mensaje en español con qué hacer; `null` si el rango es válido o está vacío. */
  error: string | null;
}

const gramo = (n: number) => n.toLocaleString("es-ES", { maximumFractionDigits: 3 });

/** `validar_rangos`: de 1 a 3 intervalos, mín ≤ máx, sin solaparse ni tocarse. Las filas vacías se ignoran. */
export function leerRangos(filas: readonly FilaRango[]): RangosLeidos {
  const usadas = filas.map((f, i) => ({ ...f, i: i + 1 })).filter((f) => f.min.trim() !== "" || f.max.trim() !== "");
  const rangos: [number | null, number | null][] = [];
  for (const f of usadas) {
    const extremos: (number | null)[] = [];
    for (const texto of [f.min, f.max]) {
      if (texto.trim() === "") {
        extremos.push(null);
        continue;
      }
      const n = leerNumero(texto);
      if (n === null) {
        return {
          rangos: [],
          error: `El extremo «${texto.trim()}» del intervalo ${f.i} no es un número: escribe el valor sin unidad (40, no «40 h») o déjalo vacío.`,
        };
      }
      extremos.push(n);
    }
    const [bajo, alto] = extremos;
    if (bajo !== null && alto !== null && bajo > alto) {
      return {
        rangos: [],
        error: `En el intervalo ${f.i} el mínimo (${gramo(bajo)}) es mayor que el máximo (${gramo(alto)}): cámbialos.`,
      };
    }
    rangos.push([bajo, alto]);
  }
  rangos.sort((a, b) => (a[0] ?? -Infinity) - (b[0] ?? -Infinity));
  for (let i = 1; i < rangos.length; i += 1) {
    const alto = rangos[i - 1][1];
    const bajo = rangos[i][0];
    if (alto === null || bajo === null || bajo <= alto) {
      return { rangos: [], error: "Los intervalos no pueden solaparse ni tocarse: únelos en uno o sepáralos." };
    }
  }
  return { rangos, error: null };
}

/** `validar_unidad`: texto de 1 a 30 caracteres; vacío es «sin unidad». */
export function leerUnidad(texto: string): { unidad: string | null; error: string | null } {
  const limpia = texto.trim();
  if (limpia === "") return { unidad: null, error: null };
  if (limpia.length > MAX_UNIDAD) {
    return {
      unidad: null,
      error: `La unidad tiene de 1 a ${MAX_UNIDAD} caracteres (por ejemplo «días», «horas por semana» o «€»).`,
    };
  }
  return { unidad: limpia, error: null };
}

/** `en_rango` de `core/schema.py`: extremos incluidos, extremo nulo abierto. */
export function enRango(valor: number, rangos: readonly RangoFavorable[]): boolean {
  return rangos.some(([bajo, alto]) => (bajo === null || valor >= bajo) && (alto === null || valor <= alto));
}

export interface ParteEnRango {
  /** Valores numéricos leídos. */
  n: number;
  dentro: number;
  /** `dentro / n`, o `null` sin valores. */
  fraccion: number | null;
}

/** Qué parte de los valores de una columna cae en el rango (vista previa del alta). */
export function parteEnRango(valores: readonly string[], rangos: readonly RangoFavorable[]): ParteEnRango {
  let n = 0;
  let dentro = 0;
  for (const v of valores) {
    const x = leerNumero(v);
    if (x === null) continue;
    n += 1;
    if (enRango(x, rangos)) dentro += 1;
  }
  return { n, dentro, fraccion: n === 0 ? null : dentro / n };
}
