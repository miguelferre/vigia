/**
 * Columnas de la tabla de `alertas/index.tsx` (artboard `Alertas`),
 * separadas para que el fichero de la pantalla quede por debajo de 9 KB.
 *
 * La casilla de selección va en la primera columna: la franja rayada de las
 * filas seleccionadas se pinta ahí, con un `div` que cancela el
 * `padding` de la celda (`DataTableFila.tsx` no se toca) para que el degradado llegue al borde izquierdo
 * de la tabla.
 */

import { MoreHorizontalIcon } from "lucide-react";
import { Link } from "react-router";

import type { Alert, Batch, Measurement } from "@/api/types";
import { StateBadge } from "@/components/vigia";
import type { LegacyColumnDef } from "@/components/vigia";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { ETIQUETA_MONITOR, formatoNumero } from "@/lib/metrics";
import { formatoRelativo } from "@/lib/fechas";
import { etiquetaFase, numeroLote, sinRepetirLote } from "@/lib/fases";
import { CasillaSeleccion, type EstadoCasilla } from "./CasillaSeleccion";
import { estadoDeSeveridad, etiquetaSeveridad } from "./severidad";
import { etiquetaEtapa } from "./etapa";
import { esRetirada } from "./alertas-utils";

/**
 * Umbral en texto corto ("umbral ≥ 0,600" / "umbral ≤ 0,150"), como en el
 * artboard. `Alert` no trae el umbral (vive en la medida de la evaluación,
 * no en la fila): `index.tsx` ya pide las evaluaciones de las alertas
 * visibles para la columna "Lote", así que se reutiliza esa misma petición
 * en vez de una de más por fila.
 */
function textoUmbral(m: Measurement | undefined, formato: FormatoValor): string | null {
  if (!m) return null;
  if (m.threshold_low !== null) return `umbral ≥ ${formato(m.metric_key, m.threshold_low)}`;
  if (m.threshold_high !== null) return `umbral ≤ ${formato(m.metric_key, m.threshold_high)}`;
  return null;
}

/** Formato de un valor de métrica con la unidad del proyecto; el de siempre en clasificación. */
type FormatoValor = (clave: string, valor: number | null | undefined) => string;
const FORMATO_POR_DEFECTO: FormatoValor = (_clave, valor) => formatoNumero(valor);

export interface ColumnasAlertasOpciones {
  loteDeAlerta: (alerta: Alert) => Batch | null;
  /** Nombre del fichero del lote de origen, si la lista de lotes lo trae. */
  ficheroDeAlerta: (alerta: Alert) => string | null;
  medidaDeAlerta: (alerta: Alert) => Measurement | undefined;
  seleccionadas: ReadonlySet<number>;
  onToggleSeleccion: (id: number) => void;
  /** Todas o ninguna: la cabecera decide su propio estado con `seleccionadas.size` sobre las filas visibles. */
  onToggleTodas: () => void;
  onAbrirPanel: (id: number) => void;
  onCerrarConMotivo: (alerta: Alert) => void;
  /** Formato del valor y del umbral con la unidad del proyecto (`useFormatoMetrica`). */
  formato?: FormatoValor;
}

