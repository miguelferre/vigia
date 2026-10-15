/**
 * Gráfica 1 del panel: «Alertas por monitor» (`LineChart`). Una línea
 * por monitor (cruzadas no van en línea); bandas de fase también en
 * demo, con la etiqueta traducida por `etiquetaLote()` («Línea base»,
 * «Casos nuevos», «Tras las medidas»);
 * eje X oculto (las etiquetas viven en la gráfica 2, mismo `syncId`).
 *
 * El clic (punto, banda o etiqueta del eje) se resuelve con el `onClick`
 * del propio `LineChart`: recharts da la categoría más cercana en
 * `activeLabel`, así que un único manejador cubre los cuatro sitios sin un `onClick` por elemento.
 */

import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import type { DotProps, LabelProps } from "recharts";

import { ChartContainer } from "@/components/ui/chart";
import type { AlertasAbiertasPorSeveridad, SeriesGranularity } from "@/api/types";
import { etiquetaLote } from "@/lib/fases";
import { EtiquetaBandaFase } from "./EtiquetaBandaFase";
import { agruparFases, CONFIG_MONITORES, formatoCifra, type Fila } from "./formato";
import { TooltipTramo } from "./TooltipTramo";

const CONFIG = { fairness: CONFIG_MONITORES.fairness, quality: CONFIG_MONITORES.quality, drift: CONFIG_MONITORES.drift };
type Monitor = keyof typeof CONFIG;

/** Punto de la línea solo cuando hay valor: en cero la línea va por el
 * suelo y el círculo estorbaría (como en `Main.dc.html`). */
function PuntoNoCero(props: DotProps & { color: string; value?: number; key?: string }) {
  const { color, key, value, cx, cy } = props;
  if (!value || cx === undefined || cy === undefined) return <g key={key} />;
  return <circle key={key} cx={cx} cy={cy} r={3.5} fill="var(--card)" stroke={color} strokeWidth={2} />;
}

/** Separadores verticales en los LÍMITES de cada tramo (no en su centro,
 * que es donde recharts pinta la rejilla vertical de una escala de bandas). */
export function limitesDeTramo(n: number) {
  return ({ offset }: { offset: { left: number; width: number } }) =>
    n > 0 ? Array.from({ length: n + 1 }, (_, i) => offset.left + (i * offset.width) / n) : [];
}

// La cifra es texto real (no un trazo de serie): va en --foreground, que sí
// cumple 4,5:1, no en el color de la línea (--chart-*), medido solo a 3:1
// para uso decorativo/gráfico en build/contraste.py.
function EtiquetaValor(props: LabelProps & { granularidad: SeriesGranularity }) {
  const valor = Number(props.value ?? 0);
  if (valor === 0) return null;
  return (
    <text
      x={props.x}
      y={Number(props.y ?? 0) - 8}
      fontSize={10}
      fontWeight={600}
      fill="var(--foreground)"
      textAnchor="middle"
    >
      {formatoCifra(valor, props.granularidad)}
    </text>
  );
}

export interface GraficaMonitoresProps {
  filas: Fila[];
  granularidad: SeriesGranularity;
  esDemo: boolean;
  tramo: string | null;
  onClicTramo: (clave: string) => void;
  crossUnbatched?: AlertasAbiertasPorSeveridad;
}

export function GraficaMonitores({ filas, granularidad, esDemo, tramo, onClicTramo, crossUnbatched }: GraficaMonitoresProps) {
  const grupos = agruparFases(filas);
  const filaTramo = tramo ? filas.find((f) => f.key === tramo) : undefined;

  function alClicar(estado: { activeLabel?: string | number }) {
    const fila = filas.find((f) => f.etiqueta === estado.activeLabel);
    if (fila) onClicTramo(fila.key);
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-md font-medium text-tertiary">Alertas por monitor</span>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {(Object.keys(CONFIG) as Monitor[]).map((m) => (
            <span key={m} className="inline-flex items-center gap-1.5">
              <span aria-hidden="true" className="size-2 rounded-full" style={{ background: CONFIG[m].color }} />
              {CONFIG[m].label}
            </span>
          ))}
        </div>
      </div>
      <ChartContainer config={CONFIG} className="h-[200px] w-full cursor-pointer">
        <LineChart data={filas} syncId="alertas-por-lote" margin={{ top: 16, right: 8, bottom: 0, left: 0 }} onClick={alClicar}>
          <CartesianGrid horizontal vertical={false} stroke="var(--line)" />
          <CartesianGrid
            horizontal={false}
            vertical
            stroke="var(--line-2)"
            verticalCoordinatesGenerator={limitesDeTramo(filas.length)}
          />
          {/* Ver la nota de `GraficaSeveridad.tsx`. Una banda
              con `x1`/`x2` fuera del dominio de hoy sale como `<rect x="NaN">`
              mientras entra un lote nuevo. */}
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
              label={{
                // Contenido propio: recibe el ancho de la banda y abrevia la
                // etiqueta en vez de solapar la de la fase vecina.
                content: (props: LabelProps) => (
                  <EtiquetaBandaFase
                    texto={esDemo ? (etiquetaLote(g.faseLabel) ?? g.faseLabel) : g.faseLabel}
                    tramos={g.fin - g.inicio + 1}
                    total={filas.length}
                    viewBox={props.viewBox}
                  />
                ),
              }}
            />
            );
          })}
          {filaTramo && filas.some((f) => f.etiqueta === filaTramo.etiqueta) ? (
            <ReferenceLine x={filaTramo.etiqueta} stroke="var(--primary)" strokeDasharray="4 4" />
          ) : null}
          <XAxis dataKey="etiqueta" tick={false} tickLine={false} axisLine={false} />
          <YAxis
            domain={[0, "auto"]}
            allowDecimals={granularidad !== "batch"}
            tickLine={false}
            axisLine={false}
            width={24}
            tick={{ fontSize: 10 }}
            tickFormatter={(v: number) => formatoCifra(v, granularidad)}
          />
          <Tooltip content={<TooltipTramo granularidad={granularidad} crossUnbatched={crossUnbatched} />} cursor={{ stroke: "var(--line-2)" }} />
          {(Object.keys(CONFIG) as Monitor[]).map((m) => (
            <Line
              key={m}
              type="linear"
              dataKey={m}
              stroke={CONFIG[m].color}
              strokeWidth={2}
              dot={<PuntoNoCero color={CONFIG[m].color} />}
              activeDot={{ r: 4, fill: CONFIG[m].color, strokeWidth: 0 }}
              label={<EtiquetaValor granularidad={granularidad} />}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ChartContainer>
    </div>
  );
}
