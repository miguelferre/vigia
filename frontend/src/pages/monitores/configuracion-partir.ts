/** `config` del monitor partido en campos simples y avanzado (JSON). Sale de
 * `configuracion.tsx` por el límite de 9 KB. */

import type { JsonObject } from "@/api/types";

import { esPrimitivo, type ConfigSimple } from "./tipos";

export function partirConfig(config: JsonObject | null): { simple: ConfigSimple; avanzado: JsonObject } {
  const simple: ConfigSimple = {};
  const avanzado: JsonObject = {};
  for (const [k, v] of Object.entries(config ?? {})) {
    if (esPrimitivo(v)) simple[k] = v;
    else avanzado[k] = v;
  }
  return { simple, avanzado };
}
