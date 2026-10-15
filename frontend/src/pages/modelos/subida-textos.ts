/**
 * Textos de ayuda de la subida y la ingesta de un dataset, fuera del JSX. El contenido largo por pantalla sale de
 * `GET /content/textos-pantalla`; esto es lo que se enseña si no ha llegado
 * y la ayuda de los campos del paso «Ingerir».
 */

export const TEXTO_SUBIDA_POR_DEFECTO: Record<"que_subir" | "formatos" | "que_pasa_despues", string> = {
  que_subir:
    "Sube un fichero con las predicciones de tu modelo, o con las etiquetas reales cuando ya las tengas, para el proyecto y la versión que quieres vigilar.",
  formatos:
    "Admite CSV, TSV y JSON (si tus datos están en Excel, guárdalos como CSV). Mapea las columnas de tu fichero a lo que Vigía necesita en el propio formulario.",
  que_pasa_despues:
    "Vigía valida las columnas y guarda el lote tal como llega. Los datos deben venir ya desidentificados: Vigía no sustituye ni oculta identificadores.",
};

/** Ficheros que acepta el selector de la subida: texto delimitado y JSON. */
export const ACEPTA_SUBIDA = ".csv,.tsv,.txt,.json";

export const AYUDA_INGESTA = {
  version: "Sin elegir, el lote entra en la versión activa del modelo.",
  etiquetaLote:
    "Una nota libre para reconocer el lote en pantalla, por ejemplo «semana 12». No cambia ningún cálculo.",
  ordenManipulado:
    "Márcalo solo si las filas se ordenaron a propósito para provocar una ventana de equidad concreta, " +
    "como en los datos sintéticos de la demo. Un despliegue real no lo necesita. Pide un motivo y queda en el diario.",
  evaluarAlIngerir:
    "Los monitores miden el lote en cuanto termina la ingesta y pueden abrir alertas. " +
    "Sin marcar, el lote se guarda y lo evalúas después.",
} as const;

/** Rótulo de la vista previa del paso «Ingerir»; `total` son las filas que trae la respuesta de la subida. */
export const TITULO_VISTA_PREVIA_INGESTA = (visibles: number, total: number) =>
  total > visibles
    ? `Vista previa: las ${visibles} primeras filas de ${total}`
    : `Vista previa: ${total === 1 ? "la fila" : `las ${total} filas`} del fichero`;
