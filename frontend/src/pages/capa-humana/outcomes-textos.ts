/**
 * Textos del bloque «Outcomes»: el formato del CSV se
 * dice una sola vez y lo usan el estado vacío y el diálogo de subida.
 */

export const COLUMNAS_OUTCOMES = "period, metric_key, value, source";

export const TEXTO_OUTCOMES = {
  vacio: `Sube un CSV con las columnas ${COLUMNAS_OUTCOMES}. Un periodo y una métrica repetidos actualizan el valor.`,
  subida: (fichero: string) => `Sube ${fichero} con las columnas ${COLUMNAS_OUTCOMES}.`,
} as const;
