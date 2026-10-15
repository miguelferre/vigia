/**
 * Ranking horizontal genérico: barras con categoría en el eje Y y alto
 * calculado por número de filas. Extraído de
 * `pages/explicabilidad/detalle.tsx` (patrón original del gráfico de
 * importancias), parametrizado para servir también al ranking de deriva por
 * característica.
 *
 * El color no es una bandera booleana: se recibe como función por fila,
 * porque cada consumidor colorea distinto (importancias locales por signo
 * del valor, deriva por serie) y una bandera no cubriría un tercer caso.
 */

import type { ComponentType } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface TooltipRankingProps {
  active?: boolean;
  payload?: { payload?: unknown }[];
}

export interface RankingBarrasProps<T> {
  datos: T[];
  /** Campo con la etiqueta de categoría (eje Y). */
  claveCategoria: keyof T;
  /** Campo con el valor numérico (eje X). */
  claveValor: keyof T;
  /** Color de cada barra; recibe la fila para poder colorear por signo o por serie. */
  color: (fila: T) => string;
  /** Contenido del tooltip de Recharts. */
  tooltip: ComponentType<TooltipRankingProps>;
  /** Clave React de cada fila; por defecto, el valor de `claveCategoria`. */
  clave?: (fila: T) => string;
  /** Clic en una barra: recibe la fila completa, no solo la etiqueta
   * legible, para que el consumidor decida qué campo enlazar (p.ej. el
   * nombre técnico de la característica). Con ella activa, el cursor pasa a
   * `pointer`. */
  onClickBarra?: (fila: T) => void;
}

/**
 * Ancho del eje Y a partir de la etiqueta más larga, para que Recharts no la
 * recorte por la izquierda (mín. 160, máx. 320 px).
 */
function anchoEjeY<T>(datos: T[], claveCategoria: keyof T): number {
  const maxLargo = Math.max(0, ...datos.map((f) => String(f[claveCategoria] ?? "").length));
  return Math.min(320, Math.max(160, 8 + maxLargo * 6));
}

export function RankingBarras<T>({
  datos,
  claveCategoria,
  claveValor,
  color,
  tooltip: TooltipContenido,
  clave,
  onClickBarra,
}: RankingBarrasProps<T>) {
  const alto = Math.max(160, datos.length * 26 + 40);
  const ancho = anchoEjeY(datos, claveCategoria);

  return (
    <div style={{ height: alto }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={datos} layout="vertical" margin={{ left: 24, right: 16 }}>
          <CartesianGrid horizontal={false} stroke="var(--border)" />
          <XAxis type="number" tick={{ fontSize: 11 }} stroke="var(--muted-foreground)" />
          <YAxis
            type="category"
            dataKey={claveCategoria as string}
            width={ancho}
            tick={{ fontSize: 11 }}
            stroke="var(--muted-foreground)"
          />
          <Tooltip content={<TooltipContenido />} />
          <Bar dataKey={claveValor as string} cursor={onClickBarra ? "pointer" : undefined}>
            {datos.map((fila) => (
              <Cell
                key={clave ? clave(fila) : String(fila[claveCategoria])}
                fill={color(fila)}
                onClick={onClickBarra ? () => onClickBarra(fila) : undefined}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default RankingBarras;
