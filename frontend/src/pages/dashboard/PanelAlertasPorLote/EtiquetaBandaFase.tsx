/**
 * Etiqueta de una banda de fase de `GraficaMonitores`: se abrevia
 * con puntos suspensivos según el hueco de la banda, en vez de solaparse con la
 * de la fase vecina (misma solución que en el violín,
 * `etiquetaFaseCorta`). El texto completo va en un `<title>`.
 *
 * El eje es de puntos (el primer lote en el borde izquierdo del área de
 * dibujo, el último en el derecho), y el `viewBox` que Recharts da a la
 * etiqueta de una `ReferenceArea` mide 0 de ancho, con `x` en el primer lote de
 * la banda. El hueco se calcula con el ancho del área de dibujo: cada lote
 * ocupa `ancho / (lotes - 1)` centrado en su punto, recortado a los bordes.
 */

import { usePlotArea } from "recharts";

import { etiquetaFaseCorta } from "@/pages/monitores/violin-svg-datos";

/** Margen a cada lado de la banda que el texto no ocupa. */
const MARGEN = 4;

interface Props {
  texto: string;
  /** Lotes que abarca la banda y lotes totales del eje. */
  tramos: number;
  total: number;
  viewBox?: object;
}

export function EtiquetaBandaFase({ texto, tramos, total, viewBox }: Props) {
  const area = usePlotArea();
  if (!area || total <= 0) return null;
  const { x = 0, y = 0 } = (viewBox ?? {}) as { x?: number; y?: number };
  const paso = total > 1 ? area.width / (total - 1) : area.width;
  const izquierda = Math.max(area.x, x - paso / 2);
  const derecha = Math.min(area.x + area.width, x + (tramos - 1) * paso + paso / 2);
  const hueco = Math.max(0, derecha - izquierda - 2 * MARGEN);
  return (
    <text x={(izquierda + derecha) / 2} y={y + 12} textAnchor="middle" fontSize={10} fill="var(--foreground-tertiary)">
      <title>{texto}</title>
      {etiquetaFaseCorta(texto, hueco)}
    </text>
  );
}
