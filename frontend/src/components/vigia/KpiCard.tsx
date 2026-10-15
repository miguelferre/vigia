/**
 * Tarjeta de indicador con estado y sparkline.
 *
 * El trazo usa `--chart-1` salvo que haya estado, en cuyo caso toma el token
 * `--state-*` correspondiente. Sin colores literales.
 *
 * @example
 * <KpiCard
 *   titulo="Equidad"
 *   valor={formatoNumero(0.82)}
 *   estado="aviso"
 *   serie={[
 *     { ts: "2026-09-01T08:00:00Z", valor: 0.91, estado: "ok" },
 *     { ts: "2026-09-02T08:00:00Z", valor: 0.82, estado: "aviso" },
 *   ]}
 *   umbrales={{ bajo: 0.8, alto: null }}
 * />
 */

import type { ReactNode } from "react";
import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StateBadge, colorEstado } from "@/components/vigia/StateBadge";
import { formatoFecha, formatoNumero } from "@/lib/metrics";
import { cn } from "@/lib/utils";
import type { EstadoMotor } from "@/api/types";

/** Punto del sparkline: fecha para el tooltip, valor y estado del motor. */
export interface PuntoSerie {
  ts: string | null;
  valor: number | null;
  estado?: EstadoMotor | null;
}

export interface KpiCardProps {
  titulo: string;
  /** Valor principal ya formateado. */
  valor: ReactNode;
  estado?: EstadoMotor | null;
  /** Texto del distintivo en lugar de la etiqueta del estado (p. ej. «Sin umbral» en multiclase). */
  textoEstado?: string;
  descripcion?: ReactNode;
  /** Serie para el sparkline, en orden cronológico. */
  serie?: PuntoSerie[];
  /** Líneas de referencia discontinuas sobre el sparkline. */
  umbrales?: { bajo?: number | null; alto?: number | null };
  /** formato del valor en el tooltip del sparkline (con la unidad en regresión). Sin él, `formatoNumero`. */
  formatoValor?: (valor: number | null) => string;
  pie?: ReactNode;
  onClick?: () => void;
  className?: string;
}

function esPunto(valor: unknown): valor is PuntoSerie {
  return typeof valor === "object" && valor !== null && "valor" in valor && "ts" in valor;
}

/** Punto del sparkline con su epoch en milisegundos, para posicionarlo por tiempo real. */
interface PuntoConTiempo extends PuntoSerie {
  tsEpoch: number;
}

/** Puntos con valor y fecha válidos, con el epoch ya calculado. Descarta lo demás: sin
 * fecha no hay dónde colocar el punto en un eje temporal. */
function conTiempo(serie: PuntoSerie[]): PuntoConTiempo[] {
  return serie
    .filter((p): p is PuntoSerie & { ts: string; valor: number } => typeof p.valor === "number" && typeof p.ts === "string")
    .map((p) => ({ ...p, tsEpoch: new Date(p.ts).getTime() }))
    .filter((p) => !Number.isNaN(p.tsEpoch));
}

/** Tooltip propio: fecha, valor y fase como dato secundario, con los tokens del tema. */
function SparkTooltip({
  active,
  payload,
  formatoValor,
}: {
  active?: boolean;
  payload?: { payload?: unknown }[];
  formatoValor?: (valor: number | null) => string;
}) {
  const punto = payload?.[0]?.payload;
  if (!active || !esPunto(punto)) return null;
  return (
    <div className="rounded-md border border-border bg-popover p-2 text-xs text-popover-foreground shadow-md">
      <p className="font-semibold">{formatoFecha(punto.ts)}</p>
      <p className="tabular-nums">{formatoValor ? formatoValor(punto.valor) : formatoNumero(punto.valor)}</p>
      {punto.estado ? <StateBadge estado={punto.estado} size="sm" className="mt-1" /> : null}
    </div>
  );
}

/**
 * Dominio del eje Y: los valores más los umbrales, con un 10 % de margen para
 * que una línea de referencia en el extremo no quede pegada al borde.
 */
function dominio(valores: number[], umbrales?: KpiCardProps["umbrales"]): [number, number] {
  const limites = [umbrales?.bajo, umbrales?.alto].filter((n): n is number => typeof n === "number");
  const todos = [...valores, ...limites];
  const min = Math.min(...todos);
  const max = Math.max(...todos);
  const margen = max - min || Math.abs(max) || 1;
  return [min - margen * 0.1, max + margen * 0.1];
}

export function KpiCard({
  titulo,
  valor,
  estado,
  textoEstado,
  descripcion,
  serie,
  umbrales,
  formatoValor,
  pie,
  onClick,
  className,
}: KpiCardProps) {
  const color = estado ? colorEstado(estado, "relleno") : "var(--chart-1)";
  const puntos = conTiempo(serie ?? []);
  const valores = puntos.map((p) => p.valor as number);

  const contenido = (
    <>
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-md font-normal text-muted-foreground">{titulo}</CardTitle>
        {estado ? <StateBadge estado={estado} texto={textoEstado} size="sm" /> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <p className="font-display text-[28px] font-semibold tracking-[-0.15px] tabular-nums">{valor}</p>
        {descripcion ? <div className="text-xs text-muted-foreground">{descripcion}</div> : null}
        {puntos.length > 1 ? (
          <div className="h-12 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={puntos} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
                {/* Eje temporal real: antes no había `XAxis` y
                    Recharts posicionaba los puntos por índice. Oculto porque a 48 px
                    de alto una escala de fechas no cabe legible; la fecha ya está en
                    el tooltip (`SparkTooltip`), formateada en español. */}
                <XAxis type="number" dataKey="tsEpoch" hide domain={["dataMin", "dataMax"]} />
                <YAxis hide domain={dominio(valores, umbrales)} />
                <Tooltip content={<SparkTooltip formatoValor={formatoValor} />} cursor={false} />
                {typeof umbrales?.bajo === "number" ? (
                  <ReferenceLine
                    y={umbrales.bajo}
                    stroke="var(--muted-foreground)"
                    strokeDasharray="3 3"
                  />
                ) : null}
                {typeof umbrales?.alto === "number" ? (
                  <ReferenceLine
                    y={umbrales.alto}
                    stroke="var(--muted-foreground)"
                    strokeDasharray="3 3"
                  />
                ) : null}
                <Line
                  type="monotone"
                  dataKey="valor"
                  stroke={color}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 3, strokeWidth: 0 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : null}
        {pie ? <div className="text-xs text-tertiary">{pie}</div> : null}
      </CardContent>
    </>
  );

  if (onClick) {
    return (
      <Card
        className={cn(
          "cursor-pointer transition-colors hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
          className,
        )}
      >
        <button type="button" onClick={onClick} className="w-full text-left">
          {contenido}
        </button>
      </Card>
    );
  }

  return <Card className={className}>{contenido}</Card>;
}
