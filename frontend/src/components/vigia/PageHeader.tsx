/**
 * Cabecera de pantalla: título, descripción, migas opcionales y acciones.
 *
 * `marcaTiempo` pinta un chip aparte con icono de reloj y texto relativo
 * («Última evaluación hace 3 min», `lib/fechas.ts:formatoRelativo`) con la
 * fecha completa en el `title`; `descripcion` sigue siendo el hueco para
 * texto normal (no se toca su uso en las pantallas existentes).
 */

import type { ReactNode } from "react";
import { Link } from "react-router";
import { ClockIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { formatoFechaLarga, formatoRelativo } from "@/lib/fechas";

export interface Miga {
  etiqueta: string;
  a?: string;
}

export interface MarcaTiempoHeader {
  etiqueta: string;
  iso: string;
}

export interface PageHeaderProps {
  titulo: string;
  descripcion?: ReactNode;
  marcaTiempo?: MarcaTiempoHeader;
  migas?: Miga[];
  acciones?: ReactNode;
  className?: string;
}

export function PageHeader({
  titulo,
  descripcion,
  marcaTiempo,
  migas,
  acciones,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("flex flex-col gap-2", className)}>
      {migas && migas.length > 0 ? (
        <nav aria-label="Migas de pan" className="text-xs text-muted-foreground">
          <ol className="flex flex-wrap items-center gap-1">
            {migas.map((miga, i) => (
              <li key={`${miga.etiqueta}-${i}`} className="flex items-center gap-1">
                {i > 0 ? <span aria-hidden="true">/</span> : null}
                {miga.a ? (
                  <Link to={miga.a} className="hover:text-foreground hover:underline">
                    {miga.etiqueta}
                  </Link>
                ) : (
                  <span>{miga.etiqueta}</span>
                )}
              </li>
            ))}
          </ol>
        </nav>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="font-display text-2xl font-semibold tracking-[-0.15px]">{titulo}</h1>
          {descripcion ? (
            <div className="max-w-prose text-sm text-muted-foreground">{descripcion}</div>
          ) : null}
          {marcaTiempo ? (
            <span
              className="inline-flex w-fit items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-xs text-tertiary"
              title={`${marcaTiempo.etiqueta}: ${formatoFechaLarga(marcaTiempo.iso)}`}
            >
              <ClockIcon className="size-3.5" aria-hidden="true" />
              {marcaTiempo.etiqueta} {formatoRelativo(marcaTiempo.iso)}
            </span>
          ) : null}
        </div>
        {acciones ? <div className="flex flex-wrap items-center gap-2">{acciones}</div> : null}
      </div>
    </header>
  );
}
