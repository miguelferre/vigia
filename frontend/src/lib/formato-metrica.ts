/**
 * Formato de valores de métrica y texto del rango favorable. Vive
 * aparte para que `metrics.ts` no pase de 9 KB; `metrics.ts` lo reexporta y
 * las pantallas lo importan de allí.
 */

import { formatoNumero } from "@/lib/metrics";

/** Rango favorable de una regresión: `[min, max]` con un extremo nulo como
 * abierto. */
export type RangoFavorable = readonly [number | null, number | null];

/**
 * Texto de los rangos favorables, copia de `texto_rangos` de
 * `core/schema.py`: «de 40 a 81 horas por semana», «desde 40 días»,
 * «hasta 7 días»; varios intervalos con comas y «y» al final. Los números
 * van con coma decimal. Sin rangos, cadena vacía.
 */
export function textoRangos(rangos: readonly RangoFavorable[] | null | undefined, unidad: string | null | undefined): string {
  if (!rangos || rangos.length === 0) return "";
  const u = unidad ? ` ${unidad}` : "";
  const n = (v: number) => v.toLocaleString("es-ES", { maximumFractionDigits: 3 });
  const partes = rangos
    .map(([min, max]) => {
      if (min !== null && max !== null) return `de ${n(min)} a ${n(max)}${u}`;
      if (min !== null) return `desde ${n(min)}${u}`;
      if (max !== null) return `hasta ${n(max)}${u}`;
      return "";
    })
    .filter(Boolean);
  if (partes.length <= 1) return partes[0] ?? "";
  return `${partes.slice(0, -1).join(", ")} y ${partes[partes.length - 1]}`;
}

/** Medidas de regresión en la unidad de la salida. Incluye las
 * claves de `details` que la interfaz enseña como métrica: la diferencia de
 * medias de la deriva y la diferencia media de los overrides. */
const EN_UNIDAD = new Set([
  "mean_absolute_error",
  "root_mean_squared_error",
  "mean_error",
  "median_absolute_error",
  "mean_absolute_error_difference",
  "mean_error_difference",
  "diferencia_medias",
  "diferencia_media",
]);
/** En la unidad al cuadrado. */
const EN_UNIDAD_CUADRADA = new Set(["mean_squared_error"]);
/** El sesgo y las diferencias llevan signo (negativo es infraestimar). */
const CON_SIGNO = new Set(["mean_error", "mean_error_difference", "mean_absolute_error_difference", "diferencia_medias"]);
/** Sin unidad, con 3 decimales fijos. */
const SIN_UNIDAD = new Set(["r2", "prediction_drift_score", "mean_absolute_error_ratio"]);

/** `true` si la medida va en la unidad de la salida (o su cuadrado). Un
 * gráfico de estas medidas no fija el eje en 0 a 1. */
export function esMedidaEnUnidad(clave: string): boolean {
  return EN_UNIDAD.has(clave) || EN_UNIDAD_CUADRADA.has(clave);
}

/** `true` si la medida lleva signo explícito (sesgo y diferencias). */
export function esMedidaConSigno(clave: string): boolean {
  return CON_SIGNO.has(clave);
}

/** Decimales según la magnitud: 0 desde 100, 1 desde 10, 2 desde 0,1 y 3
 * por debajo. */
function decimalesPorMagnitud(valor: number): number {
  const a = Math.abs(valor);
  if (a >= 100) return 0;
  if (a >= 10) return 1;
  if (a >= 0.1 || a === 0) return 2;
  return 3;
}

/** Unidad tal como acompaña al número: `días`, `días²`, `(horas por semana)²`. */
function textoUnidad(clave: string, unidad: string | null | undefined): string | null {
  if (!unidad) return null;
  if (EN_UNIDAD_CUADRADA.has(clave)) return /\s/.test(unidad) ? `(${unidad})²` : `${unidad}²`;
  return EN_UNIDAD.has(clave) ? unidad : null;
}

/** Número y unidad por separado, para tarjetas que dibujan la unidad aparte. */
export interface PartesMetrica {
  numero: string;
  unidad: string | null;
}

/** Igual que `formatoMetrica`, con el número y la unidad separados. */
export function formatoMetricaPartes(clave: string, valor: number | null | undefined, unidad?: string | null): PartesMetrica {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return { numero: "n/d", unidad: null };
  if (SIN_UNIDAD.has(clave)) return { numero: formatoNumero(valor, 3), unidad: null };
  if (!esMedidaEnUnidad(clave)) return { numero: formatoNumero(valor, 3), unidad: null };
  const d = decimalesPorMagnitud(valor);
  const numero = valor.toLocaleString("es-ES", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
    signDisplay: CON_SIGNO.has(clave) ? "exceptZero" : "auto",
  });
  return { numero, unidad: textoUnidad(clave, unidad) };
}

/**
 * Único formateador de valores de métrica. Las medidas de error de
 * regresión llevan la unidad y los decimales según la magnitud; `r2`,
 * `prediction_drift_score` y `mean_absolute_error_ratio` van sin unidad con
 * 3 decimales; el sesgo medio y las diferencias llevan signo; nunca añade un
 * «%». Cualquier otra clave sale como hoy (`formatoNumero` con 3 decimales):
 * en binario y multiclase la interfaz no cambia. Sin valor, `n/d`.
 */
export function formatoMetrica(clave: string, valor: number | null | undefined, unidad?: string | null): string {
  const p = formatoMetricaPartes(clave, valor, unidad);
  return p.unidad ? `${p.numero} ${p.unidad}` : p.numero;
}

/** Las 19 medidas de equidad que leen el 0/1 de pertenencia al rango favorable
 * (copia de `_METRICAS_PREDICCION` y `_METRICAS_ETIQUETA` de `core/fairness.py`). */
export const MEDIDAS_DE_PERTENENCIA: ReadonlySet<string> = new Set([
  "rate_unpriv", "rate_priv", "disparate_impact", "fairness_value", "impact_score",
  "statistical_parity_difference", "false_negative_rate_difference", "false_positive_rate_difference",
  "false_discovery_rate_difference", "false_omission_rate_difference", "error_rate_difference",
  "average_odds_difference", "average_abs_odds_difference", "fnr_unpriv", "fnr_priv", "fpr_unpriv",
  "fpr_priv", "tpr_unpriv", "tpr_priv",
]);

/** Etiqueta con «(rango favorable)» detrás si la medida lee la pertenencia y el
 * proyecto es una regresión con rango. */
export function etiquetaConRango(etiqueta: string, clave: string, conRango: boolean | undefined): string {
  return conRango && MEDIDAS_DE_PERTENENCIA.has(clave) ? `${etiqueta} (rango favorable)` : etiqueta;
}
