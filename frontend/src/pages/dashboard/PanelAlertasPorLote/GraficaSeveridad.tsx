/**
 * Gráfica 2 del panel: «Reparto por severidad» (`BarChart` apilado al
 * 100 %), mismo `syncId` y mismo eje X que la gráfica 1 (aquí
 * con las etiquetas visibles). Bandas de fase también en proyectos demo
 * (sin texto propio, la etiqueta va en la
 * gráfica 1).
 */

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ReferenceArea, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import type { LabelProps } from "recharts";

import { ChartContainer, type ChartConfig } from "@/components/ui/chart";
import { agruparFases, type Fila } from "./formato";
import { limitesDeTramo } from "./GraficaMonitores";

const CONFIG: ChartConfig = {
  alta: { label: "Alta", color: "var(--state-alert)" },
  media: { label: "Media", color: "var(--state-warn-fill)" },
  baja: { label: "Baja", color: "var(--state-unstable)" },
};

/** Total encima de la pila: `LabelList` con `dataKey="total"` sobre el
 * segmento «alta» (existe siempre que hay total), así `value` ya es el total
 * de la fila. Las pilas ya vienen normalizadas a [0, 1] (`filasNormalizadas`)
 * y llegan al 100 % salvo tramo sin alertas, así que el total va a una
 * altura fija: el borde superior del área de dibujo (`margin.top`), no el
 * del segmento. */
const MARGEN_SUPERIOR = 16;

function EtiquetaTotal(props: LabelProps) {
  const total = Number(props.value ?? 0);
  if (!total) return null;
  const caja = props.viewBox as { x?: number; width?: number } | undefined;
  const centro = Number(caja?.x ?? props.x ?? 0) + Number(caja?.width ?? 0) / 2;
  return (
    <text x={centro} y={MARGEN_SUPERIOR - 4} fontSize={10} fontWeight={600} fill="var(--foreground)" textAnchor="middle">
      {total}
    </text>
  );
}

export interface GraficaSeveridadProps {
  filas: Fila[];
  tramo: string | null;
  onClicTramo: (clave: string) => void;
}

export function GraficaSeveridad({ filas, tramo, onClicTramo }: GraficaSeveridadProps) {
  const grupos = agruparFases(filas);
  const filaTramo = tramo ? filas.find((f) => f.key === tramo) : undefined;

  // `stackOffset="expand"` divide cada segmento por el total de su pila; con
  // un tramo sin alertas (total 0) esa división da NaN y recharts pinta un
  // <rect> con atributos NaN. Se normaliza aquí a mano a
  // fracciones de [0, 1] (0 cuando el total es 0) y se apila con
  // `stackOffset="none"`, que ya no divide por nada.
  const filasNormalizadas = useMemo(
    () =>
      filas.map((f) => {
        const total = f.alta + f.media + f.baja;
        return {
          ...f,
          alta: total > 0 ? f.alta / total : 0,
          media: total > 0 ? f.media / total : 0,
          baja: total > 0 ? f.baja / total : 0,
        };
      }),
    [filas],
  );

  function alClicar(estado: { activeLabel?: string | number }) {
    const fila = filas.find((f) => f.etiqueta === estado.activeLabel);
    if (fila) onClicTramo(fila.key);
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-md font-medium text-tertiary">Reparto por severidad (100 %, total encima)</span>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {Object.values(CONFIG).map((c) => (
            <span key={c.label} className="inline-flex items-center gap-1.5">
              <span aria-hidden="true" className="size-2 rounded-full" style={{ background: c.color }} />
              {c.label}
            </span>
          ))}
        </div>
      </div>
      <ChartContainer config={CONFIG} className="h-[130px] w-full cursor-pointer">
        <BarChart
          data={filasNormalizadas}
          syncId="alertas-por-lote"
          stackOffset="none"
          margin={{ top: MARGEN_SUPERIOR, right: 8, bottom: 0, left: 0 }}
          onClick={alClicar}
        >
          <CartesianGrid horizontal vertical={false} stroke="var(--line)" />
          <CartesianGrid
            horizontal={false}
            vertical
            stroke="var(--line-2)"
            verticalCoordinatesGenerator={limitesDeTramo(filas.length)}
          />
          {/* Una banda o una línea cuya etiqueta no esté en
              el dominio de hoy sale como `<rect x="NaN">` o `<line x1="NaN">`
              en consola. Pasa cada vez que entra un lote nuevo mientras el
              panel está abierto: los grupos vienen del render anterior. */}
          {grupos.map((g) => {
            const x1 = filas[g.inicio]?.etiqueta;
            const x2 = filas[g.fin]?.etiqueta;
            if (x1 === undefined || x2 === undefined) return null;
            return (
              <ReferenceArea
                key={`${g.faseLabel}-${g.inicio}`}
                x1={x1}
                x2={x2}
                fill="var(--primary)"
                fillOpacity={0.08}
              />
            );
          })}
          {filaTramo && filas.some((f) => f.etiqueta === filaTramo.etiqueta) ? (
            <ReferenceLine x={filaTramo.etiqueta} stroke="var(--primary)" strokeDasharray="4 4" />
          ) : null}
          <XAxis dataKey="etiqueta" tickLine={false} axisLine={false} interval={0} tick={{ fontSize: 10 }} />
          <YAxis
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tickFormatter={(v: number) => `${Math.round(v * 100)} %`}
            tickLine={false}
            axisLine={false}
            width={48}
            tick={{ fontSize: 10 }}
          />
          <Tooltip content={() => null} cursor={{ fill: "var(--muted)" }} />
          <Bar dataKey="alta" stackId="sev" fill="var(--color-alta)" stroke="var(--card)" strokeWidth={2} barSize={28} radius={0} isAnimationActive={false}>
            <LabelList dataKey="total" content={EtiquetaTotal} />
          </Bar>
          <Bar dataKey="media" stackId="sev" fill="var(--color-media)" stroke="var(--card)" strokeWidth={2} barSize={28} radius={0} isAnimationActive={false} />
          <Bar dataKey="baja" stackId="sev" fill="var(--color-baja)" stroke="var(--card)" strokeWidth={2} barSize={28} radius={0} isAnimationActive={false} />
        </BarChart>
      </ChartContainer>
    </div>
  );
}
