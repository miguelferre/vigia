/**
 * Textos de ayuda de la pestaña «Versiones». Van aquí y no sueltos en el JSX para que el test de contratos de
 * texto los lea.
 */

export const TIPOS_DE_MODELO = [
  {
    valor: "external_files",
    etiqueta: "Ficheros externos",
    ayuda:
      "El modelo corre fuera de Vigía y tú subes sus predicciones dentro de cada lote. Vigía no ejecuta nada. Es lo habitual.",
  },
  {
    valor: "executable",
    etiqueta: "Ejecutable",
    ayuda:
      "Subes el modelo como fichero (ONNX o pickle) y Vigía lo ejecuta para predecir y explicar. Sube pickle solo si confías en quien lo creó: un pickle puede ejecutar código.",
  },
] as const;

export const AYUDA_TIPO_MODELO =
  "Cómo llega la predicción a Vigía. Se elige al crear la versión. Ficheros externos: tú subes las predicciones en cada lote. Ejecutable: subes el modelo y Vigía lo ejecuta.";

/** Nombre legible del tipo; `sim_logistic` es el modelo simulado de la demo y el laboratorio. */
export function etiquetaTipoModelo(clave: string): string {
  if (clave === "sim_logistic") return "Simulador de Vigía";
  return TIPOS_DE_MODELO.find((t) => t.valor === clave)?.etiqueta ?? clave;
}

export const AYUDA_VENTANA_EQUIDAD =
  "La equidad se calcula sobre los últimos N registros de la versión. Una ventana grande da un resultado más estable, pero tarda más en notar un cambio. Una pequeña reacciona antes, pero oscila más. Si no la rellenas, se usan 200. Se fija al crear la versión; con tu modelo no se cambia después.";

export const AYUDA_ETIQUETA_VERSION =
  "Un nombre corto para reconocerla, por ejemplo «v2» o «reentrenado 2026-10».";

export const TITULO_PASOS = "Pasos para activar";

export interface PasoVersion {
  clave: "linea-base" | "congelar" | "modelo" | "activar";
  titulo: string;
  ayuda: string;
  opcional?: boolean;
}

export const PASOS_VERSION: readonly PasoVersion[] = [
  {
    clave: "linea-base",
    titulo: "1. Subir la línea base de esta versión",
    ayuda:
      "En Datos, sube un dataset con rol línea base y elige esta versión en el selector «Versión de modelo» de la ingesta.",
  },
  {
    clave: "congelar",
    titulo: "2. Congelarla",
    ayuda:
      "Ingerir una línea base ya la congela, así que este paso sale hecho solo. Si la versión tiene lotes pero ninguno es su línea base, fíjala a mano.",
  },
  {
    clave: "modelo",
    titulo: "3. Subir el modelo",
    ayuda: "Opcional. Sin el modelo, la explicabilidad de esta versión no está disponible.",
    opcional: true,
  },
  {
    clave: "activar",
    titulo: "4. Activarla",
    ayuda: "La versión activa es la que recibe los lotes nuevos. Las alertas siguen siendo del modelo, no de la versión.",
  },
];

/** Hueco del selector de línea base cuando la versión aún no tiene lotes propios. */
export const SIN_LOTES_PROPIOS =
  "Esta versión todavía no tiene lotes propios. Sube su línea base en Datos, eligiendo esta versión en la ingesta.";

export const TEXTO_UNA_SOLA_VERSION =
  "Este modelo tiene una sola versión. Cuando crees una segunda, aparecerá la pestaña Comparar para ver en qué mejora o empeora.";

/** La línea base queda congelada al ingerirla: fijarla otra vez daría un 409. */
export const LINEA_BASE_FIJADA = "Línea base fijada";

/** Aviso del diálogo «Subir modelo» cuando la versión no tiene ningún lote. */
export const SUBIR_MODELO_SIN_LINEA_BASE =
  "Esta versión todavía no tiene línea base con el mapeo de columnas, y el modelo se valida contra ella. Antes de subirlo, ingiere y mapea la línea base en Datos > Subir dataset.";

/** Botón del aviso anterior: cierra el diálogo y lleva a la pestaña Datos. */
export const SUBIR_MODELO_IR_A_DATOS = "Ir a Datos";
