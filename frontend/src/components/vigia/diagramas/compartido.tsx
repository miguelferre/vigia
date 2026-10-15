/**
 * Piezas mínimas compartidas por los once diagramas de la presentación
 * una caja con rótulo y un icono de monitor
 * embebido en el propio `<svg>` (lucide-react ya es un componente SVG; con
 * `x`/`y`/`width`/`height` se anida sin librerías nuevas). Todo en
 * `currentColor` o tokens de `themes/tokens.css`, nunca color literal.
 *
 * Escala de rediseño (2026-09-16, tarea acotada sobre `viewBox
 * "0 0 640 460"`): texto principal 20-24/600, secundario 15-16 (mínimo 14
 * para anotaciones menores), iconos de monitor 56-64, trazos 2. `Lineas`
 * añade texto envuelto a mano (sin medir con canvas): cada diagrama decide
 * dónde parte la línea porque conoce el ancho de su caja.
 */

import type { ComponentType, SVGProps } from "react";

export interface CajaProps {
  x: number;
  y: number;
  w: number;
  h: number;
  titulo: string;
  sub?: string;
  color?: string;
  rx?: number;
}

/** Rectángulo con título centrado y una segunda línea opcional. */
export function Caja({ x, y, w, h, titulo, sub, color = "currentColor", rx = 14 }: CajaProps) {
  const cx = x + w / 2;
  const cy = y + h / 2;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={rx}
        fill="none"
        stroke={color}
        strokeWidth={2}
      />
      <text
        x={cx}
        y={sub ? cy - 10 : cy}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={20}
        fontWeight={600}
        fill="currentColor"
      >
        {titulo}
      </text>
      {sub ? (
        <text
          x={cx}
          y={cy + 20}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={16}
          fill="var(--muted-foreground)"
        >
          {sub}
        </text>
      ) : null}
    </g>
  );
}

/** Flecha simple entre dos puntos, con punta; `doble` añade otra punta en el origen. */
export function Flecha({
  x1,
  y1,
  x2,
  y2,
  color = "currentColor",
  dashed = false,
  doble = false,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color?: string;
  dashed?: boolean;
  doble?: boolean;
}) {
  const angulo = Math.atan2(y2 - y1, x2 - x1);
  const puntaLargo = 11;
  const px1 = x2 - puntaLargo * Math.cos(angulo - Math.PI / 7);
  const py1 = y2 - puntaLargo * Math.sin(angulo - Math.PI / 7);
  const px2 = x2 - puntaLargo * Math.cos(angulo + Math.PI / 7);
  const py2 = y2 - puntaLargo * Math.sin(angulo + Math.PI / 7);
  // Punta del origen: misma geometría que la del destino, con el ángulo invertido.
  const anguloInverso = angulo + Math.PI;
  const qx1 = x1 - puntaLargo * Math.cos(anguloInverso - Math.PI / 7);
  const qy1 = y1 - puntaLargo * Math.sin(anguloInverso - Math.PI / 7);
  const qx2 = x1 - puntaLargo * Math.cos(anguloInverso + Math.PI / 7);
  const qy2 = y1 - puntaLargo * Math.sin(anguloInverso + Math.PI / 7);
  return (
    <g stroke={color} fill="none">
      <line x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={2} strokeDasharray={dashed ? "6 6" : undefined} />
      <polyline points={`${px1},${py1} ${x2},${y2} ${px2},${py2}`} strokeWidth={2} strokeLinejoin="round" />
      {doble ? (
        <polyline points={`${qx1},${qy1} ${x1},${y1} ${qx2},${qy2}`} strokeWidth={2} strokeLinejoin="round" />
      ) : null}
    </g>
  );
}

/** Etiqueta de icono de monitor: círculo de fondo + glifo lucide anidado. */
export function IconoMonitor({
  x,
  y,
  size = 56,
  Icono,
  color = "currentColor",
}: {
  x: number;
  y: number;
  size?: number;
  Icono: ComponentType<SVGProps<SVGSVGElement>>;
  color?: string;
}) {
  const r = size / 2;
  const pad = size * 0.26;
  return (
    <g>
      <circle cx={x} cy={y} r={r} fill="none" stroke={color} strokeWidth={2} />
      <Icono
        x={x - r + pad}
        y={y - r + pad}
        width={size - pad * 2}
        height={size - pad * 2}
        stroke={color}
        strokeWidth={2}
      />
    </g>
  );
}

/** Texto de una sola línea, alineado a la izquierda por defecto. */
export function Texto({
  x,
  y,
  children,
  size = 16,
  weight = 400,
  anchor = "start",
  color = "currentColor",
}: {
  x: number;
  y: number;
  children: string;
  size?: number;
  weight?: number;
  anchor?: "start" | "middle" | "end";
  color?: string;
}) {
  return (
    <text x={x} y={y} textAnchor={anchor} fontSize={size} fontWeight={weight} fill={color}>
      {children}
    </text>
  );
}

/** Bloque de varias líneas ya partidas a mano, mismo x y espaciado regular. */
export function Lineas({
  x,
  y,
  lineas,
  size = 16,
  weight = 400,
  anchor = "start",
  color = "currentColor",
  interlineado,
}: {
  x: number;
  y: number;
  lineas: string[];
  size?: number;
  weight?: number;
  anchor?: "start" | "middle" | "end";
  color?: string;
  interlineado?: number;
}) {
  const salto = interlineado ?? size * 1.3;
  return (
    <>
      {lineas.map((linea, i) => (
        <text
          key={i}
          x={x}
          y={y + i * salto}
          textAnchor={anchor}
          fontSize={size}
          fontWeight={weight}
          fill={color}
        >
          {linea}
        </text>
      ))}
    </>
  );
}
