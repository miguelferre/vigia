/**
 * Histograma de residuos del lote: `predicción - real` en 20
 * cajas, en % de las filas con valor real. La caja que contiene el 0 va
 * marcada con un borde oscuro (el eje es de categorías: una línea no caería
 * en el 0 exacto): un residuo centrado en 0 es un modelo sin sesgo.
 *
 * Solo el lote: la evaluación de la línea base se calcula con otros cortes
 * (`details.residuos.bin_edges` cambia con cada ventana), así que no se
 * superpone al histograma; su media y su dispersión van en la frase de
 * debajo (`CalidadRegresion`).
 */

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatoCorto, formatoNumero } from "@/lib/metrics";

import type { HistogramaNumerico } from "./regresion-datos";

interface Fila {
  /** Borde izquierdo con los decimales comunes: etiqueta del eje. */
  eje: string;
  /** «de -25,9 a -19,1»: tooltip. */
  tramo: string;
  pct: number;
  n: number;
}

/** Los mismos decimales en todos los cortes, según el ancho de una caja. */
function decimalesDeResiduos(binEdges: number[]): number {
  const ancho = Math.abs((binEdges[1] ?? 1) - (binEdges[0] ?? 0));
  if (ancho >= 5) return 0;
  if (ancho >= 0.5) return 1;
  return ancho >= 0.05 ? 2 : 3;
}

function Tip({ active, payload }: { active?: boolean; payload?: { payload?: Fila }[] }) {
  const f = payload?.[0]?.payload;
  if (!active || !f) return null;
  return (
    <div
      className="flex min-w-40 flex-col gap-1 rounded-md p-2.5 text-xs"
      style={{ background: "var(--card)", color: "var(--card-foreground)", boxShadow: "var(--elevation-pop)" }}
    >
      <p className="font-semibold">Residuo {f.tramo}</p>
      <p>
        {formatoNumero(f.pct, 1)} % de las filas · n {formatoNumero(f.n, 0)}
      </p>
    </div>
  );
}

export function HistogramaResiduos({ histograma, unidad }: { histograma: HistogramaNumerico; unidad: string | null }) {
  const total = histograma.counts.reduce((a, b) => a + b, 0);
  if (total === 0) return <p className="text-sm text-muted-foreground">Sin residuos en esta ventana.</p>;
  const d = decimalesDeResiduos(histograma.binEdges);
  const borde = (i: number) => formatoNumero(histograma.binEdges[i] ?? 0, d);
  const filas: Fila[] = histograma.counts.map((c, i) => ({
    eje: borde(i),
    tramo: `de ${borde(i)} a ${borde(i + 1)}`,
    pct: (c / total) * 100,
    n: c,
  }));
  const iCero = histograma.counts.findIndex((_, i) => histograma.binEdges[i]! <= 0 && 0 <= histograma.binEdges[i + 1]!);
  const salto = Math.max(0, Math.ceil(filas.length / 8) - 1);
  return (
    <div className="flex flex-col gap-1" data-testid="histograma-residuos">
      <div style={{ height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={filas} margin={{ top: 10, right: 8, bottom: 0, left: 0 }} barCategoryGap={0}>
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis
              dataKey="eje"
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              interval={salto}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={40}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              tickFormatter={(v: number) => `${formatoCorto(v, 0)} %`}
            />
            <Tooltip cursor={{ fill: "var(--muted)", fillOpacity: 0.5 }} content={<Tip />} />
            <Bar dataKey="pct" fill="var(--chart-1)" fillOpacity={0.85} stroke="var(--card)" strokeWidth={1} maxBarSize={56} isAnimationActive={false}>
              {filas.map((f, i) => (
                <Cell key={f.eje} stroke={i === iCero ? "var(--foreground)" : "var(--card)"} strokeWidth={i === iCero ? 2 : 1} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-center text-xs text-muted-foreground">
        Residuo = predicción menos valor real{unidad ? `, en ${unidad}` : ""}. La caja con borde oscuro contiene el 0. A su
        izquierda, el modelo se queda corto; a su derecha, se pasa.
      </p>
    </div>
  );
}
