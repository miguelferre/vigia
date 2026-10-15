/**
 * «Predicho frente a real» de la calidad de una regresión: por
 * decil de la predicción, la banda del percentil 10 al 90 del valor real, la
 * media del valor real y la diagonal `y = x` (el modelo perfecto). Una línea
 * por encima de la diagonal quiere decir que el modelo se queda corto en ese
 * tramo; por debajo, que se pasa. `ComposedChart` con ejes numéricos iguales
 * en x e y, para que la diagonal sea de verdad una diagonal.
 */

import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatoCorto, formatoMetrica, formatoNumero } from "@/lib/metrics";

import { ticksRedondos, type TramoPredVsReal } from "./regresion-datos";

interface FilaBanda extends TramoPredVsReal {
  banda: [number, number];
}

function Tip({ active, payload, unidad }: { active?: boolean; payload?: { payload?: FilaBanda }[]; unidad: string | null }) {
  const f = payload?.[0]?.payload;
  if (!active || !f) return null;
  const v = (x: number) => formatoMetrica("mean_absolute_error", x, unidad);
  return (
    <div
      className="flex min-w-48 flex-col gap-1 rounded-md p-2.5 text-xs"
      style={{ background: "var(--card)", color: "var(--card-foreground)", boxShadow: "var(--elevation-pop)" }}
    >
      <p className="font-semibold">Tramo {f.decil} de la predicción</p>
      <p>Predicción media: {v(f.predMedia)}</p>
      <p>Valor real medio: {v(f.realMedia)}</p>
      <p>
        El 80 % de los valores reales: de {v(f.realP10)} a {v(f.realP90)}
      </p>
      <p className="text-tertiary">n {formatoNumero(f.n, 0)}</p>
    </div>
  );
}

export function PredichoFrenteAReal({ tramos, unidad }: { tramos: TramoPredVsReal[]; unidad: string | null }) {
  if (tramos.length < 2) {
    return <p className="text-sm text-muted-foreground">Sin tramos suficientes para dibujar «predicho frente a real».</p>;
  }
  const filas: FilaBanda[] = [...tramos]
    .sort((a, b) => a.predMedia - b.predMedia)
    .map((t) => ({ ...t, banda: [t.realP10, t.realP90] }));
  const bajo = Math.min(...filas.map((f) => Math.min(f.predMedia, f.realP10)));
  const alto = Math.max(...filas.map((f) => Math.max(f.predMedia, f.realP90)));
  const margen = (alto - bajo) * 0.04 || 1;
  const min = bajo - margen;
  const max = alto + margen;
  const ticks = ticksRedondos(min, max);
  const dominio: [number, number] = [min, max];
  const etiquetaUnidad = unidad ? ` (${unidad})` : "";
  return (
    <div className="flex flex-col gap-2" data-testid="predicho-frente-a-real">
      <div style={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={filas} margin={{ top: 8, right: 12, bottom: 22, left: 0 }}>
            <CartesianGrid stroke="var(--line)" />
            <XAxis
              type="number"
              dataKey="predMedia"
              domain={dominio}
              ticks={ticks}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              tickFormatter={(v: number) => formatoCorto(v, 2)}
              label={{ value: `Predicción media del tramo${etiquetaUnidad}`, position: "insideBottom", offset: -14, fontSize: 11, fill: "var(--muted-foreground)" }}
            />
            <YAxis
              type="number"
              domain={dominio}
              ticks={ticks}
              width={44}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              tickFormatter={(v: number) => formatoCorto(v, 2)}
            />
            <Tooltip content={<Tip unidad={unidad} />} />
            <ReferenceLine
              segment={[
                { x: min, y: min },
                { x: max, y: max },
              ]}
              stroke="var(--muted-foreground)"
              strokeDasharray="5 4"
              ifOverflow="hidden"
            />
            <Area
              dataKey="banda"
              name="El 80 % de los valores reales"
              stroke="none"
              fill="var(--chart-1)"
              fillOpacity={0.18}
              isAnimationActive={false}
              activeDot={false}
            />
            <Line
              dataKey="realMedia"
              name="Valor real medio"
              stroke="var(--chart-1)"
              strokeWidth={2.5}
              dot={{ r: 3, fill: "var(--card)", stroke: "var(--chart-1)", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-wrap items-center gap-3.5 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-0.5 w-4" style={{ background: "var(--chart-1)" }} />
          Valor real medio
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block size-2.5 rounded-[2px]" style={{ background: "var(--chart-1)", opacity: 0.25 }} />
          El 80 % de los valores reales (percentil 10 a 90)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-0 w-4 border-t border-dashed" style={{ borderColor: "var(--muted-foreground)" }} />
          Modelo perfecto (predicción = real)
        </span>
      </div>
    </div>
  );
}
