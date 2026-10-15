/**
 * Aviso del filtro de modelo del diario. El diario entra
 * filtrado al modelo de la sesión y, con dos modelos, el otro queda oculto sin
 * decirlo. Mientras el filtro está puesto, esta línea dice a qué modelo
 * filtra y lo quita con un clic.
 */

import { Button } from "@/components/ui/button";

export function AvisoFiltroProyecto({ proyectoNombre, onQuitar }: { proyectoNombre: string; onQuitar: () => void }) {
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground" data-testid="aviso-filtro-proyecto">
      <span>
        Solo se ven los eventos de «{proyectoNombre}». Los de los demás modelos están ocultos.
      </span>
      <Button type="button" variant="outline" size="sm" onClick={onQuitar}>
        Ver todos los modelos
      </Button>
    </p>
  );
}
