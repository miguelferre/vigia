/**
 * Sesión de trabajo: actor, rol y proyecto activo.
 *
 * No es autenticación: Vigía es local y monousuario. El actor es el nombre que
 * queda escrito en el diario de eventos, así que se pide antes de cualquier
 * mutación (`MotivoDialog`) y se persiste entre recargas.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { setActorHeaders } from "@/api/client";
import type { Rol } from "@/api/types";
import { onVigiaEvent } from "@/realtime/events";

export const ACTOR_ANONIMO = "anonimo";
const STORAGE_KEY = "vigia-session";

export interface SessionState {
  actor: string;
  role: Rol;
  projectId: number | null;
  /**
   * Pseudónimo del profesional que mira su propia vista en `/capa-humana`
   * preferencia de quien mira, como el rol; sin endpoint. Solo
   * tiene sentido con `role === "clinico"`; `null` sin elegir.
   */
  clinicianPseudonym: string | null;
}

/**
 * Capacidades sujetas al rol (incluye el laboratorio y
 * los ajustes avanzados).
 */
export type Capacidad = "registros" | "mapeos" | "config" | "laboratorio" | "ajustes_avanzados";

/**
 * Reparto explícito de capacidades por rol. Se declara entero, sin negaciones
 * ni "todo menos", para que añadir una capacidad obligue a decidir qué rol la
 * tiene en vez de heredarla por descuido.
 */
export const PERMISOS: Record<Rol, ReadonlySet<Capacidad>> = {
  gestor: new Set<Capacidad>(["registros", "mapeos", "config", "laboratorio", "ajustes_avanzados"]),
  auditor: new Set<Capacidad>(["registros", "mapeos", "config", "laboratorio"]),
  clinico: new Set<Capacidad>(["registros", "mapeos", "config", "laboratorio"]),
  // Plan §11: "Rol cliente oculta laboratorio, mapeos, registros crudos y
  // ajustes avanzados". Conjunto vacío a propósito: cualquier capacidad
  // nueva exige decidir explícitamente si cliente la tiene, no heredarla.
  cliente: new Set<Capacidad>(),
};

export interface SessionContextValue extends SessionState {
  setActor: (actor: string) => void;
  setRole: (role: Rol) => void;
  setProjectId: (projectId: number | null) => void;
  setClinicianPseudonym: (pseudonym: string | null) => void;
  /** `true` si el actor sigue siendo el anónimo por defecto. */
  esAnonimo: boolean;
}

export const ROLES: readonly Rol[] = ["gestor", "clinico", "auditor", "cliente"];

// el valor interno `clinico` no cambia; la etiqueta es genérica
// («profesional»: quien usa el modelo y decide), porque la sanidad es el
// dominio de la demo, no del producto.
export const ETIQUETA_ROL: Record<Rol, string> = {
  gestor: "Gestor",
  clinico: "Profesional",
  auditor: "Auditor",
  cliente: "Cliente",
};

const POR_DEFECTO: SessionState = {
  actor: ACTOR_ANONIMO,
  role: "gestor",
  projectId: null,
  clinicianPseudonym: null,
};

const SessionContext = createContext<SessionContextValue | null>(null);

function leerAlmacenado(): SessionState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return POR_DEFECTO;
    const parsed = JSON.parse(raw) as Partial<SessionState>;
    return {
      actor: typeof parsed.actor === "string" && parsed.actor ? parsed.actor : ACTOR_ANONIMO,
      role: ROLES.includes(parsed.role as Rol) ? (parsed.role as Rol) : "gestor",
      projectId: typeof parsed.projectId === "number" ? parsed.projectId : null,
      clinicianPseudonym:
        typeof parsed.clinicianPseudonym === "string" && parsed.clinicianPseudonym
          ? parsed.clinicianPseudonym
          : null,
    };
  } catch {
    return POR_DEFECTO;
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<SessionState>(() => {
    const inicial = leerAlmacenado();
    // Sincrono: las queries que disparan los hijos al montar deben salir ya
    // con el actor y el rol persistidos, no con el valor por defecto de
    // src/api/client.ts (el useEffect de abajo corre despues de los hijos).
    setActorHeaders({ actor: inicial.actor, role: inicial.role });
    return inicial;
  });

  useEffect(() => {
    setActorHeaders({ actor: estado.actor, role: estado.role });
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(estado));
    } catch {
      // sin persistencia disponible: la sesión sigue viva en memoria
    }
  }, [estado]);

  // un `PATCH /settings` con `rol` (desde `/ajustes`, otra pestaña
  // o la CLI) llega por el bus como `ajuste.cambiado` con `after.rol`; se aplica
  // a la sesión abierta sin recargar. `onVigiaEvent` solo escucha el emisor:
  // el flujo SSE lo abre `AppShell` (`useEventStream`).
  useEffect(
    () =>
      onVigiaEvent((evento) => {
        if (evento.action !== "ajuste.cambiado") return;
        const rol = evento.after?.rol;
        if (typeof rol === "string" && ROLES.includes(rol as Rol)) {
          setEstado((s) => (s.role === rol ? s : { ...s, role: rol as Rol }));
        }
      }),
    [],
  );

  const setActor = useCallback((actor: string) => {
    setEstado((s) => ({ ...s, actor: actor.trim() || ACTOR_ANONIMO }));
  }, []);
  const setRole = useCallback((role: Rol) => setEstado((s) => ({ ...s, role })), []);
  const setProjectId = useCallback(
    (projectId: number | null) => setEstado((s) => ({ ...s, projectId })),
    [],
  );
  const setClinicianPseudonym = useCallback(
    (pseudonym: string | null) =>
      setEstado((s) => ({ ...s, clinicianPseudonym: pseudonym?.trim() || null })),
    [],
  );

  const value = useMemo<SessionContextValue>(
    () => ({
      ...estado,
      setActor,
      setRole,
      setProjectId,
      setClinicianPseudonym,
      esAnonimo: estado.actor === ACTOR_ANONIMO,
    }),
    [estado, setActor, setRole, setProjectId, setClinicianPseudonym],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession debe usarse dentro de SessionProvider");
  return ctx;
}

/** `true` si el rol de la sesión tiene la capacidad, según `PERMISOS`. */
export function useCan(cap: Capacidad): boolean {
  const { role } = useSession();
  return PERMISOS[role].has(cap);
}
