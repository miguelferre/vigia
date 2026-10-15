/**
 * Línea de cambio de versión en las series de los monitores. Cada punto de `/timeline` trae `model_version_id`: donde
 * cambia de una fila a la siguiente empieza una versión nueva, y ahí se
 * dibuja una línea vertical rotulada con la etiqueta de esa versión.
 *
 * Las funciones devuelven datos y elementos sueltos (no un componente): en
 * Recharts 3 una `ReferenceLine` de eje de categorías funciona dentro de un
 * array de hijos del `LineChart`, y así no hay que envolverla.
 */

import { ReferenceLine } from "recharts";

import type { FilaCombinada } from "./tipos";

export interface CambioVersion {
  /** `ts` de la primera fila de la versión nueva: la categoría del eje X. */
  ts: string;
  etiqueta: string;
}

/** Versión de una fila: todos sus puntos son del mismo lote, así que sirve cualquiera. */
function versionDeFila(fila: FilaCombinada): number | null {
  const punto = Object.values(fila.porGrupo)[0];
  return punto ? punto.model_version_id : null;
}

/** Filas donde cambia la versión respecto a la anterior, con la etiqueta de la nueva. */
export function cambiosDeVersion(filas: FilaCombinada[], etiquetas: ReadonlyMap<number, string>): CambioVersion[] {
  const cambios: CambioVersion[] = [];
  let anterior: number | null = null;
  for (const fila of filas) {
    const actual = versionDeFila(fila);
    if (actual === null) continue;
    if (anterior !== null && actual !== anterior) {
      cambios.push({ ts: fila.ts, etiqueta: etiquetas.get(actual) ?? `versión ${actual}` });
    }
    anterior = actual;
  }
  return cambios;
}

/** Una `ReferenceLine` vertical rotulada por cada cambio de versión. */
export function lineasCambioVersion(cambios: CambioVersion[]) {
  return cambios.map((c) => (
    <ReferenceLine
      key={`cambio-${c.ts}`}
      x={c.ts}
      stroke="var(--foreground)"
      strokeWidth={1.5}
      strokeDasharray="4 3"
      ifOverflow="visible"
      label={{
        value: `Cambio de versión: ${c.etiqueta}`,
        position: "insideTopLeft",
        fontSize: 11,
        fill: "var(--foreground)",
      }}
    />
  ));
}
