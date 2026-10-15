/**
 * Informe HTML de la revisión en `<iframe sandbox>`: `GET /reviews/{id}/report`, con botón
 * para abrirlo en pestaña nueva.
 *
 * El informe lo dibuja Vigía en español y con los tokens del tema
 * personal incrustados (`human/informe_revision.py`). El iframe sigue en
 * `sandbox=""` (sin scripts ni mismo origen: el informe no los necesita, y
 * los enlaces internos `#rem-…` navegan dentro del propio documento), así que
 * no hereda la clase `.dark` de la app. El modo se pasa por la ruta
 * (`?modo=claro|oscuro`); sin él, el informe sigue al sistema.
 */

import { ExternalLinkIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { API_BASE } from "@/api/client";
import { useTheme } from "@/themes/theme";

export interface InformeProps {
  reviewId: number;
}

export function Informe({ reviewId }: InformeProps) {
  const { resolvedDark } = useTheme();
  const src = `${API_BASE}/reviews/${reviewId}/report?modo=${resolvedDark ? "oscuro" : "claro"}`;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" asChild>
          <a href={src} target="_blank" rel="noopener noreferrer">
            <ExternalLinkIcon className="size-4" aria-hidden="true" />
            Abrir en pestaña nueva
          </a>
        </Button>
      </div>
      <iframe
        sandbox=""
        src={src}
        title="Informe de la revisión"
        className="h-[70vh] min-h-[28rem] w-full rounded-lg border border-border bg-background"
      />
    </div>
  );
}
