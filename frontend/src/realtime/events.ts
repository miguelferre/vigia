/**
 * Flujo SSE del diario y su invalidación de caché.
 *
 * Un solo `EventSource` sobre `/api/events/stream` para toda la app. Cada
 * mensaje `{"type":"event","event":{...}}` se reemite en un `EventTarget`
 * interno (las pantallas se suscriben con `onVigiaEvent`) y se traduce a
 * invalidaciones de React Query por `object_type`. Los `heartbeat` del backend
 * llegan como evento SSE con nombre propio y no se escuchan.
 */

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { API_BASE } from "@/api/client";
import { RAICES_POR_OBJETO } from "@/api/queries";
import type { Event as EventoDiario } from "@/api/types";

export type EstadoConexion = "conectando" | "conectado" | "desconectado";

/** Mensaje del bus del backend (`app/bus.py`). */
export type MensajeBus =
  | { type: "event"; event: EventoDiario }
  | { type: "job"; job_id: number; status: string; progress: number; message: string };

const RETARDO_BASE_MS = 1000;
const RETARDO_MAXIMO_MS = 15000;

const emisor = new EventTarget();

let invalidacionEventosPausada = false;

/**
 * Pausa (o reanuda) la invalidación automática de la raíz `["events"]` al
 * llegar un evento por SSE. Lo usa el diario cuando "En vivo" está apagado:
 * los eventos siguen emitiéndose por `onVigiaEvent` y las demás raíces se
 * siguen invalidando por `object_type`. Quien pausa debe reanudar al desmontar.
 */
export function pausarInvalidacionEventos(pausa: boolean): void {
  invalidacionEventosPausada = pausa;
}

/** Escucha los eventos del diario que llegan por SSE. Devuelve la baja. */
export function onVigiaEvent(fn: (evento: EventoDiario) => void): () => void {
  const listener = (e: Event) => fn((e as CustomEvent<EventoDiario>).detail);
  emisor.addEventListener("vigia:event", listener);
  return () => emisor.removeEventListener("vigia:event", listener);
}

/** Escucha los avisos de trabajos que llegan por SSE. Devuelve la baja. */
export function onVigiaJob(fn: (mensaje: Extract<MensajeBus, { type: "job" }>) => void): () => void {
  const listener = (e: Event) =>
    fn((e as CustomEvent<Extract<MensajeBus, { type: "job" }>>).detail);
  emisor.addEventListener("vigia:job", listener);
  return () => emisor.removeEventListener("vigia:job", listener);
}

function parsear(data: string): MensajeBus | null {
  if (!data) return null;
  try {
    const msg = JSON.parse(data) as Partial<MensajeBus>;
    if (msg && (msg.type === "event" || msg.type === "job")) return msg as MensajeBus;
  } catch {
    // mensaje ilegible: se descarta sin romper el flujo
  }
  return null;
}

/**
 * Conecta el flujo global y devuelve el estado de la conexión para el
 * indicador de la cabecera. Se monta una sola vez, en `AppShell`.
 */
export function useEventStream(): { estado: EstadoConexion; ultimoEvento: EventoDiario | null } {
  const queryClient = useQueryClient();
  const [estado, setEstado] = useState<EstadoConexion>("conectando");
  const [ultimoEvento, setUltimoEvento] = useState<EventoDiario | null>(null);

  useEffect(() => {
    let fuente: EventSource | null = null;
    let temporizador: ReturnType<typeof setTimeout> | null = null;
    let intentos = 0;
    let vivo = true;

    const invalidar = (raices: readonly string[]) => {
      for (const raiz of raices) {
        void queryClient.invalidateQueries({ queryKey: [raiz] });
      }
    };

    const alMensaje = (data: string) => {
      const msg = parsear(data);
      if (msg === null) return;
      if (msg.type === "job") {
        emisor.dispatchEvent(new CustomEvent("vigia:job", { detail: msg }));
        invalidar(["jobs"]);
        return;
      }
      const evento = msg.event;
      setUltimoEvento(evento);
      emisor.dispatchEvent(new CustomEvent("vigia:event", { detail: evento }));
      if (!invalidacionEventosPausada) invalidar(["events"]);
      invalidar(RAICES_POR_OBJETO[evento.object_type] ?? []);
    };

    const conectar = () => {
      if (!vivo) return;
      setEstado(intentos === 0 ? "conectando" : "desconectado");
      fuente = new EventSource(`${API_BASE}/events/stream`);
      fuente.onopen = () => {
        intentos = 0;
        setEstado("conectado");
      };
      // El backend nombra los eventos por `type`; `message` cubre el caso sin nombre.
      fuente.addEventListener("event", (e) => alMensaje((e as MessageEvent<string>).data));
      fuente.addEventListener("job", (e) => alMensaje((e as MessageEvent<string>).data));
      fuente.onmessage = (e) => alMensaje(e.data);
      fuente.onerror = () => {
        fuente?.close();
        fuente = null;
        if (!vivo) return;
        setEstado("desconectado");
        const espera = Math.min(RETARDO_BASE_MS * 2 ** intentos, RETARDO_MAXIMO_MS);
        intentos += 1;
        temporizador = setTimeout(conectar, espera);
      };
    };

    conectar();
    return () => {
      vivo = false;
      if (temporizador !== null) clearTimeout(temporizador);
      fuente?.close();
    };
  }, [queryClient]);

  return { estado, ultimoEvento };
}
