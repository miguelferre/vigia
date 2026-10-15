/**
 * Histograma «línea base frente a lote», forma B:
 * el lote en barras (`--chart-1`) y la línea base como escalón con un punto
 * por tramo (`--chart-3`). Componente compartido para variables de deriva
 * (`pages/monitores/histograma-variable.tsx`), confianza del modelo
 * (`pages/monitores/histograma-confianza.tsx`) y clases predichas (F2,
 * `pages/monitores/TarjetaClasesPredichas.tsx`).
 *
 * `tituloEjeX`/`tituloEjeY`: títulos de eje
 * discretos y opcionales, sin afectar a los demás usos; hoy solo los pasa la
 * tarjeta de confianza.
 */

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { LabelProps } from "recharts";

import { cn } from "@/lib/utils";
import { formatoCorto, formatoNumero } from "@/lib/metrics";
import { useAnchoContenedor } from "@/hooks/useAnchoContenedor";
import { construirFilasHistograma, etiquetaEjeDeTramo, indicesQueMasCambian, type FilaHistograma } from "./histograma-base-lote-datos";

export interface HistogramaBaseLoteProps {
  /** Etiqueta ya formateada de cada tramo. */
  tramos: string[];
  /** Peso de la línea base por tramo: recuento, o tasa si `mostrarRecuentos` es `false`. */
  base: number[];
  /** Peso del lote por tramo, misma longitud que `tramos`. */
  actual: number[];
  /** Si es `false`, el tooltip no enseña recuentos (los pesos son tasas, no recuentos). */
  mostrarRecuentos?: boolean;
  /** Alto del gráfico en px. */
  alto?: number;
  etiquetaBase?: string;
  etiquetaActual?: string;
  /** Antepuesto al tramo en el título del tooltip. */
  prefijoTramo?: string;
  /** Título discreto del eje X: solo lo pasa la tarjeta de confianza. */
  tituloEjeX?: string;
  /** Título discreto del eje Y: solo lo pasa la tarjeta de confianza. */
  tituloEjeY?: string;
  /**
   * los tramos son nombres de clase, posiblemente largos y muchos. El eje X los
   * inclina y los acorta (el nombre completo sigue en el tooltip) y pinta todos, sin saltos.
   * Solo lo pasa la tarjeta de clases predichas en multiclase: el resto de usos no cambia.
   */
  etiquetasLargas?: boolean;
  className?: string;
}

/** Con `etiquetasLargas`, el nombre de la clase se acorta en el eje a este número de caracteres. */
const LARGO_ETIQUETA_EJE = 16;

function acortar(texto: string): string {
  return texto.length > LARGO_ETIQUETA_EJE ? `${texto.slice(0, LARGO_ETIQUETA_EJE - 1).trimEnd()}…` : texto;
}

/** Tope de anchura de la barra del lote: evita los bloques macizos con dos o tres tramos. */
const ANCHO_MAXIMO_BARRA = 56;

interface FilaEtiquetada extends FilaHistograma {
  tope: number;
  etiqueta: number | null;
}

function prepararFilas(filas: FilaHistograma[]): FilaEtiquetada[] {
  const indices = new Set(indicesQueMasCambian(filas, 3));
  return filas.map((f, i) => ({
    ...f,
    tope: Math.max(f.base, f.actual),
    etiqueta: indices.has(i) ? Math.round(f.actual) : null,
  }));
}

