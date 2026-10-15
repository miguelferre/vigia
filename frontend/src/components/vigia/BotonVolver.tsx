/**
 * Botón «Volver» sobre `useVolver`. Las pantallas de
 * detalle (alerta, lote, monitor con `?evaluacion`) lo colocan; este
 * componente no decide cuándo mostrarse.
 */

import { ArrowLeftIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useVolver } from "@/hooks/useVolver";
import { cn } from "@/lib/utils";

export interface BotonVolverProps {
  /** Ruta padre si no hay historial dentro de la app. */
  rutaPadre: string;
  /** Nombre de esa ruta padre, para el `title` contextual. */
  etiquetaPadre?: string;
  className?: string;
}

export function BotonVolver({ rutaPadre, etiquetaPadre, className }: BotonVolverProps) {
  const { volver, etiqueta } = useVolver(rutaPadre, etiquetaPadre);
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className={cn("gap-2", className)}
      onClick={volver}
      title={etiqueta}
    >
      <ArrowLeftIcon className="size-4" aria-hidden="true" />
      Volver
    </Button>
  );
}
