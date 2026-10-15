/**
 * Clases de un modelo multiclase en el alta y en el mapeo.
 * Funciones puras. Espejo en el navegador de lo que `services/ingest.py`
 * propone al leer el fichero completo (`_columnas_prob_por_clase`,
 * `_sugerir_clases`, `_clase_como_valor`): aquí solo se lee una muestra, así
 * que son propuestas que la persona corrige.
 */

import { claveClase } from "@/lib/tipo-tarea";

/** Número de clases admitido en multiclase. */
export const MIN_CLASES = 3;
export const MAX_CLASES = 20;

const PREFIJOS_PROBABILIDAD = ["probability_", "proba_", "prob_"] as const;

export interface ColumnaProbabilidad {
  columna: string;
  /** Lo que sigue al prefijo: el nombre de la clase según el fichero. */
  sufijo: string;
}

/** Columnas `prob_<clase>` (o `probability_<clase>`, `proba_<clase>`) en el orden del fichero. */
export function columnasProbabilidadPorClase(columnas: string[]): ColumnaProbabilidad[] {
  const halladas: ColumnaProbabilidad[] = [];
  for (const columna of columnas) {
    const nombre = columna.trim();
    const bajo = nombre.toLowerCase();
    for (const prefijo of PREFIJOS_PROBABILIDAD) {
      if (bajo.startsWith(prefijo) && nombre.length > prefijo.length) {
        const sufijo = nombre.slice(prefijo.length).replace(/^[_ ]+|[_ ]+$/g, "");
        if (sufijo) halladas.push({ columna, sufijo });
        break;
      }
    }
  }
  return halladas;
}

/**
 * Un valor leído de un fichero como clase. El navegador lee todo como texto y el backend (pandas)
 * lee `1.0` como el número 1: aquí se hace la misma lectura (entero con ceros decimales a número) y
 * la clave la da `claveClase`, el único normalizador (`clave_clase` del backend).
 */
export function normalizarClase(texto: string): string {
  const limpio = texto.trim();
  return claveClase(/^-?\d+(\.0+)?$/.test(limpio) ? Number(limpio) : limpio);
}

/** Clase para el cuerpo de la API: entero limpio como número, el resto como texto. */
export function valorDeClase(clave: string): number | string {
  return /^-?\d+$/.test(clave) ? Number(clave) : clave;
}

function valoresDeColumna(
  filas: Record<string, string>[],
  col: string,
  completos?: Record<string, string[]>,
): string[] {
  if (!col) return [];
  const vistos: string[] = [];
  // Con la lectura larga (`alta-sniff-clases.ts`) se usan sus valores distintos; sin ella, la muestra.
  const crudos = completos?.[col] ?? filas.map((fila) => fila[col] ?? "");
  for (const crudo of crudos) {
    const v = normalizarClase(crudo);
    if (v !== "" && !vistos.includes(v)) vistos.push(v);
  }
  return vistos;
}

/**
 * Clases propuestas desde el fichero de ejemplo. Con columnas `prob_<clase>`
 * manda su orden (el de las probabilidades) y cada sufijo toma el valor
 * de la predicción que coincide sin distinguir mayúsculas. Sin ellas, los
 * valores distintos de la columna de predicción y la de etiqueta: números en
 * orden y después textos en orden alfabético, como `_sugerir_clases`.
 * `completos` son los valores distintos por columna de una lectura de
 * hasta 5 MB y sustituyen a `filas`.
 */
export function sugerirClases(
  columnas: string[],
  filas: Record<string, string>[],
  prediccionCol: string,
  etiquetaCol: string,
  completos?: Record<string, string[]>,
): string[] {
  const vistos = [...valoresDeColumna(filas, prediccionCol, completos)];
  for (const v of valoresDeColumna(filas, etiquetaCol, completos)) if (!vistos.includes(v)) vistos.push(v);
  const sufijos = columnasProbabilidadPorClase(columnas).map((c) => c.sufijo);
  if (sufijos.length >= 2) {
    const porMinuscula = new Map(vistos.map((v) => [v.toLowerCase(), v] as const));
    return sufijos.map((s) => porMinuscula.get(s.toLowerCase()) ?? normalizarClase(s));
  }
  const esNumero = (v: string) => /^-?\d+$/.test(v);
  const numeros = vistos.filter(esNumero).sort((a, b) => Number(a) - Number(b));
  const textos = vistos.filter((v) => !esNumero(v)).sort();
  return [...numeros, ...textos];
}

/** La columna de probabilidad de cada clase, por coincidencia del sufijo; vacío si no hay. */
export function probabilidadPorClase(columnas: string[], clases: string[]): Record<string, string> {
  const prob = columnasProbabilidadPorClase(columnas);
  const resultado: Record<string, string> = {};
  for (const clase of clases) {
    resultado[clase] = prob.find((p) => normalizarClase(p.sufijo).toLowerCase() === clase.toLowerCase())?.columna ?? "";
  }
  return resultado;
}

/** `null` si el conjunto favorable vale; si no, el motivo en una frase (de 1 a `k - 1`). */
export function motivoFavorablesNoValidos(clases: string[], favorables: string[]): string | null {
  const k = clases.length;
  const marcadas = favorables.filter((f) => clases.includes(f)).length;
  if (marcadas === 0) return "Marca al menos una clase como favorable.";
  if (k > 1 && marcadas >= k) {
    return "Has marcado todas las clases como favorables: entonces nadie recibiría un resultado malo y la equidad no mediría nada. Deja al menos una sin marcar.";
  }
  return null;
}

/**
 * `null` si el número de clases vale; si no, el motivo. La primera frase es la del backend
 * (`schema.py`); el cierre dice qué hacer según el caso.
 */
export function motivoClasesNoValidas(clases: string[]): string | null {
  const n = clases.length;
  if (n >= MIN_CLASES && n <= MAX_CLASES) return null;
  const base = `Un proyecto multiclase declara de ${MIN_CLASES} a ${MAX_CLASES} clases y hay ${n}.`;
  if (n > MAX_CLASES) return base;
  if (n === 2) return `${base} Con dos clases, crea un proyecto binario.`;
  return `${base} Revisa las columnas de predicción y de etiqueta, o añade las clases que falten con «Añadir clase».`;
}

/** Lista de claves (`claveClase`) sin repetidos, para comparar con lo que devuelve la API. */
export function clavesUnicas(valores: (string | number)[]): string[] {
  const claves: string[] = [];
  for (const v of valores) {
    const c = claveClase(v);
    if (!claves.includes(c)) claves.push(c);
  }
  return claves;
}
