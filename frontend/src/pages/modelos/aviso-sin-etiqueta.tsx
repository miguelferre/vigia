/**
 * Aviso neutro del paso de mapeo cuando un lote de
 * producción no trae columna de etiqueta. No es un error: el lote se ingiere
 * con la plantilla y lo que necesita la etiqueta espera a las etiquetas
 * tardías. La línea base sí la exige (el servidor responde 422). Aparte de
 * `mapeo-dataset.tsx` por tamaño (límite de 9 KB).
 */

import { InfoIcon } from "lucide-react";

import type { Dataset } from "@/api/types";

export const TEXTO_LOTE_SIN_ETIQUETA =
  "Este lote no trae columna de etiqueta. Se ingiere igual con el mapeo de la plantilla; " +
  "las medidas que necesitan la etiqueta esperan a las etiquetas tardías.";

/** ¿Es un lote de producción de predicciones al que le falta la etiqueta? */
export function esLoteSinEtiqueta(dataset: Pick<Dataset, "kind" | "role">, labelCol: string): boolean {
  return (dataset.kind === "combined" || dataset.kind === "payload") && dataset.role !== "baseline" && labelCol.trim() === "";
}

export function AvisoSinEtiqueta({ dataset, labelCol }: { dataset: Pick<Dataset, "kind" | "role">; labelCol: string }) {
  if (!esLoteSinEtiqueta(dataset, labelCol)) return null;
  return (
    <p
      data-testid="aviso-sin-etiqueta"
      role="note"
      className="inline-flex items-start gap-1.5 text-xs text-muted-foreground [overflow-wrap:anywhere]"
    >
      <InfoIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
      <span>{TEXTO_LOTE_SIN_ETIQUETA}</span>
    </p>
  );
}
