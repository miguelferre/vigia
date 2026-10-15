/**
 * Estado de los umbrales de la hoja «Configurar monitor» (partido de
 * `configuracion.tsx` por tamaño). Guarda los umbrales al abrir (`iniciales`)
 * junto a los editados: una fila cuyo valor cambia pasa a origen de persona y
 * pide su nota; una fila sin cambio conserva su origen y su nota.
 */

import { useState } from "react";

import type { ThresholdOrigen } from "@/api/queries-alta";
import type { Monitor } from "@/api/types";

import { extraerUmbrales, type ThresholdEntry } from "./tipos";
import { faltaNotaDeUmbral, umbralCambiado, umbralEditado } from "./umbrales-efectivos";

export const AVISO_FALTA_NOTA_UMBRAL =
  "Falta la nota de un umbral que has cambiado: escríbela en su fila antes de guardar.";

export function useUmbralesEditables(monitor: Monitor) {
  const [iniciales, setIniciales] = useState<ThresholdEntry[]>(() => extraerUmbrales(monitor.thresholds));
  const [editados, setUmbrales] = useState<ThresholdEntry[]>(iniciales);
  // Con dos o más umbrales cambiados, un solo origen y una sola nota para el conjunto.
  const [conjunto, setConjunto] = useState<{ origen?: ThresholdOrigen; nota?: string }>({});
  const nCambiados = editados.filter((u, i) => umbralCambiado(u, iniciales[i])).length;
  const enConjunto = nCambiados >= 2;
  const primero = editados.find((u, i) => umbralCambiado(u, iniciales[i]));
  const origenConjunto = conjunto.origen ?? (primero?.origen as ThresholdOrigen | undefined) ?? "criterio_clinico";
  const notaConjunto = conjunto.nota ?? primero?.nota ?? "";
  const umbrales = !enConjunto
    ? editados
    : editados.map((u, i) =>
        umbralCambiado(u, iniciales[i]) ? { ...u, origen: origenConjunto, nota: notaConjunto } : u,
      );

  const sobre = (idx: number, cambio: (u: ThresholdEntry) => ThresholdEntry) =>
    setUmbrales((prev) => prev.map((u, i) => (i === idx ? cambio(u) : u)));

  return {
    umbrales,
    iniciales,
    /** Al reabrir la hoja: vuelve a los umbrales guardados del monitor. */
    reabrir: () => {
      const guardados = extraerUmbrales(monitor.thresholds);
      setIniciales(guardados);
      setUmbrales(guardados);
      setConjunto({});
    },
    cambiar: (idx: number, valor: number) => sobre(idx, (u) => umbralEditado(u, valor, iniciales[idx])),
    cambiarOrigen: (idx: number, origen: ThresholdOrigen) => sobre(idx, (u) => ({ ...u, origen })),
    cambiarNota: (idx: number, nota: string) => sobre(idx, (u) => ({ ...u, nota })),
    faltaNota: faltaNotaDeUmbral(umbrales, iniciales),
    enConjunto,
    nCambiados,
    origenConjunto,
    notaConjunto,
    cambiarConjunto: (cambio: { origen?: ThresholdOrigen; nota?: string }) => setConjunto((c) => ({ ...c, ...cambio })),
  };
}
