/**
 * Qué cambia en el paso «Datos» del alta según el tipo de tarea.
 * Despacha con `caps.favorables` y un `default` que asigna a `never`:
 * un valor nuevo de la capacidad hace fallar `tsc`. Aparte de `alta-datos.tsx`
 * por el límite de 9 KB.
 */

import type { CapacidadesTarea } from "@/lib/tipo-tarea";

interface Validez {
  labelCol: string;
  favorableLabel: string;
  multiclaseValido: boolean;
  regresionValido: boolean;
}

/** Binaria: un valor favorable; multiclase: columna de etiqueta y conjunto favorable; regresión: unidad y rango válidos. */
export function favorableValido(favorables: CapacidadesTarea["favorables"], v: Validez): boolean {
  switch (favorables) {
    case "uno":
      return v.favorableLabel.trim().length > 0;
    case "conjunto":
      return v.labelCol !== "" && v.multiclaseValido;
    case null:
      return v.regresionValido;
    default: {
      const _exhaustivo: never = favorables;
      throw new Error(`favorables no reconocido: ${String(_exhaustivo)}`);
    }
  }
}

/** Aviso de «sin probabilidad»: solo donde el modelo da probabilidades. */
export function sinProbabilidad(
  probabilidad: CapacidadesTarea["probabilidad"],
  v: { probabilityCol: string; multiclaseSinProbabilidad: boolean },
): boolean {
  switch (probabilidad) {
    case "escalar":
      return v.probabilityCol === "";
    case "vector":
      return v.multiclaseSinProbabilidad;
    case null:
      return false;
    default: {
      const _exhaustivo: never = probabilidad;
      throw new Error(`probabilidad no reconocida: ${String(_exhaustivo)}`);
    }
  }
}
