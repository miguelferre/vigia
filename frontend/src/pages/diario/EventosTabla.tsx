/**
 * Tabla del diario, sobre `DataTable` (base): fila expandible
 * (`renderExpandido`), clave por id (`claveFila`) y realce de fila recién
 * llegada por SSE (`filaResaltada`). Envoltorio fino: define columnas y detalle,
 * el dibujo de fila y la expansión los da `DataTable`.
 */

import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DataTable, JsonView } from "@/components/vigia";
import { ETIQUETA_CARRIL, formatoFecha } from "@/lib/metrics";
import type { Event } from "@/api/types";
import { TOKEN_CARRIL, etiquetaObjeto } from "./etiquetas";
import { numeroLote } from "@/lib/fases";
import { enlaceObjeto } from "./objeto-enlace";

/** «Lote #3» con el número del lote (`seq`), no su `id`; sin el lote a mano, solo «Lote». Otros objetos: tipo y `id`. */
function textoObjeto(evento: Event, numeroDeLote: ReadonlyMap<number, number>): string {
  const tipo = etiquetaObjeto(evento.object_type);
  if (evento.object_id === null) return tipo;
  if (evento.object_type === "batch") {
    const seq = numeroDeLote.get(evento.object_id);
    return seq === undefined ? tipo : `${tipo} ${numeroLote(seq)}`;
  }
  return `${tipo} #${evento.object_id}`;
}

export interface EventosTablaProps {
  eventos: Event[];
  cargando: boolean;
  error?: boolean;
  mensajeDeError?: string | null;
  onReintentar?: () => void;
  recienLlegados: ReadonlySet<number>;
  onCorrelacionClick: (correlationId: string) => void;
  /** `id` de lote a su número (`seq`), de los lotes del proyecto del diario. */
  numeroDeLote?: ReadonlyMap<number, number>;
}

export function EventosTabla({
  eventos,
  cargando,
  error = false,
  mensajeDeError = null,
  onReintentar,
  recienLlegados,
  onCorrelacionClick,
  numeroDeLote = new Map<number, number>(),
}: EventosTablaProps) {
  if (cargando) {
    return (
      <div className="flex flex-col gap-2" data-loading="true">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-destructive/50 px-4 py-8 text-center text-sm">
        <p className="text-destructive">
          {mensajeDeError ?? "No se han podido cargar los eventos."}
        </p>
        {onReintentar ? (
          <Button type="button" variant="outline" size="sm" onClick={onReintentar}>
            Reintentar
          </Button>
        ) : null}
      </div>
    );
  }

  const columns: LegacyColumnDef<Event, unknown>[] = [
    {
      id: "fecha",
      header: "Fecha",
      accessorFn: (e) => e.ts,
      cell: (info) => (
        <span className="whitespace-nowrap text-xs">{formatoFecha(info.getValue() as string)}</span>
      ),
    },
    {
      id: "carril",
      header: "Carril",
      accessorFn: (e) => e.actor_kind,
      cell: (info) => {
        const carril = info.getValue() as Event["actor_kind"];
        return (
          <span
            className="inline-flex items-center rounded-full border px-2 py-0.5 text-xs"
            style={{ borderColor: `var(${TOKEN_CARRIL[carril]})` }}
          >
            {ETIQUETA_CARRIL[carril]}
          </span>
        );
      },
    },
    {
      id: "actor",
      header: "Actor",
      accessorFn: (e) => e,
      // El carril de al lado ya dice «Vigía» (`ETIQUETA_CARRIL.modelo`,
      // `lib/metrics.ts`); aquí `actor_id` solo aporta algo para humano y
      // agente (correo o identificador propio). Para el carril modelo
      // (`vigia.core 0.1.0`) la celda queda vacía: es dato técnico, no de
      // usuario.
      cell: (info) => {
        const evento = info.getValue() as Event;
        if (evento.actor_kind === "modelo") return <span className="text-xs text-muted-foreground">—</span>;
        return <span className="whitespace-nowrap">{evento.actor_id}</span>;
      },
    },
    {
      id: "accion",
      header: "Evento",
      accessorFn: (e) => e.titulo,
      cell: (info) => <span className="whitespace-nowrap">{info.getValue() as string}</span>,
    },
    {
      id: "objeto",
      header: "Objeto",
      accessorFn: (e) => e,
      cell: (info) => {
        const evento = info.getValue() as Event;
        const href = enlaceObjeto(evento);
        return href ? (
          <Link to={href} className="whitespace-nowrap underline-offset-2 hover:underline">
            {textoObjeto(evento, numeroDeLote)}
          </Link>
        ) : (
          <span className="whitespace-nowrap">{textoObjeto(evento, numeroDeLote)}</span>
        );
      },
    },
    {
      id: "correlacion",
      header: "Correlación",
      accessorFn: (e) => e.correlation_id,
      cell: (info) => {
        const correlationId = info.getValue() as string | null;
        if (!correlationId) return <span className="text-xs text-muted-foreground">—</span>;
        return (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onCorrelacionClick(correlationId);
            }}
            className="block max-w-40 truncate text-left text-xs underline-offset-2 hover:underline"
            title={correlationId}
          >
            {correlationId.slice(0, 8)}
          </button>
        );
      },
    },
  ];

  return (
    <DataTable
      data={eventos}
      columns={columns}
      cargando={cargando}
      titulo="Diario de eventos"
      vacio={
        <p className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
          No hay eventos con estos filtros.
        </p>
      }
      claveFila={(e) => e.id ?? `sin-id-${e.ts}`}
      filaResaltada={(e) => e.id !== null && recienLlegados.has(e.id)}
      renderExpandido={(evento) => (
        <div className="flex flex-col gap-2">
          <p className="font-mono text-xs text-muted-foreground">{evento.action}</p>
          <JsonView
            valor={{
              before: evento.before,
              after: evento.after,
              motivo: evento.motivo,
              correlation_id: evento.correlation_id,
              job_id: evento.job_id,
            }}
            abiertoHasta={2}
          />
        </div>
      )}
    />
  );
}
