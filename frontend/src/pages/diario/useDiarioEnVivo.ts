/**
 * Cola de eventos llegados en vivo por SSE que pasan los filtros actuales.
 *
 * `EventTarget` de `src/realtime/events.ts` reparte cada mensaje del diario;
 * aquí se filtra en cliente (los mismos criterios que la consulta paginada) y
 * se guarda una cola corta para insertarla arriba de la tabla. Quien la usa
 * descarta los que ya haya recibido la consulta paginada (por id).
 */

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { onVigiaEvent, pausarInvalidacionEventos } from "@/realtime/events";
import type { ActorKind, Event } from "@/api/types";

export interface FiltrosDiario {
  actorKind: ActorKind | null;
  objectType: string | null;
  correlationId: string;
  since: string;
  projectId: number | null;
}

const MAX_COLA = 50;

function pasaFiltros(
  evento: Event,
  actorKind: ActorKind | null,
  objectType: string | null,
  correlationId: string,
  since: string,
  projectId: number | null,
): boolean {
  if (actorKind && evento.actor_kind !== actorKind) return false;
  if (objectType && evento.object_type !== objectType) return false;
  if (correlationId && evento.correlation_id !== correlationId) return false;
  if (since && evento.ts < since) return false;
  if (projectId !== null && evento.project_id !== projectId) return false;
  return true;
}

export function useDiarioEnVivo(activo: boolean, filtros: FiltrosDiario): Event[] {
  const queryClient = useQueryClient();
  const [vivos, setVivos] = useState<Event[]>([]);
  const { actorKind, objectType, correlationId, since, projectId } = filtros;

  // Apagar el modo en vivo o cambiar de filtro vacía la cola: se resuelve
  // como estado derivado en el render (no dentro del efecto de suscripción),
  // para no encadenar renderizados.
  const clave = `${activo}|${actorKind}|${objectType}|${correlationId}|${since}|${projectId}`;
  const [claveAnterior, setClaveAnterior] = useState(clave);
  if (clave !== claveAnterior) {
    setClaveAnterior(clave);
    setVivos([]);
  }

  // "En vivo" apagado: pausa la invalidación automática de la raíz `events`
  // que hace `useEventStream` (base) para que la tabla paginada no se
  // refresque sola. Al encender o desmontar, reanuda y fuerza un refetch.
  useEffect(() => {
    if (!activo) {
      pausarInvalidacionEventos(true);
      return () => pausarInvalidacionEventos(false);
    }
    pausarInvalidacionEventos(false);
    void queryClient.invalidateQueries({ queryKey: ["events"] });
    const baja = onVigiaEvent((evento) => {
      if (!pasaFiltros(evento, actorKind, objectType, correlationId, since, projectId)) return;
      setVivos((prev) => [evento, ...prev].slice(0, MAX_COLA));
    });
    return () => {
      baja();
      pausarInvalidacionEventos(false);
    };
  }, [activo, actorKind, objectType, correlationId, since, projectId, queryClient]);

  return vivos;
}
