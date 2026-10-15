/**
 * Lista del panel asistente: un bloque por grupo de `correlation_id`
 * (o un evento suelto), con el título del más reciente, el actor, la hora y
 * el enlace al objeto. Reutiliza `enlaceObjeto` de `pages/diario` (no
 * duplica el mapa `object_type` → ruta).
 */

import { Link } from "react-router";

import { horaCompleta } from "@/pages/diario/hilo";
import { enlaceObjeto } from "@/pages/diario/objeto-enlace";
import type { Event } from "@/api/types";

import type { GrupoEventosAgente } from "./useEventosAgente";

function enlaceGrupo(evento: Event): string | null {
  const propio = enlaceObjeto(evento);
  if (propio) return propio;
  if (evento.project_id !== null) return `/modelos/${evento.project_id}`;
  return null;
}

interface Props {
  grupos: GrupoEventosAgente[];
  onNavegar: () => void;
}

export function ListaEventosAgente({ grupos, onNavegar }: Props) {
  if (grupos.length === 0) {
    return <p className="text-sm text-tertiary">Ningún agente ha actuado en esta sesión.</p>;
  }

  return (
    <ul className="flex max-h-80 flex-col gap-3 overflow-y-auto">
      {grupos.map((grupo) => {
        const principal = grupo.eventos[0];
        const resto = grupo.eventos.slice(1);
        const enlace = enlaceGrupo(principal);
        const clave = grupo.correlation_id ?? `${principal.id ?? principal.ts}`;
        return (
          <li key={clave} className="flex flex-col gap-1 border-b border-border pb-2 last:border-b-0 last:pb-0">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-sm font-semibold">{principal.titulo}</span>
              <span className="shrink-0 text-xs text-tertiary">{horaCompleta(principal.ts)}</span>
            </div>
            <div className="flex items-center justify-between gap-2 text-xs text-tertiary">
              <span className="truncate">
                {principal.actor_id}
                {grupo.eventos.length > 1 ? ` · ${grupo.eventos.length} eventos` : ""}
              </span>
              {enlace ? (
                <Link to={enlace} onClick={onNavegar} className="font-semibold text-primary hover:underline">
                  Ver
                </Link>
              ) : null}
            </div>
            {resto.length > 0 ? (
              <ul className="flex flex-col gap-0.5 pl-3 text-xs text-tertiary">
                {resto.map((e) => (
                  <li key={e.id ?? `${e.ts}:${e.action}`} className="truncate">
                    {horaCompleta(e.ts)} · {e.titulo}
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
