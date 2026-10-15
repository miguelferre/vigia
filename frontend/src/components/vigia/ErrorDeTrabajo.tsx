/**
 * Forma única de enseñar el error de un trabajo en segundo plano. El backend ya guarda en `job.error` un texto limpio en español
 * aquí solo se le pone delante qué estaba haciendo Vigía y se da un
 * texto por defecto si el trabajo no dejó detalle.
 */

import { cn } from "@/lib/utils";

export interface ErrorDeTrabajoProps {
  /** `job.error` tal como llega del backend; vacío o nulo usa `porDefecto`. */
  error: string | null | undefined;
  /** Qué hacía el trabajo, en infinitivo o con sustantivo: «La ingesta», «La evaluación». */
  accion?: string;
  /** Texto si el trabajo no dejó detalle. */
  porDefecto?: string;
  className?: string;
}

/** Texto plano del error de un trabajo, para `toast.error` y sitios sin JSX. */
export function textoErrorDeTrabajo(
  error: string | null | undefined,
  accion = "El trabajo",
  porDefecto = "ha fallado sin dejar detalle: vuelve a intentarlo",
): string {
  const detalle = (error ?? "").trim();
  return detalle ? `${accion} ha fallado: ${detalle}` : `${accion} ${porDefecto}.`;
}

export function ErrorDeTrabajo({ error, accion, porDefecto, className }: ErrorDeTrabajoProps) {
  return (
    <p role="alert" className={cn("text-sm text-destructive", className)}>
      {textoErrorDeTrabajo(error, accion, porDefecto)}
    </p>
  );
}
