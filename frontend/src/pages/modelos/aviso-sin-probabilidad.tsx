/**
 * Aviso del paso de mapeo del alta cuando no se elige columna
 * de probabilidad. Sin ella, `GET /projects/{id}/thresholds/proposal` no
 * propone AUC ni calibración. Aparte de `alta-datos.tsx` y de
 * `mapeo-dataset.tsx` por tamaño (límite de 9 KB).
 */

import { InfoIcon } from "lucide-react";

export const TEXTO_SIN_PROBABILIDAD =
  "sin columna de probabilidad, la propuesta de calidad no incluye AUC ni calibración";

export function AvisoSinProbabilidad({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <p
      data-testid="aviso-sin-probabilidad"
      role="note"
      className="inline-flex items-start gap-1.5 text-xs text-muted-foreground [overflow-wrap:anywhere]"
    >
      <InfoIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
      <span>{TEXTO_SIN_PROBABILIDAD.charAt(0).toUpperCase() + TEXTO_SIN_PROBABILIDAD.slice(1)}.</span>
    </p>
  );
}
