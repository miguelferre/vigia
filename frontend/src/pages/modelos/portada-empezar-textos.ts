/**
 * Textos del bloque «Empezar» de la portada sin modelos.
 * Los tres caminos y el enlace a la guía de datos van aquí, no sueltos en el
 * JSX, para que el test de textos y la captura lean lo mismo.
 */

export const TITULO_EMPEZAR = "Empezar con Vigía";

export const DESCRIPCION_EMPEZAR =
  "Vigía vigila un modelo de IA ya en uso: compara sus resultados con una línea base y avisa cuando algo se desvía. Elige por dónde empezar.";

/** Enlace de encima del bloque: la sección «Datos» de la Ayuda (guía de datos). */
export const ENLACE_DATOS = { texto: "Qué necesito antes de empezar", ruta: "/ayuda#datos" } as const;

export const CAMINOS = {
  alta: "Dar de alta tu modelo",
  demo: "Ver la demo",
  asistente: "Conectar un asistente de IA",
} as const;

/** Entrada 19 de la guía de uso: operar Vigía con un asistente de IA. */
export const RUTA_ASISTENTE = "/ayuda#guia-19";
export const RUTA_DEMO = "/demo";

export const AYUDA_CAMINOS = {
  alta: "Tus ficheros, tus umbrales: es el camino real.",
  demo: "Un caso sintético de reumatología, sin tocar tus datos.",
  asistente: "Un asistente como Claude puede operar Vigía por ti.",
} as const;
