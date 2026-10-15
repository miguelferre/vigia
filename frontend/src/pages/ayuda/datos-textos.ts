/**
 * Rótulos fijos de la sección «Datos» de `/ayuda`. El
 * contenido de la guía (ficheros, columnas, formatos) llega de
 * `GET /content/guia-datos`; aquí solo lo que rodea a ese contenido.
 */

export const TITULO_DATOS = "Datos";

export const INTRO_DATOS =
  "Qué ficheros pide Vigía, con qué columnas y en qué formato. Cada fichero tiene una plantilla para descargar: cambia las filas por las tuyas ya desidentificadas y súbela.";

/** Ids del DOM a los que enlaza el resto de la aplicación con `/ayuda#<id>`. */
export const ID_DATOS = "datos";
export const ID_CLASE_FAVORABLE = "clase-favorable";
export const ID_CODIFICACION = "codificacion-inconclusa";
export const IDS_ANCLA_DATOS: readonly string[] = [ID_DATOS, ID_CLASE_FAVORABLE, ID_CODIFICACION];

export const RESPALDO_DATOS = "La guía de datos no está disponible en este momento. Recarga la página.";

export const DESCARGAR = "Descargar la plantilla";
export const COLUMNAS_OBLIGATORIAS = "Columnas obligatorias";
export const COLUMNAS_OPCIONALES = "Columnas opcionales";
export const SIN_PLANTILLA = "Este fichero no es un CSV: no tiene plantilla.";
