/**
 * Frases calculadas de «Línea base frente a ahora»: sustituyen a la frase única de `fraseComparada` de antes
 * (a su vez sustituta de `ranking_changed_at`). Aparte de
 * `ranking-comparado-datos.ts` para que ningún fichero de este bloque pase
 * de 9 KB; usa sus tipos (`DeltaFila`, `FilaComparada`) sin volver a
 * calcularlos.
 *
 * `orden` cuenta si el top 10 conserva el orden (con la estabilidad y las
 * entradas/salidas/cambios de puesto que ya calculaba la función original);
 * `pesos` cuenta cuánto se mueve la importancia de cada variable entre la
 * línea base y ahora, aunque el orden no cambie. `Estado.tsx` pinta cada una
 * en su propio párrafo; `TarjetaEstabilidad.tsx` no las usa (repite el
 * cálculo de estabilidad solo con `resumen.stability`).
 */

import type { EstadoMotor } from "@/api/types";
import { nombreVariable } from "@/lib/dominio-caracteristicas";
import { formatoNumero } from "@/lib/metrics";

import type { DeltaFila, FilaComparada } from "./ranking-comparado-datos";

/** Umbral inferior de `explain_stability_ndcg`, fijo (`core/thresholds.py:76`): el resumen no lo publica. */
const UMBRAL_ESTABILIDAD = 0.5;

/** Por debajo de esto un desplazamiento de importancia no cuenta como movimiento real. */
const UMBRAL_DESPLAZAMIENTO_PESO = 0.005;

/**
 * En regresión las importancias van en la unidad de la salida y no tienen
 * escala fija: el umbral es relativo, un 2 % de la mayor importancia del
 * ranking. Un 0,005 absoluto no significa lo mismo en días que en
 * euros.
 */
const UMBRAL_RELATIVO_REGRESION = 0.02;

/** Formato de un número de importancia en la frase; en regresión lleva la unidad. */
export type FormatoPeso = (valor: number) => string;

/** Las dos frases de la tarjeta: el orden importa para el diagnóstico, los pesos para el detalle fino. */
export interface FraseComparada {
  /** Si el top 10 conserva el orden, con la estabilidad y las entradas/salidas/cambios de puesto. */
  orden: string;
  /** Los mayores desplazamientos de importancia entre línea base y ahora. */
  pesos: string;
}

/** Entradas, salidas y cambios de puesto del top 10 (cálculo sin la estabilidad). */
function detalleOrden(delta: DeltaFila[], dominio: Record<string, string> | undefined): string | null {
  const entran = delta.filter((d) => d.from === null);
  const salen = delta.filter((d) => d.to === null);
  const cambian = delta.filter((d) => d.from !== null && d.to !== null);

  if (entran.length > 0 || salen.length > 0) {
    const trozos: string[] = [];
    if (entran.length > 0) {
      const nombres = entran.map((d) => nombreVariable(d.feature, dominio)).join(", ");
      trozos.push(`${entran.length === 1 ? "Entra" : "Entran"} ${nombres}`);
    }
    if (salen.length > 0) {
      const nombres = salen.map((d) => nombreVariable(d.feature, dominio)).join(", ");
      trozos.push(`${salen.length === 1 ? "sale" : "salen"} ${nombres}`);
    }
    return `${trozos.join(", ")}.`;
  }
  if (cambian.length > 0) {
    const lista = cambian
      .map((d) => `${nombreVariable(d.feature, dominio)} (${d.from}.º → ${d.to}.º)`)
      .join(", ");
    return `Cambian de puesto: ${lista}.`;
  }
  return null;
}

/** «El orden ... casi no cambia / ha cambiado: estabilidad X sobre 0,50», más el detalle si lo hay. */
function fraseOrden(
  delta: DeltaFila[],
  stability: number | null,
  stabilityState: EstadoMotor | null,
  dominio: Record<string, string> | undefined,
): string {
  const detalle = detalleOrden(delta, dominio);
  if (stability === null) return detalle ?? "Mismas variables y mismo orden que en la línea base.";

  // Mismo criterio que antes: sin estado (`null`) se lee como «ok», nunca como cambio.
  const enOk = stabilityState === null || stabilityState === "ok";
  const cifras = `estabilidad ${formatoNumero(stability, 3)} sobre ${formatoNumero(UMBRAL_ESTABILIDAD, 2)}`;
  const cabecera = enOk
    ? `El orden de las variables casi no cambia: ${cifras}.`
    : `El orden de las variables ha cambiado: ${cifras}.`;
  return detalle ? `${cabecera} ${detalle}` : cabecera;
}

interface DesplazamientoPeso {
  label: string;
  base: number;
  actual: number;
  valor: number;
}

/** Filas con línea base y actual conocidos, con su desplazamiento absoluto, de mayor a menor. */
function desplazamientosPeso(filas: FilaComparada[]): DesplazamientoPeso[] {
  const resultado: DesplazamientoPeso[] = [];
  for (const f of filas) {
    if (f.base === null || f.actual === null) continue;
    resultado.push({ label: f.label, base: f.base, actual: f.actual, valor: Math.abs(f.actual - f.base) });
  }
  return resultado.sort((a, b) => b.valor - a.valor);
}

/** «Los pesos sí se mueven: A 0,22 → 0,19; B 0,05 → 0,02» con los dos mayores, o «apenas cambian». */
function fraseCambioPesos(filas: FilaComparada[], formato?: FormatoPeso): string {
  const desplazamientos = desplazamientosPeso(filas);
  const mayor = desplazamientos[0];
  const maxImportancia = Math.max(0, ...filas.flatMap((f) => [f.base ?? 0, f.actual ?? 0]));
  const umbral = formato ? UMBRAL_RELATIVO_REGRESION * maxImportancia : UMBRAL_DESPLAZAMIENTO_PESO;
  if (!mayor || mayor.valor <= umbral) return "Los pesos apenas cambian.";
  const f = formato ?? ((v: number) => formatoNumero(v, 2));
  const lista = desplazamientos
    .slice(0, 2)
    .map((d) => `${d.label} ${f(d.base)} → ${f(d.actual)}`)
    .join("; ");
  return `Los pesos sí se mueven: ${lista}.`;
}

/**
 * Las dos frases de la tarjeta: `orden` (qué cambia en el top 10 y
 * qué dice la estabilidad) y `pesos` (los mayores desplazamientos de
 * importancia entre línea base y ahora, sobre las mismas `filasComparadas`
 * que dibuja `RankingComparado`). Con `formatoPeso` (regresión) los pesos
 * llevan la unidad y el umbral es relativo.
 */
export function fraseComparada(
  delta: DeltaFila[],
  filasComparadas: FilaComparada[],
  stability: number | null,
  stabilityState: EstadoMotor | null,
  dominio: Record<string, string> | undefined,
  formatoPeso?: FormatoPeso,
): FraseComparada {
  return {
    orden: fraseOrden(delta, stability, stabilityState, dominio),
    pesos: fraseCambioPesos(filasComparadas, formatoPeso),
  };
}
