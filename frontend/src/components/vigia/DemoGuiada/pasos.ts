/**
 * Qué pide cada paso de la demo guiada para darse por hecho, deducido
 * del contenido y no de una lista de ids: los que precargan un formulario
 * (`crear-modelo`, `subir-datos` y la anotación del diario) esperan al
 * evento del contrato; los que cargan un lote (su `fase_minima` sube
 * respecto a todo lo anterior) esperan a que termine el trabajo; el resto,
 * con llegar a su pantalla. La anotación ya no tiene ancla propia
 * (`hilo`, para que el diario desplace al evento nuevo), así que se
 * reconoce por su ruta y por el texto que el guion manda escribir entre « y ».
 */

import type { PasoDemo } from "@/api/queries-contenido";
import type { EstadoMotor } from "@/api/types";

/** Los textos entre « y » del campo `hace`: lo que el guion dice que se pulsa o se escribe. */
export function citasDe(texto: string | null | undefined): string[] {
  if (!texto) return [];
  return Array.from(texto.matchAll(/«([^»]+)»/g), (m) => m[1]!.trim());
}

/** El paso que escribe una anotación humana en el diario: va a `/diario` y dicta el texto. */
export function esPasoDeAnotacion(paso: PasoDemo): boolean {
  return (paso.destino.ruta?.startsWith("/diario") ?? false) && citasDe(paso.hace).length > 0;
}

/** El paso espera al evento de una pantalla real, no a llegar a ella. */
export function esPasoConEvento(paso: PasoDemo): boolean {
  const ancla = paso.destino.ancla;
  return ancla === "crear-modelo" || ancla === "subir-datos" || esPasoDeAnotacion(paso);
}

/** Ids de los tres pasos con evento, o `null` si el guion no los trae. */
export function pasosConEvento(pasos: PasoDemo[]): { crear: number | null; subir: number | null; anotar: number | null } {
  return {
    crear: pasos.find((p) => p.destino.ancla === "crear-modelo")?.id ?? null,
    subir: pasos.find((p) => p.destino.ancla === "subir-datos")?.id ?? null,
    anotar: pasos.find(esPasoDeAnotacion)?.id ?? null,
  };
}

/** El paso carga un lote: su `fase_minima` sube respecto a todo lo anterior (y no es la línea base). */
export function esPasoDeCarga(pasos: PasoDemo[], n: number): boolean {
  const paso = pasos[n];
  if (!paso || esPasoConEvento(paso)) return false;
  const previa = Math.max(0, ...pasos.slice(0, n).map((p) => p.fase_minima));
  return paso.fase_minima > previa && paso.fase_minima > 1;
}

/** Id del primer paso cuyo dato esperado tiene ese estado (la leyenda se abre ahí), o `null`. */
export function primerPasoConEstado(pasos: PasoDemo[], estado: EstadoMotor): number | null {
  return pasos.find((p) => p.dato.estado === estado)?.id ?? null;
}

/**
 * Lo que el paso pide ya existe (reproducción adoptada con `?run=`, o vuelta
 * atrás): el modelo para `crear-modelo`, la reproducción para `subir-datos`,
 * el lote para un paso de carga. Con llegar a la pantalla basta entonces.
 */
export function yaSatisfecho(
  pasos: PasoDemo[],
  n: number,
  estado: { projectId: number | null; runId: number | null; fasesReproducidas: number },
): boolean {
  const paso = pasos[n];
  if (!paso) return false;
  if (paso.destino.ancla === "crear-modelo") return estado.projectId !== null;
  if (paso.destino.ancla === "subir-datos") return estado.runId !== null;
  if (esPasoDeCarga(pasos, n)) return estado.fasesReproducidas >= paso.fase_minima;
  return false;
}
