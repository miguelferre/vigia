/**
 * Paginación de la vista de lista del diario, aparte para que `index.tsx`
 * no supere 9 KB.
 */

import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

export interface PaginacionEventosProps {
  offset: number;
  total: number;
  limite: number;
  onChange: (offset: number) => void;
}

export function PaginacionEventos({ offset, total, limite, onChange }: PaginacionEventosProps) {
  if (total <= limite) return null;
  const pagina = Math.floor(offset / limite) + 1;
  const paginas = Math.max(1, Math.ceil(total / limite));
  return (
    <div className="flex items-center justify-between text-sm text-muted-foreground">
      <span>
        {offset + 1}-{Math.min(offset + limite, total)} de {total}
      </span>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={offset <= 0}
          onClick={() => onChange(Math.max(0, offset - limite))}
        >
          <ChevronLeftIcon className="size-4" aria-hidden="true" />
          Anterior
        </Button>
        <span aria-live="polite">
          {pagina} / {paginas}
        </span>
        <Button size="sm" variant="outline" disabled={offset + limite >= total} onClick={() => onChange(offset + limite)}>
          Siguiente
          <ChevronRightIcon className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

export default PaginacionEventos;
