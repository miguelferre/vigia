/** Piezas visuales de `serie.tsx`: punto por grupo, tooltip y selector (< 9 KB por fichero). */

import { Line } from "recharts";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { colorEstado } from "@/components/vigia";
import { formatoFechaLarga } from "@/lib/fechas";
import { ETIQUETA_ESTADO, formatoNumero, metricLabel } from "@/lib/metrics";
import type { GroupContext } from "@/api/types-domain";

import { GRUPO_GLOBAL, type FilaCombinada } from "./tipos";
import { numeroLote } from "@/lib/fases";

export interface PuntoDotProps {
  cx?: number;
  cy?: number;
  payload?: unknown;
}

function esFilaCombinada(v: unknown): v is FilaCombinada {
  return v !== null && typeof v === "object" && "porGrupo" in v;
}

/**
 * "Global" para el grupo sin desglose; con `group_context`
 * el código que coincide con el grupo supervisado o de referencia se
 * cambia por "<protected_attr> = <valor>"; sin contexto o sin coincidencia,
 * el código de grupo tal cual.
 */
export function etiquetaGrupo(grupo: string, ctx?: GroupContext): string {
  if (grupo === GRUPO_GLOBAL) return "Global";
  if (ctx) {
    if (ctx.supervised.includes(grupo)) return `${ctx.protected_attr} = ${grupo}`;
    if (ctx.reference.includes(grupo)) return `${ctx.protected_attr} = ${grupo}`;
  }
  return grupo;
}

/** Punto coloreado por estado en la línea de un grupo concreto (una función por grupo, closure sobre su clave). */
export function crearPuntoEstado(grupo: string) {
  return function PuntoDeGrupo({ cx, cy, payload }: PuntoDotProps) {
    if (cx === undefined || cy === undefined || !esFilaCombinada(payload)) return <></>;
    const punto = payload.porGrupo[grupo];
    if (!punto) return <></>;
    return <circle cx={cx} cy={cy} r={3.5} fill={colorEstado(punto.state, "relleno")} stroke="none" />;
  };
}

/** Banda de intervalo (mín. y máx.) de un grupo único: dos líneas punteadas sueltas, sin leyenda. */
export function lineasIntervalo(grupo: string | null) {
  if (grupo === null) return null;
  const comunes = {
    stroke: "var(--muted-foreground)",
    strokeDasharray: "2 3",
    dot: false,
    legendType: "none",
    connectNulls: true,
    isAnimationActive: false,
  } as const;
  return [
    <Line key="int-min" {...comunes} dataKey={(f: FilaCombinada) => f.porGrupo[grupo]?.interval_low ?? null} name="Intervalo (mín.)" />,
    <Line key="int-max" {...comunes} dataKey={(f: FilaCombinada) => f.porGrupo[grupo]?.interval_high ?? null} name="Intervalo (máx.)" />,
  ];
}

export interface PuntoTooltipAmpliadoProps {
  active?: boolean;
  payload?: { name?: unknown; payload?: unknown }[];
  /** `batch_id -> fase`, para mostrar la fase como dato secundario. */
  faseDeLote: Map<number, string>;
  /** `group_context` del monitor, para nombrar el grupo en vez de su código. */
  groupContext?: GroupContext;
  /** Formato del valor con la unidad del proyecto; sin él, `formatoNumero`. */
  formatoValor?: (valor: number | null) => string;
}

export function PuntoTooltipAmpliado({ active, payload, faseDeLote, groupContext, formatoValor }: PuntoTooltipAmpliadoProps) {
  if (!active || !payload || payload.length === 0 || !esFilaCombinada(payload[0].payload)) return null;
  const fila = payload[0].payload;
  const referencia = Object.values(fila.porGrupo)[0];
  const fase =
    referencia && referencia.batch_id !== null
      ? (faseDeLote.get(referencia.batch_id) ?? `Lote ${numeroLote(referencia.batch_seq ?? 0)}`)
      : null;
  return (
    <div className="rounded-md border border-border bg-popover p-2 text-xs text-popover-foreground shadow-md">
      <p className="font-semibold">{formatoFechaLarga(fila.ts)}</p>
      {fase ? <p className="text-muted-foreground">{fase}</p> : null}
      <div className="mt-1 flex flex-col gap-0.5">
        {payload.map((entrada) => {
          const grupo = String(entrada.name ?? "");
          const punto = fila.porGrupo[grupo];
          if (!punto) return null;
          return (
            <p key={grupo}>
              {etiquetaGrupo(grupo, groupContext)}: {formatoValor ? formatoValor(punto.value) : formatoNumero(punto.value)} ·{" "}
              {ETIQUETA_ESTADO[punto.state]}
            </p>
          );
        })}
      </div>
    </div>
  );
}

export interface SelectorProps {
  etiqueta: string;
  valor: string;
  opciones: string[];
  onCambio: (v: string) => void;
  conEtiquetaMetrica?: boolean;
  etiquetaOpcion?: (v: string) => string;
}

export function Selector({ etiqueta, valor, opciones, onCambio, conEtiquetaMetrica, etiquetaOpcion }: SelectorProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-muted-foreground">{etiqueta}</span>
      <Select value={valor} onValueChange={onCambio}>
        <SelectTrigger size="sm" className="min-w-48" aria-label={etiqueta}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {opciones.map((o) => (
            <SelectItem key={o} value={o}>
              {conEtiquetaMetrica ? metricLabel(o) : (etiquetaOpcion ? etiquetaOpcion(o) : o)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
