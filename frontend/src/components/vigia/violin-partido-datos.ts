/**
 * Datos puros del violín de equidad: tipos de `details.favorable_probability`, parseo
 * defensivo (es JSON libre, sin esquema en `schema.d.ts`), silueta por mitad
 * y la frase calculada («viene de la puntuación» / «viene del umbral» /
 * «las dos distribuciones son parecidas»). Fichero aparte de
 * `ViolinPartido.tsx` para que el componente no se acerque a 9 KB.
 */

import { densidadPorTramo, siluetaMonotona } from "@/pages/monitores/violin-silueta";

export interface FavorableProbabilityGrupo {
  bin_counts?: unknown;
  n?: unknown;
  median?: unknown;
  rate_above_threshold?: unknown;
  motivo?: unknown;
}

export interface FavorableProbability {
  bin_edges: number[];
  threshold: number;
  threshold_motivo: string | null;
  by_group: Record<string, FavorableProbabilityGrupo | undefined>;
}

/** Grupo ya validado, listo para dibujar: `null` si el motor lo omitió (`motivo`) o no cuadra. */
export interface GrupoResuelto {
  binCounts: number[];
  n: number;
  median: number | null;
  rateAboveThreshold: number | null;
  motivo: string | null;
}

function numeroOn(v: unknown): number | null {
  return typeof v === "number" && !Number.isNaN(v) ? v : null;
}

/**
 * `details.favorable_probability` no tiene esquema Pydantic (JSON libre): se valida a mano, sin lanzar, para que un dato inesperado
 * no rompa la caja del impacto dispar.
 */
export function parseFavorableProbability(
  detalles: Record<string, unknown> | null,
): { datos: FavorableProbability | null; motivo: string | null } {
  const crudo = detalles?.["favorable_probability"];
  const motivoCrudo = detalles?.["favorable_probability_motivo"];
  const motivo = typeof motivoCrudo === "string" ? motivoCrudo : null;
  if (crudo === null || crudo === undefined || typeof crudo !== "object") return { datos: null, motivo };
  const obj = crudo as Record<string, unknown>;
  const binEdges = Array.isArray(obj.bin_edges) ? obj.bin_edges.filter((x): x is number => typeof x === "number") : [];
  const threshold = numeroOn(obj.threshold);
  const byGroup = obj.by_group && typeof obj.by_group === "object" ? (obj.by_group as Record<string, unknown>) : {};
  if (binEdges.length < 2 || threshold === null) return { datos: null, motivo };
  return {
    datos: {
      bin_edges: binEdges,
      threshold,
      threshold_motivo: typeof obj.threshold_motivo === "string" ? obj.threshold_motivo : null,
      by_group: byGroup as Record<string, FavorableProbabilityGrupo | undefined>,
    },
    motivo,
  };
}

/** Resuelve un grupo (`unpriv`/`priv`): `motivo` cuando el motor lo omitió por `min_group`. */
export function resolverGrupo(bruto: FavorableProbabilityGrupo | undefined, nBins: number): GrupoResuelto | null {
  if (!bruto) return null;
  if (typeof bruto.motivo === "string") {
    return { binCounts: [], n: 0, median: null, rateAboveThreshold: null, motivo: bruto.motivo };
  }
  const binCounts = Array.isArray(bruto.bin_counts) ? bruto.bin_counts.filter((x): x is number => typeof x === "number") : [];
  if (binCounts.length !== nBins) return null;
  return {
    binCounts,
    n: numeroOn(bruto.n) ?? 0,
    median: numeroOn(bruto.median),
    rateAboveThreshold: numeroOn(bruto.rate_above_threshold),
    motivo: null,
  };
}

/** Silueta suavizada (PCHIP) de un grupo, en la escala de densidad de `bin_edges`. */
export function siluetaDeGrupo(binEdges: number[], grupo: GrupoResuelto): { valor: number; densidad: number }[] {
  const densidades = densidadPorTramo(binEdges, grupo.binCounts);
  if (densidades.length === 0) return [];
  return siluetaMonotona(binEdges, densidades);
}

/** Densidad interpolada de una silueta ya muestreada, en un valor cualquiera del eje. */
export function densidadEnValor(silueta: { valor: number; densidad: number }[], valor: number): number {
  if (silueta.length === 0) return 0;
  if (valor <= silueta[0].valor) return silueta[0].densidad;
  if (valor >= silueta[silueta.length - 1].valor) return silueta[silueta.length - 1].densidad;
  for (let i = 0; i < silueta.length - 1; i++) {
    const a = silueta[i];
    const b = silueta[i + 1];
    if (valor >= a.valor && valor <= b.valor) {
      const t = b.valor > a.valor ? (valor - a.valor) / (b.valor - a.valor) : 0;
      return a.densidad + (b.densidad - a.densidad) * t;
    }
  }
  return 0;
}

/**
 * Frase calculada (regla nueva de 6.9, sin precedente): con la diferencia de
 * medianas si llega a 0,05, si no con la diferencia de tasas sobre el
 * umbral, si no las dos distribuciones se leen parecidas.
 */
export function fraseCalculada(
  threshold: number,
  supervisado: GrupoResuelto | null,
  referencia: GrupoResuelto | null,
  nombreSupervisado: string,
  nombreReferencia: string,
  formatoNumero: (v: number | null | undefined, decimales?: number) => string,
  formatoPorcentaje: (v: number | null, decimales?: number) => string,
): string | null {
  if (!supervisado || !referencia || supervisado.motivo || referencia.motivo) return null;
  const dSup = supervisado.median;
  const dRef = referencia.median;
  const rSup = supervisado.rateAboveThreshold;
  const rRef = referencia.rateAboveThreshold;
  if (dSup === null || dRef === null) return null;
  if (Math.abs(dSup - dRef) >= 0.05) {
    return (
      `La disparidad viene de la puntuación: la mediana de ${nombreSupervisado} es ` +
      `${formatoNumero(dSup, 2)} y la de ${nombreReferencia} es ${formatoNumero(dRef, 2)}.`
    );
  }
  if (rSup !== null && rRef !== null && Math.abs(rSup - rRef) >= 0.05) {
    return (
      `La disparidad viene del umbral: con el umbral en ${formatoNumero(threshold, 2)}, ` +
      `${formatoPorcentaje(rSup)} de ${nombreSupervisado} queda por encima frente a ` +
      `${formatoPorcentaje(rRef)} de ${nombreReferencia}.`
    );
  }
  return "Las dos distribuciones son parecidas: la disparidad medida no se explica por la puntuación ni por dónde cae el umbral.";
}
