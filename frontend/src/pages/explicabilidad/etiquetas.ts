/** Etiquetas en español de los tipos de explicación (`ExplanationKind`). */

import type { ExplanationKind } from "@/api/types";

export const ETIQUETA_KIND: Record<ExplanationKind, string> = {
  global_permutation: "Global (permutación)",
  global_shap: "Global (SHAP)",
  local_lime: "Local (LIME)",
};

/**
 * La versión de una explicación se nombra como en la pantalla de
 * versiones (v1, v2), no por su identificador interno. Sin la versión en la
 * lista del proyecto (aún sin cargar), «no disponible»: nunca el id de la fila.
 */
export function etiquetaVersion(
  versiones: readonly { id: number | null; label: string }[] | undefined,
  versionId: number,
): string {
  return versiones?.find((v) => v.id === versionId)?.label ?? "no disponible";
}
