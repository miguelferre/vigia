/**
 * Ayuda del bloque «Registro de uso»: lee
 * `GET /api/content/registro-uso` (`registro-uso-ayuda.json`) y
 * trae los textos de reserva por si la consulta aún no ha llegado. Aparte de
 * `RegistroUso.tsx` para no pasar de 9 KB.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";
import type { ValorFavorable } from "@/api/types";

export type RegistroUsoAyuda = components["schemas"]["RegistroUsoAyuda"];

export function useRegistroUsoAyuda() {
  return useQuery({
    queryKey: ["content", "registro-uso"] as const,
    queryFn: () => api.get<RegistroUsoAyuda>("/content/registro-uso"),
    staleTime: Infinity,
  });
}

/** Frase de la decisión favorable, la misma que el backend publica en `/openapi.json` y en la ayuda. */
export const FRASE_D155_RESERVA =
  "refer (o 1) es la decisión favorable para la persona afectada, en el mismo sentido que la etiqueta favorable del modelo.";

export const PREGUNTA_FAVORABLE_RESERVA = "¿Qué valor del fichero es la decisión favorable para la persona?";

export const RESUMEN_RESERVA =
  "Diario de decisiones: fecha, decisión del profesional, salida del modelo y resultado real, una fila por " +
  "decisión. Las columnas opcionales son profesional, subgrupo y número de registro.";

export const OPCIONES_FAVORABLE: ValorFavorable[] = ["refer", "no-refer", "1", "0"];

/** Qué hacer cuando la comprobación de codificación no puede decidir. */
export const AYUDA_INCONCLUSO =
  "Si no se puede comprobar, elige el valor por el significado de la decisión en tu fichero y anótalo en el motivo.";
