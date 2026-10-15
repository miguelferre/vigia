/**
 * Etiquetas en español para `DatasetKind`, `DatasetRole` y las claves de
 * `Batch.phase_label`.
 */

import type { DatasetKind, DatasetRole } from "@/api/types";

export const ETIQUETA_KIND: Record<DatasetKind, string> = {
  combined: "Combinado (predicciones y etiquetas)",
  payload: "Predicciones del modelo",
  feedback: "Etiquetas reales",
  usage_log: "Registro de uso",
  outcome: "Desenlaces",
};

/** «Papel» pasa a «Fase»: momento del despliegue en que se recogieron los datos. */
export const ETIQUETA_ROLE: Record<DatasetRole, string> = {
  baseline: "Línea base",
  production: "Producción",
};

/**
 * Dominio del proyecto (`services/projects.py::DOMINIOS`), para la tarjeta de
 * `/modelos` y el selector del alta: `libre` es el general; los otros
 * dos son los ejemplos de la demo. Las claves no cambian.
 */
export const ETIQUETA_DOMINIO: Record<string, string> = {
  libre: "General",
  reuma: "Ejemplo de la demo: reumatología",
  digestivo: "Ejemplo de la demo: digestivo",
};

/** Tipo de tarea del modelo (`Project.task_type`). */
export const ETIQUETA_TAREA: Record<string, string> = {
  binary: "clasificación binaria",
  multiclass: "clasificación multiclase",
  regression: "regresión",
};

/** Qué es la clase favorable; el alta, el mapeo y la guía de datos usan esta misma frase. */
export const FRASE_FAVORABLE = "el valor que cuenta como resultado bueno para la persona; la equidad mide quién lo recibe";

/** Lo mismo en multiclase, donde lo bueno es un conjunto de clases. */
export const FRASE_FAVORABLE_MULTICLASE =
  "las clases que cuentan como resultado bueno para la persona; la equidad mide quién recibe alguna de ellas";

/** Los campos del mapeo que cambian de sentido en multiclase. */
export const AYUDA_MAPEO_MULTICLASE = {
  favorable: `Marca ${FRASE_FAVORABLE_MULTICLASE}. Marca al menos una y deja al menos una sin marcar.`,
  prediccion: "La clase que dijo el modelo en cada caso, con su nombre (por ejemplo «permitido» o «spam»).",
  etiqueta: "La clase real de cada caso, con su nombre, la que pasó de verdad.",
  probabilidad:
    "Una columna con la probabilidad de cada clase, en el mismo orden que las clases. " +
    "Sin ellas no se mide el AUC ni la calibración.",
  formatoProbabilidad:
    "«Una columna por clase»: el fichero trae una columna de probabilidad para cada clase, " +
    "por ejemplo prob_spam y prob_odio. «Lista en una columna»: la columna trae las probabilidades de todas las " +
    "clases juntas, por ejemplo [0.7, 0.2, 0.1], en el orden de las clases.",
} as const;

/**
 * Ayuda en contexto del formulario de mapeo (`mapeo-campos.tsx`): qué
 * significa cada campo con palabras de quien no ha hecho estadística.
 */
export const AYUDA_MAPEO = {
  etiqueta:
    "El resultado real de cada caso (lo que pasó de verdad). Si llega semanas después de la predicción " +
    "(«etiquetas tardías»), no la pongas aquí: súbela más adelante en un dataset aparte de tipo " +
    "«Etiquetas reales», con la misma columna de id, y se une a su predicción.",
  formatoProbabilidad:
    "«Escalar»: la columna trae un solo número por fila, la probabilidad que da el modelo. " +
    "«Lista»: la columna trae varias probabilidades juntas, por ejemplo [0.2, 0.8]; el índice dice " +
    "qué posición de la lista se usa (empieza en 0).",
  columnaProtegida:
    "La columna que separa a las personas en grupos para medir si el modelo las trata igual " +
    "(por ejemplo sexo, edad u origen). Es opcional: sin ella no se calcula la equidad.",
  tipoAtributo:
    "«Rangos numéricos» si la columna protegida es un número (por ejemplo la edad) y cada grupo es un " +
    "intervalo. «Categórico» si son valores de texto o códigos (por ejemplo sexo) y cada grupo es una " +
    "lista de valores.",
  caracteristicas:
    "Las columnas que el modelo recibe como entrada. Sirven para medir la deriva y explicar las " +
    "predicciones. No marques ni el id, ni la predicción, ni la etiqueta.",
  favorable:
    `Elige ${FRASE_FAVORABLE}. Vacío hereda el de la plantilla del modelo o el de la línea base.`,
  identificador:
    "La columna que identifica cada caso. Con ella se unen las etiquetas reales que lleguen más tarde a su predicción.",
  prediccion: "Lo que dijo el modelo en cada caso (por ejemplo 0 o 1, o «aprobar»).",
  probabilidad: "La probabilidad que da el modelo, un número entre 0 y 1. Sin ella no se mide la calibración.",
  fecha:
    "Una fecha por fila. No cuenta como variable del modelo y los lotes siguientes la heredan.",
} as const;

export { etiquetaLote } from "@/lib/fases";