/** Etiqueta de valor sobre el punto de `tope`; `value` es `etiqueta` (null fuera de los tres tramos). */
function EtiquetaTramo(props: LabelProps) {
  const valor = props.value;
  if (valor === null || valor === undefined || valor === "") return null;
  const x = Number(props.x);
  const y = Number(props.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return (
    <text x={x} y={y - 6} textAnchor="middle" fontSize={10} fontWeight={600} fill="var(--foreground)">
      {formatoCorto(Number(valor), 0)}
    </text>
  );
}

interface TooltipHistogramaProps {
  active?: boolean;
  payload?: { payload?: FilaEtiquetada }[];
  prefijoTramo: string;
  etiquetaBase: string;
  etiquetaActual: string;
  mostrarRecuentos: boolean;
}

function TooltipHistograma({
  active,
  payload,
  prefijoTramo,
  etiquetaBase,
  etiquetaActual,
  mostrarRecuentos,
}: TooltipHistogramaProps) {
  const fila = payload?.[0]?.payload;
  if (!active || !fila) return null;
  const signo = fila.diff > 0 ? "+" : fila.diff < 0 ? "−" : "";
  return (
    <div
      className="flex min-w-44 flex-col gap-1 rounded-md p-2.5 text-xs"
      style={{ background: "var(--card)", color: "var(--card-foreground)", boxShadow: "var(--elevation-pop)" }}
    >
      <p className="font-semibold">{prefijoTramo ? `${prefijoTramo} ${fila.tramo}` : fila.tramo}</p>
      <p>
        {etiquetaBase} {formatoNumero(fila.base, 1)} %
      </p>
      <p>
        {etiquetaActual} {formatoNumero(fila.actual, 1)} %
      </p>
      <p>
        Diferencia {signo}
        {formatoCorto(Math.abs(fila.diff), 1)} pp
      </p>
      {mostrarRecuentos ? (
        <p className="text-tertiary">
          n {formatoNumero(fila.nBase, 0)} · {formatoNumero(fila.nActual, 0)}
        </p>
      ) : null}
    </div>
  );
}

export function HistogramaBaseLote({
  tramos,
  base,
  actual,
  mostrarRecuentos = true,
  alto = 220,
  etiquetaBase = "Línea base",
  etiquetaActual = "Lote",
  prefijoTramo = "",
  tituloEjeX,
  tituloEjeY,
  etiquetasLargas = false,
  className,
}: HistogramaBaseLoteProps) {
  const filas = prepararFilas(construirFilasHistograma(tramos, base, actual));
  const [refAncho, ancho] = useAnchoContenedor<HTMLDivElement>();

  if (filas.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin datos suficientes para el histograma.</p>;
  }

  // A lo sumo 8 etiquetas, y 5 si el contenedor
  // queda estrecho (panel de la demo abierto, ~500 px); antes de la primera
  // medición (`ancho === 0`) se usa el tope de 8 como hasta ahora.
  const maxEtiquetas = ancho > 0 && ancho < 500 ? 5 : 8;
  const salto = Math.max(0, Math.ceil(filas.length / maxEtiquetas) - 1);

  return (
    <div className={cn("flex flex-col gap-2", className)} ref={refAncho}>
      {tituloEjeY ? <span className="pl-9 text-xs text-muted-foreground">{tituloEjeY}</span> : null}
      <div style={{ height: alto }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={filas} margin={{ top: 20, right: 8, bottom: 0, left: 0 }} barCategoryGap={0}>
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis
              dataKey="tramo"
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tick={
                etiquetasLargas
                  ? { fontSize: 10, fill: "var(--muted-foreground)", angle: -35, textAnchor: "end" }
                  : { fontSize: 10, fill: "var(--muted-foreground)" }
              }
              tickFormatter={(v: string) => (etiquetasLargas ? acortar(v) : etiquetaEjeDeTramo(v))}
              interval={etiquetasLargas ? 0 : salto}
              height={etiquetasLargas ? 88 : undefined}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={40}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              tickFormatter={(v: number) => `${formatoCorto(v, 0)} %`}
            />
            <Tooltip
              cursor={{ fill: "var(--muted)", fillOpacity: 0.5 }}
              content={
                <TooltipHistograma
                  prefijoTramo={prefijoTramo}
                  etiquetaBase={etiquetaBase}
                  etiquetaActual={etiquetaActual}
                  mostrarRecuentos={mostrarRecuentos}
                />
              }
            />
            {/* barras de 56 px como máximo, centradas en la banda; con muchos bins
                (banda más estrecha que el tope) siguen pegadas. */}
            <Bar
              dataKey="actual"
              name={etiquetaActual}
              fill="var(--chart-1)"
              fillOpacity={0.85}
              stroke="var(--card)"
              strokeWidth={1}
              maxBarSize={ANCHO_MAXIMO_BARRA}
              isAnimationActive={false}
            />
            <Line
              type="step"
              dataKey="base"
              name={etiquetaBase}
              stroke="var(--chart-3)"
              strokeWidth={2}
              dot={{ r: 3, fill: "var(--card)", stroke: "var(--chart-3)", strokeWidth: 2 }}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            />
            <Line
              type="step"
              dataKey="tope"
              stroke="none"
              dot={false}
              activeDot={false}
              isAnimationActive={false}
              legendType="none"
              tooltipType="none"
            >
              <LabelList dataKey="etiqueta" content={EtiquetaTramo} />
            </Line>
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {tituloEjeX ? <p className="text-center text-xs text-muted-foreground">{tituloEjeX}</p> : null}
      <div className="flex items-center gap-3.5 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block size-2.5 rounded-[2px]" style={{ background: "var(--chart-3)" }} />
          {etiquetaBase}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block size-2.5 rounded-[2px]" style={{ background: "var(--chart-1)" }} />
          {etiquetaActual}
        </span>
      </div>
    </div>
  );
}

export default HistogramaBaseLote;

// Nota de recharts 3.10.1 (memoria): si en producción `LabelList`
// dentro de este `Line` invisible no recibe `x`/`y` para alguna versión,
// la alternativa es moverlo dentro del `Bar` y calcular la `y` a mano desde
// `props.viewBox` escalando `base`/`actual` contra el rango del eje Y.
