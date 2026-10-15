/**
 * Tipo de dataset por defecto según las columnas del fichero.
 * Antes el selector «Tipo» se quedaba con el del lote anterior y había que
 * cambiarlo a mano. Con la plantilla del proyecto se busca por el nombre
 * exacto de sus columnas; sin ella, por nombres habituales. Solo es un valor
 * de partida: la persona puede cambiarlo.
 */

import type { DatasetKind } from "@/api/types";

const PISTA_PREDICCION = /(^|[_\s-])(pred|prediccion|predicción|prediction|prob|probabilidad|probability|score)/i;
const PISTA_ETIQUETA = /^(label|etiqueta|target|y|y_true|real|verdad|outcome|resultado)$|(^|[_\s-])(real|actual|true|verdad)([_\s-]|$)/i;

function deLaPlantilla(plantilla: Record<string, unknown> | null | undefined, campo: string): string | null {
  const v = plantilla?.[campo];
  return typeof v === "string" && v !== "" ? v : null;
}

/**
 * `combined` si trae predicción y etiqueta, `payload` si solo predicción,
 * `feedback` si solo etiqueta; `null` si no se puede decir (se deja el tipo
 * como está).
 */
export function tipoPorColumnas(
  columnas: readonly string[],
  plantilla?: Record<string, unknown> | null,
): DatasetKind | null {
  const colPred = deLaPlantilla(plantilla, "prediction_col");
  const colEtiqueta = deLaPlantilla(plantilla, "label_col");
  const tienePrediccion = columnas.some((c) => (colPred ? c === colPred : false) || PISTA_PREDICCION.test(c));
  const tieneEtiqueta = columnas.some((c) => (colEtiqueta ? c === colEtiqueta : false) || PISTA_ETIQUETA.test(c));
  if (tienePrediccion && tieneEtiqueta) return "combined";
  if (tienePrediccion) return "payload";
  if (tieneEtiqueta) return "feedback";
  return null;
}
