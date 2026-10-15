/**
 * Línea de tiempo vertical del historial de una alerta
 * (habla en hitos, sin texto crudo del motor): un titular por
 * entrada, según su `hito` (detección, triaje, investigación, decisión) o,
 * si no trae hito (transición automática del motor, o entrada de antes de
 * esta sesión), según `from`/`to`. Un avatar por carril (Vigía o Usuario;
 * agente y sistema quedan listos) delante de cada entrada, la misma
 * forma que usa el panel lateral.
 *
 * El actor del motor firma como `"vigia.core <versión>"` (`app/events.py`):
 * nunca se enseña crudo, sale como «Vigía» (`actorLegible`). El
 * `motivo` de una entrada del motor es su propia razón interna (el cálculo
 * que cruzó el umbral, no una decisión humana): solo se enseña el motivo
 * debajo del titular cuando quien firma es una persona.
 */

import type { ComponentType } from "react";
import { Bot, Cpu, Settings, User } from "lucide-react";

import type { ActorKind, Alert, AlertDetail, AlertHistoryEntry } from "@/api/types";
import { numeroLote } from "@/lib/fases";
import { useFormatoMetrica } from "@/components/vigia/useFormatoMetrica";
import { ETIQUETA_MONITOR, formatoFecha } from "@/lib/metrics";
import { cn } from "@/lib/utils";
import { actorLegible } from "./etapa";

const TOKEN_CARRIL: Record<ActorKind, string> = {
  humano: "--chart-1",
  agente: "--chart-3",
  modelo: "--chart-2",
  sistema: "--muted-foreground",
};

const ICONO_CARRIL: Record<ActorKind, ComponentType<{ className?: string; strokeWidth?: number }>> = {
  humano: User,
  agente: Bot,
  modelo: Cpu,
  sistema: Settings,
};

/**
 * Carril de una entrada del historial: las entradas nuevas traen
 * `actor_kind` (`services/alerting.py`), que manda siempre que esté;
 * las de antes de este cambio no lo traen y se infieren por el prefijo del
 * actor, como antes (una acción del servidor MCP con `actor_kind: "agente"`
 * se pintaba como humana solo por no traer el prefijo `vigia.core`).
 *
 * `AlertHistoryEntry` (`api/schema.d.ts`, generado) todavía no declara el
 * campo: acceso tolerante hasta que se regenere.
 */
function carrilDeActor(entrada: AlertHistoryEntry): ActorKind {
  const actorKind = (entrada as { actor_kind?: ActorKind | null }).actor_kind;
  if (actorKind) return actorKind;
  if (entrada.actor.startsWith("vigia.core")) return "modelo";
  if (entrada.actor === "sistema") return "sistema";
  return "humano";
}

/** El `"(umbral ...)"` que ya trae `Alert.title` (`services/alerting._titulo`), tal cual. */
function textoUmbralDeTitulo(titulo: string): string {
  const m = titulo.match(/\(umbral[^)]*\)/);
  return m ? ` ${m[0]}` : "";
}

/**
 * Titular de una entrada, en hitos: nunca el actor crudo del motor
 * ni un "from -> to" de estados internos. Las entradas de antes de esta
 * sesión no traen `hito`: se derivan de `from`/`to` con las mismas reglas
 * que las transiciones automáticas.
 */
