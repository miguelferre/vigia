/**
 * Textos del estado vacío común de las pantallas que exigen un modelo y del bloque «Empezar» de la portada. Aquí, y no sueltos
 * en el JSX, para que el test de textos y la ayuda los lean de un sitio.
 */

/** Ruta que abre el alta de un modelo al montar `/modelos` (no la precarga de la demo). */
export const RUTA_ALTA_MODELO = "/modelos?alta=1";

export const TEXTO_ALTA = "Dar de alta tu modelo";
export const TEXTO_IR_A_MODELOS = "Ir a Modelos";

export const TITULO_SIN_MODELOS = "Todavía no hay modelos";
export const TITULO_ELIGE_MODELO = "Elige un modelo";

/** `que` es lo que la pantalla enseña de un modelo: «sus alertas», «su diario»... */
export function descripcionSinModelos(que: string): string {
  return `Vigía vigila modelos: da de alta el tuyo para ver ${que}. Antes de empezar, la Ayuda explica qué ficheros hacen falta.`;
}

export function descripcionEligeModelo(que: string): string {
  return `Elige un modelo con el selector de la cabecera para ver ${que}, o ve a Modelos para elegirlo allí.`;
}
