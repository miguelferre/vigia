/**
 * Barra flotante de acciones en lote (artboard `Alertas`): aparece
 * sobre la tabla al seleccionar una o más filas. El motivo se pide una sola
 * vez con `MotivoDialog`, desde `index.tsx` (que es quien conoce la
 * selección y llama a `POST /projects/{id}/alerts/bulk`); este componente
 * solo dispara los callbacks.
 */

import { DownloadIcon, XIcon } from "lucide-react";

export interface SeleccionAccionesProps {
  seleccionadas: number;
  onLimpiar: () => void;
  onPonerEnObservacion: () => void;
  onCerrarConMotivo: () => void;
  onExportar: () => void;
}

export function SeleccionAcciones({
  seleccionadas,
  onLimpiar,
  onPonerEnObservacion,
  onCerrarConMotivo,
  onExportar,
}: SeleccionAccionesProps) {
  if (seleccionadas === 0) return null;

  return (
    <div
      role="toolbar"
      aria-label="Acciones en lote"
      className="flex h-11 items-center gap-3 rounded-[10px] bg-foreground px-3.5 text-background shadow-pop"
    >
      <span className="text-md font-semibold whitespace-nowrap">
        {seleccionadas} seleccionada{seleccionadas === 1 ? "" : "s"}
      </span>
      <span aria-hidden="true" className="h-5 w-px bg-background/20" />
      <button type="button" className="text-md whitespace-nowrap" onClick={onPonerEnObservacion}>
        Poner en observación
      </button>
      <button type="button" className="text-md whitespace-nowrap" onClick={onCerrarConMotivo}>
        Cerrar con motivo
      </button>
      <button type="button" className="flex items-center gap-1 text-md whitespace-nowrap" onClick={onExportar}>
        <DownloadIcon className="size-3.5" aria-hidden="true" />
        Exportar
      </button>
      <button type="button" aria-label="Quitar selección" className="ml-0.5" onClick={onLimpiar}>
        <XIcon className="size-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}

export default SeleccionAcciones;