export function columnasAlertas({
  loteDeAlerta,
  ficheroDeAlerta,
  medidaDeAlerta,
  seleccionadas,
  onToggleSeleccion,
  onToggleTodas,
  onAbrirPanel,
  onCerrarConMotivo,
  formato = FORMATO_POR_DEFECTO,
}: ColumnasAlertasOpciones): LegacyColumnDef<Alert, unknown>[] {
  return [
    {
      id: "seleccion",
      header: ({ table }) => {
        const filas = table.getRowModel().rows.map((r) => r.original);
        if (filas.length > 0 && filas.every(esRetirada)) return null;
        const marcadas = filas.filter((f) => f.id !== null && seleccionadas.has(f.id)).length;
        const estado: EstadoCasilla = marcadas === 0 ? "vacia" : marcadas === filas.length ? "llena" : "parcial";
        return (
          <CasillaSeleccion estado={estado} rayada={false} onToggle={onToggleTodas} etiqueta="Seleccionar todas las filas visibles" />
        );
      },
      cell: ({ row }) => {
        const id = row.original.id;
        if (id === null || esRetirada(row.original)) return null;
        const marcada = seleccionadas.has(id);
        return (
          <CasillaSeleccion
            estado={marcada ? "llena" : "vacia"}
            rayada={marcada}
            onToggle={() => onToggleSeleccion(id)}
            etiqueta={`Seleccionar alerta ${row.original.title}`}
          />
        );
      },
    },
    {
      id: "severidad",
      header: "Severidad",
      cell: ({ row }) => (
        <StateBadge
          estado={estadoDeSeveridad(row.original.severity)}
          texto={etiquetaSeveridad(row.original.severity)}
          size="sm"
        />
      ),
    },
    {
      id: "titulo",
      header: "Alerta",
      cell: ({ row }) => {
        const a = row.original;
        // El monitor "cross" (CX-1/5/6) ya escribe el valor y el umbral
        // dentro del propio título (`vigia.human.cross_alerts`): repetirlos
        // debajo duplicaría la misma cifra dos veces.
        if (a.monitor_type === "cross") {
          return <span className="font-semibold">{a.title}</span>;
        }
        const m = medidaDeAlerta(a);
        return (
          <div className="flex flex-col gap-0.5">
            <span className="font-semibold">{a.title}</span>
            <span className="text-md text-tertiary tabular-nums">
              {formato(a.metric_key, a.last_value)}
              {textoUmbral(m, formato) ? ` · ${textoUmbral(m, formato)}` : ""}
            </span>
          </div>
        );
      },
    },
    {
      id: "monitor",
      header: "Monitor",
      cell: ({ row }) => <span>{ETIQUETA_MONITOR[row.original.monitor_type]}</span>,
    },
    {
      id: "lote",
      header: "Lote",
      cell: ({ row }) => {
        const a = row.original;
        const lote = loteDeAlerta(a);
        // El lote de origen (donde se abrió) va primero; el de la
        // última evaluación solo si es otro.
        const seqUltimo = a.batch_seq ?? lote?.seq ?? null;
        const faseUltimo = a.batch_phase_label ?? lote?.phase_label ?? null;
        // Origen con id pero sin número: su lote se borró.
        const origenBorrado = a.origin_batch_id !== null && a.origin_batch_seq === null;
        const seq = a.origin_batch_seq ?? seqUltimo;
        const fase = a.origin_batch_seq !== null ? a.origin_phase_label : faseUltimo;
        if (seq === null && !origenBorrado) return <span className="text-tertiary">n/d</span>;
        const otroUltimo =
          seqUltimo !== null && (origenBorrado || (a.origin_batch_seq !== null && seqUltimo !== a.origin_batch_seq));
        // El nombre del fichero va aparte, salvo que repita la fase de la línea de arriba.
        const fichero = sinRepetirLote(ficheroDeAlerta(a), etiquetaFase(fase));
        return (
          <div className="flex flex-col">
            <span title="El número cuenta la línea base como lote 1">
              {origenBorrado ? "Lote borrado" : `${numeroLote(seq)}${etiquetaFase(fase) ? ` · ${etiquetaFase(fase)}` : ""}`}
            </span>
            {!origenBorrado && fichero ? <span className="text-xs text-tertiary">{fichero}</span> : null}
            {otroUltimo ? (
              <span className="text-xs text-tertiary">
                último {numeroLote(seqUltimo)}
                {lote?.dataset_name ? ` · ${lote.dataset_name}` : ""}
              </span>
            ) : null}
          </div>
        );
      },
    },
    {
      id: "estado",
      header: "Estado",
      cell: ({ row }) => (
        <div className="flex flex-col">
          <span className="text-md">{etiquetaEtapa(row.original)}</span>
          {esRetirada(row.original) && row.original.retired_reason ? (
            <span className="text-xs text-tertiary">{row.original.retired_reason}</span>
          ) : null}
        </div>
      ),
    },
    {
      id: "actualizado",
      header: "Actualizado",
      cell: ({ row }) => (
        <span className="text-tertiary" title={row.original.updated_at}>
          {formatoRelativo(row.original.updated_at)}
        </span>
      ),
    },
    {
      id: "acciones",
      header: () => <span className="sr-only">Acciones</span>,
      cell: ({ row }) => {
        const a = row.original;
        if (a.id === null) return null;
        return (
          <div className="flex items-center justify-end gap-1">
          {/* Acceso directo a la página de la alerta sin pasar por «Ver protocolo». */}
          <Link
            to={`/alertas/${a.id}`}
            className="text-md text-link hover:underline"
            onClick={(e) => e.stopPropagation()}
            aria-label={`Abrir la página de la alerta ${a.title}`}
          >
            Abrir
          </Link>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-7"
                onClick={(e) => e.stopPropagation()}
                aria-label={`Más acciones para ${a.title}`}
              >
                <MoreHorizontalIcon className="size-4" aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
              <DropdownMenuItem onSelect={() => onAbrirPanel(a.id as number)}>Ver detalle</DropdownMenuItem>
              <DropdownMenuItem disabled={a.status === "cerrada" || esRetirada(a)} onSelect={() => onCerrarConMotivo(a)}>
                Cerrar con motivo
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          </div>
        );
      },
    },
  ];
}
