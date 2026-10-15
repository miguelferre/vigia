/**
 * Umbral efectivo de una métrica en la rejilla y medidas por clase.
 * Fuera de `tipos.ts` por tamaño.
 *
 * El `value` de un umbral del monitor no siempre es el límite que se evalúa:
 *
 * - Un umbral relativo (`relativo_a = "prevalencia"`) guarda una
 *   fracción (0,8), no un valor de la métrica. El límite real lo resuelve el
 *   motor con la línea base y llega en `threshold_low` de cada punto.
 * - En multiclase los umbrales de fábrica no se evalúan: solo valen los
 *   que salen de la línea base o los que fijó una persona.
 *
 * En los dos casos la serie y la tarjeta dibujan el límite que trae el último
 * punto global de la propia serie. En binario sin umbral relativo, lo de
 * siempre: el valor configurado.
 */

import type { TimelinePoint } from "@/api/types";
import { esGrupoClase } from "@/lib/tipo-tarea";
import { formatoCorto } from "@/lib/metrics";

import {
  GRUPO_GLOBAL,
  umbralesDeMetrica,
  type SerieAgrupada,
  type ThresholdEntry,
  type UmbralesMetrica,
} from "./tipos";

/** Medida por clase (`group_code = "clase:<clave>"`): sin umbral, no es un grupo protegido. */
export function esSerieDeClase(s: SerieAgrupada): boolean {
  return esGrupoClase(s.grupo);
}

/** Separa las series de una métrica en las de siempre (global y grupos protegidos) y las por clase. */
export function separarPorClase(series: SerieAgrupada[]): { globales: SerieAgrupada[]; porClase: SerieAgrupada[] } {
  const globales: SerieAgrupada[] = [];
  const porClase: SerieAgrupada[] = [];
  for (const s of series) (esSerieDeClase(s) ? porClase : globales).push(s);
  return { globales, porClase };
}

/** Último punto de la serie global (o el de la única serie que haya). */
export function ultimoPuntoGlobal(globales: SerieAgrupada[]): TimelinePoint | null {
  const serie = globales.find((s) => s.grupo === GRUPO_GLOBAL) ?? (globales.length === 1 ? globales[0] : undefined);
  return serie?.puntos[serie.puntos.length - 1] ?? null;
}

export function umbralEfectivo(
  entradas: ThresholdEntry[],
  metrica: string,
  globales: SerieAgrupada[],
  multiclase: boolean,
): UmbralesMetrica {
  const configurado = umbralesDeMetrica(entradas, metrica);
  const relativas = entradas.filter((e) => e.metric_key === metrica && e.relativo_a);
  if (!multiclase && relativas.length === 0) return configurado;
  const ultimo = ultimoPuntoGlobal(globales);
  if (multiclase) return { low: ultimo?.threshold_low ?? null, high: ultimo?.threshold_high ?? null };
  let { low, high } = configurado;
  for (const e of relativas) {
    if (e.kind === "lower_limit") low = ultimo?.threshold_low ?? null;
    else high = ultimo?.threshold_high ?? null;
  }
  return { low, high };
}

/** `true` si el umbral del monitor no se evalúa en multiclase: de fábrica o relativo. */
export function umbralSinEfectoEnMulticlase(e: ThresholdEntry): boolean {
  return e.relativo_a != null || (e.origen ?? "fabrica") === "fabrica";
}

/** Texto de un umbral configurado: «mínimo 0,7»; relativo: «relativo a la prevalencia (0,8 de la mejora de la línea base)». */
export function textoUmbralConfigurado(e: ThresholdEntry): string {
  const limite = e.kind === "lower_limit" ? "mínimo" : "máximo";
  if (e.relativo_a === "prevalencia") {
    return `${limite} relativo a la prevalencia (${formatoCorto(e.value)} de lo que la línea base mejora sobre ella)`;
  }
  return `${limite} ${formatoCorto(e.value)}`;
}

/**
 * Umbral con su valor editado. Un valor cambiado a mano
 * ya no es el de fábrica ni el de la línea base: pasa a ser tuyo
 * (`criterio_clinico`, «criterio del responsable») y
 * nunca se guarda como `fabrica`. En calidad multiclase eso también hace que
 * se empiece a evaluar. Con `inicial` (el umbral al abrir la hoja), volver al
 * valor de partida devuelve su origen y su nota. Los orígenes que ya son de una
 * persona (fabricante, criterio, política) se conservan.
 */
export function umbralEditado(u: ThresholdEntry, valor: number, inicial?: ThresholdEntry): ThresholdEntry {
  if (inicial && valor === inicial.value) return { ...inicial };
  const origen = u.origen ?? "fabrica";
  const hazteTuyo = origen === "fabrica" || origen === "linea_base";
  return { ...u, value: valor, ...(hazteTuyo ? { origen: "criterio_clinico" as const } : {}) };
}

/** `true` si el valor del umbral ya no es el que tenía al abrir la configuración. */
export function umbralCambiado(u: ThresholdEntry, inicial: ThresholdEntry | undefined): boolean {
  return inicial !== undefined && u.value !== inicial.value;
}

/** Una fila cambiada con origen de persona y sin nota: no se puede guardar (misma regla que el paso Umbrales del alta). */
export function faltaNotaDeUmbral(umbrales: ThresholdEntry[], iniciales: ThresholdEntry[]): boolean {
  return umbrales.some(
    (u, i) =>
      umbralCambiado(u, iniciales[i]) &&
      u.origen !== "linea_base" &&
      u.origen !== "fabrica" &&
      !(u.nota ?? "").trim(),
  );
}
