/**
 * Sniff de columnas en el navegador para el paso «Datos» del alta:
 * lee los primeros 64 KB del fichero de ejemplo sin subirlo, detecta el
 * separador entre coma, punto y coma o tabulador y quita el BOM si lo trae.
 * Heurística ligera a propósito (sin comillas ni escapes de CSV completo):
 * solo sirve para ofrecer columnas y valores vistos en el formulario, nunca
 * para ingerir de verdad, que sigue siendo cosa del servidor.
 */

const BLOQUE = 64 * 1024;
const SEPARADORES = [",", ";", "\t"] as const;
export type Separador = (typeof SEPARADORES)[number];

export interface ColumnasEjemplo {
  columnas: string[];
  filas: Record<string, string>[];
  separador: Separador;
}

/** Cuenta ocurrencias de cada separador candidato en la cabecera y elige el máximo (coma por defecto). */
function detectarSeparador(cabecera: string): Separador {
  let mejor: Separador = ",";
  let mejorCuenta = -1;
  for (const s of SEPARADORES) {
    const cuenta = cabecera.split(s).length - 1;
    if (cuenta > mejorCuenta) {
      mejorCuenta = cuenta;
      mejor = s;
    }
  }
  return mejor;
}

/** Una línea partida por el separador, con espacios sueltos y comillas simples de borde quitados. */
export function partirLinea(linea: string, separador: Separador): string[] {
  return linea.split(separador).map((v) => v.trim().replace(/^"(.*)"$/, "$1"));
}

/**
 * Lee las columnas y una muestra de filas de `file` (primeros 64 KB).
 * Descarta la última línea del trozo leído si está cortada a medias (no hay
 * salto de línea después).
 */
export async function leerColumnasEjemplo(file: File): Promise<ColumnasEjemplo> {
  const trozo = file.slice(0, BLOQUE);
  const texto = await trozo.text();
  const sinBom = texto.charCodeAt(0) === 0xfeff ? texto.slice(1) : texto;
  const completo = trozo.size < file.size;
  let lineas = sinBom.split(/\r\n|\r|\n/).filter((l) => l.length > 0);
  if (completo && lineas.length > 1) lineas = lineas.slice(0, -1);
  if (lineas.length === 0) return { columnas: [], filas: [], separador: "," };

  const separador = detectarSeparador(lineas[0]);
  const columnas = partirLinea(lineas[0], separador);
  const filas = lineas.slice(1).map((linea) => {
    const valores = partirLinea(linea, separador);
    const fila: Record<string, string> = {};
    columnas.forEach((col, i) => {
      fila[col] = valores[i] ?? "";
    });
    return fila;
  });
  return { columnas, filas, separador };
}

/** Espejo de `privacy.normalize_name`: minúsculas, sin acentos, separadores a `_`. */
function normalizarNombre(nombre: string): string {
  return nombre
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/**
 * Espejo de la detección de `_suggest_mapping` (`services/ingest.py`):
 * nombre normalizado igual a `timestamp`, `date` o `fecha`, por ese orden
 * (coincidencia exacta: `fecha_alta` no cuenta). Si dos columnas normalizan
 * igual, gana la última, como el diccionario del backend.
 */
export function sugerirColumnaFecha(columnas: string[]): string | null {
  const porNormalizado = new Map<string, string>();
  for (const c of columnas) porNormalizado.set(normalizarNombre(c), c);
  for (const candidato of ["timestamp", "date", "fecha"]) {
    const hallada = porNormalizado.get(candidato);
    if (hallada !== undefined) return hallada;
  }
  return null;
}

/** Valores distintos no vacíos de `col` en `filas`, en orden de aparición, topados a 50. */
export function valoresDistintos(filas: Record<string, string>[], col: string, tope = 50): string[] {
  const vistos = new Set<string>();
  for (const fila of filas) {
    const v = fila[col];
    if (v !== undefined && v !== "" && !vistos.has(v)) {
      vistos.add(v);
      if (vistos.size >= tope) break;
    }
  }
  return Array.from(vistos);
}

const PATRON_FECHA = /^\d{4}-\d{1,2}-\d{1,2}([ T]|$)|^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}([ T]|$)/;

function valoresDe(filas: Record<string, string>[], col: string): string[] {
  return filas.map((f) => (f[col] ?? "").trim()).filter((v) => v !== "");
}

/** El nombre suena a fecha o todos los valores vistos tienen forma de fecha (aaaa-mm-dd, dd/mm/aaaa). */
export function pareceFecha(col: string, filas: Record<string, string>[]): boolean {
  if (/(^|_)(fecha|date|timestamp|datetime)(_|$)/.test(normalizarNombre(col))) return true;
  const valores = valoresDe(filas, col);
  return valores.length >= 2 && valores.every((v) => PATRON_FECHA.test(v));
}

/** Un nombre de identificador solo cuenta si más de esta fracción de los valores vistos son distintos. */
export const CORTE_IDENTIFICADOR = 0.9;
/** Con menos valores vistos que estos, la fracción no dice nada y manda el nombre. */
const MUESTRA_MINIMA_IDENTIFICADOR = 5;

/**
 * El nombre suena a identificador (`id`, `*_id`, `nhc`, `uuid`...) o son textos todos distintos.
 * Un nombre como `admission_type_id` con pocos valores distintos es un código (variable
 * legítima), no un identificador: el nombre solo basta si más del 90 % de los valores son distintos.
 */
export function pareceIdentificador(col: string, filas: Record<string, string>[]): boolean {
  const valores = valoresDe(filas, col);
  if (/(^|_)(id|uuid|guid|nhc|mrn|identificador)(_|$)/.test(normalizarNombre(col))) {
    if (valores.length < MUESTRA_MINIMA_IDENTIFICADOR) return true;
    return new Set(valores).size / valores.length > CORTE_IDENTIFICADOR;
  }
  const textos = valores.length >= 5 && valores.some((v) => Number.isNaN(Number(v.replace(",", "."))));
  return textos && new Set(valores).size === valores.length && !valores.every((v) => PATRON_FECHA.test(v));
}

/** Todos los valores vistos son números y hay más de dos distintos: candidata a rangos numéricos. */
export function pareceNumerica(col: string, filas: Record<string, string>[]): boolean {
  const valores = valoresDe(filas, col);
  const numeros = valores.every((v) => v !== "" && !Number.isNaN(Number(v.replace(",", "."))));
  return valores.length > 0 && numeros && new Set(valores).size > 2;
}

/** Espejo de `_suggest_mapping` (`services/ingest.py`): el primer candidato que el fichero trae, por nombre normalizado. */
export function sugerirColumna(columnas: string[], ...candidatos: string[]): string {
  const porNormalizado = new Map(columnas.map((c) => [normalizarNombre(c), c] as const));
  for (const candidato of candidatos) {
    const hallada = porNormalizado.get(candidato);
    if (hallada !== undefined) return hallada;
  }
  return "";
}