function mensajePrincipal(
  entrada: AlertHistoryEntry,
  alerta: Alert | AlertDetail,
  formato: (clave: string, valor: number | null | undefined) => string,
): string {
  const valorTxt = entrada.value !== null ? formato(alerta.metric_key, entrada.value) : "n/d";
  if (entrada.hito === "deteccion" || (!entrada.hito && entrada.from === null)) {
    const monitor = ETIQUETA_MONITOR[alerta.monitor_type].toLowerCase();
    return `Detectada por el monitor de ${monitor}: ${valorTxt}${textoUmbralDeTitulo(alerta.title)}`;
  }
  if (entrada.hito === "triaje") return `Triaje hecho por ${actorLegible(entrada.actor)}`;
  if (entrada.hito === "investigacion") return `Investigación registrada por ${actorLegible(entrada.actor)}`;
  if (entrada.hito === "decision") {
    return `Decisión registrada por ${actorLegible(entrada.actor)}${entrada.detalle ? `: ${entrada.detalle}` : ""}`;
  }
  if (entrada.to === "retirada") return `Retirada: ${entrada.motivo ?? "su lote de origen se borró"}`;
  if (entrada.to === "cerrada") return `Cerrada por ${actorLegible(entrada.actor)}`;
  if (entrada.to === "en_observacion") return "La métrica vuelve dentro del umbral: en seguimiento";
  if (entrada.from === "en_observacion" && entrada.to === "abierta") return "Vuelve a cruzar el umbral";
  if (entrada.from === entrada.to) return `Sigue fuera del umbral: ${valorTxt}`;
  // Único caso que puede quedar sin cubrir: un triaje de antes de esta
  // sesión, escrito sin `hito` (la propia `to === "reconocida"` ya lo dice).
  if (entrada.to === "reconocida") return `Triaje hecho por ${actorLegible(entrada.actor)}`;
  return `${entrada.from ?? "sin estado previo"} → ${entrada.to}`;
}

export interface HistorialProps {
  entradas: AlertHistoryEntry[] | null;
  alerta: Alert | AlertDetail;
}

export function Historial({ entradas, alerta }: HistorialProps) {
  const { formato } = useFormatoMetrica(alerta.project_id);
  if (!entradas || entradas.length === 0) {
    return <p className="text-md text-tertiary">Sin cambios de estado registrados.</p>;
  }
  const enOrden = [...entradas].reverse();

  return (
    <ol className="flex flex-col gap-3">
      {enOrden.map((entrada, i) => {
        const carril = carrilDeActor(entrada);
        const color = `var(${TOKEN_CARRIL[carril]})`;
        const Icono = ICONO_CARRIL[carril];
        // El motivo del motor es su propia razón interna, no una decisión
        // humana: solo se enseña cuando quien firma es una persona.
        const motivoHumano = carril !== "modelo" ? entrada.motivo : null;
        return (
          <li key={`${entrada.ts}-${i}`} className="flex gap-3">
            <span
              className="flex size-7 flex-none items-center justify-center rounded-full"
              style={{ background: `color-mix(in srgb, ${color} 16%, transparent)`, color }}
              aria-hidden="true"
            >
              <Icono className="size-3.5" strokeWidth={1.5} />
            </span>
            <div className={cn("flex flex-1 flex-col gap-0.5 pb-3", i < enOrden.length - 1 && "border-b border-border")}>
              <div className="flex flex-wrap items-center gap-2 text-md">
                <span className="font-semibold">{mensajePrincipal(entrada, alerta, formato)}</span>
                <span className="text-tertiary">{formatoFecha(entrada.ts)}</span>
              </div>
              {entrada.hito === "investigacion" && entrada.detalle ? (
                <p className="text-md">
                  <span className="font-medium">Hallazgos: </span>
                  {entrada.detalle}
                </p>
              ) : null}
              {/* Detalle del motor (p. ej. la variable máxima de una deriva):
                  los hitos de decisión e investigación ya lo llevan en su texto. */}
              {entrada.detalle && entrada.hito !== "investigacion" && entrada.hito !== "decision" ? (
                <p className="text-md text-muted-foreground">{entrada.detalle}</p>
              ) : null}
              {motivoHumano ? <p className="text-md">{motivoHumano}</p> : null}
              {entrada.evaluacion_borrada ? (
                <p className="text-md text-tertiary">
                  {entrada.batch_seq != null
                    ? `evaluación borrada con el lote ${numeroLote(entrada.batch_seq)}`
                    : "evaluación borrada con su lote"}
                </p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export default Historial;
