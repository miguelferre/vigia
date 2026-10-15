/**
 * Tabla de lectura con paginación de servidor.
 *
 * Sobre `@tanstack/react-table/legacy` (API v8). El componente no
 * pagina en cliente: recibe `total`, `offset` y `limit` y avisa con
 * `onPageChange`; quien la usa vuelve a pedir a la API con esos parámetros.
 *
 * Opcionalmente cada fila puede desplegar un detalle (`renderExpandido`) y
 * resaltarse al llegar (`filaResaltada`), que es lo que necesitaba el diario. El dibujo de la fila está en
 * `DataTableFila.tsx`.
 */

import { useCallback, useId, useState } from "react";
import type { ReactNode } from "react";
import { FlexRender } from "@tanstack/react-table";
import { useLegacyTable, type LegacyColumnDef } from "@tanstack/react-table/legacy";
import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { useReducedMotion } from "motion/react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { DataTableFila } from "./DataTableFila";

export type { LegacyColumnDef };

export interface DataTableProps<T extends object> {
  data: T[];
  columns: LegacyColumnDef<T, unknown>[];
  /** Total de filas en el servidor; sin él no se muestra la paginación. */
  total?: number;
  offset?: number;
  limit?: number;
  onPageChange?: (offset: number) => void;
  cargando?: boolean;
  vacio?: ReactNode;
  onRowClick?: (fila: T) => void;
  className?: string;
  /** Etiqueta accesible de la tabla. */
  titulo?: string;
  /**
   * Detalle plegable de una fila. Si se pasa, la tabla añade una primera
   * columna con un chevron y, al abrirlo, una fila que ocupa todo el ancho
   * con lo que devuelva esta función. Devolver `null` para una fila concreta
   * la deja sin chevron. Pulsar el chevron no dispara `onRowClick`.
   */
  renderExpandido?: (fila: T) => ReactNode;
  /**
   * Clave estable de cada fila (por defecto, su índice). La expansión se
   * guarda por clave, así que con una clave del dominio (el `id` del backend)
   * la fila abierta sigue abierta aunque la lista se recargue o se reordene.
   */
  claveFila?: (fila: T) => string | number;
  /**
   * Filas recién llegadas (por SSE, normalmente): se marcan con
   * `data-recien="true"` y se realzan un momento con el color de acento.
   */
  filaResaltada?: (fila: T) => boolean;
}

export function DataTable<T extends object>({
  data,
  columns,
  total,
  offset = 0,
  limit = 50,
  onPageChange,
  cargando = false,
  vacio,
  onRowClick,
  className,
  titulo,
  renderExpandido,
  claveFila,
  filaResaltada,
}: DataTableProps<T>) {
  const table = useLegacyTable({ data, columns });
  const [abiertas, setAbiertas] = useState<ReadonlySet<string | number>>(() => new Set());
  const reducirMovimiento = useReducedMotion() ?? false;
  const idBase = useId();
  const alternar = useCallback((clave: string | number) => {
    setAbiertas((previas) => {
      const siguiente = new Set(previas);
      if (!siguiente.delete(clave)) siguiente.add(clave);
      return siguiente;
    });
  }, []);
  const hayColumnaChevron = renderExpandido !== undefined;
  const columnasTotales = columns.length + (hayColumnaChevron ? 1 : 0);
  const hayPaginacion = typeof total === "number" && total > limit && onPageChange !== undefined;
  const pagina = Math.floor(offset / Math.max(limit, 1)) + 1;
  const paginas = typeof total === "number" ? Math.max(1, Math.ceil(total / Math.max(limit, 1))) : 1;

  if (cargando) {
    return (
      <div className={cn("flex flex-col gap-2", className)} data-loading="true">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-3/4" />
      </div>
    );
  }

  if (data.length === 0) {
    // Si offset apunta a una pagina que ya no existe (el total encogio por
    // una invalidacion, un borrado o un cambio de filtro), la paginacion se
    // mantiene visible para que se pueda volver atras en vez de encallar.
    const puedeVolver = hayPaginacion && offset > 0;
    return (
      <div className={cn("flex flex-col gap-3", className)}>
        {vacio ?? <TablaVacia />}
        {puedeVolver ? (
          <div className="flex items-center justify-end">
            <Button
              size="sm"
              variant="outline"
              onClick={() => onPageChange(Math.max(0, offset - limit))}
            >
              <ChevronLeftIcon className="size-4" aria-hidden="true" />
              Volver a la página anterior
            </Button>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div className="relative overflow-x-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-sm" aria-label={titulo}>
          <thead className="bg-muted text-muted-foreground">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {hayColumnaChevron ? (
                  <th scope="col" className="w-8 px-2 py-2">
                    <span className="sr-only">Detalle</span>
                  </th>
                ) : null}
                {headerGroup.headers.map((header) => (
                  <th key={header.id} scope="col" className="px-3 py-2 text-left">
                    {header.isPlaceholder ? null : <FlexRender header={header} />}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row, indice) => {
              const clave = claveFila ? claveFila(row.original) : indice;
              return (
                <DataTableFila
                  key={clave}
                  fila={row}
                  columnas={columnasTotales}
                  expandido={renderExpandido ? renderExpandido(row.original) : undefined}
                  hayColumnaChevron={hayColumnaChevron}
                  abierto={abiertas.has(clave)}
                  onAlternar={() => alternar(clave)}
                  panelId={`${idBase}-panel-${clave}`}
                  resaltada={filaResaltada ? filaResaltada(row.original) : false}
                  reducirMovimiento={reducirMovimiento}
                  onRowClick={onRowClick}
                />
              );
            })}
          </tbody>
        </table>
      </div>
      {hayPaginacion ? (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {offset + 1}-{Math.min(offset + limit, total)} de {total}
          </span>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={offset <= 0}
              onClick={() => onPageChange(Math.max(0, offset - limit))}
            >
              <ChevronLeftIcon className="size-4" aria-hidden="true" />
              Anterior
            </Button>
            <span aria-live="polite">
              {pagina} / {paginas}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={offset + limit >= total}
              onClick={() => onPageChange(offset + limit)}
            >
              Siguiente
              <ChevronRightIcon className="size-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function TablaVacia() {
  return (
    <p className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
      No hay filas que mostrar.
    </p>
  );
}
