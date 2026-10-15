/**
 * Lectores de `details` de la equidad de regresión.
 * Sin React. Mismo criterio que `regresion-datos.ts`: defensivo, `null` si
 * falta lo que la pantalla necesita.
 */

import { detallesDe, leerHistograma, num, obj, type HistogramaNumerico } from "./regresion-datos";

export type GrupoRegresion = "unpriv" | "priv";
const GRUPOS: readonly GrupoRegresion[] = ["unpriv", "priv"];

export interface ErrorGrupo {
  grupo: GrupoRegresion;
  n: number;
  mae: number | null;
  sesgo: number | null;
  motivo: string | null;
}

/** `details.error_por_grupo` de equidad: no privilegiado primero. */
export function leerErrorPorGrupo(result: unknown): ErrorGrupo[] | null {
  const e = obj(detallesDe(result)?.error_por_grupo);
  if (!e) return null;
  const filas: ErrorGrupo[] = [];
  for (const grupo of GRUPOS) {
    const g = obj(e[grupo]);
    if (!g) continue;
    filas.push({
      grupo,
      n: num(g.n) ?? 0,
      mae: num(g.mae),
      sesgo: num(g.sesgo),
      motivo: typeof g.motivo === "string" ? g.motivo : null,
    });
  }
  return filas.length > 0 ? filas : null;
}

export interface Cuantiles {
  p5: number;
  p25: number;
  p50: number;
  p75: number;
  p95: number;
}

export interface PrediccionGrupo {
  grupo: GrupoRegresion;
  n: number;
  media: number | null;
  cuantiles: Cuantiles | null;
  histograma: HistogramaNumerico | null;
}

function leerCuantiles(v: unknown): Cuantiles | null {
  const c = obj(v);
  const p5 = num(c?.p5);
  const p25 = num(c?.p25);
  const p50 = num(c?.p50);
  const p75 = num(c?.p75);
  const p95 = num(c?.p95);
  return p5 === null || p25 === null || p50 === null || p75 === null || p95 === null ? null : { p5, p25, p50, p75, p95 };
}

/** `details.prediccion_por_grupo` de equidad: la distribución de la predicción por grupo. */
export function leerPrediccionPorGrupo(result: unknown): PrediccionGrupo[] | null {
  const e = obj(detallesDe(result)?.prediccion_por_grupo);
  if (!e) return null;
  const filas: PrediccionGrupo[] = [];
  for (const grupo of GRUPOS) {
    const g = obj(e[grupo]);
    if (!g) continue;
    filas.push({
      grupo,
      n: num(g.n) ?? 0,
      media: num(g.media),
      cuantiles: leerCuantiles(g.cuantiles),
      histograma: leerHistograma(g.histograma),
    });
  }
  return filas.length > 0 ? filas : null;
}

/** `true` si `details` marca la equidad como sin rango favorable. */
export function equidadSinRango(result: unknown): boolean {
  return detallesDe(result)?.sin_rango_favorable === true;
}

export function leerMotivoSinRango(result: unknown): string | null {
  const m = detallesDe(result)?.motivo;
  return typeof m === "string" ? m : null;
}

/** Motivo cuando el modelo no declara un rango favorable. */
export const MOTIVO_SIN_RANGO = "sin rango favorable: solo el error por grupo";

/**
 * Lectura en palabras de las tres diferencias de error entre grupos. El
 * grupo supervisado es el primero; la diferencia es supervisado menos
 * referencia. `unidad` ya viene sin formato: lo pone `formato`.
 */
export function fraseDiferenciaError(
  clave: string,
  valor: number | null,
  formato: (clave: string, valor: number) => string,
): string {
  if (valor === null) return "Sin valor.";
  switch (clave) {
    case "mean_absolute_error_difference":
      return Math.abs(valor) < 5e-4
        ? "El modelo se equivoca igual con los dos grupos."
        : valor > 0
          ? `El modelo se equivoca de media ${formato("mean_absolute_error", valor)} más con el grupo supervisado.`
          : `El modelo se equivoca de media ${formato("mean_absolute_error", -valor)} menos con el grupo supervisado.`;
    case "mean_absolute_error_ratio":
      return `El error del grupo supervisado es ${valor.toLocaleString("es-ES", { maximumFractionDigits: 2 })} veces el del grupo de referencia.`;
    case "mean_error_difference":
      return Math.abs(valor) < 5e-4
        ? "El sesgo es el mismo en los dos grupos."
        : valor < 0
          ? `Frente al grupo de referencia, el modelo asigna al grupo supervisado de media ${formato("mean_absolute_error", -valor)} menos de lo que le corresponde.`
          : `Frente al grupo de referencia, el modelo asigna al grupo supervisado de media ${formato("mean_absolute_error", valor)} más de lo que le corresponde.`;
    default:
      return "";
  }
}

/** Mediana de la predicción de cada grupo, dicha con palabras. */
export function fraseDiferenciaMedianas(
  supervisado: number | null,
  referencia: number | null,
  formato: (valor: number) => string,
): string | null {
  if (supervisado === null || referencia === null) return null;
  const d = supervisado - referencia;
  const cuanto = Math.abs(d) < 5e-4 ? null : formato(Math.abs(d));
  return cuanto === null
    ? "La predicción mediana es la misma en los dos grupos."
    : `La predicción mediana del grupo supervisado es ${formato(supervisado)}, ${cuanto} ${d < 0 ? "menos" : "más"} que la del grupo de referencia (${formato(referencia)}).`;
}
