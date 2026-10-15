/**
 * Textos de ayuda del paso «Umbrales»: una explicación por
 * columna y las etiquetas de los cinco orígenes que guarda el código
 * (`ThresholdOrigen`). Aquí, y no sueltos en el JSX, para que la tabla del
 * alta, el editor de la configuración del monitor y el test lean lo mismo.
 */

import type { ThresholdOrigen } from "@/api/queries-alta";
import { etiquetaCriterio } from "@/pages/monitores/tipos";

/** Lo que dice el paso «Umbrales» según el tipo de tarea. */
export const TEXTO_UMBRALES_MULTICLASE =
  "En un modelo multiclase, los umbrales de calidad salen de la línea base cuando la congelas. Miden el promedio de todas las clases " +
  "y llevan un pequeño margen sobre lo que mide la línea base. Aquí los confirmas o los sustituyes. " +
  "La equidad se propone desde la línea base cuando el modelo tiene clases favorables; sin ellas no hay umbral de equidad.";

/** Lo que dice el paso «Umbrales» de una regresión; los valores van en la unidad de la salida. */
export function textoUmbralesRegresion(unidad: string | null | undefined): string {
  const en = unidad ? ` (${unidad})` : "";
  return (
    `En un modelo de regresión, los umbrales salen de la línea base cuando la congelas y van en la unidad de la salida${en}. ` +
    "El error medio absoluto (MAE) y la raíz del error cuadrático medio (RMSE) son límites máximos; R² es un límite mínimo; " +
    "el sesgo medio y las diferencias entre grupos llevan un límite por cada lado, porque el modelo puede quedarse corto o pasarse. " +
    "Aquí los confirmas o los sustituyes."
  );
}

/** El número de la propuesta es el lote que se simula, no el tamaño de la línea base subida. */
export const ETIQUETA_TAMANO_LOTE = "Tamaño de lote para calcular los umbrales";

export function textoLoteSimulado(tamanoLote: number): string {
  return (
    `La propuesta se calcula con la línea base, simulando lotes de ${tamanoLote.toLocaleString("es-ES")} filas ` +
    "(el tamaño de lote para calcular los umbrales, no el número de filas de tu línea base). " +
    "Para la equidad se recomiendan lotes de 1 000 filas o más."
  );
}

/** El umbral de fábrica del AUC-PR no es un número fijo: se compara con la prevalencia. */
export const TEXTO_RELATIVO_PREVALENCIA = "relativo a la prevalencia";

/** Los cinco valores de origen, en el orden en que se explican. */
export const ORIGENES_UMBRAL: readonly ThresholdOrigen[] = [
  "linea_base",
  "fabricante",
  "criterio_clinico",
  "politica_organizacion",
  "fabrica",
];

/** Etiqueta de interfaz por origen. `criterio_clinico` se llama «criterio del responsable». */
export const ETIQUETA_ORIGEN_UMBRAL: Record<ThresholdOrigen, string> = {
  linea_base: "Línea base",
  fabricante: "Fabricante",
  criterio_clinico: "Criterio del responsable",
  politica_organizacion: "Política de la organización",
  fabrica: "Fábrica (sin calibrar)",
};

/** Etiqueta de un origen para el dominio del modelo (`criterio_clinico` cambia de nombre). */
export function etiquetaOrigenUmbral(origen: ThresholdOrigen, dominio?: string): string {
  return origen === "criterio_clinico" ? etiquetaCriterio(dominio, true) : ETIQUETA_ORIGEN_UMBRAL[origen];
}

export const EXPLICACION_ORIGEN_UMBRAL: Record<ThresholdOrigen, string> = {
  linea_base: "Aceptaste la propuesta calculada con los datos de la línea base de esta versión.",
  fabricante: "El valor lo da el fabricante del modelo; la nota dice dónde está escrito.",
  criterio_clinico: "Lo fija la persona responsable por su criterio.",
  politica_organizacion: "Lo exige una política de la organización: un protocolo, una norma interna o un contrato.",
  fabrica: "Valor por defecto de Vigía, sin calibrar para este modelo. Conviene sustituirlo.",
};

export interface AyudaColumna {
  titulo: string;
  texto: string;
}

/** Ayuda del título «Umbrales» del editor de la configuración de un monitor. */
export const AYUDA_UMBRALES_MONITOR: AyudaColumna = {
  titulo: "Umbrales",
  texto:
    "Límite inferior: la métrica no debe bajar de ese valor. Límite superior: no debe subir de él. Cada umbral guarda su origen y su nota. Si cambias un valor aquí, pide su origen y su nota; el paso Umbrales de la ficha del modelo los pide igual.",
};

export const AYUDA_COLUMNA_UMBRAL = {
  lineaBase: {
    titulo: "Línea base",
    texto: "El valor de la métrica en los datos de referencia con los que se congeló la línea base de esta versión del modelo.",
  },
  propuesta: {
    titulo: "Propuesta",
    texto:
      "El umbral que Vigía sugiere a partir de la línea base, con un margen alrededor de ese valor. Sin propuesta, la fila dice por qué.",
  },
  umbral: {
    titulo: "Umbral actual",
    texto: "El límite que vigila hoy el monitor: si la métrica lo cruza, pasa a alerta. Un mínimo vigila que no baje; un máximo, que no suba.",
  },
  origen: {
    titulo: "Origen",
    texto: "De dónde sale el umbral actual. Queda en el diario con su nota, para poder explicarlo en una auditoría.",
  },
} as const satisfies Record<string, AyudaColumna>;
