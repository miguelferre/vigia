/**
 * Una fila de `DataTable`: chevron de expansión, panel desplegado y realce de
 * la fila recién llegada.
 *
 * Vive aparte de `DataTable.tsx` solo para que ninguno de los dos pase de
 * 9 KB. El realce reproduce el de `src/pages/diario/EventosTabla.tsx`:
 * entrada con `motion` (anulada si el sistema pide menos movimiento), fondo
 * `--accent` que se desvanece en 1,5 s con `transition-colors` y el atributo
 * `data-recien` para que las pruebas puedan apuntar a la fila.
 */

import { Fragment } from "react";
import type { ReactNode } from "react";
import { FlexRender } from "@tanstack/react-table";
import type { LegacyRow } from "@tanstack/react-table/legacy";
import { ChevronDownIcon, ChevronRightIcon } from "lucide-react";
import { motion } from "motion/react";

import { cn } from "@/lib/utils";

export interface DataTableFilaProps<T extends object> {
  fila: LegacyRow<T>;
  /** Número total de columnas, incluida la del chevron. */
  columnas: number;
  /** Contenido del panel expandido; sin él la fila no es expandible. */
  expandido?: ReactNode;
  /** `true` si la tabla tiene columna de chevron (aunque esta fila no lo use). */
  hayColumnaChevron: boolean;
  abierto: boolean;
  onAlternar: () => void;
  /** `id` del `<tr>` del panel, para el `aria-controls` del chevron. */
  panelId: string;
  resaltada: boolean;
  reducirMovimiento: boolean;
  onRowClick?: (dato: T) => void;
}

export function DataTableFila<T extends object>({
  fila,
  columnas,
  expandido,
  hayColumnaChevron,
  abierto,
  onAlternar,
  panelId,
  resaltada,
  reducirMovimiento,
  onRowClick,
}: DataTableFilaProps<T>) {
  const expandible = expandido !== undefined && expandido !== null;
  return (
    <Fragment>
      <motion.tr
        layout
        initial={resaltada && !reducirMovimiento ? { opacity: 0, y: -10 } : false}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reducirMovimiento ? 0 : 0.35 }}
        data-recien={resaltada ? "true" : undefined}
        className={cn(
          "border-t border-border transition-colors duration-[1500ms] motion-reduce:transition-none",
          onRowClick ? "cursor-pointer hover:bg-muted" : "hover:bg-muted/60",
        )}
        style={resaltada ? { backgroundColor: "var(--accent)" } : undefined}
        onClick={onRowClick ? () => onRowClick(fila.original) : undefined}
      >
        {hayColumnaChevron ? (
          <td className="w-8 px-2 py-2 align-top">
            {expandible ? (
              <button
                type="button"
                // El chevron abre el detalle; no debe disparar onRowClick.
                onClick={(e) => {
                  e.stopPropagation();
                  onAlternar();
                }}
                aria-expanded={abierto}
                aria-controls={panelId}
                aria-label={abierto ? "Contraer detalle" : "Expandir detalle"}
                className="rounded hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                {abierto ? (
                  <ChevronDownIcon className="size-4" aria-hidden="true" />
                ) : (
                  <ChevronRightIcon className="size-4" aria-hidden="true" />
                )}
              </button>
            ) : null}
          </td>
        ) : null}
        {fila.getVisibleCells().map((celda) => (
          <td key={celda.id} className="px-3 py-2 align-top">
            <FlexRender cell={celda} />
          </td>
        ))}
      </motion.tr>
      {expandible && abierto ? (
        <tr id={panelId} className="border-t border-border bg-muted/30">
          <td colSpan={columnas} className="px-3 py-2">
            {expandido}
          </td>
        </tr>
      ) : null}
    </Fragment>
  );
}
