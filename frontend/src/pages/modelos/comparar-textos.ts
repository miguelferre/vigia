/**
 * Textos de la pestaña «Comparar». Van
 * aquí y no sueltos en el JSX: así los lee el test de contratos de texto.
 */

import type { ComparacionFila } from "@/api/queries-versiones";

/**
 * Dirección de una fila. `"cambia"` es la de una medida que cambió sin que
 * subir ni bajar sea mejor (una proporción de clase). Se declara aquí además de
 * en la API para que el tipo valga antes y después de regenerar `schema.d.ts`.
 */
export type DireccionComparacion = ComparacionFila["direccion"] | "cambia";

export const TITULO_AYUDA_COMPARAR = "Cómo leer la comparación";

/** Párrafos de la ayuda «Cómo leer la comparación». */
export const AYUDA_COMPARAR: readonly string[] = [
  "Cada versión se mide contra su propia línea base. Por eso la comparación enseña, para cada métrica, el valor de la versión A, el de la versión B y la diferencia (B menos A).",
  "La ventana «Último lote» usa el último lote de producción evaluado de cada versión. «Todos los lotes» usa la media de sus lotes de producción evaluados.",
  "El chip dice si B mejora, empeora o queda igual que A. «Cambia» es para una medida que cambió pero no mejora ni empeora, como la proporción de una clase. Se decide con el umbral del monitor: con solo mínimo, más alto es mejor; con solo máximo, más bajo es mejor; con los dos, mejor es estar más cerca del centro del intervalo. Queda igual si los intervalos de los dos lados se solapan o, sin intervalo, si la diferencia es menor que 0,01. Sin datos significa que una de las dos versiones no tiene lotes evaluados con esa métrica.",
  "La deriva se compara como la distancia de cada versión a su propia línea base, porque cada versión tiene la suya. Su nota lo dice.",
  "El estado de cada lado es el que guardó el motor al evaluar ese lote, no un cálculo nuevo con los umbrales de hoy.",
  "La tabla compara equidad, calidad y deriva. Las reglas cruzadas y la explicabilidad no entran en la comparación.",
];

/** Lo que cambia en la comparación de una regresión. Se enseña solo en esos proyectos. */
export const AYUDA_COMPARAR_REGRESION =
  "En una regresión, los errores van en la unidad de la salida (días, horas por semana). Una medida de error queda igual si la diferencia es menor que el 1 % de la desviación del valor real en la línea base de la versión A. " +
  "R² y la puntuación de deriva de la predicción siguen con 0,01. El sesgo medio y su diferencia entre grupos son de dos lados: mejor es estar más cerca de 0. " +
  "Si la versión A no tiene línea base con valor real que varíe, esa regla no se puede aplicar y la fila lo dice.";

/** Aviso a ancho de móvil: la tabla desliza dentro de su contenedor. */
export const AVISO_DESLIZAR_TABLA = "Desliza la tabla hacia los lados para ver todas las columnas.";

/** Rótulos de la sección de alertas vivas. */
export const TITULO_ALERTAS_VIVAS = "Alertas vivas del modelo";
export const ETIQUETA_VERSION_MEDIDA = "Versión de la última medida:";
export const SIN_VERSION_ASOCIADA = "Sin versión asociada";

/** Qué dice la sección de alertas vivas cuando no hay ninguna. */
export const SIN_ALERTAS_VIVAS = "No hay alertas vivas en este despliegue.";

export const ETIQUETA_DIRECCION: Record<DireccionComparacion, string> = {
  mejora: "Mejora",
  empeora: "Empeora",
  igual: "Igual",
  cambia: "Cambia",
  sin_datos: "Sin datos",
};

/** Texto de apoyo del chip: el color nunca es la única señal. */
export const PISTA_DIRECCION: Record<DireccionComparacion, string> = {
  mejora: "La versión B va mejor que la A en esta métrica.",
  empeora: "La versión B va peor que la A en esta métrica.",
  igual: "No hay diferencia apreciable entre las dos versiones.",
  cambia: "La medida ha cambiado entre las dos versiones, pero una proporción de clase no mejora ni empeora.",
  sin_datos: "Falta el valor de alguna de las dos versiones.",
};

export const ETIQUETA_VENTANA = {
  ultimo: "Último lote",
  todos: "Todos los lotes",
} as const;
