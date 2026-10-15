/**
 * Icono ⓘ que enseña ayuda contextual: qué mide una métrica y, si la
 * hay, su fórmula. Sobre `components/ui/tooltip.tsx` (Radix), a diferencia de
 * `MetricLabel`, que usa un `title` nativo: aquí el disparador es accesible
 * por teclado (foco visible, `aria-label`) y el contenido puede llevar
 * varias líneas.
 *
 * Cada instancia lleva su propio `TooltipProvider`: no hay uno global en la
 * aplicación y anidar el de Radix por componente es soportado.
 */

import { InfoIcon } from "lucide-react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export interface InfoTooltipProps {
  /** Título de la ayuda, normalmente la etiqueta de la métrica o el concepto. */
  titulo: string;
  /** Qué mide, en una o dos frases. */
  queMide: string;
  /**
   * Cómo se lee el valor (sentido, escala), cuando lo hay: segundo párrafo
   * con el rótulo «Cómo se lee». `null` u
   * omitido cuando la entrada de `metricas-ayuda.json` no lo trae.
   */
  comoSeLee?: string | null;
  /** Fórmula o cálculo, cuando lo hay (por ejemplo `fairness_value = (rate_unpriv / rate_priv) x 100`). */
  formula?: string | null;
  className?: string;
}

export function InfoTooltip({ titulo, queMide, comoSeLee, formula, className }: InfoTooltipProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className={cn(
              "inline-flex size-4 items-center justify-center rounded-full text-muted-foreground",
              "hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              className,
            )}
            aria-label={`Qué mide ${titulo}`}
          >
            <InfoIcon className="size-3.5" aria-hidden="true" />
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-64 text-left">
          <p className="font-semibold">{titulo}</p>
          <p className="mt-1">{queMide}</p>
          {comoSeLee ? (
            <p className="mt-1">
              <span className="font-semibold">Cómo se lee: </span>
              {comoSeLee}
            </p>
          ) : null}
          {formula ? <code className="mt-1 block text-xs opacity-80">{formula}</code> : null}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
