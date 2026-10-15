/**
 * Texto legible de un error de la API en el asistente de subida:
 * el 422 de `PUT /datasets/{id}/mapping` llega como texto, como lista de
 * errores de validación o como objeto con `message`; en todos los casos se
 * enseña una frase, nunca «error 422 de la API».
 */

import { ApiError, detalleATexto } from "@/api/client";
import type { JsonValue } from "@/api/types";

function textoDeObjeto(detail: JsonValue): string | null {
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return null;
  for (const clave of ["message", "detail", "msg", "motivo"]) {
    const v = detail[clave];
    if (typeof v === "string" && v.length > 0) return v;
  }
  return null;
}

export function textoErrorMapeo(error: unknown): string {
  if (error instanceof ApiError) {
    const deObjeto = textoDeObjeto(error.detail);
    if (deObjeto) return deObjeto;
    const texto = detalleATexto(error.detail, error.status);
    return texto;
  }
  return error instanceof Error ? error.message : "No se ha podido guardar el mapeo.";
}

/** Filas de la vista previa del servidor como texto, para sumarlas a la muestra del navegador. */
export function filasComoTexto(preview: unknown): Record<string, string>[] {
  if (!Array.isArray(preview)) return [];
  return preview
    .filter((f): f is Record<string, unknown> => !!f && typeof f === "object" && !Array.isArray(f))
    .map((f) =>
      Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === null || v === undefined ? "" : String(v)])),
    );
}
