/**
 * Ranking de importancias de Explicabilidad: como `RankingBarras` pero sin
 * animación de entrada y con la cifra de cada barra.
 *
 * Por qué aparte: la animación de Recharts dibuja las barras desde cero y
 * hasta que arranca el gráfico parece vacío (un panel en segundo plano, una
 * captura o un gráfico pequeño lo dejan así). Aquí se dibuja el estado final
 * desde el primer cuadro. La cifra va en la unidad de la salida cuando el
 * llamador pasa `etiqueta` (regresión) y también en la local de clasificación.
 * `RankingBarras` es compartido con Deriva y no se toca desde aquí.
 */

import type { ComponentType } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TooltipRankingProps } from "@/components/vigia";
import { formatoCorto } from "@/lib/metrics";

export interface RankingBarrasFijoProps<T> {
  datos: T[];
  claveCategoria: keyof T;
  claveValor: keyof T;
  color: (fila: T) => string;
  tooltip: ComponentType<TooltipRankingProps>;
  onClickBarra?: (fila: T) => void;
  /** Texto de la cifra junto a cada barra; sin él, las barras no llevan cifra. */
  etiqueta?: (valor: number) => string;
}

function anchoEjeY<T>(datos: T[], clave: keyof T): number {
  const maxLargo = Math.max(0, ...datos.map((f) => String(f[clave] ?? "").length));
  return Math.min(320, Math.max(160, 8 + maxLargo * 6));
}

/** Sube `v` a dos cifras significativas (0,624 pasa a 0,63): el extremo del eje no sale con quince decimales. */
function techo(v: number): number {
  if (v === 0) return 0;
  const paso = 10 ** (Math.floor(Math.log10(Math.abs(v))) - 1);
  return (v > 0 ? Math.ceil(v / paso) : Math.floor(v / paso)) * paso;
}

interface PropsEtiqueta {
  x?: number | string;
  y?: number | string;
  width?: number | string;
  height?: number | string;
  value?: unknown;
}

export function RankingBarrasFijo<T>({
  datos,
  claveCategoria,
  claveValor,
  color,
  tooltip: TooltipContenido,
  onClickBarra,
  etiqueta,
}: RankingBarrasFijoProps<T>) {
  const alto = Math.max(160, datos.length * 26 + 40);
  const ancho = anchoEjeY(datos, claveCategoria);
  // Con cifra, el eje deja sitio a cada lado para que no pise las etiquetas ni se corte.
  const holgura = 1.35;

  const cifra = ({ x, y, width, height, value }: PropsEtiqueta) => {
    const v = Number(value);
    if (!etiqueta || !Number.isFinite(v)) return null;
    const x0 = Number(x);
    const w = Number(width);
    const negativa = v < 0;
    // Positiva: a la derecha del extremo de la barra. Negativa: junto a la línea del cero, por el lado vacío
    // de su fila, para no pisar el nombre de la variable (en pantallas estrechas no caben fuera).
    const xTexto = negativa ? x0 + 6 : x0 + w + 6;
    return (
      <text
        x={xTexto}
        y={Number(y) + Number(height) / 2}
        dy="0.35em"
        textAnchor="start"
        fontSize={11}
        fill="var(--foreground)"
        data-testid="cifra-barra"
      >
        {etiqueta(v)}
      </text>
    );
  };

  return (
    <div style={{ height: alto }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={datos} layout="vertical" margin={{ left: 24, right: etiqueta ? 48 : 16 }}>
          <CartesianGrid horizontal={false} stroke="var(--border)" />
          <XAxis
            type="number"
            tick={{ fontSize: 11 }}
            stroke="var(--muted-foreground)"
            tickFormatter={etiqueta ? (v: number) => formatoCorto(v, 3) : undefined}
            domain={
              etiqueta
                ? [
                    (min: number) => techo(Math.min(0, min) * holgura),
                    (max: number) => techo(Math.max(0, max) * holgura),
                  ]
                : undefined
            }
          />
          <YAxis
            type="category"
            dataKey={claveCategoria as string}
            width={ancho}
            tick={{ fontSize: 11 }}
            stroke="var(--muted-foreground)"
          />
          <Tooltip content={<TooltipContenido />} />
          <Bar dataKey={claveValor as string} isAnimationActive={false} cursor={onClickBarra ? "pointer" : undefined}>
            {datos.map((fila) => (
              <Cell
                key={String(fila[claveCategoria])}
                fill={color(fila)}
                onClick={onClickBarra ? () => onClickBarra(fila) : undefined}
              />
            ))}
            {etiqueta ? <LabelList dataKey={claveValor as string} content={cifra} /> : null}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
