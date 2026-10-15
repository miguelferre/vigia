/**
 * Hook del panel asistente: siembra con
 * `GET /events?actor_kind=agente`, se suscribe a `onVigiaEvent`, deduplica
 * por `id`, poda por ventana de minutos y agrupa por `correlation_id`.
 *
 * Sin `setState` dentro de un `useEffect` para derivar datos ni llamadas
 * impuras en el render (dos reglas del linter): el `useEffect` solo suscribe
 * el listener SSE, y la lista visible (siembra + buffer, podada y agrupada)
 * se deriva con `useMemo`. El «ahora» de la poda nunca se lee en el render:
 * viene de la `queryFn` de la siembra y de los dos callbacks que §6.8 nombra
 * (llegada de un evento y apertura del panel). El despliegue automático
 * también nace en el listener, no en un efecto.
 */

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { STALE_MS } from "@/api/queries";
import { onVigiaEvent } from "@/realtime/events";
import type { Event, ListResponse } from "@/api/types";

const CLAVE_VISTO = "vigia-asistente-visto";

export interface GrupoEventosAgente {
  correlation_id: string | null;
  eventos: Event[];
}

function leerVisto(): boolean {
  try {
    return sessionStorage.getItem(CLAVE_VISTO) === "1";
  } catch {
    return false;
  }
}

function escribirVisto(): void {
  try {
    sessionStorage.setItem(CLAVE_VISTO, "1");
  } catch {
    // sessionStorage no disponible (iframe sandbox, navegación privada): sin efecto
  }
}

/** Dedupe por `id` (los de `id: null` se distinguen por `ts` + `action`). */
function claveEvento(e: Event): string {
  return e.id !== null ? `id:${e.id}` : `ts:${e.ts}:${e.action}`;
}

function agrupar(eventos: Event[]): GrupoEventosAgente[] {
  const porCorrelacion = new Map<string, Event[]>();
  const grupos: GrupoEventosAgente[] = [];
  for (const e of eventos) {
    if (!e.correlation_id) {
      grupos.push({ correlation_id: null, eventos: [e] });
      continue;
    }
    const existente = porCorrelacion.get(e.correlation_id);
    if (existente) {
      existente.push(e);
    } else {
      const grupo: GrupoEventosAgente = { correlation_id: e.correlation_id, eventos: [e] };
      porCorrelacion.set(e.correlation_id, grupo.eventos);
      grupos.push(grupo);
    }
  }
  // Cada grupo llega con sus eventos en orden de aparición (más reciente
  // primero, porque la lista de entrada ya viene en ese orden); se ordenan
  // los grupos por el `ts` del evento más reciente.
  return grupos.sort((a, b) => (a.eventos[0].ts < b.eventos[0].ts ? 1 : -1));
}

export function useEventosAgente(ventanaMin = 30): {
  grupos: GrupoEventosAgente[];
  visto: boolean;
  abierto: boolean;
  setAbierto: (abierto: boolean) => void;
} {
  const { data } = useQuery({
    queryKey: ["events", "agente"],
    queryFn: async () => {
      const lista = await api.get<ListResponse<Event>>("/events", {
        params: { actor_kind: "agente", limit: 50 },
      });
      // El «ahora» de la poda se sella aquí, en un callback, no en el render.
      return { items: lista.items, pedidoEn: Date.now() };
    },
    staleTime: STALE_MS,
  });
  const semilla = useMemo(() => data?.items ?? [], [data]);

  const [buffer, setBuffer] = useState<Event[]>([]);
  const [visto, setVisto] = useState(leerVisto);
  const [abierto, setAbiertoEstado] = useState(false);
  // Momento de la última poda, escrito solo desde callbacks (§6.8: al llegar
  // un evento nuevo o al abrir el panel; sin `setInterval` aparte).
  const [podadoEn, setPodadoEn] = useState(0);

  useEffect(() => {
    return onVigiaEvent((evento) => {
      if (evento.actor_kind !== "agente") return;
      setBuffer((anterior) => [evento, ...anterior]);
      setPodadoEn(Date.now());
      // Despliegue automático, una sola vez por pestaña, con el primer evento
      // en vivo del carril `agente`. La siembra no lo dispara:
      // son acciones anteriores a esta sesión.
      if (!leerVisto()) {
        escribirVisto();
        setVisto(true);
        setAbiertoEstado(true);
      }
    });
  }, []);

  const setAbierto = (siguiente: boolean) => {
    setAbiertoEstado(siguiente);
    if (siguiente) setPodadoEn(Date.now());
  };

  const referencia = Math.max(podadoEn, data?.pedidoEn ?? 0);

  const grupos = useMemo(() => {
    // Sin referencia todavía (ni siembra ni eventos) no hay nada que podar.
    const limite = referencia > 0 ? referencia - ventanaMin * 60_000 : 0;
    const vistas = new Set<string>();
    const combinados: Event[] = [];
    for (const e of [...buffer, ...semilla]) {
      const clave = claveEvento(e);
      if (vistas.has(clave)) continue;
      vistas.add(clave);
      if (new Date(e.ts).getTime() < limite) continue;
      combinados.push(e);
    }
    combinados.sort((a, b) => (a.ts < b.ts ? 1 : -1));
    return agrupar(combinados);
  }, [buffer, semilla, ventanaMin, referencia]);

  return { grupos, visto, abierto, setAbierto };
}
