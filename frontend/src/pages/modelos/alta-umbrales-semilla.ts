/**
 * Semilla de las ediciones del paso «Umbrales» (partida de `alta-umbrales.tsx`
 * por tamaño). Una fila con propuesta nace en «Aceptar propuesta»
 * (`linea_base`). Sin propuesta (`value` nulo) no hay nada que aceptar.
 * La equidad de multiclase con conjunto favorable y la de
 * regresión con rango traen propuesta desde la línea base, igual que la
 * binaria; ya no hay filas que sean solo el valor actual del monitor.
 */

import type { PropuestaUmbral, ThresholdsProposal } from "@/api/queries-alta";
import type { MonitorType } from "@/api/types";
import { clave, type Ediciones } from "./alta-umbrales-guardar";
import type { EdicionUmbral } from "./alta-umbrales-fila";

export function semillaEdiciones(propuesta: ThresholdsProposal): Ediciones {
  const siguiente: Ediciones = {};
  for (const m of propuesta.monitors) {
    for (const p of m.propuestas) {
      if (p.value === null) continue;
      siguiente[clave(m.monitor_type, p)] = { origen: "linea_base", value: String(p.value), nota: "" };
    }
  }
  return siguiente;
}

/** La edición de una fila: la sembrada, o «Mantener el actual» si no hay propuesta que aceptar. */
export function edicionDeFila(
  ediciones: Ediciones,
  tipoMonitor: MonitorType,
  p: PropuestaUmbral,
): EdicionUmbral {
  const sembrada = ediciones[clave(tipoMonitor, p)];
  if (sembrada) return sembrada;
  return p.value === null
    ? { origen: "fabrica", value: String(p.umbral_actual ?? ""), nota: "" }
    : { origen: "linea_base", value: "", nota: "" };
}
