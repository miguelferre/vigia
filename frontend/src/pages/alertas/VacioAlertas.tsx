/**
 * Estado vacío de la tabla de `alertas/index.tsx` según la causa (sin
 * severidad elegida, error de filtro o sin resultados). Aparte para que ese
 * fichero quede por debajo de 9 KB.
 */

import { mensajeDeError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/vigia";

export interface VacioAlertasProps {
  sinSeveridades: boolean;
  error: boolean;
  errorDetalle: unknown;
  /** Vuelve a lanzar la consulta filtrada. */
  onReintentar?: () => void;
}

export function VacioAlertas({ sinSeveridades, error, errorDetalle, onReintentar }: VacioAlertasProps) {
  if (sinSeveridades) {
    return (
      <EmptyState titulo="Ninguna severidad seleccionada" descripcion="Elige al menos un chip de severidad para ver alertas." />
    );
  }
  if (error) {
    return (
      <EmptyState
        titulo="No se ha podido aplicar este filtro"
        descripcion={mensajeDeError(errorDetalle)}
        accion={
          onReintentar ? (
            <Button type="button" variant="outline" size="sm" onClick={onReintentar}>
              Reintentar
            </Button>
          ) : undefined
        }
      />
    );
  }
  return (
    <EmptyState titulo="No hay alertas con estos filtros" descripcion="Cambia los filtros, el monitor o la búsqueda para ver más alertas." />
  );
}

export default VacioAlertas;
