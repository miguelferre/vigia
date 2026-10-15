/**
 * Datos puros del stepper de nuevo dossier (construcción del cuerpo de
 * `POST /projects/{id}/dossiers` a partir de las respuestas por pregunta y
 * borrador en `localStorage` para no perder texto al navegar entre pasos.
 */

import type { DossierPlantillaFormulario } from "@/api/types";

export type PasoStepper = "system_card" | "usage_experience" | "document_inventory";

export const PASOS: readonly PasoStepper[] = ["system_card", "usage_experience", "document_inventory"];

export const CLAVE_CUERPO: Record<PasoStepper, "profile" | "experience" | "inventory"> = {
  system_card: "profile",
  usage_experience: "experience",
  document_inventory: "inventory",
};

export interface BorradorDossier {
  respuestas: Record<PasoStepper, Record<string, string>>;
  system_name: string;
  domain: string;
  include_telemetry: boolean;
}

export function borradorVacio(): BorradorDossier {
  return {
    respuestas: { system_card: {}, usage_experience: {}, document_inventory: {} },
    system_name: "",
    domain: "",
    include_telemetry: false,
  };
}

function claveStorage(projectId: number): string {
  return `vigia-dossier-borrador-${projectId}`;
}

export function leerBorrador(projectId: number): BorradorDossier {
  try {
    const bruto = window.localStorage.getItem(claveStorage(projectId));
    if (!bruto) return borradorVacio();
    const parseado = JSON.parse(bruto) as Partial<BorradorDossier>;
    return {
      ...borradorVacio(),
      ...parseado,
      respuestas: { ...borradorVacio().respuestas, ...(parseado.respuestas ?? {}) },
    };
  } catch {
    return borradorVacio();
  }
}

export function guardarBorrador(projectId: number, borrador: BorradorDossier): void {
  try {
    window.localStorage.setItem(claveStorage(projectId), JSON.stringify(borrador));
  } catch {
    // Almacenamiento no disponible (privado o bloqueado): el borrador solo
    // vive en memoria durante esta sesión de pestaña.
  }
}

export function limpiarBorrador(projectId: number): void {
  try {
    window.localStorage.removeItem(claveStorage(projectId));
  } catch {
    // Sin efecto si el almacenamiento no está disponible.
  }
}

/** Alguna respuesta no en blanco en al menos un formulario (regla del backend). */
export function tieneAlgunaRespuesta(borrador: BorradorDossier): boolean {
  return PASOS.some((paso) => Object.values(borrador.respuestas[paso]).some((v) => v.trim().length > 0));
}

/** Cuerpo de `POST /projects/{id}/dossiers`, sin respuestas en blanco. */
export function construirCuerpo(borrador: BorradorDossier, actor: { actor: string; role: string; motivo: string }) {
  const sinBlancos = (obj: Record<string, string>) =>
    Object.fromEntries(Object.entries(obj).filter(([, v]) => v.trim().length > 0));
  return {
    system_name: borrador.system_name.trim() || null,
    domain: borrador.domain.trim() || null,
    profile: sinBlancos(borrador.respuestas.system_card),
    experience: sinBlancos(borrador.respuestas.usage_experience),
    inventory: sinBlancos(borrador.respuestas.document_inventory),
    include_telemetry: borrador.include_telemetry,
    actor: actor.actor,
    role: actor.role,
    motivo: actor.motivo,
  };
}

export function agruparPorSeccion(
  formulario: DossierPlantillaFormulario | undefined,
): Map<string, DossierPlantillaFormulario["preguntas"]> {
  const grupos = new Map<string, DossierPlantillaFormulario["preguntas"]>();
  for (const pregunta of formulario?.preguntas ?? []) {
    const lista = grupos.get(pregunta.seccion) ?? [];
    lista.push(pregunta);
    grupos.set(pregunta.seccion, lista);
  }
  return grupos;
}

export const TITULO_PASO: Record<PasoStepper, string> = {
  system_card: "Perfil del sistema",
  usage_experience: "Experiencia de uso",
  document_inventory: "Inventario documental",
};
