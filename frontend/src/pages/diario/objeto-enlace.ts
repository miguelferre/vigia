/**
 * Enlace del objeto de un evento, cuando existe una ruta para él.
 *
 * `alert` va a `/alertas/:id` y `batch` a `/datos/:batch`, ambas registradas
 * en `App.tsx`. `evaluation` no tiene ruta propia (solo está registrada
 * `/monitores/:tipo`): se enlaza ahí con `?evaluacion=id` cuando el evento
 * trae `monitor_type` en `before`/`after`, para que el carril de monitores lo
 * pueda leer si decide soportarlo.
 *
 * Las evaluaciones de alertas cruzadas (`monitor_type` `cross`) no tienen
 * monitor propio en `/monitores/:tipo`: su resultado se ve en `/alertas`, que
 * lista CX-1, CX-5 y CX-6 junto al resto. Si no hay forma de saber el tipo de
 * monitor, el objeto se muestra sin enlace.
 */

import { MONITOR_A_RUTA } from "@/lib/metrics";
import type { Event, JsonObject, MonitorType } from "@/api/types";

function monitorTypeDe(valor: JsonObject | null): MonitorType | null {
  if (valor === null || typeof valor !== "object" || Array.isArray(valor)) return null;
  const v = valor.monitor_type;
  return typeof v === "string" ? (v as MonitorType) : null;
}

export function enlaceObjeto(evento: Event): string | null {
  if (evento.object_id === null) return null;
  if (evento.object_type === "alert") return `/alertas/${evento.object_id}`;
  if (evento.object_type === "batch") return `/datos/${evento.object_id}`;
  if (evento.object_type === "evaluation") {
    const tipo = monitorTypeDe(evento.after) ?? monitorTypeDe(evento.before);
    if (tipo === "cross") return "/alertas";
    const ruta = tipo ? MONITOR_A_RUTA[tipo] : undefined;
    return ruta ? `/monitores/${ruta}?evaluacion=${evento.object_id}` : null;
  }
  return null;
}
