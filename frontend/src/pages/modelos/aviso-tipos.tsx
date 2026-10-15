/**
 * Aviso de un artefacto pickle o joblib subido antes de la
 * corrección de tipos (2026-09-29). El texto sale del backend
 * (`aviso_tipos` de la versión y de la explicación); aquí solo se pinta.
 */

import { AlertTriangleIcon } from "lucide-react";

export function AvisoTipos({ aviso }: { aviso: string | null | undefined }) {
  if (!aviso) return null;
  return (
    <p
      data-testid="aviso-tipos"
      role="note"
      className="inline-flex items-start gap-1.5 text-xs [overflow-wrap:anywhere]"
      style={{ color: "var(--state-warn)" }}
    >
      <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
      <span>{aviso.charAt(0).toUpperCase() + aviso.slice(1)}</span>
    </p>
  );
}
