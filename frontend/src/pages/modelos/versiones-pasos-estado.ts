/** Estado de los pasos de una versión nueva, partido de `versiones-pasos.tsx`. */

import type { ModelVersion } from "@/api/types";
import type { PasoVersion } from "./versiones-textos";

/** Estado de cada paso, derivado de los campos de la versión. */
export function estadoPasos(v: ModelVersion): Record<PasoVersion["clave"], boolean> {
  const congelada = v.frozen_at !== null;
  return {
    "linea-base": v.baseline_batch_id !== null || congelada,
    congelar: congelada,
    modelo: v.artifact_sha256 !== null,
    activar: v.is_active,
  };
}
