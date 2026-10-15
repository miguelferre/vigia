/**
 * Protocolo por hitos de una alerta: los textos
 * (título, descripción, entregables, responsable, plazo) vienen ya resueltos
 * en `protocol_steps` de la propia alerta (`GET /alerts/{id}`, que en el
 * backend cae a la plantilla común cuando el monitor no define esa clave,
 * `services/protocol_steps._con_textos_del_protocolo`): ya no hace falta
 * pedir aparte `GET /content/protocolo-hitos` ni fusionar nada aquí.
 *
 * También deriva `hitoActual` (`hitoAccionableActual` más abajo): el
 * hito accionable más avanzado entre triaje, investigación y decisión, que
 * gobierna el botón principal de la alerta en `AlertaPanel.tsx` y
 * `detalle.tsx` (misma lógica, un solo sitio).
 *
 * La consulta de la alerta usa `qk.alert`, la misma clave que `detalle.tsx`
 * y el panel lateral: no duplica la petición, comparte la caché.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { AlertDetail } from "@/api/types";
import type { components } from "@/api/schema";
import { actorLegible } from "./etapa";

/** Los cinco hitos estándar; el protocolo admite hitos
 * extra con clave libre, así que `PasoProtocolo.key` es `string` y este tipo
 * solo nombra los que mueven la etapa. */
export type ProtocoloHitoEstandar = "deteccion" | "triaje" | "investigacion" | "decision" | "seguimiento";
export type ProtocoloHitoKey = string;
export type ProtocoloHitoStatus = components["schemas"]["ProtocolStepStatus"];

const HITOS_ACCIONABLES: ProtocoloHitoKey[] = ["triaje", "investigacion", "decision"];

/**
 * El siguiente hito accionable: el más avanzado que no esté
 * `pending`, de atrás adelante (`pending` se salta, `done` corta porque no
 * queda nada pendiente detrás, `current` es la respuesta). El
 * backend solo tiene un `current` a la vez y el triaje se admite desde
 * cualquier `status` no cerrado (`services/alerting.acknowledge`), así que
 * esta lectura coincide con «el primer `current`»; se mantiene de atrás
 * adelante como red por si el historial de una alerta antigua trae un hito
 * hecho por delante de otro sin hacer.
 */
function hitoAccionableActual(pasos: PasoProtocolo[]): PasoProtocolo | null {
  const accionables = pasos.filter((p) => HITOS_ACCIONABLES.includes(p.key));
  for (let i = accionables.length - 1; i >= 0; i -= 1) {
    const paso = accionables[i];
    if (paso.status === "pending") continue;
    return paso.status === "current" ? paso : null;
  }
  return null;
}

/** Un hito con su estado real, sus textos y quién lo hizo, listo para pintar. */
export interface PasoProtocolo {
  key: ProtocoloHitoKey;
  orden: number;
  titulo: string;
  descripcion: string;
  entregables: string[];
  status: ProtocoloHitoStatus;
  targetDate: string | null;
  responsable: string | null;
  plazoDias: number | null;
  /** Actor legible ("Vigía" para el motor) de quien hizo este hito, `null` sin entrada todavía. */
  hechoPor: string | null;
  hechoEn: string | null;
}

export interface ResultadoProtocoloHitos {
  pasos: PasoProtocolo[];
  /** El paso accionable más avanzado (`hitoAccionableActual`) entre triaje,
   * investigación y decisión: `null` sin hito accionable (seguimiento en
   * curso, o alerta cerrada). */
  hitoActual: PasoProtocolo | null;
  hechos: number;
  total: number;
  cargando: boolean;
}

export function useProtocoloHitos(alertId: number | null): ResultadoProtocoloHitos {
  const alerta = useQuery({
    queryKey: qk.alert(alertId),
    queryFn: () => api.get<AlertDetail>(`/alerts/${alertId}`),
    enabled: alertId !== null,
  });

  const historial = alerta.data?.history ?? [];
  // Detección: la entrada con `hito == "deteccion"`, o la primera del
  // historial (`from === null`) en una alerta de antes de esta sesión que
  // todavía no la llevara. Triaje/investigación/decisión: su propio `hito`;
  // seguimiento no tiene entrada propia (se deriva, nadie lo "hace").
  function quienHizo(key: ProtocoloHitoKey): { actor: string; ts: string } | null {
    const entrada =
      key === "seguimiento"
        ? undefined
        : key === "deteccion"
          ? historial.find((e) => e.hito === "deteccion" || e.from === null)
          : historial.find((e) => e.hito === key);
    return entrada ? { actor: actorLegible(entrada.actor), ts: entrada.ts } : null;
  }

  // El orden es el índice en la lista que devuelve el backend (los
  // hitos extra van intercalados donde el protocolo del monitor los guarda).
  const pasos: PasoProtocolo[] = (alerta.data?.protocol_steps ?? [])
    .map((paso, indice) => {
      const hecho = quienHizo(paso.key);
      return {
        key: paso.key,
        orden: indice + 1,
        titulo: paso.titulo,
        descripcion: paso.descripcion,
        entregables: paso.entregables,
        status: paso.status,
        targetDate: paso.target_date,
        responsable: paso.responsable,
        plazoDias: paso.plazo_dias,
        hechoPor: hecho?.actor ?? null,
        hechoEn: hecho?.ts ?? null,
      };
    })
    .sort((a, b) => a.orden - b.orden);

  // `total` no cuenta los hitos informativos (siempre "n de 5", nunca
  // "n de 6" con un hito extra intercalado); `hechos` ya los excluye porque
  // su `status` nunca es "done".
  const total = pasos.filter((p) => p.status !== "informativo").length;
  const hechos = pasos.filter((p) => p.status === "done").length;
  const hitoActual = hitoAccionableActual(pasos);
  const cargando = alertId !== null && alerta.isLoading;

  return { pasos, hitoActual, hechos, total, cargando };
}

export default useProtocoloHitos;
